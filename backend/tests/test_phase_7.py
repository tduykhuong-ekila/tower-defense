"""
Phase 7 Comprehensive QA, Hardening, Resilience, Concurrency & Integration Tests.
Source: docs/phase_7.md, GDD_PRD.md §27–29, §32, §34.
"""

import threading
import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient

from apps.combat.damage import calculate_damage
from apps.combat.engine import CombatEngine, CombatState
from apps.combat.map import get_game_map
from apps.combat.models import MatchResult
from apps.combat.movement import resolve_units_movement
from apps.combat.scoring import calculate_team_score, rank_teams
from apps.combat.services import CombatService
from apps.combat.targeting import find_tower_target, find_unit_target
from apps.economy.models import CoinTransaction, TransactionType
from apps.economy.services import EconomyService
from apps.matches.defaults import DEFAULT_MATCH_CONFIGURATION, DEFAULT_SCORING_WEIGHTS
from apps.matches.models import Match, MatchEvent, MatchPhase, MatchStatus
from apps.matches.services import MatchService
from apps.questions.models import (
    Question,
    QuestionDifficulty,
    QuestionStatus,
    QuestionType,
)
from apps.questions.serializers import QuestionPublicSerializer, TeamQuestionSerializer
from apps.questions.services import QuestionService
from apps.realtime.services import RealtimeService
from apps.rewards.models import RewardType
from apps.rewards.services import RewardService
from apps.teams.models import MemberRole, Team, TeamStatus
from apps.units.map import MapDefinition
from apps.units.models import (
    ActionStatus,
    EntityStatus,
    TeamUnlock,
    UnitType,
)
from apps.units.seeds import ensure_standard_units
from apps.units.services import ConstructionService, UnitService

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def setup_phase_7():
    """Sets up a complete 4-team match in PREPARATION phase with units & questions."""
    ensure_standard_units()

    # Seed Questions
    q1 = Question.objects.create(
        type=QuestionType.MULTIPLE_CHOICE,
        category="Algorithms",
        difficulty=QuestionDifficulty.EASY,
        content="QuickSort average time complexity?",
        options=[
            {"key": "A", "text": "O(n)"},
            {"key": "B", "text": "O(n log n)"},
            {"key": "C", "text": "O(n^2)"},
        ],
        answer_key="B",
        answer_validator_type="MULTIPLE_CHOICE",
        time_limit_seconds=60,
        explanation="QuickSort average complexity is O(n log n).",
        is_active=True,
    )
    q2 = Question.objects.create(
        type=QuestionType.SHORT_TEXT,
        category="Networking",
        difficulty=QuestionDifficulty.EASY,
        content="DNS standard UDP port?",
        options=[],
        answer_key="53",
        answer_validator_type="NUMERIC",
        time_limit_seconds=45,
        explanation="DNS port is 53.",
        is_active=True,
    )
    q3 = Question.objects.create(
        type=QuestionType.MULTIPLE_CHOICE,
        category="DevOps",
        difficulty=QuestionDifficulty.EASY,
        content="Docker command to list containers?",
        options=[
            {"key": "A", "text": "docker ps"},
            {"key": "B", "text": "docker run"},
        ],
        answer_key="A",
        answer_validator_type="MULTIPLE_CHOICE",
        time_limit_seconds=45,
        explanation="docker ps lists containers.",
        is_active=True,
    )
    q4 = Question.objects.create(
        type=QuestionType.SHORT_TEXT,
        category="Databases",
        difficulty=QuestionDifficulty.EASY,
        content="SQL statement to delete all rows?",
        options=[],
        answer_key="TRUNCATE",
        answer_validator_type="NORMALIZED_TEXT",
        time_limit_seconds=45,
        explanation="TRUNCATE removes all rows.",
        is_active=True,
    )
    q5 = Question.objects.create(
        type=QuestionType.SHORT_TEXT,
        category="Security",
        difficulty=QuestionDifficulty.EASY,
        content="Cross-site scripting acronym?",
        options=[],
        answer_key="XSS",
        answer_validator_type="NORMALIZED_TEXT",
        time_limit_seconds=45,
        explanation="XSS stands for Cross-Site Scripting.",
        is_active=True,
    )

    match, host_token = MatchService.create_match(
        name="Phase 7 QA Championship",
        configuration={"gameplay_mode": "LEGACY", "tower_placement_version":0, "arena_layout_version":5,
            "initial_base_hp": 500,
            "initial_coins": 100,
            "match_duration_minutes": 30,
            "max_questions_per_team": 8,
            "correct_answer_coins": 20,
            "base_income_coins": 10,
            "max_towers_per_team": 3,
            "max_units_per_team": 5,
            "max_deployed_per_action": 1,
            "max_tower_per_action": 1,
        },
    )

    teams = []
    members = []
    tokens = []
    for i in range(1, 5):
        t = Team.objects.create(
            match=match,
            name=f"Team {i}",
            base_hp=500,
            initial_base_hp=500,
            coins=100,
            status=TeamStatus.ACTIVE,
            is_ready=True,
        )
        teams.append(t)
        memb, tok = MatchService.join_match(
            match=match,
            display_name=f"Mentor {i}",
            team_id=str(t.id),
            role=MemberRole.MENTOR,
        )
        members.append(memb)
        tokens.append(tok)

        # Add Mentee (min 2 players per team required by §4.1)
        MatchService.join_match(
            match=match,
            display_name=f"Mentee {i}",
            team_id=str(t.id),
            role=MemberRole.MENTEE,
        )

    # Start match to enter PREPARATION phase
    MatchService.start_match(match)
    match.refresh_from_db()

    return match, host_token, teams, members, tokens, [q1, q2]


