"""Authoritative visibility, progression, reward and inspection regression tests."""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.economy.models import CoinTransaction
from apps.matches.services import MatchService
from apps.questions.models import Question, TeamQuestion
from apps.questions.serializers import TeamQuestionSerializer
from apps.questions.services import QuestionService
from apps.questions.timers import remaining_at
from apps.realtime.services import RealtimeService, scope_live_event
from apps.rewards.models import RewardClaim
from apps.rewards.services import RewardService
from apps.units.serializers import GameEntitySerializer
from apps.units.services import UnitService

pytestmark = pytest.mark.django_db


@pytest.fixture
def room():
    match, host = MatchService.create_match(name="Visibility sessions")
    teams = [MatchService.create_team(match, f"Session {i}") for i in range(2)]
    players = [MatchService.join_match(match, f"Player {i}", team_id=team.pk) for i, team in enumerate(teams)]
    for team in teams:
        MatchService.set_team_ready(team, True)
    match = MatchService.start_match(match)
    for i in range(3):
        Question.objects.create(content=f"Question {i}", answer_key="yes", time_limit_seconds=60)
    return match, teams, players, host


def view(match, team, tq, viewer, action="OPEN"):
    return QuestionService.update_viewing(match, team, tq.pk, viewer, action)


def test_closed_assignment_never_ticks_or_advances_and_submission_requires_open(room):
    match, teams, _, _ = room
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    assert tq.timer_status == "NOT_STARTED"
    with patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(hours=1)):
        QuestionService.expire_overdue_questions(match)
        same = QuestionService.get_or_assign_current_question(match, teams[0])
        assert same.pk == tq.pk and same.remaining_ms == 60000
        with pytest.raises(ValidationError, match="Open"):
            QuestionService.submit_answer(match, teams[0], tq.pk, "yes")
    assert TeamQuestion.objects.filter(team=teams[0]).count() == 1


def test_close_reopen_preserves_deadline_and_hidden_expiration(room):
    match, teams, _, _ = room
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    start = timezone.now()
    with patch("django.utils.timezone.now", return_value=start):
        opened = view(match, teams[0], tq, "a")
    deadline = opened.expires_at
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=7)):
        closed = view(match, teams[0], tq, "a", "CLOSE")
        assert closed.remaining_ms == 53000 and closed.timer_status == "RUNNING"
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=18)):
        reopened = view(match, teams[0], tq, "b")
        assert reopened.remaining_ms == 42000 and reopened.expires_at == deadline
        view(match, teams[0], tq, "b", "CLOSE")
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=61)):
        QuestionService.expire_overdue_questions(match)
        same = QuestionService.get_or_assign_current_question(match, teams[0])
        assert same.pk == tq.pk and same.status == "EXPIRED"
        assert QuestionService.submit_answer(match, teams[0], tq.pk, "yes").status == "EXPIRED"
        assert not RewardClaim.objects.exists()


def test_shared_viewers_duplicate_open_disconnect_and_delayed_heartbeat(room):
    match, teams, _, _ = room
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    start = timezone.now()
    with patch("django.utils.timezone.now", return_value=start):
        opened = view(match, teams[0], tq, "a")
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=3)):
        second = view(match, teams[0], tq, "b")
        duplicate = view(match, teams[0], tq, "b")
        assert duplicate.remaining_ms == second.remaining_ms == 57000
        assert duplicate.expires_at == opened.expires_at
        view(match, teams[0], tq, "a", "CLOSE")
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=5)):
        closed = view(match, teams[0], tq, "b", "CLOSE")
        assert closed.remaining_ms == 55000 and closed.timer_status == "RUNNING"
        assert view(match, teams[0], tq, "b", "HEARTBEAT").expires_at == opened.expires_at
    with patch("django.utils.timezone.now", return_value=start + timedelta(minutes=2)):
        QuestionService.expire_overdue_questions(match)
        tq.refresh_from_db()
        assert tq.timer_status == "EXPIRED" and tq.remaining_ms == 0
        snap = RealtimeService.build_snapshot(match, str(teams[0].pk))["payload"]
        assert snap["viewer"]["current_question"]["id"] == str(tq.pk)
        assert snap["viewer"]["current_question"]["status"] == "EXPIRED"


def test_expiration_is_explicit_and_next_is_idempotent(room):
    match, teams, _, _ = room
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    tq.remaining_ms = 1000
    tq.save()
    start = timezone.now()
    with patch("django.utils.timezone.now", return_value=start):
        view(match, teams[0], tq, "a")
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=2)):
        QuestionService.expire_overdue_questions(match)
        same = QuestionService.get_or_assign_current_question(match, teams[0])
        assert same.pk == tq.pk and same.status == "EXPIRED"
        assert QuestionService.submit_answer(match, teams[0], tq.pk, "yes").status == "EXPIRED"
        snap = RealtimeService.build_snapshot(match, str(teams[0].pk))["payload"]
        assert snap["viewer"]["current_question"]["status"] == "EXPIRED"
        assert not RewardClaim.objects.exists()
        next_tq = QuestionService.get_or_assign_current_question(match, teams[0], advance_from=tq.pk)
        duplicate = QuestionService.get_or_assign_current_question(match, teams[0], advance_from=tq.pk)
        assert duplicate.pk == next_tq.pk and next_tq.sequence_number == 2
        assert next_tq.timer_status == "NOT_STARTED"


