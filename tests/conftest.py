"""Shared pytest fixtures."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """A tmp directory representing /workspace in the container."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
    """Single event loop per test session (pytest-asyncio default)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
