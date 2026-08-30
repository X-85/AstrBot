"""Persistent feedback operations for the DingTalk feedback adapter."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import func, select

from astrbot.core.db.po import (
    DingTalkFeedbackResponse,
    DingTalkFeedbackVote,
    DingTalkFeedbackVoteEvent,
)


class DingTalkFeedbackService:
    """Store responses and employee feedback in the AstrBot database.

    Args:
        db_helper: The initialized AstrBot database helper.
    """

    def __init__(self, db_helper) -> None:
        self.db_helper = db_helper

    async def create_response(
        self,
        *,
        platform_id: str,
        session_id: str,
        requester_id: str,
        requester_name: str,
        question: str,
        answer: str,
        mode: str,
        is_test: bool = False,
    ) -> DingTalkFeedbackResponse:
        """Create one feedback-eligible response.

        Args:
            platform_id: Configured AstrBot platform identifier.
            session_id: Conversation session identifier.
            requester_id: DingTalk sender identifier.
            requester_name: DingTalk sender display name.
            question: Original user message.
            answer: Final AI answer before feedback decoration.
            mode: Selected feedback mode.
            is_test: Whether the record belongs to a capability test.

        Returns:
            The persisted response record.
        """
        record = DingTalkFeedbackResponse(
            response_id=str(uuid.uuid4()),
            platform_id=platform_id,
            session_id=session_id,
            requester_id=requester_id,
            requester_name=requester_name,
            question=question,
            answer=answer,
            mode=mode,
            is_test=is_test,
        )
        async with self.db_helper.get_db() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return record

    async def find_recent_response(
        self, *, platform_id: str, session_id: str, requester_id: str
    ) -> DingTalkFeedbackResponse | None:
        """Find the employee's latest eligible response inside the ten minute window.

        Args:
            platform_id: Configured AstrBot platform identifier.
            session_id: Conversation session identifier.
            requester_id: DingTalk sender identifier.

        Returns:
            The latest non-test response, if one is still eligible.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        async with self.db_helper.get_db() as session:
            statement = (
                select(DingTalkFeedbackResponse)
                .where(DingTalkFeedbackResponse.platform_id == platform_id)
                .where(DingTalkFeedbackResponse.session_id == session_id)
                .where(DingTalkFeedbackResponse.requester_id == requester_id)
                .where(DingTalkFeedbackResponse.is_test.is_(False))
                .where(DingTalkFeedbackResponse.created_at >= cutoff)
                .order_by(DingTalkFeedbackResponse.created_at.desc())
                .limit(1)
            )
            return (await session.exec(statement)).first()

    async def record_vote(
        self,
        *,
        response_id: str,
        voter_id: str,
        voter_name: str,
        value: str,
        source: str,
        event_id: str,
    ) -> tuple[bool, str]:
        """Record an idempotent like or dislike action.

        Args:
            response_id: Target response identifier.
            voter_id: DingTalk employee identifier.
            voter_name: DingTalk display name.
            value: Either ``like`` or ``dislike``.
            source: ``text`` or ``card``.
            event_id: Unique DingTalk source event identifier.

        Returns:
            A tuple of whether a new event was saved and a result message.
        """
        if value not in {"like", "dislike"}:
            return False, "Invalid feedback value"

        async with self.db_helper.get_db() as session:
            response = await session.get(DingTalkFeedbackResponse, response_id)
            if response is None:
                return False, "Feedback target was not found"
            if await session.get(DingTalkFeedbackVoteEvent, event_id):
                return False, "Feedback was already recorded"

            vote = (
                await session.exec(
                    select(DingTalkFeedbackVote)
                    .where(DingTalkFeedbackVote.response_id == response_id)
                    .where(DingTalkFeedbackVote.voter_id == voter_id)
                )
            ).first()
            if vote is None:
                session.add(
                    DingTalkFeedbackVote(
                        response_id=response_id,
                        voter_id=voter_id,
                        voter_name=voter_name,
                        value=value,
                    )
                )
            else:
                vote.value = value
                vote.voter_name = voter_name
                session.add(vote)

            session.add(
                DingTalkFeedbackVoteEvent(
                    event_id=event_id,
                    response_id=response_id,
                    voter_id=voter_id,
                    voter_name=voter_name,
                    value=value,
                    source=source,
                )
            )
            if source == "card":
                response.card_callback_received = True
                session.add(response)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False, "Feedback was already recorded"
        return True, "Feedback recorded"

    async def mark_card_result(
        self, response_id: str, *, sent: bool, error: str | None = None
    ) -> None:
        """Persist the result of attempting to send an interactive card.

        Args:
            response_id: Target response identifier.
            sent: Whether DingTalk accepted the card.
            error: Failure detail, when available.
        """
        async with self.db_helper.get_db() as session:
            response = await session.get(DingTalkFeedbackResponse, response_id)
            if response is None:
                return
            response.card_sent = sent
            response.card_error = error
            session.add(response)
            await session.commit()

    async def list_responses(
        self,
        *,
        page: int,
        page_size: int,
        platform_id: str = "",
        requester: str = "",
        session_id: str = "",
        vote: str = "",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        include_tests: bool = False,
    ) -> dict:
        """Return paginated feedback audit records for the Dashboard.

        Args:
            page: One-based page number.
            page_size: Maximum number of records.
            platform_id: Optional platform filter.
            requester: Optional requester text filter.
            session_id: Optional session filter.
            vote: Optional current vote filter.
            start_time: Optional inclusive UTC start time.
            end_time: Optional inclusive UTC end time.
            include_tests: Whether test records are included.

        Returns:
            Serialized records and pagination metadata.
        """
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        async with self.db_helper.get_db() as session:
            statement = select(DingTalkFeedbackResponse)
            if platform_id:
                statement = statement.where(
                    DingTalkFeedbackResponse.platform_id == platform_id
                )
            if requester:
                statement = statement.where(
                    DingTalkFeedbackResponse.requester_name.contains(requester)
                    | DingTalkFeedbackResponse.requester_id.contains(requester)
                )
            if session_id:
                statement = statement.where(
                    DingTalkFeedbackResponse.session_id == session_id
                )
            if start_time:
                statement = statement.where(
                    DingTalkFeedbackResponse.created_at >= start_time
                )
            if end_time:
                statement = statement.where(
                    DingTalkFeedbackResponse.created_at <= end_time
                )
            if not include_tests:
                statement = statement.where(DingTalkFeedbackResponse.is_test.is_(False))
            if vote in {"like", "dislike"}:
                statement = statement.where(
                    DingTalkFeedbackResponse.response_id.in_(
                        select(DingTalkFeedbackVote.response_id).where(
                            DingTalkFeedbackVote.value == vote
                        )
                    )
                )
            total = await session.scalar(
                select(func.count()).select_from(statement.subquery())
            )
            records = (
                await session.exec(
                    statement.order_by(DingTalkFeedbackResponse.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            response_ids = [record.response_id for record in records]
            votes = []
            if response_ids:
                votes = (
                    await session.exec(
                        select(DingTalkFeedbackVote).where(
                            DingTalkFeedbackVote.response_id.in_(response_ids)
                        )
                    )
                ).all()
        totals: dict[str, dict[str, int]] = {
            key: {"like": 0, "dislike": 0} for key in response_ids
        }
        for item in votes:
            totals[item.response_id][item.value] += 1
        return {
            "items": [
                {
                    "response_id": record.response_id,
                    "platform_id": record.platform_id,
                    "session_id": record.session_id,
                    "requester_id": record.requester_id,
                    "requester_name": record.requester_name,
                    "question": record.question,
                    "answer": record.answer,
                    "mode": record.mode,
                    "is_test": record.is_test,
                    "card_sent": record.card_sent,
                    "card_callback_received": record.card_callback_received,
                    "card_error": record.card_error,
                    "created_at": record.created_at.isoformat(),
                    "likes": totals[record.response_id]["like"],
                    "dislikes": totals[record.response_id]["dislike"],
                }
                for record in records
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total or 0,
                "total_pages": max(1, ((total or 0) + page_size - 1) // page_size),
            },
        }
