"""Optional observability hooks used by AstrBot extensions."""

from .message_trace import (
    emit_message_trace,
    register_message_trace_sink,
    unregister_message_trace_sink,
)

__all__ = [
    "emit_message_trace",
    "register_message_trace_sink",
    "unregister_message_trace_sink",
]
