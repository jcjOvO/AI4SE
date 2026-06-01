"""Tool registry and the 4 built-in tools."""
from __future__ import annotations

import asyncio
import os
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ToolResult:
    """Result of a tool invocation. Tool errors go in `error`, not exceptions."""
    output: str = ""
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[ToolResult]]


def resolve_sandbox_path(root: Path, requested: str) -> Path:
    """Resolve `requested` against `root`; reject if it escapes."""
    root_resolved = root.resolve()
    if Path(requested).is_absolute():
        candidate = Path(requested).resolve()
    else:
        candidate = (root_resolved / requested).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as e:
        raise ValueError(
            f"Path escapes sandbox: {requested} resolves outside {root_resolved}"
        ) from e
    return candidate


# ---------------------------------------------------------------------------
# Task 4: read_file tool
# ---------------------------------------------------------------------------


async def _read_file_handler(args: dict[str, Any]) -> ToolResult:
    root = Path(os.environ.get("MINI_AGENT_WORKSPACE", Path.cwd()))
    try:
        path = resolve_sandbox_path(root, args["path"])
    except ValueError as e:
        return ToolResult(error=str(e))

    if not path.exists():
        return ToolResult(error=f"FileNotFound: {args['path']}")
    if path.is_dir():
        return ToolResult(error=f"IsADirectory: {args['path']}")

    offset = int(args.get("offset", 0))
    limit = int(args.get("limit", 2000))

    try:
        raw = path.read_bytes()
    except OSError as e:
        return ToolResult(error=f"{type(e).__name__}: {e}")

    # Binary detection: if any null byte in first 8KB, hex-preview
    if b"\x00" in raw[:8192]:
        preview = raw[:4096]
        return ToolResult(output=f"<binary file, {len(raw)} bytes>\n{preview.hex()}")

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    chunk = lines[offset : offset + limit]
    return ToolResult(output="\n".join(chunk))


read_file = Tool(
    name="read_file",
    description=(
        "Read a file from the workspace. Returns up to `limit` lines starting at `offset`. "
        "Binary files are returned as a hex preview."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to workspace, or absolute within workspace",
            },
            "offset": {"type": "integer", "description": "Line offset to start from", "default": 0},
            "limit": {"type": "integer", "description": "Max lines to return", "default": 2000},
        },
        "required": ["path"],
    },
    handler=_read_file_handler,
)


# ---------------------------------------------------------------------------
# Task 5: write_file tool
# ---------------------------------------------------------------------------


async def _write_file_handler(args: dict[str, Any]) -> ToolResult:
    root = Path(os.environ.get("MINI_AGENT_WORKSPACE", Path.cwd()))
    try:
        path = resolve_sandbox_path(root, args["path"])
    except ValueError as e:
        return ToolResult(error=str(e))

    content = args["content"]
    if not isinstance(content, str):
        return ToolResult(error=f"content must be str, got {type(content).__name__}")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        return ToolResult(error=f"{type(e).__name__}: {e}")

    return ToolResult(output=f"Wrote {len(content.encode('utf-8'))} bytes to {args['path']}")


write_file = Tool(
    name="write_file",
    description=(
        "Create or overwrite a file with the given content. "
        "Parent directories are created automatically."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
    handler=_write_file_handler,
)


# ---------------------------------------------------------------------------
# Task 6: edit_file tool
# ---------------------------------------------------------------------------


async def _edit_file_handler(args: dict[str, Any]) -> ToolResult:
    root = Path(os.environ.get("MINI_AGENT_WORKSPACE", Path.cwd()))
    try:
        path = resolve_sandbox_path(root, args["path"])
    except ValueError as e:
        return ToolResult(error=str(e))

    old = args["old_string"]
    new = args["new_string"]
    replace_all = bool(args.get("replace_all", False))

    if not path.exists():
        return ToolResult(error=f"FileNotFound: {args['path']}")

    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        return ToolResult(error=f"old_string not found in {args['path']}")
    if count > 1 and not replace_all:
        return ToolResult(
            error=f"old_string not unique ({count} matches); pass replace_all=true to allow"
        )

    if replace_all:
        new_text = text.replace(old, new)
        n = count
    else:
        new_text = text.replace(old, new, 1)
        n = 1

    path.write_text(new_text, encoding="utf-8")
    return ToolResult(
        output=f"Edited {args['path']} ({n} replacement{'s' if n != 1 else ''})"
    )


edit_file = Tool(
    name="edit_file",
    description=(
        "Replace a specific string in a file. By default old_string must occur exactly once. "
        "Pass replace_all=true to replace every occurrence."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean", "default": False},
        },
        "required": ["path", "old_string", "new_string"],
    },
    handler=_edit_file_handler,
)


