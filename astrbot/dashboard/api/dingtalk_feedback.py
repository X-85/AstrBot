"""Read-only DingTalk feedback Dashboard API."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.responses import ok
from astrbot.dashboard.services.dingtalk_feedback_service import (
    DingTalkFeedbackDashboardService,
)

from .auth import AuthContext, ScopeDependency

router = APIRouter(tags=["DingTalk Feedback"])
require_bot_scope = ScopeDependency("bot")


def get_service(request: Request) -> DingTalkFeedbackDashboardService:
    """Get the feedback Dashboard service.

    Args:
        request: Current FastAPI request.

    Returns:
        Configured feedback Dashboard service.
    """
    return request.app.state.services.dingtalk_feedback


@router.get("/dingtalk-feedback")
async def list_dingtalk_feedback(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    platform_id: str = Query(default=""),
    requester: str = Query(default=""),
    session_id: str = Query(default=""),
    vote: str = Query(default=""),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    include_tests: bool = Query(default=False),
    _auth: AuthContext = Depends(require_bot_scope),
    service: DingTalkFeedbackDashboardService = Depends(get_service),
):
    """List persisted DingTalk feedback audit records."""
    return ok(
        await service.list_feedback(
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
    )


@router.get("/dingtalk-feedback/preflight")
async def get_dingtalk_feedback_preflight(
    _auth: AuthContext = Depends(require_bot_scope),
    service: DingTalkFeedbackDashboardService = Depends(get_service),
):
    """Return local interactive-card readiness for the Dashboard."""
    return ok(service.get_card_preflight())