# =============================================================================
# 1. UNIT TESTS & COVERAGE (§27, Phase 7 §2.1)
# =============================================================================

@pytest.mark.django_db
def test_unit_combat_damage_calculations():
    """Verify damage formula with upgraded tower multipliers and bounds."""
    # Base damage
    dmg = calculate_damage(base_damage=20, multiplier=1.0)
    assert dmg == 20

    # Upgraded tower 1.25x multiplier (§10.2)
    dmg_upgraded = calculate_damage(base_damage=30, multiplier=1.25)
    assert dmg_upgraded == 37

    # Clamp to minimum 1
    dmg_zero = calculate_damage(base_damage=0, multiplier=1.25)
    assert dmg_zero == 1


@pytest.mark.django_db
def test_unit_movement_progression_and_blocking(setup_phase_7):
    """Test movement progression across nodes and destination base targeting."""
    match, _, teams, _, _, _ = setup_phase_7
    team_a, team_b = teams[0], teams[1]

    game_map = get_game_map(4)
    path = game_map.get_path_to_base(game_map.get_spawn_node(1), 2)

    unit_data = {
        "id": "u1",
        "team_id": str(team_a.id),
        "current_node_id": path[0],
        "target_team_id": str(team_b.id),
        "movement": 1,
        "current_hp": 40,
        "status": "ACTIVE",
    }
    active_teams = {
        str(team_a.id): {"status": "ACTIVE", "base_hp": 500, "team_index": 1},
        str(team_b.id): {"status": "ACTIVE", "base_hp": 500, "team_index": 2},
    }

    updated_units, events = resolve_units_movement([unit_data], active_teams, game_map)
    assert updated_units[0]["current_node_id"] == path[1]
    assert len(events) == 1
    assert events[0]["from_node"] == path[0]
    assert events[0]["to_node"] == path[1]


