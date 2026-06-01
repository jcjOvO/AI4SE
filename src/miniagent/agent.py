"""Agent loop: pure async function emitting events."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class AssistantDelta:
    text: str


@dataclass
class ToolCallStart:
    call_id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolCallResult:
    call_id: str
    name: str
    ok: bool
    output: str
    error: str | None


@dataclass
class EndTurn:
    final_text: str


@dataclass
class AgentError:
    message: str
    recoverable: bool


Event = AssistantDelta | ToolCallStart | ToolCallResult | EndTurn | AgentError


class LLMProtocol(Protocol):
    async def stream_step(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[Any]]: ...


class ToolsProtocol(Protocol):
    def all_schemas(self) -> list[dict[str, Any]]: ...
    async def execute(self, name: str, args: dict[str, Any]) -> Any: ...


class SessionProtocol(Protocol):
    def append_message(self, session_id: str, msg: dict[str, Any]) -> None: ...


def _to_assistant_message(text: str, tool_calls: list[Any]) -> dict[str, Any]:
    """Build an assistant message in Anthropic native format."""
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    for tc in tool_calls:
        content.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input})
    return {"role": "assistant", "content": content}


def _to_tool_result_message(call_id: str, result: Any) -> dict[str, Any]:
    """Build a user-role tool_result message in Anthropic native format."""
    body = result.error if result.is_error else result.output
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": body,
                "is_error": result.is_error,
            }
        ],
    }


async def run(
    messages: list[dict[str, Any]],
    llm: LLMProtocol,
    tools: ToolsProtocol,
    on_event: Callable[[Event], None],
    session: SessionProtocol | None = None,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Run the agent loop until end_turn / cancellation / unrecoverable error.

    Returns the updated messages list.
    """
    try:
        while True:
            text, tool_calls = await llm.stream_step(messages, tools.all_schemas())
            on_event(AssistantDelta(text=text))

            assistant_msg = _to_assistant_message(text, tool_calls)
            messages.append(assistant_msg)
            if session and session_id:
                session.append_message(session_id, assistant_msg)

            if not tool_calls:
                on_event(EndTurn(final_text=text))
                return messages

            for call in tool_calls:
                on_event(ToolCallStart(call_id=call.id, name=call.name, args=call.input))
                result = await tools.execute(call.name, call.input)
                on_event(
                    ToolCallResult(
                        call_id=call.id,
                        name=call.name,
                        ok=not result.is_error,
                        output=result.output,
                        error=result.error,
                    )
                )
                tool_msg = _to_tool_result_message(call.id, result)
                messages.append(tool_msg)
                if session and session_id:
                    session.append_message(session_id, tool_msg)
    except asyncio.CancelledError:
        # User pressed Ctrl+C. Messages up to this point are already in
        # `messages` and in the session; do NOT swallow — re-raise so the
        # caller's task cancellation propagates and the session can be
        # cleanly closed by the TUI's finally block.
        raise
    except Exception as e:
        on_event(AgentError(message=f"{type(e).__name__}: {e}", recoverable=False))
        raise
