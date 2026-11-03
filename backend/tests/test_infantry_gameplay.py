"""Infantry-specific acceptance: concurrency, unlimited paid purchases and HP snapshots."""
import copy
import importlib
import math
from datetime import datetime, timedelta

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.combat.balance import INFANTRY_MAX_HP, INFANTRY_MOVEMENT_SPEED, movement_speed
from apps.combat.continuous import ContinuousEngine, distance
from apps.combat.continuous_service import ContinuousCombatService
from apps.combat.formation import physical_position, route_lengths
from apps.combat.map import get_game_map
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.units.models import GameAction, GameEntity, TeamUnlock, UnitType
from apps.units.serializers import UnitTypeSerializer
from apps.units.services import UnitService
from tests.test_continuous_combat import room
from tests.test_live_battle_gameplay import convoy
from tests.test_troop_movement_combat import combat_column


@pytest.mark.parametrize("count", [2, 4, 20])
def test_five_infantry_depart_together_with_independent_state(count):
    state = convoy(("infantry",) * 5, count=count)
    starts = [copy.deepcopy(e["simulation_state"]) for e in state.entities]
    assert len({tuple(s["world_position"].values()) for s in starts}) == 5
    result = ContinuousEngine.step(state, .1).new_state
    for old, entity in zip(starts, result.entities):
        sim = entity["simulation_state"]
        assert entity["status"] == "ACTIVE" and sim["movement_zone"] == "ROUTE"
        assert sim["movement_state"] == "MOVING"
        assert sim["route_distance"] == pytest.approx(movement_speed(entity, state.configuration) * .1)
        assert sim["world_position"] != old["world_position"]
    assert len({id(e["simulation_state"]) for e in result.entities}) == 5


def test_stopped_attacking_infantry_does_not_constrain_any_other_infantry():
    state = combat_column(lead_range=3)
    origins = {e["id"]: e["simulation_state"].get("route_distance", 0) for e in state.entities}
    result = ContinuousEngine.step(state, .1)
    lead, *others = [e for e in result.new_state.entities if e["entity_kind"] == "UNIT"]
    assert lead["simulation_state"]["movement_state"] == "STOPPED"
    assert lead["simulation_state"]["combat_state"] == "ATTACKING"
    assert any(ev["type"] == "UNIT_ATTACKED" and ev["attacker_id"] == lead["id"] for ev in result.events)
    for entity in others:
        assert entity["simulation_state"]["route_distance"] - origins[entity["id"]] == pytest.approx(movement_speed(entity, state.configuration) * .1)


def test_speed_five_point_five_survives_json_restart():
    import json
    assert INFANTRY_MOVEMENT_SPEED == 5.5
    state = convoy(("infantry",))
    unit = state.entities[0]
    speed = movement_speed(unit, state.configuration)
    previous = unit["simulation_state"]["reference_hop_length"] / state.configuration["movement_baseline_round_seconds"] * 6
    assert speed / previous == pytest.approx(5.5 / 6)
    for _ in range(4):
        state = ContinuousEngine.step(state, .1).new_state
        state.entities = json.loads(json.dumps(state.entities))
        assert movement_speed(state.entities[0], state.configuration) == speed
    assert state.entities[0]["simulation_state"]["route_distance"] == pytest.approx(speed * .4)


def test_large_tick_includes_every_corner_and_offsets_do_not_change_attack_range():
    state = convoy(("infantry",))
    game_map = get_game_map(2)
    e = state.entities[0]
    lengths = route_lengths(e["simulation_state"]["route_nodes"], game_map)
    dt = lengths[3] / movement_speed(e, state.configuration) + .01
    moved = ContinuousEngine.step(state, dt).new_state.entities[0]
    assert len(moved["simulation_state"]["movement_path"]) >= 5
    target = {"current_node_id": "node_tower_t2_slot2", "entity_kind": "TOWER"}
    before = distance(moved, target, game_map)
    moved["simulation_state"]["world_position"] = {"x": 99999, "y": 99999}
    assert distance(moved, target, game_map) == before