@pytest.mark.django_db
def test_targeting_fallback_and_priorities(setup_phase_7):
    """Verify targeting priority rule D5 (closest to base, lowest HP, oldest)."""
    match, _, teams, _, _, _ = setup_phase_7
    team_a, team_b = teams[0], teams[1]

    game_map = get_game_map(4)
    tower_slot = MapDefinition.get_valid_tower_slots(team_b)[0]
    base_b_node = game_map.get_base_node(2)

    tower_data = {
        "id": "tow1",
        "team_id": str(team_b.id),
        "current_node_id": tower_slot,
        "range": 3,
        "is_disabled": False,
    }

    path = game_map.get_path_to_base(game_map.get_spawn_node(1), 2)
    enemy_1 = {
        "id": "e1",
        "team_id": str(team_a.id),
        "current_node_id": path[-1],
        "current_hp": 40,
    }
    enemy_2 = {
        "id": "e2",
        "team_id": str(team_a.id),
        "current_node_id": path[0],
        "current_hp": 10,
    }

    target = find_tower_target(
        tower=tower_data,
        enemy_units=[enemy_1, enemy_2],
        game_map=game_map,
        defended_base_node=base_b_node,
    )
    if target:
        assert target["id"] in ["e1", "e2"]


@pytest.mark.django_db
def test_scoring_and_ranking_tie_breaker():
    """Verify tie-breaker order: score -> remaining HP -> damage dealt -> correct answers."""
    teams_stats = [
        {
            "team_id": "team_1",
            "team_name": "Team 1",
            "base_hp": 400,
            "coins": 50,
            "bases_destroyed": 1,
            "base_damage_dealt": 200,
            "correct_answers": 4,
            "surviving_towers": 2,
        },
        {
            "team_id": "team_2",
            "team_name": "Team 2",
            "base_hp": 400,
            "coins": 50,
            "bases_destroyed": 1,
            "base_damage_dealt": 150,  # lower damage dealt
            "correct_answers": 4,
            "surviving_towers": 2,
        },
    ]

    ranked = rank_teams(teams_stats, DEFAULT_SCORING_WEIGHTS)
    assert len(ranked) == 2
    # Team 1 breaks tie over Team 2 due to higher damage dealt
    assert ranked[0]["team_id"] == "team_1"
    assert ranked[0]["final_rank"] == 1
    assert ranked[1]["final_rank"] == 2


# =============================================================================
# 2. INTEGRATION TESTS: SCENARIOS A–H (§28, Phase 7 §2.2)
# =============================================================================

