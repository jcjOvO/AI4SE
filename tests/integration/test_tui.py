from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from textual.widgets import Input, RichLog, Static

from miniagent.tui import AgentApp


@pytest.mark.asyncio
async def test_app_starts_and_shows_header_and_input() -> None:
    app = AgentApp(
        llm=None,
        tools=None,
        session=None,
        session_id="test-123",
        model_name="claude-x",  # type: ignore[arg-type]
    )
    async with app.run_test() as pilot:
        header = app.query_one("#header", Static)
        header_text = str(header.renderable)
        assert "miniagent" in header_text
        assert "claude-x" in header_text
        assert "test-123" in header_text
        assert "ready" in header_text
        status = app.query_one("#status", Static)
        assert status is not None
        assert app.query_one(Input) is not None
        await pilot.pause()


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------


@dataclass
class _Msg:
    text: str = ""
    is_error: bool = False
    calls: list[Any] | None = None


@dataclass
class _LLM:
    async def stream_step(self, messages, tools):
        last = messages[-1]
        content = last.get("content", "") if isinstance(last.get("content"), str) else "hi"
        return "Echo: " + content, [], None


@dataclass
class _Tools:
    def all_schemas(self) -> list:
        return []

    async def execute(self, name, args):
        return _Msg()


# ---------------------------------------------------------------------------
# Input -> agent.run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_input_triggers_agent_run() -> None:
    app = AgentApp(
        llm=_LLM(),  # type: ignore[arg-type]
        tools=_Tools(),  # type: ignore[arg-type]
        session=None,
        session_id="s-1",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("h", "e", "l", "l", "o", "enter")
        for _ in range(20):
            await pilot.pause()
            log = app.query_one("#log", RichLog)
            text = "\n".join(str(line) for line in log.lines)
            if "Echo: hello" in text:
                break
        else:
            pytest.fail(f"Agent response never appeared. Log was:\n{text}")
        assert "you" in text
        assert "assistant" in text
        status = app.query_one("#status", Static)
        status_text = str(status.renderable)
        assert "ready" in status_text


# ---------------------------------------------------------------------------
# History replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initial_messages_replayed_on_mount() -> None:
    """When --resume passes initial_messages, they render on mount
    so the user sees prior context. New user input is then appended."""
    history = [
        {"role": "user", "content": "previous question"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "previous answer"},
                {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "x"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "ok", "is_error": False},
            ],
        },
    ]
    app = AgentApp(
        llm=_LLM(),  # type: ignore[arg-type]
        tools=_Tools(),  # type: ignore[arg-type]
        session=None,
        session_id="s-2",
        initial_messages=history,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.query_one("#log", RichLog)
        text = "\n".join(str(line) for line in log.lines)
        assert "previous question" in text
        assert "previous answer" in text
