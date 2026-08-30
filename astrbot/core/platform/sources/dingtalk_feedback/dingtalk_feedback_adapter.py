"""DingTalk adapter with response feedback support."""

from __future__ import annotations

import json
import uuid
from typing import cast

import dingtalk_stream
from dingtalk_stream import AckMessage

from astrbot import astrbot_config, db_helper, logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import (
    DingtalkPlatformAdapter,
)

from ...register import register_platform_adapter
from .dingtalk_feedback_event import DingTalkFeedbackMessageEvent
from .feedback_service import DingTalkFeedbackService


@register_platform_adapter(
    "dingtalk_feedback",
    "钉钉反馈增强适配器",
    default_config_tmpl={
        "id": "dingtalk_feedback",
        "type": "dingtalk_feedback",
        "enable": False,
        "client_id": "",
        "client_secret": "",
        "feedback_mode": "text",
        "card_template_id": "",
    },
    adapter_display_name="钉钉反馈增强适配器",
    support_streaming_message=True,
    config_metadata={
        "feedback_mode": {
            "description": "反馈模式",
            "type": "select",
            "options": ["text", "interactive_card"],
            "hint": "text 使用有用/没用；interactive_card 需要钉钉互动卡片权限。",
        },
        "card_template_id": {
            "description": "互动卡片模板 ID",
            "type": "string",
            "hint": "仅 interactive_card 模式必填。",
        },
    },
)
class DingTalkFeedbackPlatformAdapter(DingtalkPlatformAdapter):
    """Keep official DingTalk behavior while adding opt-in feedback workflows."""

    def __init__(self, platform_config: dict, platform_settings: dict, event_queue) -> None:
        """Initialize the official transport and feedback callback handlers.

        Args:
            platform_config: Configured feedback adapter settings.
            platform_settings: Shared AstrBot platform settings.
            event_queue: AstrBot incoming event queue.
        """
        self.feedback_mode = str(platform_config.get("feedback_mode", "text"))
        self.card_template_id = str(platform_config.get("card_template_id", "")).strip()
        if self.feedback_mode not in {"text", "interactive_card"}:
            raise ValueError("feedback_mode must be text or interactive_card")
        if self.feedback_mode == "interactive_card" and not self.card_template_id:
            raise ValueError("card_template_id is required for interactive_card mode")
        self.feedback_service = DingTalkFeedbackService(db_helper)
        self.card_callback_registered = False
        super().__init__(platform_config, platform_settings, event_queue)
        self._register_card_callback_handler()

    def _register_card_callback_handler(self) -> None:
        """Register a card callback handler when the installed SDK supports it."""
        handler_base = getattr(dingtalk_stream, "CardCallbackHandler", None)
        card_message = getattr(dingtalk_stream, "CardCallbackMessage", None)
        if handler_base is None or card_message is None:
            if self.feedback_mode == "interactive_card":
                logger.warning("DingTalk SDK does not expose interactive-card callbacks.")
            return
        outer_self = self

        class FeedbackCardHandler(handler_base):
            async def process(self, message: dingtalk_stream.CallbackMessage):
                await outer_self.handle_card_callback(message)
                return AckMessage.STATUS_OK, "OK"

        self.client_.register_callback_handler(card_message.TOPIC, FeedbackCardHandler())
        self.card_callback_registered = True

    def meta(self) -> PlatformMetadata:
        """Return feedback adapter metadata for Dashboard discovery.

        Returns:
            Platform metadata for this adapter instance.
        """
        return PlatformMetadata(
            name="dingtalk_feedback",
            description="钉钉反馈增强适配器",
            id=cast(str, self.config.get("id")),
            support_streaming_message=True,
            support_proactive_message=True,
        )

    def create_event(self, message: AstrBotMessage) -> DingTalkFeedbackMessageEvent:
        """Create a DingTalk event that intercepts marked model responses.

        Args:
            message: Parsed AstrBot incoming message.

        Returns:
            Event bound to this feedback adapter.
        """
        return DingTalkFeedbackMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
            adapter=self,
        )

    async def handle_msg(self, abm: AstrBotMessage) -> None:
        """Consume feedback phrases and test commands before normal message handling.

        Args:
            abm: Parsed DingTalk incoming message.
        """
        raw = abm.raw_message
        text = abm.message_str.strip()
        sender_staff_id = str(getattr(raw, "sender_staff_id", "") or abm.sender.user_id)
        sender_id = str(abm.sender.user_id or "")
        sender_name = str(getattr(abm.sender, "nickname", "") or "")
        if text == "/dingtalk_card_test":
            admin_ids = {str(item) for item in astrbot_config.get("admins_id", [])}
            if sender_id not in admin_ids and sender_staff_id not in admin_ids:
                await self.send_message_chain_with_incoming(
                    raw, MessageChain().message("无权限执行互动卡片测试。")
                )
                return
            await self.send_card_test(raw, abm)
            return
        vote_value = {"有用": "like", "👍": "like", "没用": "dislike", "👎": "dislike"}.get(text)
        if vote_value:
            record = await self.feedback_service.find_recent_response(
                platform_id=self.meta().id,
                session_id=abm.session_id,
                requester_id=abm.sender.user_id,
            )
            if record:
                saved, message = await self.feedback_service.record_vote(
                    response_id=record.response_id,
                    voter_id=sender_staff_id,
                    voter_name=sender_name,
                    value=vote_value,
                    source="text",
                    event_id=f"text:{abm.message_id}",
                )
                if saved:
                    await self.send_message_chain_with_incoming(raw, MessageChain().message("已记录反馈，感谢。"))
                    return
                logger.info("DingTalk feedback phrase ignored: %s", message)
        await super().handle_msg(abm)

    async def send_feedback_response(self, incoming_message, message_chain: MessageChain) -> None:
        """Persist and deliver one final answer through the selected feedback mode.

        Args:
            incoming_message: Original DingTalk request message.
            message_chain: Final AI message chain.
        """
        answer = message_chain.get_plain_text().strip()
        if not answer:
            await self.send_message_chain_with_incoming(incoming_message, message_chain)
            return
        requester_id = self._id_to_sid(cast(str, incoming_message.sender_id or ""))
        requester_name = str(incoming_message.sender_nick or "")
        session_id = (
            cast(str, incoming_message.conversation_id)
            if incoming_message.conversation_type == "2"
            else requester_id
        )
        record = await self.feedback_service.create_response(
            platform_id=self.meta().id,
            session_id=session_id,
            requester_id=requester_id,
            requester_name=requester_name,
            question=cast(str, incoming_message.text.content or ""),
            answer=answer,
            mode=self.feedback_mode,
        )
        if self.feedback_mode == "text":
            decorated = message_chain.derive(list(message_chain.chain))
            decorated.chain.append(Plain("\n\n这条回答有帮助吗？回复“有用”或“没用”。"))
            await self.send_message_chain_with_incoming(incoming_message, decorated)
            return
        try:
            card_replier_type = getattr(dingtalk_stream, "AICardReplier")
            card_replier = card_replier_type(self.client_, incoming_message)
            await card_replier.async_create_and_deliver_card(
                self.card_template_id,
                {"content": answer, "response_id": record.response_id},
            )
            await self.feedback_service.mark_card_result(record.response_id, sent=True)
        except Exception as exc:
            logger.error("DingTalk feedback card delivery failed: %s", exc)
            await self.feedback_service.mark_card_result(
                record.response_id, sent=False, error=str(exc)
            )
            await self.send_message_chain_with_incoming(incoming_message, message_chain)

    async def send_card_test(self, incoming_message, abm: AstrBotMessage) -> None:
        """Send an isolated interactive-card capability test.

        Args:
            incoming_message: Original DingTalk admin command.
            abm: Parsed AstrBot message for audit ownership.
        """
        if self.feedback_mode != "interactive_card":
            await self.send_message_chain_with_incoming(
                incoming_message, MessageChain().message("请先将反馈模式设置为 interactive_card。")
            )
            return
        record = await self.feedback_service.create_response(
            platform_id=self.meta().id,
            session_id=abm.session_id,
            requester_id=abm.sender.user_id,
            requester_name=str(getattr(abm.sender, "nickname", "") or ""),
            question="/dingtalk_card_test",
            answer="互动卡片能力测试",
            mode=self.feedback_mode,
            is_test=True,
        )
        try:
            card_replier_type = getattr(dingtalk_stream, "AICardReplier")
            card_replier = card_replier_type(self.client_, incoming_message)
            await card_replier.async_create_and_deliver_card(
                self.card_template_id,
                {"content": "互动卡片能力测试，请点击赞或踩。", "response_id": record.response_id},
            )
            await self.feedback_service.mark_card_result(record.response_id, sent=True)
        except Exception as exc:
            await self.feedback_service.mark_card_result(
                record.response_id, sent=False, error=str(exc)
            )
            await self.send_message_chain_with_incoming(
                incoming_message, MessageChain().message(f"互动卡片测试发送失败：{exc}")
            )

    async def handle_card_callback(self, message: dingtalk_stream.CallbackMessage) -> None:
        """Persist a DingTalk interactive-card action.

        Args:
            message: Raw SDK card callback payload.
        """
        raw_data = getattr(message, "data", {})
        try:
            data = raw_data if isinstance(raw_data, dict) else json.loads(raw_data)
        except (TypeError, json.JSONDecodeError):
            logger.warning("Ignored DingTalk feedback card callback with invalid data.")
            return
        if not isinstance(data, dict):
            logger.warning("Ignored DingTalk feedback card callback with invalid payload.")
            return
        params = data.get("cardParamMap") or data.get("card_param_map") or {}
        action = str(params.get("action") or data.get("action") or "")
        response_id = str(params.get("response_id") or data.get("response_id") or "")
        voter_id = str(data.get("userId") or data.get("user_id") or "")
        voter_name = str(data.get("userName") or data.get("user_name") or "")
        headers = getattr(message, "headers", None)
        event_id = str(
            getattr(headers, "event_id", "")
            or data.get("eventId")
            or data.get("event_id")
            or uuid.uuid4()
        )
        if action not in {"like", "dislike"} or not response_id or not voter_id:
            logger.warning("Ignored invalid DingTalk feedback card callback.")
            return
        await self.feedback_service.record_vote(
            response_id=response_id,
            voter_id=voter_id,
            voter_name=voter_name,
            value=action,
            source="card",
            event_id=f"card:{event_id}",
        )