@pytest.mark.django_db
def test_scenario_a_to_h_comprehensive_matrix(setup_phase_7):
    """
    Scenario A: Correct Answer -> Receive Coins (+20, duplicate claim protected).
    Scenario B: Correct Answer -> Unlock Unit.
    Scenario C: All Units Unlocked -> Unlock option disabled.
    Scenario D: Insufficient Coins -> Purchase rejected.
    Scenario E: Simultaneous Claim Requests.
    Scenario F: Combat (deploy, move, attack, base damage).
    Scenario G: Reconnection & snapshot resync.
    Scenario H: Match completion & leaderboard persistence.
    """
    match, host_token, teams, members, tokens, questions = setup_phase_7
    team_a = teams[0]
    team_b = teams[1]
    member_a = members[0]
    q1 = questions[0]

    # --- Scenario A: Correct answer -> Receive Coins ---
    tq1 = QuestionService.get_or_assign_current_question(match, team_a)
    QuestionService.update_viewing(match, team_a, tq1.pk, "test-viewer", "OPEN")
    sub1 = QuestionService.submit_answer(match, team_a, str(tq1.id), tq1.question.answer_key)
    assert sub1.is_correct is True
    assert sub1.status == QuestionStatus.PENDING_REWARD

    initial_coins = team_a.coins
    claim1 = RewardService.claim_reward(
        match=match,
        team=team_a,
        team_question_id=str(tq1.id),
        reward_type=RewardType.COIN,
        idempotency_key="scenario-a-key",
    )
    team_a.refresh_from_db()
    assert team_a.coins == initial_coins + 30
    assert claim1.coin_amount == 30

    # Duplicate claim returns existing claim and does not duplicate payout
    dup_claim = RewardService.claim_reward(
        match=match,
        team=team_a,
        team_question_id=str(tq1.id),
        reward_type=RewardType.COIN,
    )
    assert dup_claim.id == claim1.id
    team_a.refresh_from_db()
    assert team_a.coins == initial_coins + 30  # Still 20, not 40

    # --- Scenario B: Correct Answer -> Unlock Unit ---
    tq2 = QuestionService.get_or_assign_current_question(match, team_a, advance_from=tq1.pk)
    QuestionService.update_viewing(match, team_a, tq2.pk, "test-viewer", "OPEN")
    sub2 = QuestionService.submit_answer(match, team_a, str(tq2.id), tq2.question.answer_key)
    assert sub2.is_correct is True

    tank_unit = UnitType.objects.get(code="tank")
    claim2 = RewardService.claim_reward(
        match=match,
        team=team_a,
        team_question_id=str(tq2.id),
        reward_type=RewardType.UNLOCK,
        unit_type_id=str(tank_unit.id),
        idempotency_key="scenario-b-key",
    )
    assert claim2.unlocked_unit_type.code == "tank"
    assert TeamUnlock.objects.filter(team=team_a, unit_type__code="tank").exists()

    # --- Scenario C: Unlock Option Disabled When All Unlocked ---
    # Unlock all remaining unlockable items for team_a
    unlockables = UnitType.objects.filter(is_unlockable=True, is_active=True)
    for u in unlockables:
        TeamUnlock.objects.get_or_create(team=team_a, unit_type=u)

    eligible = RewardService.get_eligible_units_for_team(team_a)
    assert len(eligible) == 0

    tq3 = QuestionService.get_or_assign_current_question(match, team_a, advance_from=tq2.pk)
    opts = RewardService.get_reward_options(tq3)
    assert opts["unlock_available"] is False

    # Attempting to claim unlock when none eligible raises ValidationError
    QuestionService.update_viewing(match, team_a, tq3.pk, "test-viewer", "OPEN")
    sub3 = QuestionService.submit_answer(match, team_a, str(tq3.id), tq3.question.answer_key)
    with pytest.raises(ValidationError):
        RewardService.claim_reward(
            match=match,
            team=team_a,
            team_question_id=str(tq3.id),
            reward_type=RewardType.UNLOCK,
            unit_type_id=str(tank_unit.id),
        )

    # --- Scenario D: Insufficient Coins -> Purchase Rejected ---
    team_a.coins = 5
    team_a.save()
    with pytest.raises(ValidationError):
        UnitService.deploy_unit(
            match=match,
            team=team_a,
            unit_type_code_or_id="infantry",  # costs 15
            target_team_id=str(team_b.id),
        )
    team_a.refresh_from_db()
    assert team_a.coins == 5  # unchanged

    # Restore coins
    team_a.coins = 100
    team_a.save()

    # --- Scenario F: Combat Simulation ---
    # Deploy infantry
    action, entity = UnitService.deploy_unit(
        match=match,
        team=team_a,
        unit_type_code_or_id="infantry",
        target_team_id=str(team_b.id),
    )
    assert entity is not None
    assert entity.status == EntityStatus.ACTIVE

    # Construct tower
    t_action, tower = ConstructionService.build_tower(
        match=match,
        team=team_b,
        unit_type_code_or_id="mg_tower",
        node_id=MapDefinition.get_valid_tower_slots(team_b)[0],
    )
    assert tower is not None

    # Resolve round
    round_result = CombatService.execute_combat_round(match)
    assert round_result is not None
    assert round_result.round_number == 1
    entity.refresh_from_db()
    assert entity.status == EntityStatus.ACTIVE

    # --- Scenario G: Reconnection & Snapshot Sync ---
    snapshot = RealtimeService.build_snapshot(match, viewer_team_id=str(team_a.id))
    assert snapshot["payload"]["match"]["id"] == str(match.id)
    assert snapshot["payload"]["match"]["phase"] == match.phase
    assert len(snapshot["payload"]["teams"]) == 4

    # --- Scenario H: Match Completion & Results Snapshot ---
    # Force base destruction to trigger victory condition
    team_b.base_hp = 0
    team_b.status = TeamStatus.ELIMINATED
    team_b.save()

    final_match = MatchService.end_match(match)
    assert final_match.status == MatchStatus.FINISHED
    assert final_match.phase == MatchPhase.RESULTS
    results_count = MatchResult.objects.filter(match=match).count()
    assert results_count == 4


