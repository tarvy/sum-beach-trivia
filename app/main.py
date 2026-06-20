from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import models, rounds as rounds_mod, scoring
from app.db import connect, init_db
from app.serializers import host_question, public_question

UPLOAD_DIR = pathlib.Path(os.environ.get("TRIVIA_UPLOADS", "uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)


class MarkIn(BaseModel):
    team_id: int
    question_id: int
    is_correct: Optional[bool] = None
    score: Optional[float] = None
    items_correct: Optional[int] = None


class AlternateIn(BaseModel):
    question_id: int
    alternate: str


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

    SUBMIT_PHASES = {"round_open", "final_open"}

    def _grade(image_bytes, media_type, questions):
        grader = getattr(app.state, "grading_client", None)
        if grader is not None:
            return grader.grade(image_bytes, media_type, questions)
        from app import grading
        return grading.grade_sheet(image_bytes, media_type, questions)

    @app.post("/api/submit")
    async def submit(team_id: int = Form(...), round_id: int = Form(...),
                     photo: UploadFile = File(...)):
        g = models.get_game(db())
        if g["phase"] not in SUBMIT_PHASES or g["current_round_id"] != round_id:
            raise HTTPException(status_code=409, detail="submissions closed for this round")
        data = await photo.read()
        ext = (photo.filename or "sheet.png").rsplit(".", 1)[-1]
        fname = f"team{team_id}_round{round_id}.{ext}"
        (UPLOAD_DIR / fname).write_bytes(data)
        db().execute(
            "INSERT INTO submission (team_id, round_id, photo_path) VALUES (?, ?, ?) "
            "ON CONFLICT(team_id, round_id) DO UPDATE SET photo_path=excluded.photo_path, "
            "submitted_at=datetime('now')",
            (team_id, round_id, fname))
        db().commit()

        rows = db().execute(
            "SELECT * FROM question WHERE round_id = ? ORDER BY display_order", (round_id,)
        ).fetchall()
        questions = [host_question(r) for r in rows]
        qpayload = [{"id": q["id"], "text": q["text"], "answer": q["answer"],
                     "acceptable": q["acceptable_answers"], "answer_items": q["answer_items"],
                     "ordered": q["ordered"]} for q in questions]
        result = _grade(data, photo.content_type or "image/png", qpayload)

        by_id = {q["id"]: q for q in questions}
        for gr in result.grades:
            q = by_id.get(gr.question_id)
            if q is None:
                continue
            score = q["point_value"] if gr.is_correct else 0
            db().execute(
                "INSERT INTO mark (team_id, question_id, transcription, is_correct, score, "
                "items_correct, confidence, flagged) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(team_id, question_id) DO UPDATE SET transcription=excluded.transcription, "
                "is_correct=excluded.is_correct, score=excluded.score, items_correct=excluded.items_correct, "
                "confidence=excluded.confidence, flagged=excluded.flagged "
                "WHERE manually_corrected = 0",
                (team_id, gr.question_id, gr.transcription, int(gr.is_correct), score,
                 gr.items_correct, gr.confidence, int(gr.confidence < 0.5)))
        db().commit()
        return {"ok": True}

    @app.get("/api/host/marks")
    def host_marks(host_key: str, round_id: int):
        require_host(host_key)
        teams = db().execute("SELECT id, name FROM team ORDER BY id").fetchall()
        qids = [r["id"] for r in db().execute(
            "SELECT id FROM question WHERE round_id = ?", (round_id,))]
        out = []
        for t in teams:
            sub = db().execute(
                "SELECT photo_path FROM submission WHERE team_id=? AND round_id=?",
                (t["id"], round_id)).fetchone()
            marks = []
            for qid in qids:
                m = db().execute(
                    "SELECT * FROM mark WHERE team_id=? AND question_id=?",
                    (t["id"], qid)).fetchone()
                marks.append({
                    "question_id": qid,
                    "transcription": m["transcription"] if m else "",
                    "is_correct": bool(m["is_correct"]) if m else False,
                    "score": m["score"] if m else 0,
                    "items_correct": m["items_correct"] if m else None,
                    "flagged": bool(m["flagged"]) if m else False,
                    "submitted": sub is not None,
                })
            out.append({"team_id": t["id"], "name": t["name"],
                        "photo_url": f"/uploads/{sub['photo_path']}" if sub else None,
                        "marks": marks})
        return {"teams": out}

    @app.post("/api/host/mark")
    def host_mark(body: MarkIn, host_key: str):
        require_host(host_key)
        existing = db().execute(
            "SELECT * FROM mark WHERE team_id=? AND question_id=?",
            (body.team_id, body.question_id)).fetchone()
        is_correct = body.is_correct if body.is_correct is not None else (
            bool(existing["is_correct"]) if existing else False)
        score = body.score if body.score is not None else (
            existing["score"] if existing else 0)
        db().execute(
            "INSERT INTO mark (team_id, question_id, is_correct, score, items_correct, "
            "manually_corrected) VALUES (?, ?, ?, ?, ?, 1) "
            "ON CONFLICT(team_id, question_id) DO UPDATE SET is_correct=?, score=?, "
            "items_correct=COALESCE(?, items_correct), manually_corrected=1",
            (body.team_id, body.question_id, int(is_correct), score, body.items_correct,
             int(is_correct), score, body.items_correct))
        db().commit()
        return {"ok": True}

    @app.post("/api/host/add-alternate")
    def add_alternate(body: AlternateIn, host_key: str):
        require_host(host_key)
        row = db().execute("SELECT acceptable_answers FROM question WHERE id=?",
                           (body.question_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no such question")
        acc = json.loads(row["acceptable_answers"])
        if body.alternate not in acc:
            acc.append(body.alternate)
        db().execute("UPDATE question SET acceptable_answers=? WHERE id=?",
                     (json.dumps(acc), body.question_id))
        db().commit()
        return {"ok": True}

    app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

    return app


app = create_app()
