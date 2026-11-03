from datetime import timedelta
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.matches.action_policy import ActionPolicy
from apps.matches.models import Match, MatchStatus
from apps.matches.services import MatchService
from apps.questions.models import (
    Question,
    QuestionDifficulty,
    QuestionStatus,
    TeamQuestion,
)
from apps.questions.state_machine import transition_team_question
from apps.questions.validators import validate_answer
from apps.rewards.coin_rewards import draw_coin_reward
from apps.teams.models import Team


class QuestionService:
    @classmethod
    @transaction.atomic
    def open_session(cls, match, team, question_id, viewer, member=None):
        """Only an explicit quiz-card click may advance and start the next timer.

        A retry carries the previously observed ID, so it cannot skip a question
        another viewer has just opened. OPEN/HEARTBEAT remain non-advancing.
        """
        match = Match.objects.select_for_update().get(pk=match.pk)
        team = Team.objects.select_for_update().get(pk=team.pk)
        ActionPolicy.require_context(match, team, "ANSWER_QUESTION", member)
        question = cls.get_or_assign_current_question(match, team)
        previous_expired = False
        if question and str(question.pk) == str(question_id):
            previous_expired = question.status == QuestionStatus.EXPIRED
            question = cls.get_or_assign_current_question(match, team, advance_from=question.pk)
        if question:
            question = cls.update_viewing(match, team, question.pk, viewer, "OPEN", member)
        return question, previous_expired

    @classmethod
    def question_total(cls, match):
        if match.question_bank_id:
            return match.question_bank.question_count
        return min(match.configuration.get("max_questions_per_team", 8), Question.objects.filter(question_bank__isnull=True, is_active=True).count())

    @classmethod
    def progress(cls, match, team):
        from django.db.models import (
            Case,
            CharField,
            Count,
            IntegerField,
            Max,
            Q,
            Subquery,
            Value,
            When,
        )
        from django.db.models.functions import Cast, Coalesce

        # One bounded query, including for a new team with no assigned questions.
        legacy_total = Question.objects.filter(question_bank__isnull=True, is_active=True).order_by().annotate(
            group=Value(1)).values("group").annotate(total=Count("id")).values("total")
        own = Q(team_questions__team=team)
        counts = Match.objects.filter(pk=match.pk).annotate(
            total=Coalesce("question_bank__question_count", Subquery(legacy_total), Value(0), output_field=IntegerField()),
            answered=Count("team_questions", filter=own & (Q(team_questions__is_correct__isnull=False) | Q(team_questions__status=QuestionStatus.EXPIRED))),
            correct=Count("team_questions", filter=own & Q(team_questions__is_correct=True)),
            pending_reward_id=Max(Case(When(own & Q(team_questions__status=QuestionStatus.PENDING_REWARD), then=Cast("team_questions__id", CharField())), output_field=CharField())),
        ).values("total", "answered", "correct", "pending_reward_id").get()
        total = counts["total"] if match.question_bank_id else min(counts["total"], match.configuration.get("max_questions_per_team", 8))
        return {**counts, "total": total, "remaining": max(0, total - counts["answered"]),
                "exhausted": counts["answered"] >= total}

    @classmethod
    def get_preferred_difficulty(cls, sequence_number: int) -> str:
        """Determines expected difficulty level based on team's question sequence."""
        if sequence_number <= 2:
            return QuestionDifficulty.EASY
        if sequence_number <= 5:
            return QuestionDifficulty.MEDIUM
        return QuestionDifficulty.HARD

    @classmethod
    @transaction.atomic
    def expire_overdue_questions(cls, match: Optional[Match] = None, now=None):
        """Find all expired pending questions and transition them to EXPIRED status."""
        now = now or timezone.now()
        from apps.questions.timers import settle
        # Serialize timer writes with open/close/submit (same match -> team -> question order).
        matches = Match.objects.filter(pk=match.pk) if match else Match.objects.filter(status=MatchStatus.ACTIVE)
        expired_list = []
        for locked in matches.select_for_update().order_by("pk"):
            for tq in TeamQuestion.objects.select_for_update().filter(match=locked, status=QuestionStatus.PENDING_QUESTION, timer_status__in=["RUNNING", "EXPIRED"]):
                settle(tq, now)
                cls._expire_if_needed(tq, now)
                tq.save()
                if tq.status == QuestionStatus.EXPIRED:
                    expired_list.append(tq)
        return expired_list

    @classmethod
    def expire_reward_deadlines(cls, match: Match, now=None):
        """Legacy scheduler hook: earned rewards persist until claimed or match end.

        Stored grace deadlines from earlier versions cannot discard an entitlement.
        """
        return []

    @classmethod
    @transaction.atomic
    def get_or_assign_current_question(cls, match: Match, team: Team, advance_from=None) -> Optional[TeamQuestion]:
        """
        Retrieves the team's active question or assigns a new one if eligible.
        Guarantees:
        - Eliminated teams may continue questions while the match is active.
        - Max questions limit is enforced (§5.4).
        - Questions are not repeated for the same team in a match.
        - Questions with expired timers are marked EXPIRED automatically (§5.3).
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        team_locked = Team.objects.select_for_update().get(pk=team.pk)

        cls.expire_reward_deadlines(match_locked)

        now = timezone.now()

        # 1. Check for any current active question
        current = (
            TeamQuestion.objects.select_for_update()
            .filter(
                match=match_locked,
                team=team_locked,
            )
            .order_by("-sequence_number")
            .first()
        )

        if current:
            if current.status == QuestionStatus.PENDING_QUESTION:
                from apps.questions.timers import settle
                settle(current, now)
                cls._expire_if_needed(current, now)
                current.save()
            # GET/refresh/reconnect never progresses. NEXT must acknowledge this result.
            if (str(current.pk) != str(advance_from) or current.status in
                    [QuestionStatus.PENDING_QUESTION, QuestionStatus.PENDING_REWARD]):
                return current

        # Check match status
        if not ActionPolicy.context(match_locked, team_locked, "ANSWER_QUESTION").allowed:
            return None

        # 2. Check question limit (§5.4)
        max_questions = cls.question_total(match_locked)
        assigned_count = TeamQuestion.objects.filter(
            match=match_locked,
            team=team_locked,
        ).count()

        if assigned_count >= max_questions:
            return None

        # 3. Fair Question Assignment (§5.4, §2.2)
        next_seq = assigned_count + 1
        preferred_diff = cls.get_preferred_difficulty(next_seq)

        assigned_question_ids = TeamQuestion.objects.filter(
            match=match_locked,
            team=team_locked,
        ).values_list("question_id", flat=True)

        candidate_qs = Question.objects.filter(question_bank_id=match_locked.question_bank_id, is_active=True).exclude(
            id__in=assigned_question_ids
        )

        # Try to match preferred difficulty first
        next_question = (candidate_qs.order_by("?").first() if match_locked.question_bank_id
                         else candidate_qs.filter(difficulty=preferred_diff).order_by("?").first())
        if not next_question:
            # Fallback to any difficulty
            next_question = candidate_qs.order_by("?").first()

        if not next_question:
            # No active unassigned questions available in bank
            return None

        expires_at = now + timedelta(seconds=next_question.time_limit_seconds)
        tq = TeamQuestion.objects.create(
            match=match_locked,
            team=team_locked,
            question=next_question,
            sequence_number=next_seq,
            status=QuestionStatus.PENDING_QUESTION,
            assigned_at=now,
            expires_at=expires_at,
            remaining_ms=next_question.time_limit_seconds * 1000,
            reward_coin_amount=match_locked.configuration.get("correct_answer_coin_reward", 20),
            reward_coin_random=True,
        )

        MatchService.record_match_event(
            match=match_locked,
            event_type="QUESTION_ASSIGNED",
            payload={
                "team_id": str(team_locked.id),
                "team_question_id": str(tq.id),
                "sequence_number": next_seq,
                "question_id": str(next_question.id),
                "time_limit_seconds": next_question.time_limit_seconds,
            },
        )
        return tq

    @classmethod
    @transaction.atomic
    def submit_answer(
        cls,
        match: Match,
        team: Team,
        team_question_id: str,
        answer: str,
        member=None,
    ) -> TeamQuestion:
        """
        Validate and record one final answer submission for a team question (§5.3).
        Transitions:
        - If expired: PENDING_QUESTION -> EXPIRED
        - If correct: PENDING_QUESTION -> ANSWER_SUBMITTED -> ANSWER_CORRECT -> PENDING_REWARD
        - If incorrect: PENDING_QUESTION -> ANSWER_SUBMITTED -> ANSWER_INCORRECT
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        team_locked = Team.objects.select_for_update().get(pk=team.pk)

        ActionPolicy.require_context(match_locked, team_locked, "ANSWER_QUESTION", member)

        try:
            tq = (
                TeamQuestion.objects.select_for_update()
                .select_related("question")
                .get(pk=team_question_id, match=match_locked)
            )
        except TeamQuestion.DoesNotExist:
            raise ValidationError("Team question does not exist in this match.")

        if tq.team_id != team_locked.id:
            raise ValidationError("Cannot submit answers for another team's question.")

        if tq.question.question_bank_id != match_locked.question_bank_id:
            raise ValidationError("Question does not belong to this room's question bank.")

        if tq.status != QuestionStatus.PENDING_QUESTION:
            return tq

        now = timezone.now()

        from apps.questions.timers import settle
        settle(tq, now)
        if cls._expire_if_needed(tq, now):
            tq.save()
            return tq
        if tq.timer_status != "RUNNING":
            raise ValidationError("Open the question before submitting an answer.")
        tq.timer_status = "COMPLETED"
        tq.timer_started_at = None
        tq.viewing_leases = {}
        tq.timer_version += 1
        tq.save()

        # Transition: PENDING_QUESTION -> ANSWER_SUBMITTED
        transition_team_question(tq, QuestionStatus.ANSWER_SUBMITTED, save=False)

        # Validate answer
        is_correct = validate_answer(
            submitted=answer,
            answer_key=tq.question.answer_key,
            validator_type=tq.question.answer_validator_type,
            options=tq.question.options,
        )

        tq.submitted_at = now
        tq.submitted_answer = str(answer)
        tq.is_correct = is_correct

        if is_correct:
            if tq.reward_coin_random:
                tq.reward_coin_amount = draw_coin_reward()
            # Transition: ANSWER_SUBMITTED -> ANSWER_CORRECT -> PENDING_REWARD
            transition_team_question(tq, QuestionStatus.ANSWER_CORRECT, save=False)
            transition_team_question(tq, QuestionStatus.PENDING_REWARD, save=False)
            tq.save(
                update_fields=["status", "is_correct", "submitted_at", "submitted_answer", "reward_coin_amount"]
            )
            MatchService.record_match_event(
                match=match_locked,
                event_type="QUESTION_ANSWERED_CORRECT",
                payload={
                    "team_id": str(team_locked.id),
                    "team_question_id": str(tq.id),
                    "sequence_number": tq.sequence_number,
                    "member_id": str(member.id) if member else None,
                },
            )
        else:
            # Transition: ANSWER_SUBMITTED -> ANSWER_INCORRECT
            transition_team_question(tq, QuestionStatus.ANSWER_INCORRECT, save=False)
            tq.save(
                update_fields=["status", "is_correct", "submitted_at", "submitted_answer"]
            )
            MatchService.record_match_event(
                match=match_locked,
                event_type="QUESTION_ANSWERED_INCORRECT",
                payload={
                    "team_id": str(team_locked.id),
                    "team_question_id": str(tq.id),
                    "sequence_number": tq.sequence_number,
                    "member_id": str(member.id) if member else None,
                },
            )

        return tq

    @classmethod
    def _expire_if_needed(cls, tq, now):
        if tq.status != QuestionStatus.PENDING_QUESTION or tq.remaining_ms > 0:
            return False
        transition_team_question(tq, QuestionStatus.EXPIRED, save=False)
        tq.is_correct = False
        tq.submitted_at = now
        tq.timer_version += 1
        tq.save()
        MatchService.record_match_event(tq.match, "QUESTION_EXPIRED", {
            "team_id": str(tq.team_id), "team_question_id": str(tq.pk),
            "sequence_number": tq.sequence_number,
        })
        return True

    @classmethod
    @transaction.atomic
    def update_viewing(cls, match, team, question_id, viewer, action, member=None):
        from apps.questions.timers import renew, settle
        match = Match.objects.select_for_update().get(pk=match.pk)
        team = Team.objects.select_for_update().get(pk=team.pk)
        # Closing must also work when the match has just paused/ended.
        if action != "CLOSE":
            ActionPolicy.require_context(match, team, "ANSWER_QUESTION", member)
        tq = TeamQuestion.objects.select_for_update().select_related("question").get(
            pk=question_id, match=match, team=team)
        if tq.status != QuestionStatus.PENDING_QUESTION:
            return tq
        now = timezone.now()
        settle(tq, now)
        if cls._expire_if_needed(tq, now):
            return tq
        if action == "OPEN":
            renew(tq, viewer, now)
        # CLOSE and HEARTBEAT reconcile time only; neither pauses nor starts it.
        tq.timer_version += 1
        tq.save()
        MatchService.record_match_event(match, "QUESTION_TIMER_UPDATED", {
            "team_id": str(team.pk), "team_question_id": str(tq.pk),
        })
        return tq