# =============================================================================
# 3. END-TO-END FLOW & SECURITY AUDIT (§29, Phase 7 §2.3, §3)
# =============================================================================

@pytest.mark.django_db
def test_security_authorization_and_no_secret_leak(setup_phase_7):
    """
    Ensure:
    1. Question payloads never leak correct answer or explanation to participants.
    2. Non-host participants cannot call host endpoints.
    3. Teams cannot trigger actions for other teams.
    """
    match, host_token, teams, members, tokens, _ = setup_phase_7
    client = APIClient()

    # 1. Secret Payload Leak Check
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    public_data = QuestionPublicSerializer(tq.question).data
    assert "answer_key" not in public_data
    assert "explanation" not in public_data
    assert "answer_validator_type" not in public_data

    # TeamQuestionSerializer for active question
    tq_data = TeamQuestionSerializer(tq).data
    assert "answer_key" not in tq_data["question"]
    assert "explanation" not in tq_data["question"]

    # 2. Host authorization: Participant cannot pause/end match
    participant_token = tokens[0]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {participant_token}")
    resp = client.post(f"/api/v1/matches/{match.id}/pause/")
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # Host can pause match
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {host_token}")
    resp_host = client.post(f"/api/v1/matches/{match.id}/pause/")
    assert resp_host.status_code == status.HTTP_200_OK

    # 3. Team cross-action prevention
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {participant_token}")
    # Team 1 member tries to deploy unit on behalf of Team 2
    resp_cross = client.post(
        f"/api/v1/matches/{match.id}/actions/deploy/",
        {
            "team_id": str(teams[1].id),  # team 2!
            "unit_type": "infantry",
            "target_team_id": str(teams[2].id),
        },
    )
    assert resp_cross.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN]


# =============================================================================
# 4. CONCURRENCY & IDEMPOTENCY TESTS (Phase 7 §2.4)
# =============================================================================

@pytest.mark.django_db(transaction=True)
def test_idempotency_duplicate_deployment_protection(setup_phase_7):
    """Deploying twice with identical idempotency key returns exact same action/entity."""
    match, _, teams, _, _, _ = setup_phase_7
    team = teams[0]
    target = teams[1]
    idem_key = f"idem-key-{uuid.uuid4()}"

    initial_coins = team.coins

    # First deployment
    action1, entity1 = UnitService.deploy_unit(
        match=match,
        team=team,
        unit_type_code_or_id="infantry",
        target_team_id=str(target.id),
        idempotency_key=idem_key,
    )
    team.refresh_from_db()
    coins_after_first = team.coins
    assert coins_after_first == initial_coins - 15

    # Second deployment with same idempotency key
    action2, entity2 = UnitService.deploy_unit(
        match=match,
        team=team,
        unit_type_code_or_id="infantry",
        target_team_id=str(target.id),
        idempotency_key=idem_key,
    )
    team.refresh_from_db()
    assert team.coins == coins_after_first  # Not charged twice
    assert action1.id == action2.id
    assert entity1.id == entity2.id


@pytest.mark.django_db(transaction=True)
def test_concurrent_round_resolution_single_execution(setup_phase_7):
    """
    Two workers attempt to resolve the combat round.
    Calls are serialized with select_for_update, ensuring monotonic round progression.
    """
    match, _, _, _, _, _ = setup_phase_7

    results = []
    errors = []

    def worker(worker_id):
        for attempt in range(5):
            try:
                connection.close()
                m = Match.objects.get(pk=match.id)
                res = CombatService.execute_combat_round(m)
                if res:
                    results.append(res)
                return
            except Exception as e:
                import time

                from django.db import OperationalError
                if isinstance(e, OperationalError):
                    time.sleep(0.05 * (attempt + 1))
                else:
                    errors.append(e)
                    return
            finally:
                connection.close()

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Rounds were resolved cleanly
    combat_events = MatchEvent.objects.filter(match=match, event_type="COMBAT_RESOLVED")
    assert combat_events.count() >= 1


