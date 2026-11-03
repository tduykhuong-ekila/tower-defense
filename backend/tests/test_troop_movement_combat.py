"""Independent staging, distance budgets, passing, cooldowns and durable recovery."""

import copy
import math
from datetime import datetime

import pytest

from apps.combat.balance import TROOP_MOVEMENT_SPEED, movement_speed
from apps.combat.continuous import ContinuousEngine
from apps.combat.continuous_service import ContinuousCombatService
from apps.combat.formation import (
    bodies_clear,
    initialize_spawn,
    physical_position,
    synchronize_position,
)
from apps.combat.map import get_game_map
from apps.combat.navigation import project, staging_bounds
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.units.services import UnitService
from tests.test_continuous_combat import room
from tests.test_live_battle_gameplay import convoy


def assert_clear(state):
    game_map = get_game_map(len(state.teams))
    units = [e for e in state.entities if e["entity_kind"] == "UNIT" and e["status"] != "DESTROYED"]
    for i, a in enumerate(units):
        for b in units[i + 1 :]:
            if a["team_id"] == b["team_id"] and a["unit_type_code"] != "infantry" and b["unit_type_code"] != "infantry":
                assert bodies_clear(
                    a,
                    b,
                    physical_position(a, game_map),
                    physical_position(b, game_map),
                    state.configuration,
                )


@pytest.mark.parametrize("count", [2, 4, 8, 20])
def test_five_free_staging_positions_sixth_never_reorders_and_all_enter_roads(count):
    state = convoy(("tank",) * 5, count=count)
    game_map = get_game_map(count)
    before = copy.deepcopy(state.entities)
    points = [project(physical_position(e, game_map)) for e in state.entities]
    assert len(set(points)) == 5
    assert any(
        abs(
            (b[0] - points[0][0]) * (c[1] - points[0][1])
            - (b[1] - points[0][1]) * (c[0] - points[0][0])
        )
        > 1
        for b in points[1:]
        for c in points[1:]
    )
    sixth = copy.deepcopy(state.entities[-1])
    sixth.update(id="sixth", simulation_state={})
    initialize_spawn(
        sixth, state.entities, game_map.get_base_node(2), game_map, 6, state.configuration
    )
    assert state.entities == before
    state.entities.append(sixth)
    bounds = [project(p) for p in staging_bounds(game_map, sixth["current_node_id"])]
    for e in state.entities:
        x, y = project(physical_position(e, game_map))
        assert bounds[0][0] <= x <= bounds[2][0] and bounds[0][1] <= y <= bounds[2][1]
        assert e["simulation_state"]["route_distance"] == 0
    assert_clear(state)
    for _ in range(160):
        state = ContinuousEngine.step(state, 0.1).new_state
        assert_clear(state)
        if all(e["simulation_state"]["movement_zone"] == "ROUTE" for e in state.entities):
            break
    assert all(
        e["status"] == "ACTIVE" and e["simulation_state"]["movement_zone"] == "ROUTE"
        for e in state.entities
    )


def combat_column(codes=("infantry",) * 4, lead_range=3):
    state = convoy(codes)
    state.configuration["movement_baseline_round_seconds"] = 4
    game_map = get_game_map(2)
    for e, progress in zip(state.entities, [365, 290, 215, 140]):
        e["status"] = "ACTIVE"
        sim = e["simulation_state"]
        sim.update(movement_zone="ROUTE", route_distance=progress)
        sim.pop("world_position", None)
        synchronize_position(e, game_map)
    state.entities[0]["range"] = lead_range
    state.entities.append(
        {
            "id": "enemy",
            "team_id": "b",
            "entity_kind": "TOWER",
            "unit_type_code": "mg_tower",
            "damage": 0,
            "range": 0,
            "current_hp": 10000,
            "current_shield": 0,
            "status": "ACTIVE",
            "current_node_id": "node_tower_t2_slot1",
            "simulation_state": {},
        }
    )
    return state


