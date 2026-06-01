"""Configuration: load + validate TOML, overlay CLI args."""
from __future__ import annotations

import sys
import tomllib
import warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

DEFAULT_USER_CONFIG = Path.home() / ".config" / "mini-agent" / "config.toml"
DEFAULT_PROJECT_CONFIG = Path.cwd() / ".mini-agent.toml"


class LLMConfig(BaseModel):
    api_key: str
    base_url: str = "https://api.anthropic.com"
    model: str = "claude-sonnet-4-6"


class PathsConfig(BaseModel):
    sessions_dir: Path = Field(
        default_factory=lambda: Path.home() / ".local" / "share" / "mini-agent" / "sessions"
    )


class AgentConfig(BaseModel):
    pass


class Config(BaseModel):
    llm: LLMConfig
    paths: PathsConfig = Field(default_factory=PathsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overlay into base; overlay wins on leaf conflicts."""
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(
    user_path: Path | None = None,
    project_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> Config:
    """Load config from user → project → CLI (later wins)."""
    user_path = user_path or DEFAULT_USER_CONFIG
    project_path = project_path if project_path is not None else DEFAULT_PROJECT_CONFIG

    user_data = _load_toml(user_path)
    project_data = _load_toml(project_path)

    # Warn on unknown top-level keys
    for src_name, src in (("user", user_data), ("project", project_data)):
        for key in src:
            if key not in {"llm", "paths", "agent"}:
                warnings.warn(f"Unknown config key '{key}' in {src_name} config", stacklevel=2)

    merged = _deep_merge(user_data, project_data)
    if cli_overrides:
        merged = _deep_merge(merged, cli_overrides)

    try:
        return Config.model_validate(merged)
    except ValidationError as e:
        print(f"Config validation failed:\n{e}", file=sys.stderr)
        print(
            "\nHint: minimal config.toml example:\n"
            '  [llm]\n'
            '  api_key = "sk-ant-..."\n'
            '  base_url = "https://api.anthropic.com"\n'
            '  model = "claude-sonnet-4-6"\n',
            file=sys.stderr,
        )
        raise SystemExit(2) from e
