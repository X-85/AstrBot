import json

import pytest

from astrbot.core.observability.message_trace import (
    emit_message_trace,
    register_message_trace_sink,
    unregister_message_trace_sink,
)
from data.plugins.astrbot_plugin_message_trace.serializers import serialize_value


def test_trace_serializer_masks_sensitive_values_and_bounds_text():
    value = serialize_value(
        {"api_key": "secret", "content": "x" * 100},
        max_chars=20,
        mask=True,
    )
    assert value["api_key"] == "[MASKED]"
    assert len(value["content"]) == 20


@pytest.mark.asyncio
async def test_message_trace_sink_is_optional_and_receives_trace_id():
    received = []

    async def sink(event, stage, payload):
        received.append((event, stage, payload))

    register_message_trace_sink(sink)
    try:
        trace_id = await emit_message_trace(None, "inbound_raw", {"value": 1})
    finally:
        unregister_message_trace_sink(sink)

    assert received[0][1] == "inbound_raw"
    assert received[0][2]["trace_id"] == trace_id


def test_trace_serializer_is_json_safe():
    serialized = serialize_value({"items": {1, 2}}, max_chars=100, mask=False)
    json.dumps(serialized)
