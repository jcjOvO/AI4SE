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

    responses: list[tuple[str, list[FakeToolCall]]]

    async def stream_step(
        self, messages: list[dict], tools: list[dict]
    ) -> tuple[str, list[FakeToolCall]]:
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
    llm = FakeLLM(responses=[("Hi there!", [])])
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


async def test_run_executes_tool_and_reflows_result() -> None:
    async def fake_read(args: dict[str, Any]) -> ToolResult:
        return ToolResult(output="contents of foo")

    tool = Tool(name="read_file", description="r", input_schema={}, handler=fake_read)
    tools = FakeTools(by_name={"read_file": tool})

    llm = FakeLLM(responses=[
        ("Let me read it.", [FakeToolCall(id="c1", name="read_file", input={"path": "foo"})]),
        ("Done.", []),
    ])
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
        AssistantDelta, ToolCallStart, ToolCallResult, AssistantDelta, EndTurn,
    ]
    assert events[2].output == "contents of foo"  # type: ignore[union-attr]


async def test_run_reflows_tool_error_back_to_llm() -> None:
    async def bad_read(args: dict[str, Any]) -> ToolResult:
        return ToolResult(error="FileNotFound: foo")

    tool = Tool(name="read_file", description="r", input_schema={}, handler=bad_read)
    tools = FakeTools(by_name={"read_file": tool})

    llm = FakeLLM(responses=[
        ("Reading.", [FakeToolCall(id="c1", name="read_file", input={"path": "foo"})]),
        ("Sorry, file missing.", []),
    ])
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


async def test_run_propagates_cancellation() -> None:
    """Ctrl+C cancels the LLM call; run() re-raises CancelledError; partial messages preserved."""

    @dataclass
    class HangingLLM:
        async def stream_step(self, messages, tools):
            await asyncio.sleep(10)  # never returns
            return "", []  # pragma: no cover

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
