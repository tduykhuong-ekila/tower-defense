from django.core.exceptions import ValidationError

from apps.questions.models import QuestionStatus

# Exact allowed transitions defined in GDD_PRD.md §6.5 & phase_2.md §2.3, §2.4
VALID_TRANSITIONS = {
    QuestionStatus.PENDING_QUESTION: {
        QuestionStatus.ANSWER_SUBMITTED,
        QuestionStatus.EXPIRED,
    },
    QuestionStatus.ANSWER_SUBMITTED: {
        QuestionStatus.ANSWER_CORRECT,
        QuestionStatus.ANSWER_INCORRECT,
    },
    QuestionStatus.ANSWER_CORRECT: {
        QuestionStatus.PENDING_REWARD,
    },
    QuestionStatus.PENDING_REWARD: {
        QuestionStatus.REWARD_CLAIMED,
        QuestionStatus.EXPIRED,  # Explicit administrative closure of a reward.
    },
    QuestionStatus.ANSWER_INCORRECT: set(),  # Terminal state for incorrect answer
    QuestionStatus.REWARD_CLAIMED: set(),    # Terminal state for claimed reward
    QuestionStatus.EXPIRED: set(),           # Terminal state for expired question
}


class InvalidQuestionStateTransitionError(ValidationError):
    """Raised when an invalid state transition is attempted on TeamQuestion."""

    def __init__(self, current_status: str, target_status: str):
        message = (
            f"Invalid transition from state '{current_status}' to '{target_status}'. "
            f"Allowed next states: {list(VALID_TRANSITIONS.get(current_status, []))}."
        )
        super().__init__(message)
        self.current_status = current_status
        self.target_status = target_status


def can_transition(current_status: str, target_status: str) -> bool:
    """Check whether a transition between two question states is valid."""
    allowed = VALID_TRANSITIONS.get(current_status, set())
    return target_status in allowed


def transition_team_question(team_question, target_status: str, save: bool = True):
    """
    Validate and apply a state transition on a TeamQuestion instance.
    Raises InvalidQuestionStateTransitionError if the transition is illegal.
    """
    current_status = team_question.status
    if current_status == target_status:
        return team_question

    if not can_transition(current_status, target_status):
        raise InvalidQuestionStateTransitionError(current_status, target_status)

    team_question.status = target_status
    if save:
        team_question.save(update_fields=["status"])
    return team_question
