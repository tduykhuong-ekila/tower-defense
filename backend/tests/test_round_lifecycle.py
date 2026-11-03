"""Exercise real purchases from spawn through clock, combat, persistence and results."""
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.combat.engine import CombatEngine, CombatState
from apps.combat.models import MatchResult
from apps.combat.services import CombatService
from apps.economy.models import CoinTransaction, TransactionType
from apps.matches.models import MatchEvent
from apps.matches.scheduler import MatchScheduler
from apps.matches.services import MatchService
from apps.questions.models import Question, QuestionStatus
from apps.questions.services import QuestionService
from apps.realtime.services import RealtimeService
from apps.rewards.models import RewardClaim
from apps.rewards.services import RewardService
from apps.units.models import EntityStatus, TeamUnlock, UnitType
from apps.units.seeds import ensure_standard_units
from apps.units.services import ConstructionService, UnitService

T0 = datetime(2026, 10, 17, 8, tzinfo=dt_timezone.utc)


def arena(count=2, hp=500, duration=300):
    ensure_standard_units()
    match, token = MatchService.create_match(configuration={"gameplay_mode": "LEGACY", "tower_placement_version": 0, "arena_layout_version": 5,
        "max_teams": count, "initial_base_hp": hp, "initial_coins": 500,
        "round_duration_seconds": 10, "match_duration_seconds": duration,
        "phase_durations": {"PREPARATION": 10, "BUILD_AND_SCOUT": 100,
                            "WAR": 100, "FINAL_ASSAULT": 100, "RESULTS": 10},
    })
    teams = []
    for i in range(count):
        team = MatchService.create_team(match, f"Team {i + 1}")
        MatchService.join_match(match, f"Player {i + 1}", team_id=team.pk)
        MatchService.set_team_ready(team, True)
        teams.append(team)
    with patch("django.utils.timezone.now", return_value=T0):
        match = MatchService.start_match(match)
    return match, teams, token


def tick(match, seconds):
    MatchScheduler.advance_due(match.pk, T0 + timedelta(seconds=seconds))
    match.refresh_from_db()


@pytest.mark.django_db
def test_round_phase_deadlines_replay_and_finalization():
    match, teams, _ = arena()
    match.configuration["phase_durations"].update(BUILD_AND_SCOUT=20, WAR=20, FINAL_ASSAULT=20)
    match.save()
    tick(match, 9)
    assert match.phase == "PREPARATION"
    tick(match, 10)
    assert match.phase == "BUILD_AND_SCOUT"
    tick(match, 19)
    assert not MatchEvent.objects.filter(match=match, event_type="COMBAT_RESOLVED").exists()
    tick(match, 20)
    assert match.configuration["current_round"] == 2
    first = MatchEvent.objects.get(match=match, event_type="COMBAT_RESOLVED")
    assert first.payload["current_round"] == 2
    assert first.payload["timer_state"]["next_round_at"] == (T0 + timedelta(seconds=30)).isoformat()
    tick(match, 20)
    replay = CombatService.execute_combat_round(match, expected_round=1)
    assert replay.new_state is None
    assert replay.events == first.payload["events"]
    assert CoinTransaction.objects.filter(match=match, transaction_type=TransactionType.PASSIVE_INCOME).count() == 2
    tick(match, 30)
    assert match.phase == "WAR"
    assert match.configuration["current_round"] == 3
    tick(match, 200)
    assert (match.status, match.phase) == ("FINISHED", "RESULTS")
    assert MatchResult.objects.filter(match=match).count() == 2
    assert MatchEvent.objects.filter(match=match, event_type="COMBAT_RESOLVED").count() == 6
    assert MatchEvent.objects.filter(match=match, event_type="MATCH_ENDED").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("count", [4, 20])
def test_complete_multiteam_match_using_only_legal_purchases(count):
    match, teams, _ = arena(count=count, hp=10)
    expected = 1
    for target in teams[1:]:
        UnitService.deploy_unit(match, teams[0], "infantry", str(target.pk))
        for _ in range(15):
            result = CombatService.execute_combat_round(match, expected_round=expected)
            expected += 1
            if str(target.pk) in result.eliminated_team_ids:
                break
        else:
            pytest.fail("Purchased infantry did not reach the enemy base")
    match.refresh_from_db()
    results = MatchResult.objects.filter(match=match)
    assert match.status == "FINISHED"
    assert results.count() == count
    assert results.get(final_rank=1).team_id == teams[0].pk
    assert match.teams.filter(status="ELIMINATED").count() == count - 1
    assert MatchEvent.objects.filter(match=match, event_type="MATCH_ENDED").count() == 1
    ids = list(MatchResult.objects.filter(match=match).values_list("id", flat=True))
    tick(match, 300)
    MatchService.end_match(match)
    assert ids == list(MatchResult.objects.filter(match=match).values_list("id", flat=True))
    assert APIClient().get(f"/api/v1/matches/{match.pk}/results/").status_code == 200


