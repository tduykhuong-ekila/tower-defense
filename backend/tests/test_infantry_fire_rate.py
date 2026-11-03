"""Deterministic attack cadence, unchanged damage and checkpoint recovery."""
import json
from datetime import datetime, timedelta

import pytest

from apps.combat.balance import attack_cooldown
from apps.combat.continuous import ContinuousEngine
from apps.combat.continuous_service import ContinuousCombatService
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.units.models import GameEntity
from apps.units.services import UnitService
from tests.test_continuous_combat import pure_state, room


def stationary_target(code="infantry", target="BASE", cooldown=2):
    state = pure_state(code=code, node="node_lane_t2_1", config={"attack_cooldown_seconds": cooldown})
    state.teams["b"]["base_hp"] = 100000
    if target != "BASE":
        state.entities.append({
            "id": "enemy", "team_id": "b", "unit_type_code": "tank",
            "entity_kind": target, "damage": 0, "movement": 0, "range": 0,
            "current_hp": 100000, "current_shield": 0, "status": "ACTIVE",
            "current_node_id": "node_lane_t2_1", "simulation_state": {},
        })
    return state


@pytest.mark.parametrize("dt", [.1, .2, .5, 1])
@pytest.mark.parametrize("target", ["BASE", "UNIT", "TOWER"])
def test_infantry_fires_45_in_60_seconds_with_one_unchanged_hit_per_event(dt, target):
    state = stationary_target(target=target)
    shots, times = [], []
    hp = 100000
    for tick in range(round(60 / dt)):
        result = ContinuousEngine.step(state, dt)
        state = result.new_state
        attacks = [ev for ev in result.events if ev["type"] in ("UNIT_ATTACKED", "BASE_DAMAGED")]
        assert len(attacks) <= 1
        for event in attacks:
            assert event["damage"] == event["hp_damage"] == 5
            hp -= 5
            assert event.get("target_hp_remaining", event.get("base_hp_remaining")) == hp
            times.append((tick + 1) * dt)
        shots.extend(attacks)
        state.entities = json.loads(json.dumps(state.entities))
    assert attack_cooldown(state.entities[0], state.configuration) == pytest.approx(2 / 1.5)
    assert len(shots) == 45  # Previous 2-second cadence: 30 shots in this window.
    for ordinal, at in enumerate(times):
        assert abs(at - (dt + ordinal * 2 / 1.5)) <= dt + 1e-8
    actual = state.teams["b"]["base_hp"] if target == "BASE" else next(e for e in state.entities if e["id"] == "enemy")["current_hp"]
    assert actual == 100000 - 45 * 5


@pytest.mark.parametrize("code", ["tank", "artillery"])
def test_vehicles_keep_their_two_second_cadence(code):
    state = stationary_target(code=code)
    attacks = []
    for _ in range(300):
        result = ContinuousEngine.step(state, .2)
        state = result.new_state
        attacks.extend(e for e in result.events if e["type"] == "BASE_DAMAGED")
    assert len(attacks) == 30
    assert attack_cooldown(state.entities[0], state.configuration) == 2


def test_tower_cadence_and_damage_are_unchanged():
    state = stationary_target(target="UNIT")
    state.entities[0].update(entity_kind="TOWER", unit_type_code="mg_tower", damage=15)
    attacks = []
    for _ in range(300):
        result = ContinuousEngine.step(state, .2)
        state = result.new_state
        attacks.extend(e for e in result.events if e["type"] == "TOWER_ATTACKED")
    assert len(attacks) == 30
    assert all(e["damage"] == 15 for e in attacks)


def test_entity_and_match_cooldown_overrides_and_idle_do_not_bank_extra_shots():
    state = stationary_target(cooldown=3)
    assert attack_cooldown(state.entities[0], state.configuration) == 2
    state.entities[0]["attack_cooldown_seconds"] = 1.5
    assert attack_cooldown(state.entities[0], state.configuration) == 1
    state.entities[0]["simulation_state"]["attack_remaining"] = -999
    result = ContinuousEngine.step(state, .2)
    assert len([e for e in result.events if e["type"] == "BASE_DAMAGED"]) == 1
    assert result.new_state.entities[0]["simulation_state"]["attack_remaining"] == 1
    state = result.new_state
    state.entities[0]["simulation_state"]["attack_remaining"] = .8
    result = ContinuousEngine.step(state, .2)
    assert not any(e["type"] == "BASE_DAMAGED" for e in result.events)
    assert result.new_state.entities[0]["simulation_state"]["attack_remaining"] == pytest.approx(.6)


@pytest.mark.django_db
def test_committed_shot_cooldown_snapshot_and_retry_survive_service_reload():
    match, teams, _, _ = room(battle=600)
    _, unit = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    GameEntity.objects.filter(pk=unit.pk).update(current_node_id="node_lane_t2_1", simulation_state={})
    match = MatchService.advance_phase(match)
    at = datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    assert ContinuousCombatService.tick(match.pk, at)
    unit.refresh_from_db()
    teams[1].refresh_from_db()
    assert unit.simulation_state["attack_remaining"] == pytest.approx(2 / 1.5)
    assert teams[1].base_hp == 495
    assert not ContinuousCombatService.tick(match.pk, at)
    assert ContinuousCombatService.tick(match.pk, at + timedelta(seconds=.2))
    unit.refresh_from_db()
    teams[1].refresh_from_db()
    assert unit.simulation_state["attack_remaining"] == pytest.approx(2 / 1.5 - .2)
    assert teams[1].base_hp == 495
    snapshot = RealtimeService.build_snapshot(match)
    assert snapshot["payload"]["simulation_at"] == (at + timedelta(seconds=.2)).isoformat()
    saved = next(e for e in snapshot["payload"]["entities"] if e["id"] == str(unit.pk))
    assert saved["simulation_state"]["attack_remaining"] == unit.simulation_state["attack_remaining"]


def test_short_custom_cooldown_retains_each_distinct_shot_at_coarse_ticks():
    state = stationary_target(cooldown=.3)
    shots = []
    # New cooldown .2 s at a 1-second tick: five due shots per steady tick.
    for _ in range(11):
        result = ContinuousEngine.step(state, 1)
        state = result.new_state
        shots.extend(e for e in result.events if e["type"] == "BASE_DAMAGED")
        assert state.entities[0]["simulation_state"]["attack_remaining"] > 0
    assert len(shots) == 51  # First eligible boundary, plus ten seconds at 5 Hz.
    assert state.teams["b"]["base_hp"] == 100000 - 51 * 5
