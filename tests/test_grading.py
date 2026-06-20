from app.grading import QuestionGrade, SheetGrade, build_prompt, grade_sheet


def test_build_prompt_includes_questions_and_answers():
    qs = [
        {"id": 1, "text": "Capital of France?", "answer": "Paris",
         "acceptable": [], "answer_items": None, "ordered": False},
        {"id": 2, "text": "Order these by year", "answer": "",
         "acceptable": [], "answer_items": ["A", "B", "C"], "ordered": True},
    ]
    prompt = build_prompt(qs)
    assert "Capital of France?" in prompt
    assert "Paris" in prompt
    assert "1" in prompt and "2" in prompt
    # multi-item guidance present
    assert "items_correct" in prompt.lower() or "in order" in prompt.lower()


class _FakeClient:
    """Mimics anthropic client: .messages.parse(...) -> object with .parsed_output."""
    def __init__(self, payload):
        self._payload = payload
        self.messages = self

    def parse(self, **kwargs):
        # capture for assertions
        self.last_kwargs = kwargs
        class R:  # noqa: N801
            parsed_output = self_payload = self._payload
        return R

    @property
    def _payload_obj(self):
        return self._payload


def test_grade_sheet_returns_parsed_grades():
    payload = SheetGrade(grades=[
        QuestionGrade(question_id=1, transcription="Paris", is_correct=True, confidence=0.95),
    ])

    class Resp:
        parsed_output = payload

    class Msgs:
        def parse(self, **kwargs):
            Msgs.captured = kwargs
            return Resp

    class Client:
        messages = Msgs()

    result = grade_sheet(
        image_bytes=b"\x89PNG fake",
        media_type="image/png",
        questions=[{"id": 1, "text": "Capital of France?", "answer": "Paris",
                    "acceptable": [], "answer_items": None, "ordered": False}],
        client=Client(),
    )
    assert isinstance(result, SheetGrade)
    assert result.grades[0].is_correct is True
    # image was attached as a base64 block
    content = Msgs.captured["messages"][0]["content"]
    assert any(b.get("type") == "image" for b in content)
