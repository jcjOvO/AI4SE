"""Entry point: python -m miniagent"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from miniagent.config import load_config
from miniagent.llm import LLMClient
from miniagent.session import AsyncSessionStore, SessionStore
from miniagent.tools import tools as tools_ns


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="miniagent")
    p.add_argument("--resume", help="Resume a session by id")
    p.add_argument(
        "--list",
        dest="list_sessions",
        action="store_true",
        help="List recent sessions and exit",
    )
    p.add_argument("--model", help="Override model from config")
    p.add_argument("--config", help="Path to user-level config.toml")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    cli_overrides: dict[str, Any] = {}
    if args.model:
        cli_overrides.setdefault("llm", {})
        if isinstance(cli_overrides.get("llm"), dict):
            cli_overrides["llm"]["model"] = args.model

    config = load_config(
        user_path=Path(args.config) if args.config else None,
        cli_overrides=cli_overrides if cli_overrides else None,
    )

    # Default workspace: $MINI_AGENT_WORKSPACE or <cwd>/workspace
    # In Docker the env var is typically set to /workspace; locally we
    # auto-create a workspace/ subdirectory so the sandbox behaviour is
    # consistent between the two environments.
    ws = Path(os.environ.get("MINI_AGENT_WORKSPACE", str(Path.cwd() / "workspace")))
    ws.mkdir(parents=True, exist_ok=True)
    os.environ["MINI_AGENT_WORKSPACE"] = str(ws)

    # Sessions dir
    sessions_dir = config.paths.sessions_dir
    sessions_dir.mkdir(parents=True, exist_ok=True)
    store = SessionStore(sessions_dir / "sessions.db")

    if args.list_sessions:
        for meta in store.list_recent(20):
            print(f"{meta.id}\t{meta.title or '(untitled)'}\t{meta.updated_at}")
        store.close()
        return 0

    initial_messages: list[dict[str, Any]] = []
    if args.resume:
        session_id = args.resume
        try:
            store.get(session_id)
            initial_messages = store.load_messages(session_id)
        except KeyError:
            print(f"No session with id {session_id!r}", file=sys.stderr)
            store.close()
            return 1
    else:
        session_id = store.create()
        print(f"New session: {session_id}")

    llm = LLMClient(
        api_key=config.llm.api_key,
        base_url=config.llm.base_url,
        model=config.llm.model,
        config=config.agent,
    )

    # AsyncSessionStore wraps the sync store so the agent loop never
    # blocks the TUI event loop on disk I/O (SPEC §3.5). It owns the
    # background flusher; we close it before the sync store.
    async_session: AsyncSessionStore = AsyncSessionStore(store)

    # Lazy import: textual is heavy
    from miniagent.tui import AgentApp

    app = AgentApp(
        llm=llm,
        tools=tools_ns,
        session=async_session,
        session_id=session_id,
        model_name=config.llm.model,
        initial_messages=initial_messages,
    )
    try:
        app.run()
    finally:
        # Drain the async session queue before closing SQLite.
        asyncio.run(async_session.close())
        store.close()
        asyncio.run(llm.close())
    return 0


if __name__ == "__main__":
    sys.exit(main())