@pytest.mark.django_db
def test_pause_freezes_round_phase_match_and_repair_until_next_round():
    match, teams, _ = arena()
    tick(match, 10)
    teams[0].base_hp = 300
    teams[0].save()
    with patch("django.utils.timezone.now", return_value=T0 + timedelta(seconds=15)):
        ConstructionService.repair_base(match, teams[0])
        MatchService.pause_match(match)
    tick(match, 500)
    assert match.configuration["current_round"] == 1
    assert match.configuration["timer_state"]["round_remaining_seconds"] == 5
    with patch("django.utils.timezone.now", return_value=T0 + timedelta(seconds=515)):
        match = MatchService.resume_match(match)
        with pytest.raises(ValidationError):
            ConstructionService.repair_base(match, teams[0])
    tick(match, 519)
    assert match.configuration["current_round"] == 1
    tick(match, 520)
    assert match.configuration["current_round"] == 2
    ConstructionService.repair_base(match, teams[0])
    assert match.configuration["timer_state"]["match_deadline_at"] == (T0 + timedelta(
        seconds=match.configuration["match_duration_seconds"] + 500
    )).isoformat()


@pytest.mark.django_db
def test_total_match_deadline_finishes_before_phase_deadline():
    match, _, _ = arena(duration=60)
    # Existing configuration validation aligns duration to the phase sum.
    # Exercise an earlier persisted match deadline (e.g. a restored room).
    match.configuration["timer_state"]["match_deadline_at"] = (T0 + timedelta(seconds=60)).isoformat()
    match.save()
    tick(match, 60)
    assert match.status == "FINISHED"
    assert MatchEvent.objects.filter(match=match, event_type="COMBAT_RESOLVED").count() == 5
    assert MatchResult.objects.filter(match=match, final_rank=1).count() == 2


@pytest.mark.django_db
def test_shield_lifetime_cooldown_and_emp_persist():
    match, teams, _ = arena()
    TeamUnlock.objects.create(team=teams[1], unit_type=UnitType.objects.get(code="shield_generator"))
    _, shield = ConstructionService.build_tower(match, teams[1], "shield_generator", "node_tower_t2_slot1")
    r1 = CombatService.execute_combat_round(match, expected_round=1)
    assert any(e["type"] == "SHIELD_GENERATED" for e in r1.events)
    match.refresh_from_db()
    assert match.configuration["active_shields"][str(teams[1].pk)] == 1
    assert match.configuration["entity_effects"][str(shield.pk)]["cooldown_remaining"] == 2
    r2 = CombatService.execute_combat_round(match, expected_round=2)
    assert any(e["type"] == "SHIELD_EXPIRED" for e in r2.events)
    r3 = CombatService.execute_combat_round(match, expected_round=3)
    assert not any(e["type"] == "SHIELD_GENERATED" for e in r3.events)
    r4 = CombatService.execute_combat_round(match, expected_round=4)
    assert any(e["type"] == "SHIELD_GENERATED" for e in r4.events)
    ConstructionService.emp(match, teams[0], str(shield.pk))
    r5 = CombatService.execute_combat_round(match, expected_round=5)
    shield.refresh_from_db()
    assert shield.status == EntityStatus.ACTIVE
    assert any(e["type"] == "TOWER_ENABLED" and e["entity_id"] == str(shield.pk) for e in r5.events)


@pytest.mark.django_db
@pytest.mark.parametrize("count", [2, 4, 20])
def test_purchase_spawn_movement_tower_fire_base_impact_and_elimination(count):
    match, teams, _ = arena(count=count, hp=10)
    ConstructionService.build_tower(match, teams[-1], "mg_tower", f"node_tower_t{count}_slot1")
    # A wave can breach one MG tower with the real infantry HP and damage.
    units = [UnitService.deploy_unit(match, teams[0], "infantry", str(teams[-1].pk))[1]
             for _ in range(5)]
    all_events = []
    for i in range(1, 16):
        result = CombatService.execute_combat_round(match, expected_round=i)
        all_events.extend(result.events)
        if str(teams[-1].pk) in result.eliminated_team_ids:
            break
    teams[-1].refresh_from_db()
    assert teams[-1].base_hp == 0
    assert teams[-1].status == "ELIMINATED"
    assert {"UNIT_MOVED", "TOWER_ATTACKED", "BASE_DAMAGED", "ENTITY_DESTROYED", "TEAM_ELIMINATED"} <= {e["type"] for e in all_events}
    for unit in units:
        unit.refresh_from_db()
        assert unit.current_hp >= 0
    snapshot = RealtimeService.build_snapshot(match, str(teams[0].pk))["payload"]
    assert next(t for t in snapshot["teams"] if t["id"] == str(teams[-1].pk))["status"] == "ELIMINATED"
    if count == 2:
        match.refresh_from_db()
        assert match.status == "FINISHED"
        assert MatchResult.objects.get(match=match, final_rank=1).team_id == teams[0].pk
    else:
        result = CombatService.execute_combat_round(match, expected_round=i + 1)
        assert any(e["type"] == "UNIT_RETARGETED" for e in result.events)
    with pytest.raises(ValidationError):
        UnitService.deploy_unit(match, teams[-1], "infantry", str(teams[0].pk))


