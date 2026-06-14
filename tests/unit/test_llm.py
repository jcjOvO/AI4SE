from __future__ import annotations

import json

import httpx
import pytest
import respx

from miniagent.llm import LLMClient, StepUsage


@pytest.fixture
def llm() -> LLMClient:
    return LLMClient(api_key="sk-test", base_url="https://api.example.com", model="claude-x")


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
            "usage": {"output_tokens": 42},
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
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    respx.post("https://api.example.com/v1/messages").mock(side_effect=sse_response)

    text, tool_calls, usage = await llm.stream_step(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
    )
    assert text == "Hello world"
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "read_file"
    assert tool_calls[0].input == {"path": "foo.py"}
    assert tool_calls[0].id == "toolu_1"
    # usage assertions
    assert isinstance(usage, StepUsage)
    assert usage.input_tokens == 5  # from message_start
    assert usage.output_tokens == 42  # from message_delta


@respx.mock
async def test_stream_step_passes_messages_and_model(llm: LLMClient) -> None:
    route = respx.post("https://api.example.com/v1/messages").mock(
        return_value=httpx.Response(
            200, text=_empty_sse(), headers={"content-type": "text/event-stream"}
        )
    )
    text, _, _ = await llm.stream_step(messages=[{"role": "user", "content": "x"}], tools=[])
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


# ---------------------------------------------------------------------------
# Task 10: retry logic
# ---------------------------------------------------------------------------


@respx.mock
async def test_retries_on_429_then_succeeds(llm: LLMClient) -> None:
    route = respx.post("https://api.example.com/v1/messages").mock(
        side_effect=[
            httpx.Response(429, text="rate limited"),
            httpx.Response(429, text="rate limited"),
            httpx.Response(200, text=_empty_sse(), headers={"content-type": "text/event-stream"}),
        ]
    )
    text, _, _ = await llm.stream_step(messages=[{"role": "user", "content": "x"}], tools=[])
    assert text == ""
    assert route.call_count == 3


@respx.mock
async def test_no_retry_on_401(llm: LLMClient) -> None:
    respx.post("https://api.example.com/v1/messages").mock(
        return_value=httpx.Response(401, text="bad key")
    )
    with pytest.raises(Exception) as exc:
        await llm.stream_step(messages=[{"role": "user", "content": "x"}], tools=[])
    # Should NOT be RetryExhausted; should be AuthError
    from miniagent.llm import AuthError

    assert isinstance(exc.value, AuthError)


@respx.mock
async def test_retry_exhausted_after_4_attempts(llm: LLMClient) -> None:
    respx.post("https://api.example.com/v1/messages").mock(
        return_value=httpx.Response(500, text="server error")
    )
    from miniagent.llm import RetryExhaustedError

    with pytest.raises(RetryExhaustedError):
        await llm.stream_step(messages=[{"role": "user", "content": "x"}], tools=[])


@respx.mock
async def test_stream_step_usage_defaults_to_zero_when_missing(llm: LLMClient) -> None:
    """API 未返回 usage 字段时，默认 StepUsage(0, 0)。"""
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "m",
                "role": "assistant",
                "content": [],
                "stop_reason": "end_turn",
            },
        },
        {"type": "message_stop"},
    ]
    body = "\n".join(f"event: {e['type']}\ndata: {json.dumps(e)}" for e in events)
    respx.post("https://api.example.com/v1/messages").mock(
        return_value=httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    )
    _, _, usage = await llm.stream_step(messages=[{"role": "user", "content": "x"}], tools=[])
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0


# ---------------------------------------------------------------------------
# System prompt tests
# ---------------------------------------------------------------------------


def test_build_system_prompt_contains_tool_names() -> None:
    from miniagent.llm import _build_system_prompt

    prompt = _build_system_prompt()
    # Should mention all 4 built-in tools
    assert "read_file" in prompt
    assert "write_file" in prompt
    assert "edit_file" in prompt
    assert "bash" in prompt


def test_build_system_prompt_contains_safety_rules() -> None:
    from miniagent.llm import _build_system_prompt

    prompt = _build_system_prompt()
    assert "/workspace" in prompt
    assert "Safety Rules" in prompt


def test_build_system_prompt_contains_response_style() -> None:
    from miniagent.llm import _build_system_prompt

    prompt = _build_system_prompt()
    assert "Response Style" in prompt
    assert "Chinese" in prompt


def test_build_system_prompt_appends_config_custom() -> None:
    from miniagent.config import AgentConfig
    from miniagent.llm import _build_system_prompt

    cfg = AgentConfig(system_prompt="Custom instruction here")
    prompt = _build_system_prompt(cfg)
    assert "Custom instruction here" in prompt
    assert "---" in prompt


def test_build_system_prompt_no_separator_when_empty() -> None:
    from miniagent.config import AgentConfig
    from miniagent.llm import _build_system_prompt

    cfg = AgentConfig(system_prompt="")
    prompt = _build_system_prompt(cfg)
    # The "---" separator should NOT appear when custom is empty
    # Split by sections and check no standalone "---"
    lines = prompt.split("\n")
    assert "---" not in lines


def test_build_system_prompt_default_when_no_config() -> None:
    from miniagent.llm import _build_system_prompt

    prompt = _build_system_prompt(None)
    assert "coding assistant" in prompt
    assert "read_file" in prompt


@respx.mock
async def test_stream_step_sends_system_prompt() -> None:
    """Verify that the API request body includes a system prompt."""
    from miniagent.config import AgentConfig

    cfg = AgentConfig(system_prompt="Custom instruction")
    client = LLMClient(
        api_key="sk-test",
        base_url="https://api.example.com",
        model="claude-x",
        config=cfg,
    )
    route = respx.post("https://api.example.com/v1/messages").mock(
        return_value=httpx.Response(
            200, text=_empty_sse(), headers={"content-type": "text/event-stream"}
        )
    )
    await client.stream_step(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
    )
    body = json.loads(route.calls.last.request.content.decode())
    assert "system" in body
    assert "coding assistant" in body["system"]
    assert "Custom instruction" in body["system"]


@respx.mock
async def test_stream_step_system_prompt_without_config() -> None:
    """LLMClient without config still gets a default system prompt."""
    client = LLMClient(
        api_key="sk-test",
        base_url="https://api.example.com",
        model="claude-x",
    )
    route = respx.post("https://api.example.com/v1/messages").mock(
        return_value=httpx.Response(
            200, text=_empty_sse(), headers={"content-type": "text/event-stream"}
        )
    )
    await client.stream_step(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
    )
    body = json.loads(route.calls.last.request.content.decode())
    assert "system" in body
    assert "read_file" in body["system"]