def test_reward_amount_snapshot_idempotency_and_reconnect(room):
    match, teams, _, _ = room
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    view(match, teams[0], tq, "a")
    with patch("apps.questions.services.draw_coin_reward", return_value=40):
        result = QuestionService.submit_answer(match, teams[0], tq.pk, "yes")
    assert result.reward_coin_amount == 40
    assert QuestionService.submit_answer(match, teams[0], tq.pk, "wrong").pk == tq.pk
    match.configuration["correct_answer_coin_reward"] = 20
    match.save()
    result.refresh_from_db()
    assert RewardService.get_reward_options(result)["coin_amount"] is None
    assert RealtimeService.build_snapshot(match, str(teams[0].pk))["payload"]["viewer"]["pending_reward"]["coin_amount"] is None
    teams[0].refresh_from_db()
    before = teams[0].coins
    claim = RewardService.claim_reward(match, teams[0], tq.pk, "COIN", idempotency_key="once")
    assert claim.coin_amount == 40
    assert RewardService.claim_reward(match, teams[0], tq.pk, "COIN", idempotency_key="retry").pk == claim.pk
    teams[0].refresh_from_db()
    assert teams[0].coins == before + 40
    assert CoinTransaction.objects.filter(reference_id=str(tq.pk), transaction_type="REWARD_COIN").count() == 1
    assert QuestionService.get_or_assign_current_question(match, teams[0]).status == "REWARD_CLAIMED"
    # Newly assigned questions use mystery bags even in older room configurations.
    older = QuestionService.get_or_assign_current_question(match, teams[1])
    assert older.reward_coin_amount == 20
    assert older.reward_coin_random


def test_authenticated_visibility_api_and_private_timer_events(room):
    match, teams, players, host = room
    client = APIClient()
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=players[0][1])
    url = f"/api/v1/matches/{match.pk}/questions/current/"
    q = client.get(url).data
    viewer = str(uuid.uuid4())
    opened = client.post(url, {"action": "OPEN", "question_id": q["id"], "viewer_id": viewer}, format="json")
    assert opened.status_code == 200 and opened.data["timer"]["status"] == "RUNNING"
    other = QuestionService.get_or_assign_current_question(match, teams[1])
    denied = client.post(url, {"action": "CLOSE", "question_id": str(other.pk), "viewer_id": viewer}, format="json")
    assert denied.status_code == 400
    event = {"event_type": "QUESTION_TIMER_UPDATED", "payload": {"team_id": str(teams[0].pk), "question_state": q}}
    assert scope_live_event(event, str(teams[1].pk), False)["event_type"] == "EVENT_REDACTED"
    assert scope_live_event(event, str(teams[0].pk), False) == event


def test_match_pause_preserves_current_question_and_hidden_resume(room):
    match, teams, _, _ = room
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    start = timezone.now()
    with patch("django.utils.timezone.now", return_value=start):
        view(match, teams[0], tq, "a")
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=7)):
        MatchService.pause_match(match)
        same = QuestionService.get_or_assign_current_question(match, teams[0])
        assert same.pk == tq.pk and same.timer_status == "PAUSED" and same.remaining_ms == 53000
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=30)):
        MatchService.resume_match(match)
        same.refresh_from_db()
        assert same.timer_status == "RUNNING" and remaining_at(same) == 53000
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=84)):
        QuestionService.expire_overdue_questions(match)
        same.refresh_from_db()
        assert same.pk == tq.pk and same.status == "EXPIRED"


def test_entity_inspection_uses_engine_stats_and_live_hp(room):
    match, teams, _, _ = room
    match = MatchService.advance_phase(match)
    _, entity = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    payload = GameEntitySerializer(entity).data
    assert payload["max_hp"] == 80 and payload["movement_speed"] == 7
    assert payload["damage"] == entity.unit_type.base_stats["damage"] * .5
    assert payload["attack_interval_seconds"] == 2 / 1.5
    entity.current_hp = 56
    entity.save()
    snap = RealtimeService.build_snapshot(match, str(teams[0].pk))["payload"]
    public = next(e for e in snap["entities"] if e["id"] == str(entity.pk))
    assert public["current_hp"] == 56 and public["damage"] == payload["damage"]


def test_match_end_freezes_question_and_retains_readable_result(room):
    match, teams, _, _ = room
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    view(match, teams[0], tq, "a")
    match = MatchService.end_match(match)
    tq.refresh_from_db()
    assert tq.timer_status == "PAUSED" and not tq.viewing_leases
    assert QuestionService.get_or_assign_current_question(match, teams[0]).pk == tq.pk
    with pytest.raises(ValidationError):
        QuestionService.submit_answer(match, teams[0], tq.pk, "yes")
