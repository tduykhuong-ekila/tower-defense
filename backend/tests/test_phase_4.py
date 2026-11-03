"""
Comprehensive Test Suite for Phase 4 — Combat Engine, Map, Victory & Scoring (§9, §10, §12, §13 FR-07, §19.12-19.13, §28 Scenario F, H).
"""

import pytest
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APIClient

from apps.combat.damage import apply_damage_to_base, calculate_damage
from apps.combat.engine import CombatEngine, CombatState
from apps.combat.map import get_game_map
from apps.combat.models import MatchResult
from apps.combat.scoring import ScoringService, calculate_team_score, rank_teams
from apps.combat.services import CombatService
from apps.matches.defaults import DEFAULT_MATCH_CONFIGURATION, DEFAULT_SCORING_WEIGHTS
from apps.matches.models import MatchPhase, MatchStatus
from apps.matches.services import MatchService, hash_token
from apps.teams.models import MemberRole, Team, TeamMember, TeamStatus
from apps.units.models import (
    EntityStatus,
)
from apps.units.seeds import ensure_standard_units
from apps.units.services import ConstructionService, UnitService


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def setup_match():
    """Create an active match with 4 teams, 8 members, and standard units seeded."""
    ensure_standard_units()
    match, host_token = MatchService.create_match(name="Combat Arena Phase 4", configuration={"gameplay_mode": "LEGACY", "tower_placement_version":0, "arena_layout_version":5})
    teams = []
    plain_tokens = []

    for i in range(4):
        team = Team.objects.create(match=match, name=f"Team {chr(65 + i)}")
        pt1 = f"pt_mentor_p4_{i}"
        TeamMember.objects.create(
            match=match,
            team=team,
            display_name=f"Mentor-{i}",
            role=MemberRole.MENTOR,
            token_hash=hash_token(pt1),
        )
        pt2 = f"pt_mentee_p4_{i}"
        TeamMember.objects.create(
            match=match,
            team=team,
            display_name=f"Mentee-{i}",
            role=MemberRole.MENTEE,
            token_hash=hash_token(pt2),
        )
        team.is_ready = True
        team.save()
        teams.append(team)
        plain_tokens.append(pt1)

    started_match = MatchService.start_match(match)
    return started_match, host_token, teams, plain_tokens


# ==============================================================================
# 1. Map Tests (§9.1, §9.2)
# ==============================================================================

def test_map_reachability_and_no_orphan_nodes():
    """
    §9.1, §4.1: Test map graph topology for 4, 6, and 8 teams:
    - Every base is reachable from every other team's spawn point.
    - No orphan nodes (every node has degree >= 1).
    - Impassable barrier nodes are never traversed by movement paths.
    """
    for n_teams in [4, 6, 8]:
        gmap = get_game_map(n_teams)
        is_valid, errors = gmap.validate_map()
        assert is_valid, f"Validation failed for {n_teams} teams: {errors}"
        assert len(errors) == 0

        # Check reachability and path progression
        for s in range(1, n_teams + 1):
            spawn = gmap.get_spawn_node(s)
            for t in range(1, n_teams + 1):
                if s == t:
                    continue
                path = gmap.get_path_to_base(spawn, t)
                assert len(path) >= 5, f"Path from {spawn} to base {t} is too short"
                assert path[0] == spawn
                assert path[-1] == gmap.attack_position(gmap.get_base_node(t))

                # Verify no barrier nodes in movement path
                for node_id in path:
                    assert not node_id.startswith("node_barrier_"), "Movement path contains barrier node!"
                    assert gmap.nodes[node_id].is_passable or gmap.nodes[node_id].node_type == "spawn"

        # Check tower slots per team
        for i in range(1, n_teams + 1):
            for slot_i in range(1, 4):
                tower_node = f"node_tower_t{i}_slot{slot_i}"
                assert tower_node in gmap.nodes
                # Tower must be adjacent to at least one lane node
                adj = gmap.adjacency[tower_node]
                assert any("lane" in neighbor or "center" in neighbor for neighbor in adj)


# ==============================================================================
# 2. Damage Formula & Multipliers (§10.2, §10.4)
# ==============================================================================

