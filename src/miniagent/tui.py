"""Textual TUI app."""
from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static


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

    def compose(self) -> ComposeResult:
        yield Static(
            f"● miniagent · {self.model_name} · {self.session_id[:8]}",
            id="header",
        )
        yield VerticalScroll(id="log")
        yield Static("ready", id="status")
        yield Input(placeholder="Type a message and press Enter…", id="input")

    def on_mount(self) -> None:
        self.query_one("#input", Input).focus()
