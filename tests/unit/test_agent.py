from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from miniagent.agent import (
    AgentError,
    AssistantDelta,
    EndTurn,
    Event,
    ToolCallResult,
    ToolCallStart,
    run,
)
from miniagent.tools import Tool, ToolResult


@dataclass
class FakeToolCall:
    id: str
    name: str
    input: dict


@dataclass
class FakeLLM:
    """Mimics LLMClient.stream_step; user scripts a queue of responses."""

    responses: list[tuple[str, list[FakeToolCall], None]]

    async def stream_step(
        self, messages: list[dict], tools: list[dict]
    ) -> tuple[str, list[FakeToolCall], None]:
        return self.responses.pop(0)


@dataclass
class FakeTools:
    """Mimics the tools module's execute + all_schemas."""

    by_name: dict[str, Tool]

    def all_schemas(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self.by_name.values()
        ]

    async def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        return await self.by_name[name].handler(args)


async def test_run_emits_assistant_delta_and_end_turn_on_text_only_response() -> None:
    llm = FakeLLM(responses=[("Hi there!", [], None)])
    tools = FakeTools(by_name={})
    events: list[Event] = []

    msgs = await run(
        messages=[{"role": "user", "content": "hi"}],
        llm=llm,  # type: ignore[arg-type]
        tools=tools,  # type: ignore[arg-type]
        on_event=events.append,
    )
    assert msgs  # returned messages list is non-empty

    assert len(events) == 2
    assert isinstance(events[0], AssistantDelta)
    assert events[0].text == "Hi there!"
    assert isinstance(events[1], EndTurn)
    assert events[1].final_text == "Hi there!"
    assert events[1].input_tokens == 0  # FakeLLM returns None for usage
    assert events[1].output_tokens == 0


async def test_run_handles_empty_text_response() -> None:
    """When LLM returns empty text and no tool calls, message content must be non-empty.

    Anthropic API requires all messages to have non-empty content.
    """
    llm = FakeLLM(responses=[("", [], None)])
    tools = FakeTools(by_name={})
    events: list[Event] = []

    msgs = await run(
        messages=[{"role": "user", "content": "hi"}],
        llm=llm,  # type: ignore[arg-type]
        tools=tools,  # type: ignore[arg-type]
        on_event=events.append,
    )
    assert len(msgs) == 2  # user + assistant

    # Verify assistant message has non-empty content
    assistant_msg = msgs[1]
    assert assistant_msg["role"] == "assistant"
    assert len(assistant_msg["content"]) > 0
    assert assistant_msg["content"][0]["type"] == "text"


async def test_run_end_turn_carries_usage_from_llm() -> None:
    """When LLM returns StepUsage, EndTurn should carry the token counts."""
    from miniagent.llm import StepUsage

    @dataclass
    class UsageLLM:
        async def stream_step(self, messages, tools):
            return "Hi!", [], StepUsage(input_tokens=10, output_tokens=25)

    events: list[Event] = []
    await run(
        messages=[{"role": "user", "content": "hi"}],
        llm=UsageLLM(),  # type: ignore[arg-type]
        tools=FakeTools(by_name={}),
        on_event=events.append,
    )
    end = events[-1]
    assert isinstance(end, EndTurn)
    assert end.input_tokens == 10
    assert end.output_tokens == 25


async def test_run_executes_tool_and_reflows_result() -> None:
    async def fake_read(args: dict[str, Any]) -> ToolResult:
        return ToolResult(output="contents of foo")

    tool = Tool(name="read_file", description="r", input_schema={}, handler=fake_read)
    tools = FakeTools(by_name={"read_file": tool})

    llm = FakeLLM(
        responses=[
            (
                "Let me read it.",
                [FakeToolCall(id="c1", name="read_file", input={"path": "foo"})],
                None,
            ),
            ("Done.", [], None),
        ]
    )
    events: list[Event] = []

    msgs = await run(
        messages=[{"role": "user", "content": "read foo"}],
        llm=llm,  # type: ignore[arg-type]
        tools=tools,  # type: ignore[arg-type]
        on_event=events.append,
    )
    assert msgs  # returned messages list is non-empty

    # Should see: AssistantDelta, ToolCallStart, ToolCallResult, AssistantDelta, EndTurn
    assert [type(e) for e in events] == [
        AssistantDelta,
        ToolCallStart,
        ToolCallResult,
        AssistantDelta,
        EndTurn,
    ]
    assert events[2].output == "contents of foo"  # type: ignore[union-attr]