def test_damage_formula_and_upgraded_tower_multiplier():
    """
    §10.2: final_damage = max(1, floor(base_damage * multiplier)).
    Default multiplier = 1.0, upgraded tower = 1.25.
    Minimum damage is always >= 1.
    """
    # 1. Base damage 10 with 1.0 multiplier -> 10
    assert calculate_damage(10, 1.0) == 10

    # 2. MG Tower (damage 15) upgraded (1.25) -> floor(15 * 1.25) = floor(18.75) = 18
    assert calculate_damage(15, 1.25) == 18

    # 3. Cannon Tower (damage 30) upgraded (1.25) -> floor(30 * 1.25) = 37
    assert calculate_damage(30, 1.25) == 37

    # 4. Tiny damage with fractional multiplier -> min 1
    assert calculate_damage(1, 0.1) == 1
    assert calculate_damage(0, 1.0) == 1


def test_shield_absorption_cooldown_and_no_negative_hp():
    """
    §10.4, D7: Base shield absorbs damage first, then HP.
    HP never drops below 0.
    """
    # Case A: Shield absorbs all damage
    s_abs, hp_dmg, new_s, new_hp = apply_damage_to_base(current_hp=500, current_shield=40, incoming_damage=25)
    assert s_abs == 25
    assert hp_dmg == 0
    assert new_s == 15
    assert new_hp == 500

    # Case B: Shield partially absorbs, remainder penetrates to HP
    s_abs, hp_dmg, new_s, new_hp = apply_damage_to_base(current_hp=500, current_shield=40, incoming_damage=60)
    assert s_abs == 40
    assert hp_dmg == 20
    assert new_s == 0
    assert new_hp == 480

    # Case C: Overkill damage does not reduce HP below 0
    s_abs, hp_dmg, new_s, new_hp = apply_damage_to_base(current_hp=30, current_shield=10, incoming_damage=100)
    assert s_abs == 10
    assert hp_dmg == 30
    assert new_s == 0
    assert new_hp == 0


# ==============================================================================
# 3. Movement Progression & Enemy Blocking (§9.2, D8)
# ==============================================================================

def test_movement_progression_and_enemy_blocking():
    """
    §9.2:
    - Unit advances according to movement speed along predefined path.
    - If next node is occupied by an enemy unit, unit is blocked and cannot advance.
    """
    gmap = get_game_map(4)
    # Path from Team 1 spawn to Team 2 base:
    # ['node_spawn_t1', 'node_lane_t1_2', 'node_lane_t1_3', 'node_center_ring_t1', ...]
    path = gmap.get_path_to_base(gmap.get_spawn_node(1), 2)

    team1_unit = {
        "id": "u1",
        "team_id": "team_1",
        "unit_type_code": "infantry",
        "entity_kind": "UNIT",
        "current_hp": 40,
        "current_shield": 0,
        "level": 1,
        "status": "ACTIVE",
        "current_node_id": path[0],  # node_spawn_t1
        "target_team_id": "team_2",
        "movement": 1,
        "range": 1,
        "damage": 10,
    }

    active_teams = {
        "team_1": {"status": "ACTIVE", "base_hp": 500, "team_index": 1},
        "team_2": {"status": "ACTIVE", "base_hp": 500, "team_index": 2},
    }

    # Round 1 movement: unit moves from path[0] to path[1]
    from apps.combat.movement import resolve_units_movement
    units, events = resolve_units_movement([team1_unit], active_teams, gmap)
    assert units[0]["current_node_id"] == path[1]
    assert len(events) == 1
    assert events[0]["from_node"] == path[0]
    assert events[0]["to_node"] == path[1]

    # Blocking rule test: Place an enemy unit on path[2]
    enemy_unit = {
        "id": "u_enemy",
        "team_id": "team_2",
        "unit_type_code": "tank",
        "entity_kind": "UNIT",
        "current_hp": 120,
        "status": "ACTIVE",
        "current_node_id": path[2],  # Next node on path
        "movement": 0,  # Enemy is standing still
    }

    units_blocked, events_blocked = resolve_units_movement(
        [units[0], enemy_unit], active_teams, gmap
    )
    # Unit 1 should be blocked and remain at path[1]
    u1_updated = next(u for u in units_blocked if u["id"] == "u1")
    assert u1_updated["current_node_id"] == path[1], "Unit 1 should have been blocked by enemy unit!"


