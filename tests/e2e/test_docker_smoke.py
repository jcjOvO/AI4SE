"""End-to-end test: run a mock LLM, drive agent.run() against it.

This is the *unit-level* E2E (no Docker, no TUI). The Docker-based E2E
(constructing a container, sending keys, reading TUI) is manual.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from miniagent.agent import AssistantDelta, EndTurn, run
from miniagent.llm import LLMClient


@pytest.fixture(scope="module")
def mock_server() -> str:
    proc = subprocess.Popen(
        [sys.executable, "scripts/mock_anthropic.py", "8765"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for it to be ready
    for _ in range(50):
        try:
            httpx.get("http://127.0.0.1:8765/v1/messages", timeout=0.5)
        except Exception:
            time.sleep(0.1)
        else:
            break
    yield "http://127.0.0.1:8765"
    proc.terminate()
    proc.wait()


@pytest.mark.e2e
async def test_agent_against_mock_llm(mock_server: str, tmp_path: Path) -> None:
    llm = LLMClient(api_key="sk-fake", base_url=mock_server, model="claude-mock")
    from miniagent.tools import tools

    events = []
    msgs = await run(
        messages=[{"role": "user", "content": "hi"}],
        llm=llm,
        tools=tools,
        on_event=events.append,
    )
    assert msgs
    assert any(
        isinstance(e, AssistantDelta) and "Hello from mock" in e.text for e in events
    )
    assert any(isinstance(e, EndTurn) for e in events)
    await llm.close()