async def test_run_reflows_tool_error_back_to_llm() -> None:
    async def bad_read(args: dict[str, Any]) -> ToolResult:
        return ToolResult(error="FileNotFound: foo")

    tool = Tool(name="read_file", description="r", input_schema={}, handler=bad_read)
    tools = FakeTools(by_name={"read_file": tool})

    llm = FakeLLM(
        responses=[
            ("Reading.", [FakeToolCall(id="c1", name="read_file", input={"path": "foo"})], None),
            ("Sorry, file missing.", [], None),
        ]
    )
    events: list[Event] = []

    await run(
        messages=[{"role": "user", "content": "read foo"}],
        llm=llm,  # type: ignore[arg-type]
        tools=tools,  # type: ignore[arg-type]
        on_event=events.append,
    )

    tool_result_event = events[2]
    assert isinstance(tool_result_event, ToolCallResult)
    assert tool_result_event.ok is False
    assert "FileNotFound" in tool_result_event.error


async def test_run_maintains_message_consistency_on_tool_exception() -> None:
    """When a tool raises an exception, messages should still have matching pairs.

    This is the fix for the bug where tool_use without tool_result caused
    API errors.
    """

    async def failing_tool(args: dict[str, Any]) -> ToolResult:
        raise RuntimeError("Tool execution failed!")

    tool = Tool(
        name="failing_tool",
        description="fails",
        input_schema={},
        handler=failing_tool,
    )
    tools = FakeTools(by_name={"failing_tool": tool})

    llm = FakeLLM(
        responses=[
            (
                "Let me try.",
                [FakeToolCall(id="c1", name="failing_tool", input={})],
                None,
            ),
            ("Tool failed.", [], None),
        ]
    )
    events: list[Event] = []

    msgs = await run(
        messages=[{"role": "user", "content": "do something"}],
        llm=llm,  # type: ignore[arg-type]
        tools=tools,  # type: ignore[arg-type]
        on_event=events.append,
    )

    # Verify message structure: each tool_use must have a matching tool_result
    for i, msg in enumerate(msgs):
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                tool_use_blocks = [
                    b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
                ]
                if tool_use_blocks:
                    # Next message should be user with tool_result
                    assert i + 1 < len(msgs), f"tool_use at index {i} has no following message"
                    next_msg = msgs[i + 1]
                    assert next_msg.get("role") == "user", (
                        f"Expected user message after tool_use at {i}"
                    )
                    next_content = next_msg.get("content", [])
                    if isinstance(next_content, list):
                        tool_result_ids = {
                            b.get("tool_use_id")
                            for b in next_content
                            if isinstance(b, dict) and b.get("type") == "tool_result"
                        }
                        for block in tool_use_blocks:
                            assert block.get("id") in tool_result_ids, (
                                f"tool_use id={block.get('id')} missing from tool_result ids"
                            )

    # Verify error was reported
    error_events = [e for e in events if isinstance(e, ToolCallResult) and not e.ok]
    assert len(error_events) == 1
    assert "RuntimeError" in error_events[0].error


async def test_run_propagates_cancellation() -> None:
    """Ctrl+C cancels the LLM call; run() re-raises CancelledError; partial messages preserved."""

    @dataclass
    class HangingLLM:
        async def stream_step(self, messages, tools):
            await asyncio.sleep(10)  # never returns
            return "", [], None  # pragma: no cover

    events: list[Event] = []
    msgs = [{"role": "user", "content": "hi"}]

    task = asyncio.create_task(
        run(
            messages=msgs,
            llm=HangingLLM(),  # type: ignore[arg-type]
            tools=FakeTools(by_name={}),
            on_event=events.append,
        )
    )
    await asyncio.sleep(0.05)  # let it start
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # No AgentError should have been emitted (cancellation is not an error).
    assert not any(isinstance(e, AgentError) for e in events)
