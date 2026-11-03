"""Absolute server deadlines, independent of viewer presence or popup visibility."""
from datetime import timedelta

from django.utils import timezone


def remaining_at(question, now=None):
    now = now or timezone.now()
    if not question.timer_started_at or question.timer_status != "RUNNING":
        return question.remaining_ms
    return max(0, int((question.expires_at - now).total_seconds() * 1000))


def settle(question, now):
    question.remaining_ms = remaining_at(question, now)
    question.viewing_leases = {}
    if not question.remaining_ms:
        question.timer_status = "EXPIRED"
        question.timer_started_at = None


def renew(question, viewer, now):
    # Only first opening (or explicit match resume) establishes a deadline.
    if question.timer_status in ("NOT_STARTED", "PAUSED") and question.remaining_ms:
        question.timer_started_at = now
        question.timer_status = "RUNNING"
        question.expires_at = now + timedelta(milliseconds=question.remaining_ms)


def freeze_for_match(match, now):
    """Caller holds the match lock; freezing preserves the question and its remaining budget."""
    from apps.questions.models import QuestionStatus, TeamQuestion
    for tq in TeamQuestion.objects.select_for_update().filter(match=match, status=QuestionStatus.PENDING_QUESTION):
        settle(tq, now)
        tq.timer_started_at = None
        tq.timer_status = "PAUSED" if tq.remaining_ms else "EXPIRED"
        tq.viewing_leases = {}
        tq.timer_version += 1
        tq.save()


def resume_for_match(match, now):
    from apps.questions.models import TeamQuestion
    for tq in TeamQuestion.objects.select_for_update().filter(match=match, status="PENDING_QUESTION", timer_status="PAUSED"):
        renew(tq, None, now)
        tq.timer_version += 1
        tq.save()
