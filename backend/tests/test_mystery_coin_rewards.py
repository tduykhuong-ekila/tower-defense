"""Exact odds, sealed results, persisted draws and one credit per team question."""
from collections import Counter
from importlib import import_module
from unittest.mock import patch

import pytest
from django.apps import apps

from apps.economy.models import CoinTransaction
from apps.matches.defaults import calculate_balance_preview, get_default_configuration
from apps.questions.models import TeamQuestion
from apps.questions.serializers import TeamQuestionSerializer
from apps.questions.services import QuestionService
from apps.realtime.services import RealtimeService
from apps.rewards.coin_rewards import EXPECTED_COIN_REWARD, draw_coin_reward
from apps.rewards.services import RewardService
from tests.test_quiz_sessions import room as room

pytestmark = pytest.mark.django_db
ODDS = [
    {"amount": 20, "probability_percent": 15},
    {"amount": 25, "probability_percent": 20},
    {"amount": 30, "probability_percent": 35},
    {"amount": 40, "probability_percent": 25},
    {"amount": 60, "probability_percent": 5},
]


def test_all_100_draw_tickets_have_exact_requested_odds():
    with patch("apps.rewards.coin_rewards.randbelow", side_effect=range(100)) as random:
        payouts = Counter(draw_coin_reward() for _ in range(100))
    assert payouts == {20: 15, 25: 20, 30: 35, 40: 25, 60: 5}
    assert all(call.args == (100,) for call in random.call_args_list)
    assert EXPECTED_COIN_REWARD == 31.5


@pytest.mark.parametrize("amount", [20, 25, 30, 40, 60])
def test_correct_answer_seals_one_draw_and_claim_credits_exact_amount(room, amount):
    match, teams, _, _ = room
    team = teams[0]
    tq = QuestionService.get_or_assign_current_question(match, team)
    assert tq.reward_coin_random
    QuestionService.update_viewing(match, team, tq.pk, "viewer", "OPEN")
    with patch("apps.questions.services.draw_coin_reward", return_value=amount) as draw:
        result = QuestionService.submit_answer(match, team, tq.pk, "yes")
        assert result.reward_coin_amount == amount
        QuestionService.submit_answer(match, team, tq.pk, "wrong")
        QuestionService.get_or_assign_current_question(match, team)
        QuestionService.update_viewing(match, team, tq.pk, "other-viewer", "OPEN")
        assert draw.call_count == 1
    options = RewardService.get_reward_options(result)
    assert options["coin_amount"] is None
    assert options["coin_distribution"] == ODDS
    public = TeamQuestionSerializer(result).data
    assert "reward_coin_amount" not in public
    assert public["reward_options"] == options
    snapshot = RealtimeService.build_snapshot(match, str(team.pk))["payload"]
    assert snapshot["viewer"]["pending_reward"] == options
    event = match.events.get(event_type="QUESTION_ANSWERED_CORRECT")
    assert event.payload["question_state"]["reward_options"] == options
    # Changing the old fixed-reward setting cannot change the sealed payout.
    match.configuration["correct_answer_coin_reward"] = 20
    match.save()
    team.refresh_from_db()
    before = team.coins
    claim = RewardService.claim_reward(match, team, tq.pk, "COIN", idempotency_key="first")
    assert claim.coin_amount == amount
    for key in ["first", "retry", None]:
        assert RewardService.claim_reward(match, team, tq.pk, "COIN", idempotency_key=key).pk == claim.pk
    assert RewardService.claim_reward(match, team, tq.pk, "UNLOCK", "tank").pk == claim.pk
    team.refresh_from_db()
    assert team.coins == before + amount
    assert CoinTransaction.objects.filter(reference_id=str(tq.pk), transaction_type="REWARD_COIN").count() == 1


def test_wrong_answer_never_draws_and_unlock_never_credits_coins(room):
    match, teams, _, _ = room
    with patch("apps.questions.services.draw_coin_reward", return_value=60) as draw:
        wrong = QuestionService.get_or_assign_current_question(match, teams[0])
        QuestionService.update_viewing(match, teams[0], wrong.pk, "viewer", "OPEN")
        QuestionService.submit_answer(match, teams[0], wrong.pk, "wrong")
        draw.assert_not_called()
        tq = QuestionService.get_or_assign_current_question(match, teams[1])
        QuestionService.update_viewing(match, teams[1], tq.pk, "viewer", "OPEN")
        QuestionService.submit_answer(match, teams[1], tq.pk, "yes")
    teams[1].refresh_from_db()
    before = teams[1].coins
    claim = RewardService.claim_reward(match, teams[1], tq.pk, "UNLOCK", "tank")
    assert claim.reward_type == "UNLOCK" and claim.coin_amount == 0
    teams[1].refresh_from_db()
    assert teams[1].coins == before
    assert not CoinTransaction.objects.filter(reference_id=str(tq.pk), transaction_type="REWARD_COIN").exists()


def test_legacy_assignment_keeps_fixed_reward(room):
    match, teams, _, _ = room
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    TeamQuestion.objects.filter(pk=tq.pk).update(reward_coin_random=False, reward_coin_amount=20)
    QuestionService.update_viewing(match, teams[0], tq.pk, "viewer", "OPEN")
    with patch("apps.questions.services.draw_coin_reward") as draw:
        result = QuestionService.submit_answer(match, teams[0], tq.pk, "yes")
        draw.assert_not_called()
    options = RewardService.get_reward_options(result)
    assert options["coin_amount"] == 20 and options["coin_distribution"] == []
    assert RewardService.claim_reward(match, teams[0], tq.pk, "COIN").coin_amount == 20


def test_balance_preview_separates_expected_and_maximum_coins():
    config = get_default_configuration()
    preview = calculate_balance_preview(config)
    assert preview["expected_question_coins"] == config["max_questions_per_team"] * 31.5
    assert preview["max_question_coins"] == config["max_questions_per_team"] * 60
    assert preview["total_projected_coins_per_team"] == (
        preview["initial_coins"] + preview["projected_passive_coins"] + preview["expected_question_coins"]
    )


def test_rollout_converts_only_unanswered_assignments(room):
    match, teams, _, _ = room
    pending = QuestionService.get_or_assign_current_question(match, teams[0])
    earned = QuestionService.get_or_assign_current_question(match, teams[1])
    TeamQuestion.objects.filter(pk=pending.pk).update(reward_coin_random=False)
    TeamQuestion.objects.filter(pk=earned.pk).update(
        reward_coin_random=False, reward_coin_amount=20, status="PENDING_REWARD", is_correct=True,
    )
    migration = import_module("apps.questions.migrations.0005_teamquestion_reward_coin_random")
    migration.enable_unanswered_bags(apps, None)
    pending.refresh_from_db()
    earned.refresh_from_db()
    assert pending.reward_coin_random
    assert not earned.reward_coin_random and earned.reward_coin_amount == 20