def test_attacking_infantry_does_not_pause_followers_and_resumes_after_target_dies():
    state = combat_column()
    game_map = get_game_map(2)
    start = {e["id"]: physical_position(e, game_map) for e in state.entities[:4]}
    lead_progress = state.entities[0]["simulation_state"]["route_distance"]
    attacks, bypassed = [], set()
    for _ in range(100):
        before = copy.deepcopy(state)
        result = ContinuousEngine.step(state, 0.1)
        state = result.new_state
        attacks.extend(result.events)
        for old, e in zip(before.entities[:4], state.entities[:4]):
            path = e["simulation_state"]["movement_path"]
            traveled = sum(
                math.dist((a["x"], a["y"]), (b["x"], b["y"])) for a, b in zip(path, path[1:])
            )
            assert traveled <= movement_speed(e, state.configuration) * 0.1 + 1e-6
            assert (
                math.dist(physical_position(old, game_map), physical_position(e, game_map))
                <= movement_speed(e, state.configuration) * 0.1 + 1e-6
            )
            if e["id"] != "u-0" and e["simulation_state"]["route_distance"] > lead_progress:
                bypassed.add(e["id"])
        assert_clear(state)
    lead = state.entities[0]
    assert lead["simulation_state"]["route_distance"] == lead_progress
    assert lead["simulation_state"]["combat_state"] == "ATTACKING"
    assert all(
        math.dist(start[e["id"]], physical_position(e, game_map)) > 10 for e in state.entities[1:4]
    )
    assert bypassed == {"u-1", "u-2", "u-3"}
    assert any(e["type"] == "UNIT_ATTACKED" and e["attacker_id"] == "u-0" for e in attacks)
    state.entities[-1].update(status="DESTROYED", current_hp=0)
    state = ContinuousEngine.step(state, 0.1).new_state
    assert state.entities[0]["simulation_state"]["route_distance"] > lead_progress
    assert state.entities[0]["simulation_state"]["combat_state"] == "IDLE"


def test_multiple_attackers_have_independent_cooldowns_while_other_units_move():
    state = combat_column(("artillery", "tank", "infantry", "infantry"))
    state.entities[1]["range"] = 4
    state.entities[0]["attack_cooldown_seconds"] = 0.7
    state.entities[1]["attack_cooldown_seconds"] = 1.1
    fired = {"u-0": [], "u-1": []}
    origins = [e["simulation_state"]["route_distance"] for e in state.entities[2:4]]
    for tick in range(24):
        result = ContinuousEngine.step(state, 0.1)
        state = result.new_state
        for event in result.events:
            if event["type"] == "UNIT_ATTACKED" and event["attacker_id"] in fired:
                fired[event["attacker_id"]].append(tick)
        assert_clear(state)
    assert fired == {"u-0": [0, 7, 14, 21], "u-1": [0, 11, 22]}
    assert all(
        e["simulation_state"]["route_distance"] > start
        for e, start in zip(state.entities[2:4], origins)
    )


def test_standard_infantry_range_stops_only_the_front_unit():
    state = combat_column(lead_range=1)
    game_map = get_game_map(2)
    for e, progress in zip(state.entities[:4], [515.9662594909163, 440, 365, 290]):
        e["simulation_state"]["route_distance"] = progress
        synchronize_position(e, game_map)
    origins = [e["simulation_state"]["route_distance"] for e in state.entities[:4]]
    attacks = []
    for _ in range(5):
        result = ContinuousEngine.step(state, 0.1)
        state = result.new_state
        attacks.extend(result.events)
        assert_clear(state)
    assert state.entities[0]["simulation_state"]["route_distance"] == origins[0]
    assert any(e["type"] == "UNIT_ATTACKED" and e["attacker_id"] == "u-0" for e in attacks)
    assert all(
        e["simulation_state"]["route_distance"] > origin
        for e, origin in zip(state.entities[1:4], origins[1:])
    )


