"""Tool registry and the 4 built-in tools."""
from __future__ import annotations

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


# Registry populated by later tasks; declared here so the import works.
REGISTRY: dict[str, Tool] = {}


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
