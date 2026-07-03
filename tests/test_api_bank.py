"""Question bank: host add-question + delete endpoints, and the import
script's mapping/dedupe logic (pure functions, no network)."""
import importlib.util
import pathlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app

_spec = importlib.util.spec_from_file_location(
    "import_bank",
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "import_bank.py")
import_bank = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(import_bank)


@pytest.fixture
async def app_client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield app, c


def _hk(app):
    return app.state.conn.execute("SELECT host_key FROM game WHERE id=1").fetchone()["host_key"]


BANK_Q = {"category": "History", "text": "Who was the first US president?",
          "answer": "George Washington"}


# ── POST /api/host/bank-question ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_bank_question_bad_key_403(app_client):
    app, c = app_client
    r = await c.post("/api/host/bank-question", params={"host_key": "wrong"}, json=BANK_Q)
    assert r.status_code == 403


@pytest.mark.anyio
async def test_bank_question_bad_category_400(app_client):
    app, c = app_client
    r = await c.post("/api/host/bank-question", params={"host_key": _hk(app)},
                     json=BANK_Q | {"category": "Nope"})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_bank_question_inserts_with_source_host(app_client):
    app, c = app_client
    hk = _hk(app)
    r = await c.post("/api/host/bank-question", params={"host_key": hk},
                     json=BANK_Q | {"acceptable": ["Washington"]})
    assert r.status_code == 200
    qid = r.json()["id"]
    qs = (await c.get("/api/questions", params={"host_key": hk})).json()["questions"]
    q = next(q for q in qs if q["id"] == qid)
    assert q["source"] == "host"
    assert q["author_name"] == "host"
    assert q["category"] == "History"
    assert q["answer"] == "George Washington"
    assert q["acceptable_answers"] == ["Washington"]
    assert q["round_id"] is None


# ── DELETE /api/host/questions/{id} ──────────────────────────────────────────

@pytest.mark.anyio
async def test_delete_bad_key_403(app_client):
    app, c = app_client
    r = await c.delete("/api/host/questions/1", params={"host_key": "wrong"})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_delete_unknown_id_404(app_client):
    app, c = app_client
    r = await c.delete("/api/host/questions/9999", params={"host_key": _hk(app)})
    assert r.status_code == 404


@pytest.mark.anyio
async def test_delete_assigned_to_round_409(app_client):
    app, c = app_client
    hk = _hk(app)
    qid = (await c.post("/api/host/bank-question", params={"host_key": hk},
                        json=BANK_Q)).json()["id"]
    await c.post("/api/host/build-rounds", params={"host_key": hk})
    qs = (await c.get("/api/questions", params={"host_key": hk})).json()["questions"]
    assert next(q for q in qs if q["id"] == qid)["round_id"] is not None
    r = await c.delete(f"/api/host/questions/{qid}", params={"host_key": hk})
    assert r.status_code == 409


@pytest.mark.anyio
async def test_delete_unassigned_200(app_client):
    app, c = app_client
    hk = _hk(app)
    qid = (await c.post("/api/host/bank-question", params={"host_key": hk},
                        json=BANK_Q)).json()["id"]
    r = await c.delete(f"/api/host/questions/{qid}", params={"host_key": hk})
    assert r.status_code == 200
    qs = (await c.get("/api/questions", params={"host_key": hk})).json()["questions"]
    assert qid not in [q["id"] for q in qs]


@pytest.mark.anyio
async def test_bank_page_served(app_client):
    app, c = app_client
    r = await c.get("/bank.html")
    assert r.status_code == 200


# ── import script: category mapping ──────────────────────────────────────────

def _raw(**over):
    base = {"category": "history", "type": "text_choice",
            "question": {"text": "In which year did WW2 end?"},
            "correctAnswer": "1945", "incorrectAnswers": ["1944", "1946", "1939"]}
    return base | over


def test_map_question_maps_category_and_answer():
    q = import_bank.map_question(_raw())
    assert q == {"category": "History", "text": "In which year did WW2 end?",
                 "answer": "1945", "acceptable": []}


def test_map_question_skips_unmapped_category():
    assert import_bank.map_question(_raw(category="society_and_culture")) is None


def test_map_question_skips_non_text_choice():
    assert import_bank.map_question(_raw(type="boolean")) is None


def test_map_question_skips_choice_dependent_phrasing():
    raw = _raw(question={"text": "Which of these fruits is not a pome?"})
    assert import_bank.map_question(raw) is None


def test_all_nine_standard_categories_covered():
    from app.db import STANDARD_CATEGORIES
    assert set(import_bank.CATEGORY_MAP.values()) == set(STANDARD_CATEGORIES)


# ── import script: normalize + dedupe ────────────────────────────────────────

def test_normalize_ignores_case_punctuation_whitespace():
    assert import_bank.normalize("What's  the CAPITAL of France?") == \
        import_bank.normalize("whats the capital of france")


def test_import_is_idempotent(db):
    raws = [_raw(), _raw(category="music", question={"text": "Who wrote Thriller?"},
                         correctAnswer="Michael Jackson")]
    counts = import_bank.import_questions(db, raws)
    assert counts["inserted"] == 2
    again = import_bank.import_questions(db, raws)
    assert again["inserted"] == 0 and again["duplicate"] == 2
    assert db.execute("SELECT COUNT(*) FROM question").fetchone()[0] == 2


def test_import_dedupes_against_existing_db_rows(db):
    from app import models
    models.add_question(db, "amy", "History", "In which year did WW2 end??", "1945")
    counts = import_bank.import_questions(db, [_raw()])  # same text modulo punctuation
    assert counts["duplicate"] == 1 and counts["inserted"] == 0


def test_import_inserts_as_bank_source(db):
    import_bank.import_questions(db, [_raw()])
    row = db.execute("SELECT * FROM question").fetchone()
    assert row["source"] == "bank"
    assert row["author_name"] == "bank"
    assert row["contributor_id"] is None
    assert row["round_id"] is None
