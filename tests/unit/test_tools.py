from __future__ import annotations

from pathlib import Path

import pytest

from miniagent.tools import (  # noqa: F401
    REGISTRY,
    ToolResult,
    bash,
    edit_file,
    read_file,
    resolve_sandbox_path,
    write_file,
)


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


# ---------------------------------------------------------------------------
# Task 4: read_file tool
# ---------------------------------------------------------------------------
# Note: read_file's handler reads the workspace root from the
# MINI_AGENT_WORKSPACE env var (with a cwd fallback). The spec did not mention
# setting it, but without it the handler would resolve paths against cwd and
# miss the tmp_workspace fixture. Each test below sets the env var explicitly
# (precedent: Task 2/3 monkeypatch fix in AGENT_LOG #4 / #5).


async def test_read_file_basic(tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    (tmp_workspace / "hello.txt").write_text("line1\nline2\nline3\n")
    r = await read_file.handler({"path": "hello.txt"})
    assert r.error is None
    assert "line1" in r.output
    assert "line3" in r.output


async def test_read_file_missing(tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await read_file.handler({"path": "nope.txt"})
    assert r.is_error
    assert "FileNotFound" in r.error


async def test_read_file_offset_and_limit(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    (tmp_workspace / "f.txt").write_text("\n".join(f"line{i}" for i in range(100)))
    r = await read_file.handler({"path": "f.txt", "offset": 10, "limit": 5})
    assert r.error is None
    assert "line10" in r.output
    assert "line14" in r.output
    assert "line15" not in r.output


async def test_read_file_rejects_traversal(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await read_file.handler({"path": "../secret.txt"})
    assert r.is_error
    assert "escapes sandbox" in r.error


async def test_read_file_binary(tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    (tmp_workspace / "bin.dat").write_bytes(b"\x00\x01\x02hello\xff")
    r = await read_file.handler({"path": "bin.dat"})
    assert r.error is None
    # Should be hex-preview, not raw
    assert "00 01 02" in r.output or "000102" in r.output


# ---------------------------------------------------------------------------
# Task 5: write_file tool
# ---------------------------------------------------------------------------


async def test_write_file_creates(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await write_file.handler({"path": "out.txt", "content": "hi\n"})
    assert r.error is None
    assert (tmp_workspace / "out.txt").read_text() == "hi\n"


async def test_write_file_overwrites(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    (tmp_workspace / "f.txt").write_text("old")
    r = await write_file.handler({"path": "f.txt", "content": "new"})
    assert r.error is None
    assert (tmp_workspace / "f.txt").read_text() == "new"


async def test_write_file_creates_parent_dirs(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await write_file.handler({"path": "deep/nested/dir/f.txt", "content": "x"})
    assert r.error is None
    assert (tmp_workspace / "deep" / "nested" / "dir" / "f.txt").exists()


async def test_write_file_rejects_traversal(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await write_file.handler({"path": "../escape.txt", "content": "x"})
    assert r.is_error
    assert "escapes sandbox" in r.error
    assert not (tmp_workspace.parent / "escape.txt").exists()


async def test_write_file_returns_size(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await write_file.handler({"path": "f.txt", "content": "abcde"})
    assert "5 bytes" in r.output


# ---------------------------------------------------------------------------
# Task 6: edit_file tool
# ---------------------------------------------------------------------------


async def test_edit_file_single_replacement(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    (tmp_workspace / "f.txt").write_text("hello world\nhello there\n")
    r = await edit_file.handler({
        "path": "f.txt",
        "old_string": "hello world",
        "new_string": "hi world",
    })
    assert r.error is None
    assert (tmp_workspace / "f.txt").read_text() == "hi world\nhello there\n"


async def test_edit_file_not_unique_errors(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    (tmp_workspace / "f.txt").write_text("aaa\naaa\n")
    r = await edit_file.handler({
        "path": "f.txt", "old_string": "aaa", "new_string": "bbb",
    })
    assert r.is_error
    assert "not unique" in r.error
    assert (tmp_workspace / "f.txt").read_text() == "aaa\naaa\n"  # unchanged


async def test_edit_file_not_found_errors(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    (tmp_workspace / "f.txt").write_text("hello")
    r = await edit_file.handler({
        "path": "f.txt", "old_string": "goodbye", "new_string": "hi",
    })
    assert r.is_error
    assert "not found" in r.error


async def test_edit_file_replace_all(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    (tmp_workspace / "f.txt").write_text("aaa\naaa\n")
    r = await edit_file.handler({
        "path": "f.txt", "old_string": "aaa", "new_string": "bbb", "replace_all": True,
    })
    assert r.error is None
    assert "2 replacements" in r.output
    assert (tmp_workspace / "f.txt").read_text() == "bbb\nbbb\n"


async def test_edit_file_rejects_traversal(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await edit_file.handler({
        "path": "../escape.txt", "old_string": "x", "new_string": "y",
    })
    assert r.is_error
    assert "escapes sandbox" in r.error


# ---------------------------------------------------------------------------
# Task 7: bash tool
# ---------------------------------------------------------------------------


async def test_bash_runs_command(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await bash.handler({"command": "echo hello"})
    assert r.error is None
    assert "hello" in r.output
    assert "exit: 0" in r.output


async def test_bash_captures_nonzero_exit(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await bash.handler({"command": "exit 7"})
    # Non-zero exit is NOT an error; it's reported in output
    assert r.error is None
    assert "exit: 7" in r.output


async def test_bash_captures_stderr(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await bash.handler({"command": "echo oops >&2; echo ok"})
    assert r.error is None
    assert "oops" in r.output
    assert "ok" in r.output


async def test_bash_rejects_path_escape(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    # Outside-root path → reject
    r = await bash.handler({"command": "cat /etc/passwd"})
    assert r.is_error
    assert "escapes sandbox" in r.error


async def test_bash_rejects_traversal_token(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await bash.handler({"command": "ls ../"})
    assert r.is_error
    assert "escapes sandbox" in r.error


async def test_bash_respects_workspace_root(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    r = await bash.handler({"command": "pwd"})
    assert r.error is None
    # Subprocess shells on Windows (MSYS/Git Bash) may translate the cwd
    # to a Posix-style path (e.g. `/tmp/...`); check the leaf name
    # invariant instead of the full path.
    assert tmp_workspace.name in r.output


async def test_bash_does_not_validate_shell_expansion(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Document the bash sandbox's known limitation: tokens that go
    through shell expansion (e.g. $HOME, $(...), ~) are not pre-validated.
    The detector only inspects literal shlex-split tokens. Container
    filesystem permissions + cwd restriction are the real boundary."""
    monkeypatch.setenv("MINI_AGENT_WORKSPACE", str(tmp_workspace))
    # `echo hi` (no escape) — passes
    r_ok = await bash.handler({"command": "echo hi"})
    assert r_ok.error is None
    # `cat $HOME/secret` — the $HOME token doesn't start with "/"
    # or "../", so the detector does not block it. This is a known
    # limitation; we assert current behavior so future refactors
    # don't regress silently.
    r = await bash.handler({"command": "echo $HOME"})
    assert r.error is None  # detector did not block
    # The command actually runs; the detector's only contract is
    # "reject literal /etc/passwd and literal ../", which we test
    # in the rejection tests above.