def test_target_invalidation_and_fallback_policy():
    """
    §9.4, D8: When target base is eliminated:
    - RETARGET_NEAREST: unit automatically retargets closest surviving active enemy base.
    - IDLE: unit remains idle.
    """
    gmap = get_game_map(4)
    unit = {
        "id": "u1",
        "team_id": "team_1",
        "status": "ACTIVE",
        "current_hp": 40,
        "current_node_id": "node_lane_t1_3",
        "target_team_id": "team_2",
        "movement": 1,
    }

    # Team 2 is ELIMINATED (HP 0)
    active_teams = {
        "team_1": {"status": "ACTIVE", "base_hp": 500, "team_index": 1},
        "team_2": {"status": "ELIMINATED", "base_hp": 0, "team_index": 2},
        "team_3": {"status": "ACTIVE", "base_hp": 500, "team_index": 3},
        "team_4": {"status": "ACTIVE", "base_hp": 500, "team_index": 4},
    }

    from apps.combat.movement import resolve_unit_target
    enemy_active = {tid: t for tid, t in active_teams.items() if tid != "team_1"}

    # Policy 1: RETARGET_NEAREST
    new_target, new_base = resolve_unit_target(unit, enemy_active, "RETARGET_NEAREST", gmap)
    assert new_target in ["team_3", "team_4"], "Unit should retarget an active team"
    assert new_target != "team_2", "Unit should not target eliminated team"

    # Policy 2: IDLE
    new_target_idle, new_base_idle = resolve_unit_target(unit, enemy_active, "IDLE", gmap)
    assert new_target_idle is None
    assert new_base_idle is None


# ==============================================================================
# 4. Pure Combat Engine 12-Step Deterministic Execution (§10.1, D5)
# ==============================================================================

def test_engine_tower_targeting_d5_priority_and_range():
    """
    §10.3, D5: Tower targets enemy unit closest to defended base (fewer remaining hops).
    Tie-breaker: smaller entity.id. Tower does not attack outside range.
    """
    gmap = get_game_map(4)
    defended_base_node = gmap.get_base_node(2)  # Team 2 base

    tower = {
        "id": "tower_1",
        "team_id": "team_2",
        "unit_type_code": "mg_tower",
        "entity_kind": "TOWER",
        "level": 1,
        "damage": 15,
        "range": 2,
        "status": "ACTIVE",
        "current_node_id": "node_tower_t2_slot1",
        "is_disabled": False,
    }

    # Candidate A: at node_lane_t2_2 (distance to base is 2 hops)
    enemy_a = {
        "id": "enemy_z_close",
        "team_id": "team_1",
        "entity_kind": "UNIT",
        "current_hp": 40,
        "current_shield": 0,
        "status": "ACTIVE",
        "current_node_id": "node_lane_t2_1",  # 1 hop to base
    }

    # Candidate B: at node_lane_t2_3 (distance to base is 3 hops)
    enemy_b = {
        "id": "enemy_a_far",
        "team_id": "team_1",
        "entity_kind": "UNIT",
        "current_hp": 40,
        "current_shield": 0,
        "status": "ACTIVE",
        "current_node_id": "node_lane_t2_2",  # 2 hops to base
    }

    from apps.combat.targeting import find_tower_target
    target = find_tower_target(tower, [enemy_b, enemy_a], gmap, defended_base_node)
    assert target is not None
    assert target["id"] == "enemy_z_close", "D5: Tower must target unit closest to base, even if entity ID is alphabetically later"

    # Out of range test: Unit far away in Team 3 territory
    enemy_far = {
        "id": "enemy_far",
        "team_id": "team_3",
        "entity_kind": "UNIT",
        "current_hp": 40,
        "status": "ACTIVE",
        "current_node_id": "node_lane_t3_1",
    }
    target_out_of_range = find_tower_target(tower, [enemy_far], gmap, defended_base_node)
    assert target_out_of_range is None, "Tower cannot shoot units out of range"


