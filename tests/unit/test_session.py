from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from miniagent.session import AsyncSessionStore, CorruptSessionError, SessionStore


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions.db")


def test_init_creates_schema(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    SessionStore(db)
    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    assert ("messages",) in rows
    assert ("sessions",) in rows
    con.close()


def test_create_returns_uuid(store: SessionStore) -> None:
    sid = store.create()
    assert isinstance(sid, str)
    assert len(sid) == 36  # UUID4


def test_get_returns_metadata(store: SessionStore) -> None:
    sid = store.create()
    meta = store.get(sid)
    assert meta.id == sid
    assert meta.title is None
    assert meta.created_at > 0


def test_get_missing_raises(store: SessionStore) -> None:
    with pytest.raises(KeyError):
        store.get("nonexistent")


def test_list_recent_orders_by_updated(store: SessionStore) -> None:
    s1 = store.create()
    s2 = store.create()
    s3 = store.create()
    recents = store.list_recent(limit=10)
    assert [r.id for r in recents[:3]] == [s3, s2, s1]


def test_append_and_load_messages_roundtrip(store: SessionStore) -> None:
    sid = store.create()
    store.append_message(sid, {"role": "user", "content": "hi"})
    store.append_message(sid, {"role": "assistant", "content": "hello"})
    msgs = store.load_messages(sid)
    assert msgs == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_append_message_sync_writes_immediately(store: SessionStore) -> None:
    """append_message is sync and must persist before returning (not queue-only)."""
    sid = store.create()
    store.append_message(sid, {"role": "user", "content": "x"})
    # Open a new connection → verify the row is there
    fresh = SessionStore(store.db_path)
    msgs = fresh.load_messages(sid)
    assert len(msgs) == 1


def test_corrupt_db_raises(tmp_path: Path) -> None:
    db = tmp_path / "broken.db"
    db.write_text("not a sqlite database at all")
    with pytest.raises(CorruptSessionError):
        SessionStore(db)


# ---------------------------------------------------------------------------
# Task 8b: AsyncSessionStore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_store_does_not_block(tmp_path: Path) -> None:
    sync = SessionStore(tmp_path / "s.db")
    sid = sync.create()
    async_store = AsyncSessionStore(sync)

    t0 = asyncio.get_event_loop().time()
    for i in range(100):
        async_store.append_message(sid, {"role": "user", "content": f"msg-{i}"})
    elapsed = asyncio.get_event_loop().time() - t0
    # 100 sync appends to an in-memory queue should take < 50ms
    assert elapsed < 0.05, f"append_message blocked for {elapsed:.3f}s"

    # Flush and verify all messages persisted
    await async_store.close()
    fresh = SessionStore(tmp_path / "s.db")
    msgs = fresh.load_messages(sid)
    assert len(msgs) == 100
    assert msgs[0]["content"] == "msg-0"
    assert msgs[-1]["content"] == "msg-99"
    fresh.close()


@pytest.mark.asyncio
async def test_async_store_close_drains_queue(tmp_path: Path) -> None:
    sync = SessionStore(tmp_path / "s.db")
    sid = sync.create()
    async_store = AsyncSessionStore(sync)
    async_store.append_message(sid, {"role": "user", "content": "x"})
    # close() must block until the queue is fully drained
    await async_store.close()
    fresh = SessionStore(tmp_path / "s.db")
    msgs = fresh.load_messages(sid)
    assert len(msgs) == 1
    fresh.close()