def test_thirty_staging_units_enter_when_downstream_occupancy_clears():
    state = convoy(("infantry",) * 30)
    for team in state.teams.values():
        team["base_hp"] = 1_000_000
    entered = set()
    for _ in range(200):
        state = ContinuousEngine.step(state, 0.2).new_state
        assert_clear(state)
        for e in state.entities:
            if e["simulation_state"]["movement_zone"] == "ROUTE":
                entered.add(e["id"])
            # A finite one-file destination cannot hold 30 bodies. Release its
            # arrivals to test staging liveness independently of terminal capacity.
            if e["current_node_id"] == "node_lane_t2_1":
                e.update(status="DESTROYED", current_hp=0)
        if len(entered) == 30:
            break
    assert len(entered) == 30


def test_saved_negative_queues_admit_independently_without_teleporting():
    state = convoy(("infantry",) * 3)
    game_map = get_game_map(2)
    for e, progress in zip(state.entities, [0, -60, -120]):
        sim = e["simulation_state"]
        for key in ["movement_zone", "world_position", "staging_entry_distance", "crowd_offset"]:
            sim.pop(key, None)
        sim["route_distance"] = progress
        synchronize_position(e, game_map)
    state.entities[0]["movement"] = 0
    before = {e["id"]: physical_position(e, game_map) for e in state.entities}
    state = ContinuousEngine.step(state, 0.2).new_state
    for e in state.entities:
        assert (
            math.dist(before[e["id"]], physical_position(e, game_map))
            <= movement_speed(e, state.configuration) * 0.2 + 1e-6
        )
        assert e["simulation_state"]["route_distance"] >= 0
        assert e["current_hp"] == 100
    for _ in range(80):
        state = ContinuousEngine.step(state, 0.2).new_state
        assert_clear(state)
        if all(e["simulation_state"]["movement_zone"] == "ROUTE" for e in state.entities):
            break
    assert all(e["simulation_state"]["movement_zone"] == "ROUTE" for e in state.entities)
    assert state.entities[0]["simulation_state"]["route_distance"] == 0


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_exact_setting_four_fixed_step_equivalence_and_restored_round(code):
    factor = {"infantry": 5.5, "tank": 4, "artillery": 5}[code]
    assert TROOP_MOVEMENT_SPEED == 4
    state = convoy((code,))
    state.configuration["movement_baseline_round_seconds"] = 30
    speed = movement_speed(state.entities[0], state.configuration)
    assert speed == pytest.approx(
        state.entities[0]["movement"]
        * state.entities[0]["simulation_state"]["reference_hop_length"]
        / 30
        * factor
    )
    for dt in [0.05, 0.1, 0.2]:
        run = copy.deepcopy(state)
        for _ in range(round(2 / dt)):
            run = ContinuousEngine.step(run, dt).new_state
        assert run.entities[0]["simulation_state"]["route_distance"] == pytest.approx(speed * 2)
        restored = copy.deepcopy(run)
        restored.round_number += 1
        restored = ContinuousEngine.step(restored, dt).new_state
        assert restored.entities[0]["simulation_state"]["route_distance"] == pytest.approx(
            speed * (2 + dt)
        )


@pytest.mark.django_db
def test_persisted_ticks_and_snapshot_restore_position_zone_combat_and_cooldown():
    match, teams, _, _ = room(prep=10, battle=60, max_active_units_per_team=6)
    entities = [
        UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))[1] for _ in range(6)
    ]
    assert len({tuple(e.simulation_state["world_position"].values()) for e in entities}) == 6
    match = MatchService.advance_phase(match)
    at = datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    assert ContinuousCombatService.tick(match.pk, at)
    tick = match.events.filter(event_type="COMBAT_TICK").latest("sequence_number")
    updates = {e["id"]: e for e in tick.payload["entity_updates"]}
    snapshot = RealtimeService.build_snapshot(match)["payload"]
    for restored in snapshot["entities"]:
        sim = restored["simulation_state"]
        public = updates[restored["id"]]["simulation_state"]
        for field in [
            "world_position",
            "movement_zone",
            "movement_state",
            "combat_state",
            "attack_target_id",
            "attack_remaining",
        ]:
            assert sim[field] == public[field]