@pytest.mark.django_db
def test_mystery_coins_or_free_unlock_and_reward_grace():
    match, teams, _ = arena()
    Question.objects.create(content="2 + 2?", answer_key="4", time_limit_seconds=120)
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    QuestionService.update_viewing(match, teams[0], tq.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match, teams[0], str(tq.pk), "4")
    claim = RewardService.claim_reward(match, teams[0], str(tq.pk), "COIN", idempotency_key="once")
    tq.refresh_from_db()
    assert claim.coin_amount == tq.reward_coin_amount
    assert RewardService.claim_reward(match, teams[0], str(tq.pk), "UNLOCK").pk == claim.pk
    teams[0].refresh_from_db()
    assert teams[0].coins == 500 + claim.coin_amount
    assert RewardClaim.objects.filter(team_question=tq).count() == 1
    tq2 = QuestionService.get_or_assign_current_question(match, teams[1])
    QuestionService.update_viewing(match, teams[1], tq2.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match, teams[1], str(tq2.pk), "4")
    RewardService.claim_reward(match, teams[1], str(tq2.pk), "UNLOCK", unit_type_id="tank")
    teams[1].refresh_from_db()
    assert teams[1].coins == 500
    assert TeamUnlock.objects.filter(team=teams[1], unit_type__code="tank").exists()
    Question.objects.create(content="3 + 3?", answer_key="6", time_limit_seconds=120)
    tq3 = QuestionService.get_or_assign_current_question(match, teams[0], advance_from=tq.pk)
    QuestionService.update_viewing(match, teams[0], tq3.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match, teams[0], str(tq3.pk), "6")
    MatchService.advance_phase(match, effective_at=timezone.now())
    match.refresh_from_db()
    # Legacy saved deadlines must no longer discard an earned reward.
    deadline = timezone.now() + timedelta(seconds=20)
    match.configuration["reward_deadlines"] = {str(tq3.pk): deadline.isoformat()}
    match.save(update_fields=["configuration"])
    QuestionService.expire_reward_deadlines(match, now=deadline)
    tq3.refresh_from_db()
    assert tq3.status == QuestionStatus.PENDING_REWARD
    with patch("django.utils.timezone.now", return_value=deadline):
        claim = RewardService.claim_reward(match, teams[0], str(tq3.pk), "COIN")
        assert claim.coin_amount == tq3.reward_coin_amount



@pytest.mark.django_db
def test_elimination_winner_precedes_high_scoring_eliminated_opponent():
    match, teams, _ = arena(hp=10)
    match.configuration["combat_stats"] = {str(teams[1].pk): {"bases_destroyed": 20, "base_damage_dealt": 10000}}
    match.save()
    UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    for i in range(1, 16):
        result = CombatService.execute_combat_round(match, expected_round=i)
        if result.is_match_over:
            break
    results = list(MatchResult.objects.filter(match=match).order_by("final_rank"))
    assert results[0].team_id == teams[0].pk
    assert results[1].final_score > results[0].final_score
    teams[0].refresh_from_db()
    assert teams[0].score == results[0].final_score
    assert MatchEvent.objects.filter(match=match, event_type="MATCH_ENDED").count() == 1


def test_artillery_destroys_disabled_structure_without_reviving_it():
    state = CombatState(round_number=1, is_paused=False, actions=[], configuration={}, teams={
        "a": {"team_index":1, "base_hp":500, "status":"ACTIVE"},
        "b": {"team_index":2, "base_hp":500, "status":"ACTIVE"},
    }, entities=[
        {"id":"artillery", "team_id":"a", "entity_kind":"UNIT", "status":"ACTIVE",
         "current_node_id":"node_lane_t2_2", "target_team_id":"b", "current_hp":45,
         "range":3, "damage":40, "movement":0},
        {"id":"tower", "team_id":"b", "entity_kind":"TOWER", "status":"DISABLED",
         "current_node_id":"node_tower_t2_slot1", "current_hp":10},
    ])
    result = CombatEngine.resolve_round(state)
    assert next(e for e in result.new_state.entities if e["id"] == "tower")["status"] == "DESTROYED"
    assert any(e["type"] == "UNIT_ATTACKED" and e["target_entity_id"] == "tower" for e in result.events)
    assert not any(e["type"] == "TOWER_ENABLED" for e in result.events)
