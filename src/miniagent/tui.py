"""Textual TUI app."""
from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static

from miniagent.agent import (
    AgentError,
    AssistantDelta,
    EndTurn,
    Event,
    ToolCallResult,
    ToolCallStart,
)
from miniagent.agent import (
    run as agent_run,
)


class AgentApp(App[None]):
    """Single-panel TUI: header / scrollable log / input / status bar."""

    CSS = """
    #header {
        dock: top;
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    #log {
        height: 1fr;
        border: solid $primary;
    }
    #input {
        dock: bottom;
    }
    #status {
        dock: bottom;
        height: 1;
        background: $boost;
        color: $text;
    }
    """

    def __init__(
        self,
        llm: Any,
        tools: Any,
        session: Any,
        session_id: str,
        model_name: str = "claude-x",
    ) -> None:
        super().__init__()
        self.llm = llm
        self.tools = tools
        self.session = session
        self.session_id = session_id
        self.model_name = model_name
        self._current_assistant_text: str = ""
        self._busy: bool = False

    def compose(self) -> ComposeResult:
        yield Static(
            f"● miniagent · {self.model_name} · {self.session_id[:8]}",
            id="header",
        )
        yield RichLog(id="log", wrap=True, highlight=True, markup=True)
        yield Static("ready", id="status")
        yield Input(placeholder="Type a message and press Enter…", id="input")

    def on_mount(self) -> None:
        self.query_one("#input", Input).focus()
        self.query_one(RichLog).write(
            "[bold]Welcome to miniagent. Type a message to begin.[/bold]"
        )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._busy:
            return
        text = event.value.strip()
        if not text:
            return
        if text == "/exit":
            self.exit()
            return
        if text == "/reset":
            self.query_one(RichLog).write(
                "[italic]Session reset (history kept on disk)[/italic]"
            )
            self.query_one("#input", Input).value = ""
            return

        log = self.query_one(RichLog)
        log.write(f"[bold cyan]you>[/bold cyan] {text}")
        self.query_one("#input", Input).value = ""
        self._set_status("thinking...")
        self._busy = True
        self._current_assistant_text = ""

        # Hand off to agent in a background task
        asyncio.create_task(self._run_agent(text))

    async def _run_agent(self, user_text: str) -> None:
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]

        def emit(event: Event) -> None:
            self._render_event(event)

        try:
            await agent_run(
                messages=messages,
                llm=self.llm,
                tools=self.tools,
                on_event=emit,
                session=self.session,
                session_id=self.session_id,
            )
        except asyncio.CancelledError:
            self.query_one(RichLog).write("[yellow]interrupted[/yellow]")
        except Exception as e:
            self.query_one(RichLog).write(f"[red]error: {e}[/red]")
        finally:
            self._busy = False
            self._set_status("ready")

    def _render_event(self, event: Event) -> None:
        log = self.query_one(RichLog)
        if isinstance(event, AssistantDelta):
            if not self._current_assistant_text:
                log.write("[bold green]assistant>[/bold green] ")
            self._current_assistant_text += event.text
            # The spec's `write(prefix); accumulate text` never actually
            # renders the text. Write each delta so the log shows the
            # streamed content (newline-per-delta is acceptable for v1).
            log.write(event.text)
        elif isinstance(event, ToolCallStart):
            log.write(f"  [magenta]🔧 {event.name}({event.args})[/magenta]")
        elif isinstance(event, ToolCallResult):
            mark = "✓" if event.ok else "✗"
            color = "green" if event.ok else "red"
            payload = event.output if event.ok else (event.error or "")
            log.write(f"  [{color}]{mark} {payload}[/{color}]")
        elif isinstance(event, EndTurn):
            # Already streamed via AssistantDelta; just log a separator
            log.write("")
        elif isinstance(event, AgentError):
            log.write(f"[red]agent error: {event.message}[/red]")

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)