def test_determinism_identical_runs():
    """
    §10.5, Phase 4 §4: Same initial CombatState executed across multiple runs
    produces bit-for-bit identical results and event sequence.
    """
    state = CombatState(
        round_number=1,
        is_paused=False,
        teams={
            "t1": {"id": "t1", "name": "Team 1", "team_index": 1, "base_hp": 500, "base_shield": 0, "coins": 100, "status": "ACTIVE"},
            "t2": {"id": "t2", "name": "Team 2", "team_index": 2, "base_hp": 500, "base_shield": 0, "coins": 100, "status": "ACTIVE"},
            "t3": {"id": "t3", "name": "Team 3", "team_index": 3, "base_hp": 500, "base_shield": 0, "coins": 100, "status": "ACTIVE"},
            "t4": {"id": "t4", "name": "Team 4", "team_index": 4, "base_hp": 500, "base_shield": 0, "coins": 100, "status": "ACTIVE"},
        },
        entities=[
            {
                "id": "e_u1",
                "team_id": "t1",
                "unit_type_code": "infantry",
                "entity_kind": "UNIT",
                "current_hp": 40,
                "max_hp": 40,
                "current_shield": 0,
                "level": 1,
                "status": "ACTIVE",
                "current_node_id": "node_lane_t2_2",
                "target_team_id": "t2",
                "movement": 1,
                "range": 1,
                "damage": 10,
            },
            {
                "id": "e_tow1",
                "team_id": "t2",
                "unit_type_code": "mg_tower",
                "entity_kind": "TOWER",
                "current_hp": 100,
                "max_hp": 100,
                "current_shield": 0,
                "level": 1,
                "status": "ACTIVE",
                "current_node_id": "node_tower_t2_slot1",
                "target_team_id": None,
                "movement": 0,
                "range": 2,
                "damage": 15,
            },
        ],
        actions=[],
        configuration={**DEFAULT_MATCH_CONFIGURATION, "arena_layout_version": 4},
    )

    baseline_res = CombatEngine.resolve_round(state)

    for _ in range(50):
        test_res = CombatEngine.resolve_round(state)
        assert test_res.round_number == baseline_res.round_number
        assert test_res.eliminated_team_ids == baseline_res.eliminated_team_ids
        assert test_res.winner_team_id == baseline_res.winner_team_id
        assert len(test_res.events) == len(baseline_res.events)
        for i in range(len(test_res.events)):
            assert test_res.events[i] == baseline_res.events[i]


# ==============================================================================
# 5. Scoring & Tie-Breaking (§12, D6, D11)
# ==============================================================================

def test_scoring_weights_capping_and_tie_breaking():
    """
    §12.2, §12.3, D6, D11:
    - Scoring weights:
      - enemy base destroyed: +100
      - damage dealt: +10 per 100 HP
      - remaining HP: +5 per 100 HP
      - correct answer: +3
      - surviving tower: +5
      - coins: +1 per 10 coins
    - D11: damage dealt capped at total initial enemy base HP.
    - Tie-breaking: Score > Bases destroyed > Remaining HP > Coins > Shared rank.
    """
    weights = DEFAULT_SCORING_WEIGHTS

    team_data = {
        "bases_destroyed": 2,       # 2 * 100 = 200
        "base_damage_dealt": 750,    # floor(750/100) * 10 = 70
        "base_hp": 450,              # floor(450/100) * 5 = 20
        "correct_answers": 5,        # 5 * 3 = 15
        "surviving_towers": 2,       # 2 * 5 = 10
        "coins": 35,                 # floor(35/10) * 1 = 3
    }
    score_res = calculate_team_score(team_data, weights)
    # Expected total: 200 + 70 + 20 + 15 + 10 + 3 = 318
    assert score_res["total_score"] == 318
    assert score_res["breakdown"]["bases_destroyed_pts"] == 200
    assert score_res["breakdown"]["damage_dealt_pts"] == 70
    assert score_res["breakdown"]["remaining_hp_pts"] == 20
    assert score_res["breakdown"]["correct_answers_pts"] == 15
    assert score_res["breakdown"]["surviving_towers_pts"] == 10
    assert score_res["breakdown"]["coins_pts"] == 3

    # D11: Cap test
    capped_res = calculate_team_score(
        {"bases_destroyed": 1, "base_damage_dealt": 5000, "base_hp": 500, "correct_answers": 0, "surviving_towers": 0, "coins": 0},
        weights,
        damage_dealt_cap=1500,
    )
    # Damage dealt should be capped at 1500 -> floor(1500/100)*10 = 150
    assert capped_res["base_damage_dealt"] == 1500
    assert capped_res["breakdown"]["damage_dealt_pts"] == 150

    # Tie-breaking test (§12.3, D6)
    teams_stats = [
        # Team B: lower score
        {"id": "tB", "name": "Team B", "total_score": 200, "bases_destroyed": 1, "base_hp": 500, "coins": 50},
        # Team A: higher score
        {"id": "tA", "name": "Team A", "total_score": 300, "bases_destroyed": 1, "base_hp": 400, "coins": 20},
        # Team C: same score as Team D, but more bases destroyed
        {"id": "tC", "name": "Team C", "total_score": 250, "bases_destroyed": 2, "base_hp": 100, "coins": 10},
        {"id": "tD", "name": "Team D", "total_score": 250, "bases_destroyed": 1, "base_hp": 300, "coins": 10},
    ]
    ranked = rank_teams(teams_stats, weights)
    assert ranked[0]["id"] == "tA" and ranked[0]["final_rank"] == 1
    assert ranked[1]["id"] == "tC" and ranked[1]["final_rank"] == 2
    assert ranked[2]["id"] == "tD" and ranked[2]["final_rank"] == 3
    assert ranked[3]["id"] == "tB" and ranked[3]["final_rank"] == 4


