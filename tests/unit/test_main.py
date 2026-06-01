from __future__ import annotations

from pathlib import Path

import pytest

from miniagent.__main__ import parse_args


def test_parse_args_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["miniagent"])
    args = parse_args()
    assert args.resume is None
    assert args.list_sessions is False
    assert args.model is None


def test_parse_args_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["miniagent", "--resume", "abc-123"])
    args = parse_args()
    assert args.resume == "abc-123"
