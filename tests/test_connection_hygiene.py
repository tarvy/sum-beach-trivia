"""A failed write must never leave a connection holding an open transaction.

Regression for the live-game lockup (2026-07-02 beta test): a duplicate team
name 409'd, the failed INSERT's implicit transaction was never rolled back,
and that thread-local connection held the write lock — every host action
afterward 500'd with "database is locked".
"""
import sqlite3

import pytest

from app import models
from app.db import connect, init_db


@pytest.fixture
def file_db(tmp_path):
    path = str(tmp_path / "t.db")
    conn = connect(path, check_same_thread=False)
    init_db(conn)
    models.create_game(conn, code="TEST", host_key="hk")
    yield path, conn
    conn.close()


def test_duplicate_team_join_leaves_no_open_transaction(file_db):
    path, conn = file_db
    models.join_team(conn, "The Regulars")
    with pytest.raises(ValueError):
        models.join_team(conn, "The Regulars")  # duplicate → must roll back
    assert not conn.in_transaction  # the poison this regression guards against


def test_other_connections_can_write_after_failed_join(file_db):
    path, conn = file_db
    models.join_team(conn, "The Regulars")
    with pytest.raises(ValueError):
        models.join_team(conn, "The Regulars")

    # a second connection (= another request thread) must be able to write
    # immediately — this hung for 5s then raised "database is locked" before
    other = connect(path, check_same_thread=False)
    other.execute("PRAGMA busy_timeout = 200")  # fail fast if the lock leaked
    models.set_phase(other, "lobby")
    assert other.execute("SELECT phase FROM game").fetchone()["phase"] == "lobby"
    other.close()


def test_stale_team_member_add_leaves_no_open_transaction(file_db):
    path, conn = file_db
    with pytest.raises(ValueError):
        models.add_team_member(conn, team_id=9999, name="Ghost")  # FK violation
    assert not conn.in_transaction
