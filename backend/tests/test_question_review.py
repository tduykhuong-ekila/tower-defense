import pytest

from apps.questions.models import Question, QuestionStatus, TeamQuestion
from apps.questions.serializers import TeamQuestionSerializer


@pytest.mark.parametrize(
    "question_type,options,answer,expected",
    [
        ("MULTIPLE_CHOICE", [{"key": "A", "text": "Sai"}, {"key": "B", "text": "Đúng"}], "B", "B. Đúng"),
        ("MULTIPLE_CHOICE", ["Sai", "Đúng"], "B", "B. Đúng"),
        ("MULTIPLE_CHOICE", [{"key": "B", "text": "Đúng"}], "Đúng", "B. Đúng"),
        ("SHORT_TEXT", [], "Hà Nội", "Hà Nội"),
    ],
)
def test_wrong_answer_review_includes_correct_answer_text(question_type, options, answer, expected):
    question = Question(type=question_type, content="Câu hỏi", options=options, answer_key=answer)
    team_question = TeamQuestion(question=question, status=QuestionStatus.ANSWER_INCORRECT)

    data = TeamQuestionSerializer().get_question(team_question)

    assert data["correct_answer"] == expected
    assert "answer_key" not in data


@pytest.mark.parametrize("status", [QuestionStatus.PENDING_QUESTION, QuestionStatus.ANSWER_SUBMITTED])
def test_unresolved_question_hides_correct_answer(status):
    question = Question(content="Câu hỏi", answer_key="B", explanation="Giải thích")
    data = TeamQuestionSerializer().get_question(TeamQuestion(question=question, status=status))

    assert "correct_answer" not in data
    assert "answer_key" not in data
    assert "explanation" not in data
