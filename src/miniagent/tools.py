"""Tool registry and the 4 built-in tools."""
from __future__ import annotations

import os
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


# Registry populated by later tasks; declared here so the import works.
REGISTRY: dict[str, Tool] = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
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
