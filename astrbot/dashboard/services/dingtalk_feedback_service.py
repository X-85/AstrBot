"""Dashboard queries for DingTalk response feedback."""

from datetime import datetime

from astrbot.core.platform.sources.dingtalk_feedback.feedback_service import (
    DingTalkFeedbackService,
)


class DingTalkFeedbackDashboardService:
    """Expose read-only feedback audit queries to the Dashboard.

    Args:
        db_helper: The AstrBot database helper.
    """

    def __init__(self, db_helper, core_lifecycle) -> None:
        self.feedback_service = DingTalkFeedbackService(db_helper)
        self.core_lifecycle = core_lifecycle

    async def list_feedback(
        self,
        *,
        page: int,
        page_size: int,
        platform_id: str,
        requester: str,
        session_id: str,
        vote: str,
        start_time: datetime | None,
        end_time: datetime | None,
        include_tests: bool,
    ) -> dict:
        """List feedback audit records.

        Args:
            page: One-based page number.
            page_size: Number of records per page.
            platform_id: Optional platform filter.
            requester: Optional requester filter.
            session_id: Optional session filter.
            vote: Optional vote filter.
            start_time: Optional UTC start time.
            end_time: Optional UTC end time.
            include_tests: Include card test records.

        Returns:
            Paginated feedback audit data.
        """
        return await self.feedback_service.list_responses(
            page=page,
            page_size=page_size,
            platform_id=platform_id,
            requester=requester,
            session_id=session_id,
            vote=vote,
            start_time=start_time,
            end_time=end_time,
            include_tests=include_tests,
        )

    def get_card_preflight(self) -> dict:
        """Return local interactive-card readiness for running feedback adapters.

        Returns:
            Configured adapter status. DingTalk permission is verified only by a test card.
        """
        adapters = []
        for adapter in self.core_lifecycle.platform_manager.get_insts():
            if adapter.meta().name != "dingtalk_feedback":
                continue
            adapters.append(
                {
                    "platform_id": adapter.meta().id,
                    "mode": adapter.feedback_mode,
                    "template_configured": bool(adapter.card_template_id),
                    "stream_connected": bool(
                        getattr(adapter.client_, "websocket", None)
                    ),
                    "callback_registered": adapter.card_callback_registered,
                }
            )
        return {"adapters": adapters}
