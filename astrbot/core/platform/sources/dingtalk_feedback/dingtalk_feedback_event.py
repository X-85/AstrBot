"""Message event implementation for the DingTalk feedback adapter."""

from __future__ import annotations

from astrbot.api.event import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from astrbot.core.platform.sources.dingtalk.dingtalk_event import DingtalkMessageEvent


class DingTalkFeedbackMessageEvent(DingtalkMessageEvent):
    """Route marked final responses through the feedback adapter.

    Args:
        message_str: Incoming text content.
        message_obj: Parsed AstrBot incoming message.
        platform_meta: Platform metadata.
        session_id: Session identifier.
        client: DingTalk callback client.
        adapter: Owning feedback adapter.
    """

    async def send(self, message: MessageChain) -> None:
        """Send a final response with feedback when it carries the marker.

        Args:
            message: Outgoing AstrBot message chain.
        """
        if message.type == "dingtalk_feedback_final" and self.adapter:
            await self.adapter.send_feedback_response(self.message_obj.raw_message, message)
            await AstrMessageEvent.send(self, message)
            return
        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        """Buffer streaming output and submit it as exactly one feedback response.

        Args:
            generator: Streaming message-chain generator.
            use_fallback: Kept for the platform event contract.

        Returns:
            ``None`` after the buffered message has been delivered.
        """
        buffer = None
        async for chain in generator:
            if buffer is None:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)
        if buffer is None:
            return None
        buffer.squash_plain()
        buffer.type = "dingtalk_feedback_final"
        await self.send(buffer)
        return None
