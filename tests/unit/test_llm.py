from __future__ import annotations

import json

import httpx
import pytest
import respx

from miniagent.llm import LLMClient


@pytest.fixture
def llm() -> LLMClient:
    return LLMClient(
        api_key="sk-test", base_url="https://api.example.com", model="claude-x"
    )


@respx.mock
async def test_stream_step_returns_text_and_tool_calls(llm: LLMClient) -> None:
    # Build a fake Anthropic streaming response (SSE format)
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "m1",
                "role": "assistant",
                "content": [],
                "stop_reason": None,
                "usage": {"input_tokens": 5, "output_tokens": 0},
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Hello "},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "world"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "read_file",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"path":'},
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '"foo.py"}'},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use", "stop_sequence": None},
        },
        {"type": "message_stop"},
    ]

    def sse_response(request: httpx.Request) -> httpx.Response:
        # respx 0.23+ invokes side_effect callables with the Request; the
        # spec's `def sse_response()` signature is a respx 0.20-ism and
        # raises TypeError on newer releases. We accept the argument but
        # don't need it.
        del request
        body = "\n".join(f"event: {e['type']}\ndata: {json.dumps(e)}" for e in events)
        return httpx.Response(
            200, text=body, headers={"content-type": "text/event-stream"}
        )

    respx.post("https://api.example.com/v1/messages").mock(side_effect=sse_response)

    text, tool_calls = await llm.stream_step(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
    )
    assert text == "Hello world"
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "read_file"
    assert tool_calls[0].input == {"path": "foo.py"}
    assert tool_calls[0].id == "toolu_1"


@respx.mock
async def test_stream_step_passes_messages_and_model(llm: LLMClient) -> None:
    route = respx.post("https://api.example.com/v1/messages").mock(
        return_value=httpx.Response(
            200, text=_empty_sse(), headers={"content-type": "text/event-stream"}
        )
    )
    await llm.stream_step(messages=[{"role": "user", "content": "x"}], tools=[])
    assert route.called
    body = route.calls.last.request.content.decode()
    payload = json.loads(body)
    assert payload["model"] == "claude-x"
    assert payload["messages"] == [{"role": "user", "content": "x"}]
    assert payload["stream"] is True


def _empty_sse() -> str:
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "m",
                "role": "assistant",
                "content": [],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
        {"type": "message_stop"},
    ]
    return "\n".join(f"event: {e['type']}\ndata: {json.dumps(e)}" for e in events)
