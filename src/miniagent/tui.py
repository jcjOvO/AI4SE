"""Textual TUI app."""

from __future__ import annotations

import asyncio
import json as _json
import time
from pathlib import Path
from typing import Any

from rich.panel import Panel
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

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_CSS_PATH = Path(__file__).parent / "tui.css"


class AgentApp(App[None]):
    """Single-panel TUI: header / scrollable log / status / input."""

    CSS_PATH = _CSS_PATH

    def __init__(
        self,
        llm: Any,
        tools: Any,
        session: Any,
        session_id: str,
        model_name: str = "claude-x",
        initial_messages: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self.llm = llm
        self.tools = tools
        self.session = session
        self.session_id = session_id
        self.model_name = model_name
        self._messages: list[dict[str, Any]] = list(initial_messages or [])
        self._busy: bool = False
        self._turn_start: float = 0.0
        self._total_input: int = 0
        self._total_output: int = 0
        self._spinner_idx: int = 0
        self._spinner_timer: Any = None

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="header")
        yield RichLog(id="log", wrap=True, highlight=True, markup=True)
        yield Static("ready", id="status")
        yield Input(placeholder="Type a message and press Enter…", id="input")

    def on_mount(self) -> None:
        if hasattr(self.session, "start"):
            self.session.start()
        self.query_one("#input", Input).focus()
        log = self.query_one(RichLog)
        log.write("[bold]Welcome to miniagent. Type a message to begin.[/bold]")
        for msg in self._messages:
            self._replay_message(msg)

    # ── Header helpers ─────────────────────────────────────

    def _header_text(self, right: str = "ready") -> str:
        left = f"● miniagent · {self.model_name} · {self.session_id[:8]}"
        return f" {left}    {right}"

    def _update_header(self, right: str) -> None:
        self.query_one("#header", Static).update(self._header_text(right))

    # ── Status bar helpers ─────────────────────────────────

    def _update_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _start_spinner(self, status_text: str) -> None:
        self._spinner_idx = 0
        self._update_status(f"{_SPINNER_FRAMES[0]} {status_text}")

        def tick() -> None:
            self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER_FRAMES)
            frame = _SPINNER_FRAMES[self._spinner_idx]
            self._update_status(f"{frame} {status_text}")

        self._spinner_timer = self.set_interval(0.08, tick)

    def _stop_spinner(self, final_status: str = "ready") -> None:
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self._update_status(final_status)

    # ── Token formatting ───────────────────────────────────

    def _format_tokens(self, inp: int, out: int) -> str:
        def _fmt(n: int) -> str:
            if n >= 1000:
                return f"{n / 1000:.1f}k"
            return str(n)

        return f"tokens: {_fmt(inp)} / {_fmt(out)}"

    # ── History replay ─────────────────────────────────────

    def _replay_message(self, msg: dict[str, Any]) -> None:
        log = self.query_one(RichLog)
        content = msg.get("content", "")
        if isinstance(content, str):
            if msg.get("role") == "user":
                panel = Panel(
                    content,
                    title="[bold cyan]you[/bold cyan]",
                    border_style="cyan",
                    expand=True,
                )
                log.write(panel)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    panel = Panel(
                        block.get("text", ""),
                        title="[bold green]assistant[/bold green]",
                        border_style="green",
                        expand=True,
                    )
                    log.write(panel)
                elif btype == "tool_use":
                    args_str = _json.dumps(block.get("input", {}), ensure_ascii=False)
                    panel = Panel(
                        f"[dim]{args_str}[/dim]",
                        title=f"[bold magenta]\U0001f527 {block.get('name')}[/bold magenta]",
                        border_style="magenta",
                        expand=True,
                    )
                    log.write(panel)
                elif btype == "tool_result":
                    payload = block.get("content", "")
                    ok = not block.get("is_error", False)
                    mark = "✓" if ok else "✗"
                    color = "green" if ok else "red"
                    panel = Panel(
                        f"[{color}]{mark}[/{color}] {payload}",
                        border_style=color,
                        expand=True,
                    )
                    log.write(panel)

    # ── Input handling ─────────────────────────────────────

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
            self._messages.clear()
            self._total_input = 0
            self._total_output = 0
            self._update_header("ready")
            self.query_one(RichLog).write("[italic]Session reset (history cleared)[/italic]")
            self.query_one("#input", Input).value = ""
            return

        log = self.query_one(RichLog)
        panel = Panel(
            text,
            title="[bold cyan]you[/bold cyan]",
            border_style="cyan",
            expand=True,
        )
        log.write(panel)
        self.query_one("#input", Input).value = ""
        self._busy = True
        self._turn_start = time.monotonic()
        self._start_spinner("thinking...")

        asyncio.create_task(self._run_agent(text))

    # ── Agent execution ────────────────────────────────────

    async def _run_agent(self, user_text: str) -> None:
        user_msg: dict[str, Any] = {"role": "user", "content": user_text}
        self._messages.append(user_msg)
        if self.session and self.session_id:
            self.session.append_message(self.session_id, user_msg)

        def emit(event: Event) -> None:
            self._render_event(event)

        try:
            await agent_run(
                messages=self._messages,
                llm=self.llm,
                tools=self.tools,
                on_event=emit,
                session=self.session,
                session_id=self.session_id,
            )
        except asyncio.CancelledError:
            self.query_one(RichLog).write("[yellow]interrupted[/yellow]")
            self._stop_spinner("interrupted")
        except Exception as e:
            self.query_one(RichLog).write(f"[red]error: {e}[/red]")
            self._stop_spinner("error")
        else:
            self._stop_spinner("ready")
        finally:
            self._busy = False

    # ── Event rendering ────────────────────────────────────

    def _render_event(self, event: Event) -> None:
        log = self.query_one(RichLog)
        if isinstance(event, AssistantDelta):
            panel = Panel(
                event.text,
                title="[bold green]assistant[/bold green]",
                border_style="green",
                expand=True,
            )
            log.write(panel)
        elif isinstance(event, ToolCallStart):
            self._stop_spinner()
            self._start_spinner(f"calling {event.name}...")
            args_str = _json.dumps(event.args, ensure_ascii=False)
            panel = Panel(
                f"[dim]{args_str}[/dim]",
                title=f"[bold magenta]\U0001f527 {event.name}[/bold magenta]",
                border_style="magenta",
                expand=True,
            )
            log.write(panel)
        elif isinstance(event, ToolCallResult):
            self._stop_spinner()
            self._start_spinner("thinking...")
            mark = "✓" if event.ok else "✗"
            color = "green" if event.ok else "red"
            payload = event.output if event.ok else (event.error or "")
            lines = payload.split("\n")
            if len(lines) > 5:
                payload = "\n".join(lines[:3]) + f"\n[dim][... {len(lines) - 3} more lines][/dim]"
            panel = Panel(
                f"[{color}]{mark}[/{color}] {payload}",
                border_style=color,
                expand=True,
            )
            log.write(panel)
        elif isinstance(event, EndTurn):
            elapsed = time.monotonic() - self._turn_start if self._turn_start else 0
            self._total_input += event.input_tokens
            self._total_output += event.output_tokens
            right = f"{self._format_tokens(self._total_input, self._total_output)} · {elapsed:.1f}s"
            self._update_header(right)
        elif isinstance(event, AgentError):
            log.write(f"[red]agent error: {event.message}[/red]")