# ==============================================================================
# 6. Scenario F: Full Combat Loop (§28 Scenario F)
# ==============================================================================

@pytest.mark.django_db
def test_scenario_f_full_combat_loop(setup_match):
    """
    §28 Scenario F:
    1. Team A deploys a unit targeting Team B.
    2. Unit advances through the lane.
    3. Team B's tower attacks unit when in range.
    4. Unit HP is updated.
    5. Infantry stops to attack Team B's tower before damaging the base.
    """
    match, host_token, teams, plain_tokens = setup_match
    team_a = teams[0]
    team_b = teams[1]

    # 1. Build a tower for Team B on slot 1 (covers lane 1 & 2)
    tower_action, tower_entity = ConstructionService.build_tower(
        match=match,
        team=team_b,
        unit_type_code_or_id="mg_tower",
        node_id="node_tower_t2_slot1",
    )
    assert tower_entity.status == EntityStatus.ACTIVE

    # 2. Deploy Infantry for Team A targeting Team B
    deploy_action, unit_entity = UnitService.deploy_unit(
        match=match,
        team=team_a,
        unit_type_code_or_id="infantry",
        target_team_id=str(team_b.id),
    )
    assert unit_entity.status == EntityStatus.ACTIVE

    # 3. Fast forward unit to node_lane_t2_2 (right in front of tower) to observe combat resolution
    unit_entity.status = EntityStatus.ACTIVE
    unit_entity.current_node_id = "node_lane_t2_2"
    unit_entity.save()

    # Initial Team B base HP
    assert team_b.base_hp == 500

    # 4. Execute combat round via authoritative CombatService
    round_result = CombatService.execute_combat_round(match)
    assert round_result.round_number == 1

    unit_entity.refresh_from_db()
    tower_entity.refresh_from_db()
    team_b.refresh_from_db()

    assert unit_entity.status == EntityStatus.ACTIVE
    assert unit_entity.current_node_id == "node_lane_t2_2"
    assert tower_entity.current_hp == tower_entity.max_hp - 10
    assert team_b.base_hp == 500

    # Verify event trail
    event_types = [e["type"] for e in round_result.events]
    # Graph adjacency alone no longer authorizes a tower shot: the unit must
    # also be inside the physical ellipse displayed on the battlefield.
    from apps.combat.continuous import target_distance
    from apps.combat.balance import entity_attack_range
    graph = get_game_map(4, match.configuration.get("arena_layout_version", 3))
    tower_data = {"entity_kind": "TOWER", "current_node_id": tower_entity.current_node_id,
                  "simulation_state": tower_entity.simulation_state}
    unit_data = {"current_node_id": unit_entity.current_node_id,
                 "simulation_state": unit_entity.simulation_state}
    assert ("TOWER_ATTACKED" in event_types) == (target_distance(tower_data, unit_data, graph) <= entity_attack_range(tower_entity))
    assert "UNIT_ATTACKED" in event_types
    assert "BASE_DAMAGED" not in event_types
    assert "COMBAT_RESOLVED" in event_types


