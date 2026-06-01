from __future__ import annotations

import pytest
from textual.widgets import Input, Static

from miniagent.tui import AgentApp


@pytest.mark.asyncio
async def test_app_starts_and_shows_header_and_input() -> None:
    app = AgentApp(llm=None, tools=None, session=None, session_id="test-123")  # type: ignore[arg-type]
    async with app.run_test() as pilot:
        # Header is rendered
        header = app.query_one("#header", Static)
        assert "test-123" in str(header.renderable)
        # Input is focusable
        assert app.query_one(Input) is not None
        await pilot.pause()
