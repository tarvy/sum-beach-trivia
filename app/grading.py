from __future__ import annotations

import base64
import json
import os
from typing import List, Optional

from pydantic import BaseModel


class QuestionGrade(BaseModel):
    question_id: int
    transcription: str
    is_correct: bool
    confidence: float
    items_correct: Optional[int] = None


class SheetGrade(BaseModel):
    grades: List[QuestionGrade]


def build_prompt(questions: List[dict]) -> str:
    lines = [
        "You are grading a photo of a team's handwritten trivia answer sheet.",
        "For EACH numbered question below, find the team's handwritten answer in the image,",
        "transcribe it, and decide if it is correct. Be generous about spelling, abbreviations,",
        "and well-known equivalents (e.g. 'JFK' = 'John F. Kennedy'). Set a confidence 0..1;",
        "use low confidence when the handwriting is unclear or no answer is found.",
        "For multi-item questions (a list, or 'put these in order'), set items_correct to the",
        "number of items the team got right (for ordered questions, count correct positions).",
        "",
        "Questions:",
    ]
    for q in questions:
        if q.get("answer_items"):
            expected = ", ".join(q["answer_items"])
            kind = "ORDERED list" if q.get("ordered") else "set of items"
            lines.append(
                f'#{q["id"]} ({kind}): {q["text"]}  Expected items: [{expected}]'
            )
        else:
            acc = q.get("acceptable") or []
            extra = f" (also accept: {', '.join(acc)})" if acc else ""
            lines.append(f'#{q["id"]}: {q["text"]}  Correct answer: {q["answer"]}{extra}')
    return "\n".join(lines)


def _client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


def grade_sheet(image_bytes: bytes, media_type: str, questions: List[dict],
                client=None) -> tuple[SheetGrade, dict]:
    """Grade one sheet photo. Returns (grades, usage) — usage carries the model
    and token counts for cost tracking (app/usage.py)."""
    client = client or _client()
    model = os.environ.get("GRADING_MODEL", "claude-opus-4-8")
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    resp = client.messages.parse(
        model=model,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": build_prompt(questions)},
            ],
        }],
        # output_format (not a hand-built output_config schema): the SDK converts
        # the Pydantic model to an API-legal schema — bare model_json_schema()
        # lacks additionalProperties:false and the API 400s on it.
        output_format=SheetGrade,
    )
    u = getattr(resp, "usage", None)
    usage = {"model": model,
             "input_tokens": getattr(u, "input_tokens", None),
             "output_tokens": getattr(u, "output_tokens", None),
             "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", None),
             "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", None)}
    parsed = resp.parsed_output
    if isinstance(parsed, SheetGrade):
        return parsed, usage
    if isinstance(parsed, dict):
        return SheetGrade(**parsed), usage
    # parsed_output may already be the typed object; fall back to text JSON
    return SheetGrade(**json.loads(parsed)), usage