# ==============================================================================
# 7. Scenario H: Match Completion & Immutable Snapshot (§28 Scenario H)
# ==============================================================================

@pytest.mark.django_db
def test_scenario_h_match_completion_and_results(setup_match):
    """
    §28 Scenario H, §19.13:
    1. Base is destroyed or timer expires.
    2. Server finalizes the match.
    3. Scores are calculated.
    4. Immutable MatchResult snapshot is persisted.
    5. Second call to finalize is idempotent and returns existing snapshot.
    """
    match, host_token, teams, plain_tokens = setup_match

    # Set team A as the dominant survivor, destroy others
    teams[0].base_hp = 450
    teams[0].save()
    for t in teams[1:]:
        t.base_hp = 0
        t.status = TeamStatus.ELIMINATED
        t.save()

    # Finalize match
    results = ScoringService.finalize_match(match)
    match.refresh_from_db()

    assert match.status == MatchStatus.FINISHED
    assert match.phase == MatchPhase.RESULTS
    assert len(results) == 4
    assert MatchResult.objects.filter(match=match).count() == 4

    # Winner must be Rank 1
    rank_1 = MatchResult.objects.get(match=match, final_rank=1)
    assert rank_1.team_id == teams[0].id

    # Idempotency check: calling finalize again returns exact same objects
    results_second = ScoringService.finalize_match(match)
    assert len(results_second) == 4
    assert [r.id for r in results_second] == [r.id for r in results]


# ==============================================================================
# 8. Idempotency & Pause Guarantees (§10.5, §11)
# ==============================================================================

@pytest.mark.django_db
def test_pause_freezes_combat_and_passive_income(setup_match):
    """
    §11, Phase 4 §4:
    - When match is PAUSED, execute_combat_round raises ValidationError.
    - Pure engine with is_paused=True grants NO passive income.
    """
    match, host_token, teams, _ = setup_match

    # Pause match
    MatchService.pause_match(match)
    match.refresh_from_db()
    assert match.status == MatchStatus.PAUSED

    # Attempting to resolve round while paused must be rejected
    with pytest.raises(ValidationError) as exc:
        CombatService.execute_combat_round(match)
    assert "tạm dừng" in str(exc.value)

    # Pure engine verification
    state = CombatState(
        round_number=1,
        is_paused=True,
        teams={"t1": {"status": "ACTIVE", "base_hp": 500, "coins": 50}},
        entities=[],
        actions=[],
        configuration={"base_income_per_round": 10},
    )
    res = CombatEngine.resolve_round(state)
    assert res.new_state.teams["t1"]["coins"] == 50, "Coins should not increase while paused!"


# ==============================================================================
# 9. REST API Endpoints: Results & Manual Combat Resolve (§20)
# ==============================================================================

@pytest.mark.django_db
def test_combat_api_endpoints(api_client, setup_match):
    """
    §20:
    - POST /api/v1/matches/{id}/combat/resolve/ (Host only)
    - GET /api/v1/matches/{id}/results/
    """
    match, host_token, teams, plain_tokens = setup_match

    # 1. Non-host attempt to resolve round -> 403 Forbidden
    res_forbidden = api_client.post(
        f"/api/v1/matches/{match.id}/combat/resolve/",
        HTTP_AUTHORIZATION=f"Bearer {plain_tokens[0]}",
    )
    assert res_forbidden.status_code == status.HTTP_403_FORBIDDEN

    # 2. Host resolve round -> 200 OK
    res_ok = api_client.post(
        f"/api/v1/matches/{match.id}/combat/resolve/",
        HTTP_X_HOST_TOKEN=host_token,
    )
    assert res_ok.status_code == status.HTTP_200_OK
    data = res_ok.json()
    assert data["round_number"] == 1
    assert "events" in data
    assert "is_match_over" in data

    # 3. GET /api/v1/matches/{id}/results/
    res_results = api_client.get(f"/api/v1/matches/{match.id}/results/")
    assert res_results.status_code == status.HTTP_200_OK
    res_data = res_results.json()
    assert res_data["match_id"] == str(match.id)
    assert "results" in res_data
