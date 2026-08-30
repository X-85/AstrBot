from datetime import datetime, timedelta, timezone

import pytest

from astrbot.core.db.po import DingTalkFeedbackResponse
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform.sources.dingtalk_feedback.feedback_service import (
    DingTalkFeedbackService,
)


@pytest.mark.asyncio
async def test_feedback_vote_is_idempotent_and_can_switch(tmp_path):
    """One employee has one current vote while every event remains auditable."""
    db = SQLiteDatabase(str(tmp_path / "feedback.db"))
    await db.initialize()
    service = DingTalkFeedbackService(db)
    response = await service.create_response(
        platform_id="feedback",
        session_id="session",
        requester_id="user",
        requester_name="User",
        question="Question",
        answer="Answer",
        mode="text",
    )

    assert await service.record_vote(
        response_id=response.response_id,
        voter_id="staff",
        voter_name="Staff",
        value="like",
        source="text",
        event_id="message-1",
    ) == (True, "Feedback recorded")
    assert await service.record_vote(
        response_id=response.response_id,
        voter_id="staff",
        voter_name="Staff",
        value="like",
        source="text",
        event_id="message-1",
    ) == (False, "Feedback was already recorded")
    assert await service.record_vote(
        response_id=response.response_id,
        voter_id="staff",
        voter_name="Staff",
        value="dislike",
        source="text",
        event_id="message-2",
    ) == (True, "Feedback recorded")

    result = await service.list_responses(page=1, page_size=20)
    assert result["items"][0]["likes"] == 0
    assert result["items"][0]["dislikes"] == 1


@pytest.mark.asyncio
async def test_recent_response_excludes_tests_and_expired_records(tmp_path):
    """Text feedback only resolves an eligible response from the last ten minutes."""
    db = SQLiteDatabase(str(tmp_path / "feedback.db"))
    await db.initialize()
    service = DingTalkFeedbackService(db)
    record = await service.create_response(
        platform_id="feedback",
        session_id="session",
        requester_id="user",
        requester_name="User",
        question="Question",
        answer="Answer",
        mode="text",
    )
    assert (
        await service.find_recent_response(
            platform_id="feedback", session_id="session", requester_id="user"
        )
    ).response_id == record.response_id

    async with db.get_db() as session:
        persisted = await session.get(DingTalkFeedbackResponse, record.response_id)
        persisted.created_at = datetime.now(timezone.utc) - timedelta(minutes=11)
        session.add(persisted)
        await session.commit()

    assert await service.find_recent_response(
        platform_id="feedback", session_id="session", requester_id="user"
    ) is None
