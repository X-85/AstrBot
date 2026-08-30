"""Optional message-flow tracing hooks."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from astrbot.core.platform.astr_message_event import AstrMessageEvent

MessageTraceSink = Callable[
    [AstrMessageEvent | None, str, dict[str, Any]], Awaitable[None]
]
_sinks: list[MessageTraceSink] = []


def register_message_trace_sink(sink: MessageTraceSink) -> None:
    """Register an optional message trace sink.

    Args:
        sink: Async callback receiving the event, stage name, and payload.
    """
    if sink not in _sinks:
        _sinks.append(sink)


def unregister_message_trace_sink(sink: MessageTraceSink) -> None:
    """Unregister a previously registered message trace sink.

    Args:
        sink: Sink callback to remove.
    """
    if sink in _sinks:
        _sinks.remove(sink)


async def emit_message_trace(
    event: AstrMessageEvent | None,
    stage: str,
    payload: dict[str, Any] | None = None,
    *,
    trace_id: str | None = None,
) -> str:
    """Publish a best-effort message trace event.

    Args:
        event: AstrBot event associated with the observation, if available.
        stage: Stable observation stage name.
        payload: JSON-like stage data.
        trace_id: Existing trace ID for observations created before event wrapping.

    Returns:
        The trace ID assigned to this message flow.
    """
    if event is not None:
        current_id = event.get_extra("message_trace_id")
        trace_id = str(current_id or trace_id or uuid.uuid4())
        event.set_extra("message_trace_id", trace_id)
    else:
        trace_id = str(trace_id or uuid.uuid4())

    if not _sinks:
        return trace_id

    record = dict(payload or {})
    record.setdefault("trace_id", trace_id)
    for sink in tuple(_sinks):
        try:
            await sink(event, stage, record)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue
    return trace_id
