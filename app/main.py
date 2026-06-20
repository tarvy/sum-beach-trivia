from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import models
from app.db import connect, init_db
from app.serializers import host_question, public_question


class QuestionIn(BaseModel):
    author: str
    category: str
    text: str
    answer: str = ""
    acceptable: Optional[list] = None


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

    return app


app = create_app()
