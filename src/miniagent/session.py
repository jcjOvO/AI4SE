"""SQLite-backed session storage."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CorruptSessionError(Exception):
    """Raised when the sessions DB file is unreadable or has wrong schema."""


@dataclass
class SessionMeta:
    id: str
    title: str | None
    created_at: float
    updated_at: float


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  REAL NOT NULL,
    PRIMARY KEY (session_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, seq);
"""


class SessionStore:
    """Synchronous CRUD over a single SQLite file.

    Writes are immediate (not queued) — for the async-flush queue behavior,
    wrap this with an AsyncSessionStore in a later task.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        try:
            self._con = sqlite3.connect(str(db_path), isolation_level=None)
            self._con.execute("PRAGMA journal_mode=WAL")
            self._con.execute("PRAGMA foreign_keys=ON")
            self._con.executescript(_SCHEMA)
        except sqlite3.DatabaseError as e:
            raise CorruptSessionError(f"Cannot initialize {db_path}: {e}") from e

    def create(self) -> str:
        sid = str(uuid.uuid4())
        now = time.time()
        self._con.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, NULL, ?, ?)",
            (sid, now, now),
        )
        return sid

    def get(self, session_id: str) -> SessionMeta:
        row = self._con.execute(
            "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No session with id {session_id!r}")
        return SessionMeta(id=row[0], title=row[1], created_at=row[2], updated_at=row[3])

    def list_recent(self, limit: int = 20) -> list[SessionMeta]:
        # Tie-break by created_at DESC (and id DESC for fully-identical
        # timestamps) so that sessions created in the same nanosecond
        # still come back in a deterministic, most-recent-first order.
        rows = self._con.execute(
            "SELECT id, title, created_at, updated_at FROM sessions "
            "ORDER BY updated_at DESC, created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            SessionMeta(id=r[0], title=r[1], created_at=r[2], updated_at=r[3])
            for r in rows
        ]

    def append_message(self, session_id: str, msg: dict[str, Any]) -> None:
        # seq: max + 1 (or 1 if empty)
        row = self._con.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        seq = row[0]
        content_str = json.dumps(msg.get("content", ""), ensure_ascii=False)
        self._con.execute(
            "INSERT INTO messages (session_id, seq, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, seq, msg["role"], content_str, time.time()),
        )
        self._con.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (time.time(), session_id),
        )

    def load_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._con.execute(
            "SELECT seq, role, content FROM messages WHERE session_id = ? ORDER BY seq ASC",
            (session_id,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for _seq, role, content_str in rows:
            content = json.loads(content_str)
            out.append({"role": role, "content": content})
        return out

    def close(self) -> None:
        self._con.close()
