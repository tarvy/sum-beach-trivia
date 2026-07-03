from __future__ import annotations

import csv
import io
import json
import os
import pathlib
import re
import sqlite3
import threading
import time
from typing import Optional

import segno
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import final_options, models, rounds as rounds_mod, scoring
from app.db import connect, init_db
from app.serializers import host_question, public_question

UPLOAD_DIR = pathlib.Path(os.environ.get("TRIVIA_UPLOADS", "uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)

# The display passes its own browser origin (the public sprite URL it was loaded
# from), so the QR points phones at the exact same address. Validated to keep
# arbitrary strings out of the generated code.
_ORIGIN_RE = re.compile(r"^https?://[^/\s]+$")


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
    contributor_id: Optional[int] = None


class QuestionEditIn(BaseModel):
    contributor_id: int
    category: str
    text: str
    answer: str = ""
    acceptable: Optional[list] = None


class QuestionSetItem(BaseModel):
    category: str
    text: str
    answer: str = ""
    acceptable: Optional[list] = None


class QuestionSetIn(BaseModel):
    contributor_id: int
    author: str
    questions: list[QuestionSetItem]


class BankQuestionIn(BaseModel):
    category: str
    text: str
    answer: str
    acceptable: Optional[list] = None


class SubmissionsIn(BaseModel):
    open: bool


class ContributorIn(BaseModel):
    token: str
    name: str


class TeamIn(BaseModel):
    name: str


class PhaseIn(BaseModel):
    phase: str
    round_id: Optional[int] = None


class PauseIn(BaseModel):
    paused: bool


class McModeIn(BaseModel):
    mode: str


class QuestionNavIn(BaseModel):
    action: str  # 'next' | 'prev'


class SettingsIn(BaseModel):
    questions_per_person: Optional[int] = None
    question_seconds: Optional[int] = None


class FinalIn(BaseModel):
    # no wager cap — teams bet whatever they dare (clients sending a legacy
    # wager_cap key are ignored harmlessly by pydantic)
    text: str
    items: list[str]
    ordered: bool = False


class WagerIn(BaseModel):
    team_id: int
    round_id: int
    amount: int


class TiebreakIn(BaseModel):
    question: str
    value: float


def create_app(db_path: Optional[str] = None) -> FastAPI:
    db_path = db_path or os.environ.get("TRIVIA_DB", "trivia.db")
    app = FastAPI(title="Sum Beach Trivia")
    app.state.db_path = db_path
    # Changes on every deploy/restart. The display (an unattended TV tab that
    # otherwise never reloads its HTML) watches this and reloads itself when
    # it changes, so it can't keep rendering a stale page after a deploy.
    app.state.boot = int(time.time())

    # FastAPI runs each sync route handler on a thread-pool thread. A single SQLite
    # connection MUST NOT be shared across threads — concurrent use corrupts memory
    # and crashes the process. So every thread gets its own connection (thread-local).
    # Exception: an in-memory ":memory:" db only exists for the lifetime of one
    # connection, so tests that use it share a single connection (they run requests
    # sequentially, so there is no concurrency).
    is_memory = db_path == ":memory:"
    app.state.is_memory = is_memory

    init_conn = connect(db_path, check_same_thread=False)
    init_db(init_conn)
    if is_memory:
        app.state.shared_conn = init_conn
    else:
        init_conn.close()
        app.state.shared_conn = None

    _local = threading.local()

    def db():
        if is_memory:
            return app.state.shared_conn
        conn = getattr(_local, "conn", None)
        if conn is None:
            conn = _local.conn = connect(db_path, check_same_thread=False)
        return conn

    # exposed for tests/diagnostics
    app.state.get_conn = db
    # Back-compat alias: tests read the host key via app.state.conn. This is the
    # connection for whatever thread create_app runs on (the main thread); it's
    # safe for test reads. Production routes never touch it — they use db().
    app.state.conn = db()

    if models.get_game(db()) is None:
        code = models.gen_code()
        host_key = models.gen_recovery()
        models.create_game(db(), code=code, host_key=host_key)
        print(f"[sum-beach-trivia] game code={code}  HOST KEY={host_key}", flush=True)

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

    @app.post("/api/contributor")
    def resolve_contributor(c: ContributorIn):
        try:
            return models.resolve_contributor(db(), c.token, c.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/contributor/recover")
    def recover_contributor(recovery_code: str):
        row = models.contributor_by_recovery(db(), recovery_code)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown recovery code")
        return {"contributor_id": row["id"], "name": row["name"], "token": row["token"]}

    @app.get("/api/authors")
    def list_authors():
        # One row per contributing person (host's final-round author excluded).
        rows = db().execute(
            "SELECT id, name FROM contributor ORDER BY id"
        ).fetchall()
        return {"authors": [{"contributor_id": r["id"], "name": r["name"]} for r in rows]}

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
        if not g["submissions_open"]:
            raise HTTPException(status_code=409, detail="submissions are closed")
        try:
            qid = models.add_question(db(), q.author, q.category, q.text, q.answer,
                                      q.acceptable, q.contributor_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"id": qid}

    @app.post("/api/questions/set")
    def submit_set(body: QuestionSetIn):
        g = models.get_game(db())
        if not g["submissions_open"]:
            raise HTTPException(status_code=409, detail="submissions are closed")
        try:
            ids = models.submit_question_set(
                db(), body.contributor_id, body.author,
                [q.model_dump() for q in body.questions])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ids": ids}

    @app.put("/api/questions/{question_id}")
    def edit_question(question_id: int, q: QuestionEditIn):
        # Trust boundary: open/closed and ownership are enforced here, not in the UI.
        g = models.get_game(db())
        if not g["submissions_open"]:
            raise HTTPException(status_code=409, detail="submissions are closed")
        try:
            ok = models.update_question(db(), question_id, q.contributor_id,
                                        q.category, q.text, q.answer, q.acceptable)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not ok:
            raise HTTPException(status_code=404, detail="not your question")
        return {"ok": True}

    @app.get("/api/questions/mine")
    def my_questions(contributor_id: Optional[int] = None, author: Optional[str] = None):
        # contributor_id is the identity key; author kept for back-compat.
        if contributor_id is not None:
            rows = db().execute(
                "SELECT * FROM question WHERE contributor_id = ? ORDER BY id", (contributor_id,)
            ).fetchall()
        elif author is not None:
            rows = db().execute(
                "SELECT * FROM question WHERE author_name = ? ORDER BY id", (author,)
            ).fetchall()
        else:
            raise HTTPException(status_code=400, detail="contributor_id or author required")
        # Owner-facing: include category name + answer/acceptable so the contributor
        # can review and edit their OWN set. (public_question omits answers for display.)
        cats = {r["id"]: r["name"] for r in db().execute("SELECT id, name FROM category")}
        return {"questions": [{
            "id": r["id"], "text": r["text"], "answer": r["answer"],
            "acceptable": json.loads(r["acceptable_answers"]),
            "category": cats.get(r["category_id"]),
        } for r in rows]}

    @app.get("/api/questions")
    def all_questions(host_key: str):
        require_host(host_key)
        rows = db().execute("SELECT * FROM question ORDER BY id").fetchall()
        cats = {r["id"]: r["name"] for r in db().execute("SELECT id, name FROM category")}
        return {"questions": [
            host_question(r) | {"category": cats.get(r["category_id"])} for r in rows]}

    @app.post("/api/host/bank-question")
    def add_bank_question(q: BankQuestionIn, host_key: str):
        # The host (MC) adds her own questions to the pool — as host, not as a
        # player. They join the per-category pools like everyone else's.
        require_host(host_key)
        try:
            qid = models.add_question(db(), "host", q.category, q.text, q.answer,
                                      q.acceptable, contributor_id=None, source="host")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"id": qid}

    @app.delete("/api/host/questions/{question_id}")
    def delete_question(question_id: int, host_key: str):
        require_host(host_key)
        row = db().execute("SELECT round_id FROM question WHERE id = ?",
                           (question_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no such question")
        if row["round_id"] is not None:
            raise HTTPException(status_code=409, detail="question is assigned to a round")
        try:
            db().execute("DELETE FROM question WHERE id = ?", (question_id,))
        except sqlite3.Error:
            db().rollback()  # e.g. a mark references it — don't poison the connection
            raise HTTPException(status_code=409, detail="question is referenced by marks")
        db().commit()
        return {"ok": True}

    VALID_PHASES = {
        "draft", "lobby", "round_open", "round_closed", "marking", "reveal",
        "final_wager", "final_open", "tiebreak", "done", "paused",
    }

    def _round_public(round_id: int, reveal: bool = False, upto: int | None = None) -> dict | None:
        r = db().execute("SELECT * FROM round WHERE id = ?", (round_id,)).fetchone()
        if r is None:
            return None
        qs = db().execute(
            "SELECT * FROM question WHERE round_id = ? ORDER BY display_order", (round_id,)
        ).fetchall()
        total = len(qs)
        # One-question-at-a-time anti-spoiler: while a round is live, clients only
        # ever receive questions up to the current cursor — future questions must
        # not reach the player/display payload at all.
        if upto is not None:
            qs = qs[:upto + 1]
        out = []
        for q in qs:
            pq = public_question(q)
            # Author is a spoiler during play — only attach it at reveal.
            if reveal:
                pq["author_name"] = q["author_name"]
            out.append(pq)
        # Round position among the non-final rounds (the display's "Round 2 of 4"
        # + the standings ticker shows only after round 1). Final → number None.
        nf = [row["id"] for row in db().execute(
            "SELECT id FROM round WHERE is_final = 0 ORDER BY display_order").fetchall()]
        return {
            "id": r["id"], "title": r["title"], "is_final": bool(r["is_final"]),
            "wager_cap": r["wager_cap"], "questions": out,
            "question_count": total,
            "round_number": (nf.index(r["id"]) + 1) if r["id"] in nf else None,
            "round_count": len(nf),
        }

    @app.post("/api/host/build-rounds")
    def build(host_key: str):
        require_host(host_key)
        rs = rounds_mod.build_rounds(db())
        return {"rounds": rs, "warnings": rounds_mod.imbalance_warnings(db())}

    @app.get("/api/host/rounds")
    def list_rounds(host_key: str):
        require_host(host_key)
        rows = db().execute(
            "SELECT r.id, r.title, r.is_final, r.wager_cap, "
            "COUNT(q.id) AS question_count "
            "FROM round r LEFT JOIN question q ON q.round_id = r.id "
            "GROUP BY r.id ORDER BY r.display_order"
        ).fetchall()
        return {"rounds": [
            {
                "id": row["id"],
                "title": row["title"],
                "is_final": bool(row["is_final"]),
                "wager_cap": row["wager_cap"],
                "question_count": row["question_count"],
            }
            for row in rows
        ]}

    @app.post("/api/host/phase")
    def set_phase_route(body: PhaseIn, host_key: str):
        require_host(host_key)
        if body.phase not in VALID_PHASES:
            raise HTTPException(status_code=400, detail="unknown phase")
        models.set_phase(db(), body.phase)
        if body.round_id is not None:
            models.set_current_round(db(), body.round_id)
        if body.phase in ("round_open", "final_open"):
            # a round going live starts at question 1 with a fresh timer
            db().execute("UPDATE game SET current_question_idx = 0, "
                         "question_opened_at = datetime('now') WHERE id = 1")
            db().commit()
        return {"ok": True}

    @app.post("/api/host/question")
    def question_nav(body: QuestionNavIn, host_key: str):
        # Lacey drives: advance (or loosely step back) the live question.
        g = require_host(host_key)
        if g["phase"] != "round_open" or not g["current_round_id"]:
            raise HTTPException(status_code=409, detail="no live round")
        if body.action not in ("next", "prev"):
            raise HTTPException(status_code=400, detail="action must be next or prev")
        (total,) = db().execute("SELECT COUNT(*) FROM question WHERE round_id = ?",
                                (g["current_round_id"],)).fetchone()
        idx = g["current_question_idx"] + (1 if body.action == "next" else -1)
        idx = max(0, min(idx, max(total - 1, 0)))
        db().execute("UPDATE game SET current_question_idx = ?, "
                     "question_opened_at = datetime('now') WHERE id = 1", (idx,))
        db().commit()
        return {"question_idx": idx}

    @app.post("/api/host/pause")
    def pause_route(body: PauseIn, host_key: str):
        require_host(host_key)
        models.set_paused(db(), body.paused)
        return {"ok": True}

    @app.post("/api/host/mc-mode")
    def set_mc_mode_route(body: McModeIn, host_key: str):
        # Switchable at ANY phase — if the AI misbehaves mid-game, Lacey takes over
        # (and vice versa). Only affects how FUTURE submissions are graded.
        require_host(host_key)
        try:
            models.set_mc_mode(db(), body.mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"mc_mode": body.mode}

    @app.post("/api/host/settings")
    def set_settings(body: SettingsIn, host_key: str):
        # All settings are adjustable mid-game; keep-N takes effect at the next
        # round build, the timer at the next question.
        require_host(host_key)
        try:
            if body.questions_per_person is not None:
                models.set_questions_per_person(db(), body.questions_per_person)
            if body.question_seconds is not None:
                models.set_question_seconds(db(), body.question_seconds)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.post("/api/host/submissions")
    def set_submissions(body: SubmissionsIn, host_key: str):
        require_host(host_key)
        models.set_submissions_open(db(), body.open)
        return {"submissions_open": body.open}

    @app.get("/api/qr")
    def qr(origin: str = "", request: Request = None):
        # Prefer the display's reported origin (the public sprite URL it loaded
        # from); fall back to the request host so a bare /api/qr still works.
        base = origin if _ORIGIN_RE.match(origin) else f"{request.url.scheme}://{request.headers['host']}"
        url = f"{base.rstrip('/')}/play.html"
        buf = io.BytesIO()
        segno.make(url, error="m").save(buf, kind="svg", scale=8, border=2)
        return Response(buf.getvalue(), media_type="image/svg+xml",
                        headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    def state():
        g = models.get_game(db())
        # While a normal round is live, only expose questions up to the cursor.
        upto = g["current_question_idx"] if g["phase"] in ("round_open", "round_closed") else None
        cur = _round_public(g["current_round_id"], reveal=g["phase"] == "reveal", upto=upto) \
            if g["current_round_id"] else None
        elapsed = None
        if g["question_opened_at"]:
            (elapsed,) = db().execute(
                "SELECT CAST(strftime('%s','now') - strftime('%s', question_opened_at) "
                "AS INTEGER) FROM game WHERE id = 1").fetchone()
        # Tiebreak QUESTION text is public once the tiebreak starts (the display
        # shows it); the tiebreak VALUE is the answer and stays host-only.
        return {"phase": g["phase"], "paused": bool(g["paused"]),
                "boot": app.state.boot,
                "submissions_open": bool(g["submissions_open"]),
                "mc_mode": g["mc_mode"],
                "questions_per_person": g["questions_per_person"],
                "question_idx": g["current_question_idx"],
                "question_seconds": g["question_seconds"],
                "question_elapsed": elapsed,
                "current_round": cur,
                "tiebreak_question": g["tiebreak_question"] if g["phase"] == "tiebreak" else None}

    # round_closed included on purpose: "pens down" stops writing, but teams still
    # need a window to photograph + hand in the sheet they already wrote. The
    # window truly shuts when the host moves to marking.
    SUBMIT_PHASES = {"round_open", "round_closed", "final_open"}

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
        raw_ext = (photo.filename or "sheet.png").rsplit(".", 1)[-1]
        ext = re.sub(r"[^a-zA-Z0-9]", "", raw_ext)[:5].lower() or "bin"
        fname = f"team{team_id}_round{round_id}.{ext}"
        (UPLOAD_DIR / fname).write_bytes(data)
        try:
            db().execute(
                "INSERT INTO submission (team_id, round_id, photo_path) VALUES (?, ?, ?) "
                "ON CONFLICT(team_id, round_id) DO UPDATE SET photo_path=excluded.photo_path, "
                "submitted_at=datetime('now')",
                (team_id, round_id, fname))
        except sqlite3.IntegrityError:
            db().rollback()  # stale team id from a previous game's localStorage
            raise HTTPException(status_code=404, detail="unknown team")
        db().commit()

        # Lacey in Charge mode: the photo is kept as the team's handed-in sheet,
        # but a human MC does all the marking — no AI call.
        if g["mc_mode"] == "lacey":
            return {"ok": True, "graded": False}

        # Gladys mode: AI-grade the sheet. A grading failure must NEVER lose the
        # submission — the photo is already saved, so the MC can mark it by hand
        # from the marking grid.
        rows = db().execute(
            "SELECT * FROM question WHERE round_id = ? ORDER BY display_order", (round_id,)
        ).fetchall()
        questions = [host_question(r) for r in rows]
        qpayload = [{"id": q["id"], "text": q["text"], "answer": q["answer"],
                     "acceptable": q["acceptable_answers"], "answer_items": q["answer_items"],
                     "ordered": q["ordered"]} for q in questions]
        try:
            result = _grade(data, photo.content_type or "image/png", qpayload)
        except Exception:
            return {"ok": True, "graded": False}

        by_id = {q["id"]: q for q in questions}
        try:
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
        except sqlite3.Error:
            db().rollback()  # bad AI output must not poison the connection; MC marks by hand
            return {"ok": True, "graded": False}
        return {"ok": True, "graded": True}

    @app.get("/api/host/marks")
    def host_marks(host_key: str, round_id: int):
        require_host(host_key)
        teams = db().execute("SELECT id, name FROM team ORDER BY id").fetchall()
        qrows = db().execute(
            "SELECT id, author_name FROM question WHERE round_id = ?", (round_id,)).fetchall()
        qids = [r["id"] for r in qrows]
        authors = {r["id"]: r["author_name"] for r in qrows}
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
                    "author_name": authors.get(qid),
                    # "marked": a mark row exists. Lets the MC console tell
                    # "not marked yet" apart from "marked wrong" (both default
                    # is_correct=false in this payload).
                    "marked": m is not None,
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
        try:
            db().execute(
                "INSERT INTO mark (team_id, question_id, is_correct, score, items_correct, "
                "manually_corrected) VALUES (?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(team_id, question_id) DO UPDATE SET is_correct=?, score=?, "
                "items_correct=COALESCE(?, items_correct), manually_corrected=1",
                (body.team_id, body.question_id, int(is_correct), score, body.items_correct,
                 int(is_correct), score, body.items_correct))
        except sqlite3.IntegrityError:
            db().rollback()  # unknown team/question id — don't poison the connection
            raise HTTPException(status_code=404, detail="unknown team or question")
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

    # Curated pick-lists (app/final_options.py). The list payloads hide the
    # answers (items/values) so the person setting up can pick blind and still
    # play; ?id=N returns the full option for the actual POST.
    @app.get("/api/host/final-options")
    def get_final_options(host_key: str, id: Optional[int] = None):
        require_host(host_key)
        opts = final_options.FINAL_OPTIONS
        if id is None:
            return {"options": [
                {"id": i, "text": o["text"], "ordered": o["ordered"],
                 "item_count": len(o["items"])}
                for i, o in enumerate(opts)]}
        if not 0 <= id < len(opts):
            raise HTTPException(status_code=404, detail="no such option")
        return {"id": id, **opts[id]}

    @app.get("/api/host/tiebreak-options")
    def get_tiebreak_options(host_key: str, id: Optional[int] = None):
        require_host(host_key)
        opts = final_options.TIEBREAK_OPTIONS
        if id is None:
            return {"options": [{"id": i, "question": o["question"]}
                                for i, o in enumerate(opts)]}
        if not 0 <= id < len(opts):
            raise HTTPException(status_code=404, detail="no such option")
        return {"id": id, **opts[id]}

    @app.post("/api/host/final")
    def create_final(body: FinalIn, host_key: str):
        require_host(host_key)
        (max_order,) = db().execute(
            "SELECT COALESCE(MAX(display_order), -1) FROM round").fetchone()
        cur = db().execute(
            "INSERT INTO round (title, display_order, is_final, wager_cap, bonus_multiplier) "
            "VALUES ('Final Round', ?, 1, NULL, 1)", (max_order + 1,))
        rid = cur.lastrowid
        db().execute(
            "INSERT INTO question (author_name, category_id, text, answer_items, ordered, "
            "round_id, point_value, display_order) "
            "VALUES ('host', (SELECT id FROM category ORDER BY display_order LIMIT 1), "
            "?, ?, ?, ?, 0, 0)",
            (body.text, json.dumps(body.items), int(body.ordered), rid))
        db().commit()
        return {"round_id": rid}

    @app.delete("/api/host/final")
    def delete_final(host_key: str):
        # Nothing is set in stone: the host (Lacey) can swap the final at ANY
        # time, even mid-game. Any wagers/marks tied to the old final go with it
        # (the client warns first when they exist). Order matters — clear child
        # rows before the questions/round they reference (foreign_keys is ON).
        require_host(host_key)
        fin = db().execute("SELECT id FROM round WHERE is_final = 1").fetchone()
        if fin is None:
            raise HTTPException(status_code=404, detail="no final round to change")
        rid = fin["id"]
        try:
            db().execute(
                "DELETE FROM mark WHERE question_id IN "
                "(SELECT id FROM question WHERE round_id=?)", (rid,))
            db().execute("DELETE FROM wager WHERE round_id=?", (rid,))
            db().execute("DELETE FROM question WHERE round_id=?", (rid,))
            if models.get_game(db())["current_round_id"] == rid:
                models.set_current_round(db(), None)
            db().execute("DELETE FROM round WHERE id=?", (rid,))
            db().commit()
        except sqlite3.Error:
            db().rollback()
            raise HTTPException(status_code=500, detail="could not clear the final")
        return {"ok": True}

    @app.post("/api/wager")
    def place_wager(body: WagerIn):
        g = models.get_game(db())
        if g["phase"] != "final_wager":
            raise HTTPException(status_code=409, detail="wagering closed")
        round_row = db().execute("SELECT id FROM round WHERE id=?",
                                 (body.round_id,)).fetchone()
        if round_row is None:
            raise HTTPException(status_code=404, detail="no such round")
        amount = max(0, body.amount)  # no cap — bet what you dare
        try:
            db().execute(
                "INSERT INTO wager (team_id, round_id, amount) VALUES (?, ?, ?) "
                "ON CONFLICT(team_id, round_id) DO UPDATE SET amount=excluded.amount",
                (body.team_id, body.round_id, amount))
        except sqlite3.IntegrityError:
            db().rollback()  # stale team id from a previous game's localStorage
            raise HTTPException(status_code=404, detail="unknown team")
        db().commit()
        return {"amount": amount}

    @app.post("/api/host/tiebreak")
    def set_tiebreak(body: TiebreakIn, host_key: str):
        require_host(host_key)
        db().execute("UPDATE game SET tiebreak_question=?, tiebreak_value=? WHERE id=1",
                     (body.question, body.value))
        db().execute("DELETE FROM tiebreak_guess")
        db().commit()
        return {"ok": True}

    @app.post("/api/tiebreak")
    def guess_tiebreak(team_id: int, value: float):
        try:
            db().execute(
                "INSERT INTO tiebreak_guess (team_id, value) VALUES (?, ?) "
                "ON CONFLICT(team_id) DO UPDATE SET value=excluded.value",
                (team_id, value))
        except sqlite3.IntegrityError:
            db().rollback()  # stale team id from a previous game's localStorage
            raise HTTPException(status_code=404, detail="unknown team")
        db().commit()
        return {"ok": True}

    @app.get("/api/host/tiebreak-result")
    def tiebreak_result(host_key: str):
        require_host(host_key)
        g = models.get_game(db())
        target = g["tiebreak_value"]
        rows = db().execute(
            "SELECT tg.team_id, t.name, tg.value FROM tiebreak_guess tg "
            "JOIN team t ON t.id = tg.team_id"
        ).fetchall()
        ranked = sorted(
            ({"team_id": r["team_id"], "name": r["name"], "guess": r["value"],
              "delta": abs(r["value"] - target)} for r in rows),
            key=lambda x: x["delta"])
        return {"target": target, "ranked": ranked}

    @app.get("/api/host/export.csv")
    def export_csv(host_key: str):
        require_host(host_key)
        rounds = db().execute(
            "SELECT id, title FROM round ORDER BY display_order").fetchall()
        totals = {t["team_id"]: t for t in scoring.team_totals(db())}
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["team"] + [r["title"] for r in rounds] + ["total"])
        for t in db().execute("SELECT id, name FROM team ORDER BY name").fetchall():
            row = [t["name"]]
            for r in rounds:
                if db().execute("SELECT is_final FROM round WHERE id=?",
                                (r["id"],)).fetchone()["is_final"]:
                    row.append(scoring._final_total(db(), t["id"], r["id"]))
                else:
                    s = db().execute(
                        "SELECT COALESCE(SUM(m.score),0) AS s FROM mark m "
                        "JOIN question q ON q.id=m.question_id "
                        "WHERE m.team_id=? AND q.round_id=?", (t["id"], r["id"])).fetchone()["s"]
                    bonus = db().execute("SELECT bonus_multiplier FROM round WHERE id=?",
                                         (r["id"],)).fetchone()["bonus_multiplier"]
                    row.append(s * bonus)
            row.append(totals.get(t["id"], {}).get("total", 0))
            w.writerow(row)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app


app = create_app()