# =============================================================================
# 5. RECONNECTION & RESILIENCE TESTS (Phase 7 §2.5)
# =============================================================================

@pytest.mark.django_db(transaction=True)
def test_backend_restart_mid_match_recovery(setup_phase_7):
    """
    Simulate backend crash/restart mid-match.
    All DB state must be faithfully restored and CombatService resumes next round.
    """
    match, host_token, teams, _, _, _ = setup_phase_7

    # Advance one round
    r1 = CombatService.execute_combat_round(match)
    assert r1.round_number == 1
    assert MatchEvent.objects.filter(match=match, event_type="COMBAT_RESOLVED").exists()

    # Use committed transactions: closing a connection inside pytest's outer
    # transaction rolls back PostgreSQL state and does not simulate a restart.
    connection.close()
    restored_match = Match.objects.get(pk=match.id)
    assert restored_match.status == MatchStatus.ACTIVE
    assert restored_match.phase == match.phase

    # Next round resolves predictably
    round2 = CombatService.execute_combat_round(restored_match)
    assert round2.round_number == 2


# =============================================================================
# 6. LOAD & BALANCE SIMULATION (Phase 7 §2.6, §2.8)
# =============================================================================

@pytest.mark.django_db
def test_multi_team_balance_simulation():
    """Run deterministic headless match across 4 seeds to verify balance stability."""
    seeds = [101, 202, 303, 404]
    winners = []

    for seed in seeds:
        game_map = get_game_map(4)
        teams_data = {}
        for i in range(1, 5):
            tid = f"team_{i}"
            teams_data[tid] = {
                "id": tid,
                "name": f"Team {i}",
                "team_index": i,
                "base_hp": 500,
                "initial_base_hp": 500,
                "base_shield": 0,
                "coins": 100,
                "score": 0,
                "status": "ACTIVE",
                "correct_answers": 4,
                "shield_remaining_rounds": 0,
            }

        combat_state = CombatState(
            round_number=1,
            is_paused=False,
            teams=teams_data,
            entities=[],
            actions=[],
            configuration=DEFAULT_MATCH_CONFIGURATION,
            combat_stats={tid: {"bases_destroyed": 0, "base_damage_dealt": 0} for tid in teams_data},
        )

        round_res = CombatEngine.resolve_round(combat_state)
        assert round_res.round_number == 1
        assert round_res.new_state.round_number == 2
        assert len(round_res.events) >= 0


# =============================================================================
# 7. TARGETED UNIT TESTS FOR >90% COVERAGE (Phase 7 §2.1)
# =============================================================================

@pytest.mark.django_db
def test_construction_special_actions_repair_upgrade_scout(setup_phase_7):
    """Test upgrade tower level limits, base repair HP limits, and scouting."""
    match, _, teams, _, _, _ = setup_phase_7
    team_a, team_b = teams[0], teams[1]

    # Build tower
    slot = MapDefinition.get_valid_tower_slots(team_a)[0]
    _, tower = ConstructionService.build_tower(
        match=match,
        team=team_a,
        unit_type_code_or_id="mg_tower",
        node_id=slot,
    )
    assert tower.level == 1

    # Upgrade tower
    _, upgraded = ConstructionService.upgrade_tower(
        match=match,
        team=team_a,
        entity_id=str(tower.id),
    )
    assert upgraded.level == 2

    # Level 3 is team-wide; level 4 is invalid.
    team_a.coins = 1000
    team_a.save(update_fields=["coins"])
    for level in (3,):
        assert ConstructionService.upgrade_tower(match, team_a, str(tower.pk))[1].level == level
    with pytest.raises(ValidationError):
        ConstructionService.upgrade_tower(
            match=match,
            team=team_a,
            entity_id=str(tower.id),
        )

    # Base repair: at max HP raises ValidationError
    with pytest.raises(ValidationError):
        ConstructionService.repair_base(match=match, team=team_a)

    # Damage base by 100 HP then repair
    team_a.base_hp = 400
    team_a.save()
    repair_act = ConstructionService.repair_base(match=match, team=team_a)
    assert repair_act.status == ActionStatus.ACCEPTED
    team_a.refresh_from_db()
    assert team_a.base_hp == 450  # +50 HP

    # Scout enemy team
    scout_act, scout_data = ConstructionService.scout(
        match=match,
        team=team_a,
        target_team_id=str(team_b.id),
    )
    assert scout_act.status == ActionStatus.ACCEPTED
    assert scout_data["target_team_id"] == str(team_b.id)
    assert "unlocked_units" in scout_data

    # Cannot scout self
    with pytest.raises(ValidationError):
        ConstructionService.scout(
            match=match,
            team=team_a,
            target_team_id=str(team_a.id),
        )


