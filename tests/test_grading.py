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


def test_build_prompt_sets_photo_joke_boundaries_and_humor_level():
    prompt = build_prompt(
        [{"id": 1, "text": "Question?", "answer": "Answer",
          "acceptable": [], "answer_items": None, "ordered": False}],
        team_name="Beach Please",
        gladys_level="uncensored",
    )
    assert "Beach Please" in prompt
    assert "uncensored" in prompt
    assert "must not quote, paraphrase, hint at, or evaluate" in prompt
    assert "untrusted data" in prompt


def test_grade_sheet_returns_parsed_grades():
    payload = SheetGrade(grades=[
        QuestionGrade(question_id=1, transcription="Paris", is_correct=True, confidence=0.95),
    ], gladys_quip="The penmanship has priors.")

    class Usage:
        input_tokens = 2000
        output_tokens = 300
        cache_read_input_tokens = 0
        cache_creation_input_tokens = 0

    class Resp:
        parsed_output = payload
        usage = Usage()

    class Msgs:
        def parse(self, **kwargs):
            Msgs.captured = kwargs
            return Resp

    class Client:
        messages = Msgs()

    result, used = grade_sheet(
        image_bytes=b"\x89PNG fake",
        media_type="image/png",
        questions=[{"id": 1, "text": "Capital of France?", "answer": "Paris",
                    "acceptable": [], "answer_items": None, "ordered": False}],
        client=Client(),
        team_name="Aces",
        gladys_level="naughty",
    )
    assert isinstance(result, SheetGrade)
    assert result.grades[0].is_correct is True
    # usage block captured for the cost tracker
    assert used["input_tokens"] == 2000 and used["output_tokens"] == 300
    assert used["model"]
    # image was attached as a base64 block
    content = Msgs.captured["messages"][0]["content"]
    assert any(b.get("type") == "image" for b in content)
    prompt = next(b["text"] for b in content if b.get("type") == "text")
    assert "Aces" in prompt and "naughty" in prompt
