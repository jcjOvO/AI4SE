from __future__ import annotations

from pathlib import Path

import pytest

from miniagent.tools import REGISTRY, ToolResult, resolve_sandbox_path  # noqa: F401


def test_resolve_sandbox_path_inside(tmp_workspace: Path) -> None:
    p = resolve_sandbox_path(tmp_workspace, "foo/bar.py")
    assert p == (tmp_workspace / "foo" / "bar.py").resolve()


def test_resolve_sandbox_path_rejects_traversal(tmp_workspace: Path) -> None:
    with pytest.raises(ValueError, match="escapes sandbox"):
        resolve_sandbox_path(tmp_workspace, "../etc/passwd")


def test_resolve_sandbox_path_rejects_absolute_outside(tmp_workspace: Path) -> None:
    with pytest.raises(ValueError, match="escapes sandbox"):
        resolve_sandbox_path(tmp_workspace, "/etc/passwd")


def test_tool_result_is_error() -> None:
    ok = ToolResult(output="hi")
    err = ToolResult(output="", error="boom")
    assert not ok.is_error
    assert err.is_error
