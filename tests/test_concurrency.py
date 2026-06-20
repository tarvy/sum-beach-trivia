"""Regression tests for the SQLite-across-threads crash.

A single shared sqlite3 connection used from multiple FastAPI thread-pool
threads corrupts memory and crashes the process (SIGBUS). Each thread must get
its own connection for a file-backed db.
"""
import asyncio
import threading

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


def test_file_db_connection_is_per_thread(tmp_path):
    app = create_app(db_path=str(tmp_path / "t.db"))
    get_conn = app.state.get_conn

    # same thread → same connection
    main_conn = get_conn()
    assert get_conn() is main_conn

    # different threads → different connections. Keep the connection objects
    # alive (store the object, not id()) and hold both threads at a barrier so
    # their addresses can't be reused — otherwise a dead thread's freed conn
    # address could be recycled and look identical.
    conns = {}
    barrier = threading.Barrier(2)

    def grab(key):
        c = get_conn()
        barrier.wait()
        conns[key] = c

    t1 = threading.Thread(target=grab, args=("t1",))
    t2 = threading.Thread(target=grab, args=("t2",))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert conns["t1"] is not conns["t2"]
    assert conns["t1"] is not main_conn
    assert conns["t2"] is not main_conn


def test_memory_db_uses_one_shared_connection():
    app = create_app(db_path=":memory:")
    get_conn = app.state.get_conn
    # in-memory db only exists on one connection, so it must be shared
    assert id(get_conn()) == id(get_conn()) == id(app.state.shared_conn)


@pytest.mark.anyio
async def test_concurrent_requests_do_not_crash(tmp_path):
    # Exercises the exact failure mode: many simultaneous requests against a
    # file-backed db, each handled on its own thread-pool thread.
    app = create_app(db_path=str(tmp_path / "game.db"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.post("/api/teams", json={"name": "Aces"})
        results = await asyncio.gather(
            *[c.get("/api/leaderboard") for _ in range(40)],
            *[c.get("/api/state") for _ in range(40)],
        )
    assert all(r.status_code == 200 for r in results)
    assert any(r.json().get("teams") for r in results if "teams" in r.json())
