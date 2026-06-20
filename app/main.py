from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import models, rounds as rounds_mod, scoring
from app.db import connect, init_db
from app.serializers import host_question, public_question


class QuestionIn(BaseModel):
    author: str
    category: str
    text: str
    answer: str = ""
    acceptable: Optional[list] = None


class TeamIn(BaseModel):
    name: str


class PhaseIn(BaseModel):
    phase: str
    round_id: Optional[int] = None


class PauseIn(BaseModel):
    paused: bool


def create_app(db_path: Optional[str] = None) -> FastAPI:
    db_path = db_path or os.environ.get("TRIVIA_DB", "trivia.db")
    app = FastAPI(title="Sum Beach Trivia")

    # FastAPI runs sync route handlers in a thread pool, so we need
    # check_same_thread=False for all connections (both file-backed and :memory:).
    conn = connect(db_path, check_same_thread=False)
    app.state.conn = conn

    init_db(conn)
    if models.get_game(conn) is None:
        code = models.gen_code()
        host_key = models.gen_recovery()
        models.create_game(conn, code=code, host_key=host_key)
        print(f"[sum-beach-trivia] game code={code}  HOST KEY={host_key}")

    def db():
        return app.state.conn

    def require_host(host_key: str):
        g = models.get_game(db())
        if g is None or host_key != g["host_key"]:
            raise HTTPException(status_code=403, detail="bad host key")
        return g

    @app.post("/api/teams")
    def create_team(t: TeamIn):
        try:
            return models.join_team(db(), t.name)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @app.get("/api/teams")
    def list_teams():
        rows = db().execute("SELECT id, name FROM team ORDER BY id").fetchall()
        return {"teams": [{"id": r["id"], "name": r["name"]} for r in rows]}

    @app.get("/api/teams/recover")
    def recover_team(recovery_code: str):
        row = models.team_by_recovery(db(), recovery_code)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown recovery code")
        return {"team_id": row["id"], "name": row["name"]}

    @app.get("/api/leaderboard")
    def leaderboard():
        return {"teams": scoring.team_totals(db())}

    @app.get("/api/categories")
    def categories():
        rows = db().execute("SELECT name FROM category ORDER BY display_order")
        return {"categories": [r["name"] for r in rows]}

    @app.post("/api/questions")
    def add_question(q: QuestionIn):
        g = models.get_game(db())
        if g["phase"] != "draft":
            raise HTTPException(status_code=409, detail="game already started")
        try:
            qid = models.add_question(db(), q.author, q.category, q.text, q.answer, q.acceptable)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"id": qid}

    @app.get("/api/questions/mine")
    def my_questions(author: str):
        rows = db().execute(
            "SELECT * FROM question WHERE author_name = ? ORDER BY id", (author,)
        ).fetchall()
        return {"questions": [public_question(r) for r in rows]}

    @app.get("/api/questions")
    def all_questions(host_key: str):
        require_host(host_key)
        rows = db().execute("SELECT * FROM question ORDER BY id").fetchall()
        return {"questions": [host_question(r) for r in rows]}

    VALID_PHASES = {
        "draft", "lobby", "round_open", "round_closed", "marking", "reveal",
        "final_wager", "final_open", "tiebreak", "done", "paused",
    }

    def _round_public(round_id: int) -> dict | None:
        r = db().execute("SELECT * FROM round WHERE id = ?", (round_id,)).fetchone()
        if r is None:
            return None
        qs = db().execute(
            "SELECT * FROM question WHERE round_id = ? ORDER BY display_order", (round_id,)
        ).fetchall()
        return {
            "id": r["id"], "title": r["title"], "is_final": bool(r["is_final"]),
            "wager_cap": r["wager_cap"],
            "questions": [public_question(q) for q in qs],
        }

    @app.post("/api/host/build-rounds")
    def build(host_key: str):
        require_host(host_key)
        rs = rounds_mod.build_rounds(db())
        return {"rounds": rs, "warnings": rounds_mod.imbalance_warnings(db())}

    @app.post("/api/host/phase")
    def set_phase_route(body: PhaseIn, host_key: str):
        require_host(host_key)
        if body.phase not in VALID_PHASES:
            raise HTTPException(status_code=400, detail="unknown phase")
        models.set_phase(db(), body.phase)
        if body.round_id is not None:
            models.set_current_round(db(), body.round_id)
        return {"ok": True}

    @app.post("/api/host/pause")
    def pause_route(body: PauseIn, host_key: str):
        require_host(host_key)
        models.set_paused(db(), body.paused)
        return {"ok": True}

    @app.get("/api/state")
    def state():
        g = models.get_game(db())
        cur = _round_public(g["current_round_id"]) if g["current_round_id"] else None
        return {"phase": g["phase"], "paused": bool(g["paused"]), "current_round": cur}

    return app


app = create_app()