@pytest.mark.django_db
@pytest.mark.parametrize("number", [5, 10, 20, 50, 100])
def test_unlimited_paid_deployment_no_rally_or_shared_count_rejection(number):
    match, teams, tokens, _ = room(max_active_units_per_team=1, initial_coins=number * 15)
    entities = [UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk), idempotency_key=f"inf-{i}")[1] for i in range(number)]
    assert len({e.pk for e in entities}) == number
    assert all(e.current_hp == e.max_hp == INFANTRY_MAX_HP == 80 for e in entities)
    assert all(e.simulation_state["route_nodes"][0] == "node_spawn_t1" for e in entities)
    spawn = get_game_map(2, match.configuration["arena_layout_version"]).nodes["node_spawn_t1"]
    assert all(math.dist((spawn.x, spawn.y), tuple(e.simulation_state["world_position"].values())) < 40 for e in entities)
    teams[0].refresh_from_db()
    assert teams[0].coins == 0
    retry = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk), idempotency_key="inf-0")[1]
    assert retry.pk == entities[0].pk
    with pytest.raises(ValidationError) as rejected:
        UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    assert rejected.value.code == "INSUFFICIENT_COINS"
    assert GameAction.objects.filter(team=teams[0]).count() == number
    response = APIClient().get(f"/api/v1/matches/{match.pk}/teams/{teams[0].pk}/state/", HTTP_X_PARTICIPANT_TOKEN=tokens[0])
    limits = response.json()["limits"]
    assert limits["infantry"] == {"current": number, "max": None}
    assert limits["other_units"] == {"current": 0, "max": 1}


@pytest.mark.django_db
def test_other_units_keep_their_cap_and_infantry_does_not_consume_it():
    match, teams, _, _ = room(max_active_units_per_team=1, initial_coins=2000)
    for _ in range(12):
        UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    tank = UnitType.objects.get(code="tank")
    TeamUnlock.objects.create(team=teams[0], unit_type=tank)
    deployed = UnitService.deploy_unit(match, teams[0], "tank", str(teams[1].pk))[1]
    assert deployed.max_hp == 100
    with pytest.raises(ValidationError) as rejected:
        UnitService.deploy_unit(match, teams[0], "tank", str(teams[1].pk))
    assert rejected.value.code == "UNIT_LIMIT_REACHED"
    UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))


@pytest.mark.django_db
def test_hp_migration_keeps_existing_survivors_and_new_spawn_and_snapshot_use_eighty():
    match, teams, _, _ = room()
    old = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))[1]
    GameEntity.objects.filter(pk=old.pk).update(current_hp=91, max_hp=100)
    dead = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))[1]
    GameEntity.objects.filter(pk=dead.pk).update(current_hp=0, max_hp=100, status="DESTROYED")
    importlib.import_module("apps.units.migrations.0006_infantry_hp").update_infantry_catalog(apps, None)
    old.refresh_from_db()
    dead.refresh_from_db()
    assert (old.current_hp, old.max_hp) == (91, 100)
    assert (dead.current_hp, dead.max_hp, dead.status) == (0, 100, "DESTROYED")
    new = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))[1]
    GameEntity.objects.filter(pk=new.pk).update(current_hp=71)
    match = MatchService.advance_phase(match)
    at = datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    assert ContinuousCombatService.tick(match.pk, at)
    snapshot = {e["id"]: e for e in RealtimeService.build_snapshot(match)["payload"]["entities"]}
    assert (snapshot[str(new.pk)]["current_hp"], snapshot[str(new.pk)]["max_hp"]) == (71, 80)
    assert (snapshot[str(old.pk)]["current_hp"], snapshot[str(old.pk)]["max_hp"]) == (91, 100)
    catalog = UnitTypeSerializer(new.unit_type, context={"match": match}).data
    assert catalog["hp"] == 80 and catalog["movement_speed"] == 7 and catalog["max_active_units"] is None


@pytest.mark.django_db
def test_catchup_yields_after_wall_budget_without_losing_next_tick(monkeypatch):
    from apps.matches.scheduler import MatchScheduler
    match, teams, _, _ = room(prep=2, battle=60)
    UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    match = MatchService.advance_phase(match)
    at = datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    readings = iter([0, 1.1])
    monkeypatch.setattr("apps.matches.scheduler.time.monotonic", lambda: next(readings))
    MatchScheduler.advance_continuous(match, at + timedelta(seconds=3))
    match.refresh_from_db()
    assert match.configuration["simulation_tick"] == 1
    assert datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"]) == at + timedelta(seconds=.2)