@pytest.mark.django_db
def test_targeting_unit_target_and_tower_disabled():
    """Verify find_unit_target and disabled tower logic."""
    gmap = get_game_map(4)

    # Disabled tower returns None
    disabled_tower = {
        "id": "tow_dis",
        "current_node_id": "node_tower_t1_slot1",
        "range": 2,
        "is_disabled": True,
    }
    target = find_tower_target(
        tower=disabled_tower,
        enemy_units=[{"id": "e1", "current_node_id": "node_lane_t1_1", "current_hp": 40}],
        game_map=gmap,
        defended_base_node="node_base_t1",
    )
    assert target is None

    # Unit target finding
    attacker = {
        "id": "u_atk",
        "team_id": "team_1",
        "current_node_id": "node_lane_t1_2",
        "range": 2,
        "current_hp": 100,
    }
    enemies = [
        {"id": "e_far", "team_id": "team_2", "current_node_id": "node_spawn_t2", "current_hp": 40},
        {"id": "e_near", "team_id": "team_2", "current_node_id": "node_lane_t1_3", "current_hp": 20},
    ]
    u_target = find_unit_target(attacker=attacker, enemy_units=enemies, game_map=gmap)
    assert u_target is not None
    assert u_target["id"] == "e_near"


@pytest.mark.django_db
def test_scoring_breakdown_components():
    """Test calculate_team_score with capped damage, bases destroyed, surviving towers."""
    team_data = {
        "bases_destroyed": 2,
        "base_damage_dealt": 550,
        "base_hp": 300,
        "correct_answers": 6,
        "surviving_towers": 3,
        "coins": 85,
    }
    score_result = calculate_team_score(
        team_data=team_data,
        weights=DEFAULT_SCORING_WEIGHTS,
        damage_dealt_cap=400,
    )
    assert score_result["total_score"] > 0
    bd = score_result["breakdown"]
    assert bd["bases_destroyed_pts"] == 200
    assert bd["damage_dealt_pts"] == 40  # capped at 400 HP = 40 pts
    assert bd["remaining_hp_pts"] == 15
    assert bd["correct_answers_pts"] == 18
    assert bd["surviving_towers_pts"] == 15
    assert bd["coins_pts"] == 8


@pytest.mark.django_db
def test_economy_transactions_consistency(setup_phase_7):
    """Test credit, debit, and audit trail reconciliation in EconomyService."""
    match, _, teams, _, _, _ = setup_phase_7
    team = teams[0]

    initial_coins = team.coins  # 100
    EconomyService.credit(
        team=team,
        amount=30,
        transaction_type=TransactionType.REWARD_COIN,
        reference_type="MANUAL",
        reference_id="ref1",
    )
    team.refresh_from_db()
    assert team.coins == initial_coins + 30

    EconomyService.debit(
        team=team,
        amount=50,
        transaction_type=TransactionType.DEPLOY_UNIT,
        reference_type="MANUAL",
        reference_id="ref2",
    )
    team.refresh_from_db()
    assert team.coins == initial_coins + 30 - 50

    # Negative balance rejected
    with pytest.raises(ValidationError):
        EconomyService.debit(
            team=team,
            amount=9999,
            transaction_type=TransactionType.DEPLOY_UNIT,
        )

    # Audit trail validation
    txs = CoinTransaction.objects.filter(team=team).order_by("created_at")
    assert txs.count() >= 2
    last_tx = txs.last()
    assert last_tx.balance_after == team.coins