# ---------------------------------------------------------------------------
# Task 7: bash tool
# ---------------------------------------------------------------------------


def _command_escapes_sandbox(command: str, root_resolved: Path) -> str | None:
    """Return the offending path token if `command` references anything outside `root_resolved`.

    `root_resolved` must already be `.resolve()`d by the caller (so this
    function is safe to call from async code without blocking I/O).
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None  # let the shell fail; not a sandbox concern
    # Strip shell metachars
    file_like = [
        t for t in tokens if not t.startswith(("-", "$", ";")) and "=" not in t
    ]
    for tok in file_like:
        # skip obvious non-paths
        if tok in {"&&", "||", "|", ">", "<", ">>", "<<<", "2>&1"}:
            continue
        if (
            tok.startswith(("./", "/", "../"))
            or "/" in tok
            or tok in {".", ".."}
        ):
            try:
                if Path(tok).is_absolute():
                    candidate = Path(tok).resolve()
                else:
                    candidate = (root_resolved / tok).resolve()
                candidate.relative_to(root_resolved)
            except (ValueError, OSError):
                return tok
    return None


async def _bash_handler(args: dict[str, Any]) -> ToolResult:
    root = Path(os.environ.get("MINI_AGENT_WORKSPACE", Path.cwd()))
    command = args["command"]
    timeout = int(args.get("timeout", 30))

    # .resolve() may hit the filesystem (symlinks, Windows quirks), so
    # offload to a thread to avoid blocking the event loop (ASYNC240).
    root_resolved = await asyncio.to_thread(root.resolve)
    escaper = _command_escapes_sandbox(command, root_resolved)
    if escaper is not None:
        return ToolResult(
            error=f"Path escapes sandbox: '{escaper}' is outside {root_resolved}"
        )

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(root_resolved),
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(error=f"Command timed out after {timeout}s")
    except Exception as e:
        return ToolResult(error=f"{type(e).__name__}: {e}")

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    parts = [stdout.rstrip("\n")]
    if stderr:
        parts.append(f"[stderr: {stderr.rstrip()}]")
    parts.append(f"[exit: {proc.returncode}]")
    return ToolResult(output="\n".join(parts))


bash = Tool(
    name="bash",
    description=(
        "Execute a shell command in the workspace. Returns stdout, stderr, and exit code. "
        "Commands referencing literal paths outside the workspace are rejected. "
        "Default timeout 30s (configurable). "
        "Note: the path-escape check inspects shlex-split tokens after stripping "
        "common shell metachars; it does NOT expand shell variables (e.g. "
        "`$HOME/secret`, `~/secret`, `$(echo /etc/passwd)`). For those, rely on "
        "container filesystem permissions — the command runs with `cwd` set to the "
        "workspace root."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {
                "type": "integer",
                "default": 30,
                "description": "Timeout in seconds",
            },
        },
        "required": ["command"],
    },
    handler=_bash_handler,
)


# Registry populated by later tasks; declared here so the import works.
REGISTRY: dict[str, Tool] = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "bash": bash,
}


def all_schemas() -> list[dict[str, Any]]:
    """Return tool schemas in Anthropic format for the LLM."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in REGISTRY.values()
    ]


async def execute(name: str, args: dict[str, Any]) -> ToolResult:
    """Look up a tool by name and run its handler. Unknown name → error ToolResult."""
    tool = REGISTRY.get(name)
    if tool is None:
        return ToolResult(error=f"Unknown tool: {name}")
    try:
        return await tool.handler(args)
    except Exception as e:  # programming errors only; tool errors should be returned, not raised
        return ToolResult(error=f"{type(e).__name__}: {e}")


class _ToolsNamespace:
    """Object wrapper exposing all_schemas() / execute() as methods.

    The agent loop's `ToolsProtocol` expects an object (calls
    `tools.all_schemas()` and `await tools.execute(...)`), not a raw dict
    or module. This singleton lets callers do
    `from miniagent.tools import tools` and pass the object directly.
    """

    all_schemas = staticmethod(all_schemas)
    execute = staticmethod(execute)


tools = _ToolsNamespace()
