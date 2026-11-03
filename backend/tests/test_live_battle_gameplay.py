"""Authoritative speed, HP, lane traffic and battle-time command acceptance."""
import copy
import importlib
import math
from datetime import datetime, timedelta

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError

from apps.combat.balance import (
    TROOP_DAMAGE_MULTIPLIER,
    TROOP_MOVEMENT_SPEED,
    attack_damage,
    movement_speed,
)
from apps.combat.continuous import ContinuousEngine, base_in_range
from apps.combat.engine import CombatState
from apps.combat.formation import (
    bodies_clear,
    initialize_route,
    initialize_spawn,
    physical_position,
    synchronize_position,
)
from apps.combat.map import get_game_map
from apps.matches.action_policy import ActionPolicy
from apps.matches.services import MatchService
from apps.units.models import GameEntity, TeamUnlock, UnitType
from apps.units.services import ConstructionService, UnitService
from tests.test_continuous_combat import advance, pure_state, room


def convoy(codes=("infantry", "infantry"), count=2):
    state = pure_state(config={"movement_baseline_round_seconds": 1})
    state.entities = []
    game_map = get_game_map(count)
    if count != 2:
        state.teams = {str(i): {"team_index": i + 1, "status": "ACTIVE", "base_hp": 500, "base_shield": 0} for i in range(count)}
    owner, target = list(state.teams)[:2]
    for i, code in enumerate(codes):
        e = copy.deepcopy(pure_state(code).entities[0])
        e.update(id=f"u-{i}", team_id=owner, target_team_id=target, current_hp=100, max_hp=100, status="QUEUED")
        initialize_spawn(e, state.entities, game_map.get_base_node(state.teams[target]["team_index"]), game_map, i+1, state.configuration)
        state.entities.append(e)
    return state


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_speed_setting_is_four_and_never_compounds(code):
    state = convoy((code,))
    state.configuration["movement_baseline_round_seconds"] = 30
    unit = state.entities[0]
    # Isolate road speed from the finite walk out of vehicle parking slots.
    game_map = get_game_map(2)
    unit["simulation_state"].update(movement_zone="ROUTE", crowd_offset={"x": 0, "y": 0})
    unit["simulation_state"].pop("world_position", None)
    factor = {"infantry": 5.5, "tank": 4, "artillery": 5}[code]
    baseline = unit["movement"] * unit["simulation_state"]["reference_hop_length"] / state.configuration["movement_baseline_round_seconds"]
    assert TROOP_MOVEMENT_SPEED == 4 and TROOP_DAMAGE_MULTIPLIER == .5
    assert movement_speed(unit, state.configuration) == pytest.approx(baseline * factor)
    original_reference = unit["simulation_state"]["reference_hop_length"]
    for _ in range(5):
        state = ContinuousEngine.step(state, .2).new_state
    unit = state.entities[0]
    assert unit["simulation_state"]["route_distance"] == pytest.approx(baseline * factor)
    assert unit["simulation_state"]["reference_hop_length"] == original_reference
    before = unit["simulation_state"]["route_distance"]
    restored = copy.deepcopy(state)
    restored.round_number += 1
    restored = ContinuousEngine.step(restored, .2).new_state
    assert restored.entities[0]["simulation_state"]["route_distance"] - before == pytest.approx(baseline*factor*.2)
    assert sum(attack_damage(unit) for _ in range(10)) == {"infantry":50,"tank":125,"artillery":200}[code]


@pytest.mark.parametrize("codes", [("tank",)*2, ("tank",)*5, ("tank","artillery","tank")])
def test_staging_admission_and_independent_road_traffic_respect_speed_budgets(codes):
    state = convoy(codes)
    game_map = get_game_map(2)
    for team in state.teams.values():
        team["base_hp"] = 1_000_000
    # Parking bodies are separated; road traffic uses bounded cosmetic offsets
    # and independent progression rather than the old exclusive convoy slots.
    for i, a in enumerate(state.entities):
        for b in state.entities[i+1:]:
            assert bodies_clear(a, b, physical_position(a, game_map), physical_position(b, game_map), state.configuration)
    for _ in range(160):
        before = {e["id"]: physical_position(e, game_map) for e in state.entities}
        state = ContinuousEngine.step(state, .2).new_state
        for e in state.entities:
            assert math.dist(before[e["id"]], physical_position(e, game_map)) <= movement_speed(e, state.configuration) * .2 + 1e-6
    assert all(e["simulation_state"]["movement_zone"] == "ROUTE" for e in state.entities)
    assert all(base_in_range(e, "node_base_t2", game_map) for e in state.entities)


def test_stationary_troop_does_not_lock_others_and_late_spawn_is_independent():
    state = convoy(("tank", "tank"))
    game_map = get_game_map(2)
    for e, progress in zip(state.entities, [150, 60]):
        e["simulation_state"].update(movement_zone="ROUTE", route_distance=progress)
        e["simulation_state"].pop("world_position", None)
        synchronize_position(e, game_map)
        e["status"] = "ACTIVE"
    state.entities[0]["movement"] = 0
    for _ in range(5):
        state = ContinuousEngine.step(state, .2).new_state
    a, b = state.entities
    assert a["simulation_state"]["route_distance"] == 150
    assert b["simulation_state"]["route_distance"] > 150
    before = copy.deepcopy([e["simulation_state"] for e in state.entities])
    new = copy.deepcopy(pure_state("tank").entities[0])
    new.update(id="late",status="QUEUED")
    initialize_spawn(new,state.entities,"node_base_t2",game_map,3,state.configuration)
    assert new["simulation_state"]["movement_zone"] == "STAGING"
    assert [e["simulation_state"] for e in state.entities] == before
    state.entities.append(new)
    for _ in range(100):
        state = ContinuousEngine.step(state, .2).new_state
    assert next(e for e in state.entities if e["id"] == "late")["simulation_state"]["movement_zone"] == "ROUTE"
    assert next(e for e in state.entities if e["id"] == "u-0")["simulation_state"]["route_distance"] == 150


@pytest.mark.django_db
@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_new_troops_spawn_current_hp_and_historical_hp_migration_never_heals(code):
    match, teams, _, _ = room()
    unit_type = UnitType.objects.get(code=code)
    TeamUnlock.objects.get_or_create(team=teams[0],unit_type=unit_type)
    _, entity = UnitService.deploy_unit(match,teams[0],code,str(teams[1].pk))
    assert entity.current_hp == entity.max_hp == unit_type.base_stats["hp"] == ({"infantry": 80, "tank": 110, "artillery": 80}[code])
    GameEntity.objects.filter(pk=entity.pk).update(current_hp=27,max_hp=120)
    migration = importlib.import_module("apps.units.migrations.0005_mobile_troop_hp")
    migration.normalize_mobile_hp(apps,None)
    entity.refresh_from_db()
    assert entity.current_hp == 27 and entity.max_hp == 100
    GameEntity.objects.filter(pk=entity.pk).update(current_hp=120,max_hp=120)
    migration.normalize_mobile_hp(apps,None)
    entity.refresh_from_db()
    assert entity.current_hp == entity.max_hp == 100
    _,tower=ConstructionService.build_tower(match,teams[1],"mg_tower","node_tower_t2_slot1")
    assert tower.current_hp == tower.max_hp == 100
    teams[0].refresh_from_db()
    assert teams[0].base_hp == 500


@pytest.mark.django_db
def test_real_live_battle_actions_keep_timer_and_join_current_tick_then_survive_next_round():
    match,teams,_,_=room(prep=2,battle=12,movement_baseline_round_seconds=1)
    a,b=teams
    one=UnitService.deploy_unit(match,a,"infantry",str(b.pk),idempotency_key="one")[1]
    two=UnitService.deploy_unit(match,a,"infantry",str(b.pk),idempotency_key="two")[1]
    assert one.current_hp == two.current_hp == 80
    assert two.simulation_state["movement_zone"] == "ROUTE"
    assert one.simulation_state["world_position"] != two.simulation_state["world_position"]
    match=MatchService.advance_phase(match)
    timer=copy.deepcopy(match.configuration["timer_state"])
    start=datetime.fromisoformat(timer["phase_started_at"])
    advance(match,start+timedelta(seconds=1))
    one.refresh_from_db()
    graph = get_game_map(2, match.configuration["arena_layout_version"])
    old_position = physical_position({"current_node_id": one.current_node_id,
                                      "simulation_state": one.simulation_state}, graph)
    tower=ConstructionService.build_tower(match,b,"mg_tower","node_tower_t2_slot1",idempotency_key="tower")[1]
    a.refresh_from_db()
    coins=a.coins
    _,third=UnitService.deploy_unit(match,a,"infantry",str(b.pk),idempotency_key="third")
    third_start=third.simulation_state["route_distance"]
    third_start_position=copy.deepcopy(third.simulation_state["world_position"])
    _,retry=UnitService.deploy_unit(match,a,"infantry",str(b.pk),idempotency_key="third")
    a.refresh_from_db()
    assert a.coins == coins-15 and retry.pk == third.pk
    advance(match,start+timedelta(seconds=2))
    one.refresh_from_db()
    third.refresh_from_db()
    tower.refresh_from_db()
    # A tower built mid-battle legitimately changes the route origin. Verify
    # actual motion/combat instead of comparing distances from different routes.
    assert physical_position({"current_node_id": one.current_node_id,
                              "simulation_state": one.simulation_state}, graph) != old_position or one.simulation_state["combat_state"] == "ATTACKING"
    assert third.simulation_state["route_distance"] > third_start or third.simulation_state["world_position"] != third_start_position
    assert match.configuration["timer_state"]["phase_ends_at"] == timer["phase_ends_at"]
    assert match.configuration["current_round"] == 1
    assert match.configuration["simulation_tick"] >= 10
    assert ActionPolicy.context(match,a,"TARGET_SELECTED").allowed
    assert ActionPolicy.context(match,a,"ANSWER_QUESTION").allowed
    with pytest.raises(ValidationError):
        ConstructionService.build_tower(match,b,"mg_tower","node_tower_t1_slot1")
    advance(match,start+timedelta(seconds=9))
    hits=[event for tick in match.events.filter(event_type="COMBAT_TICK") for event in tick.payload["events"] if event["type"]=="TOWER_ATTACKED"]
    assert hits and hits[0]["damage"]==15 and hits[0]["target_hp_remaining"]==65
    match=MatchService.advance_phase(match)
    assert match.phase == "PREPARATION" and match.configuration["current_round"] == 2
    assert GameEntity.objects.filter(pk__in=[one.pk,two.pk,third.pk,tower.pk]).count()==4


def test_junction_progress_is_independent_and_all_units_reach_destination():
    game_map = get_game_map(2)
    state = convoy(("tank","tank"))
    for e,node in zip(state.entities,["node_spawn_t2","node_lane_t2_3"]):
        e.update(current_node_id=node,status="ACTIVE")
        order=e["simulation_state"]["formation_order"]
        e["simulation_state"]={"formation_order":order}
        initialize_route(e,"node_base_t2",game_map)
        synchronize_position(e,game_map)
    for team in state.teams.values():
        team["base_hp"] = 1_000_000
    previous=[e["simulation_state"]["route_distance"] for e in state.entities]
    entered=[]
    for _ in range(100):
        state=ContinuousEngine.step(state,.2).new_state
        for i,e in enumerate(state.entities):
            assert e["simulation_state"]["route_distance"] >= previous[i]
            previous[i]=e["simulation_state"]["route_distance"]
            if base_in_range(e, "node_base_t2", game_map) and e["id"] not in entered:
                entered.append(e["id"])
        assert all(e["simulation_state"]["route_distance"] >= 0 for e in state.entities)
    assert set(entered) == {"u-0", "u-1"}
    state.entities[0].update(status="DESTROYED",current_hp=0)
    for _ in range(30):
        state=ContinuousEngine.step(state,.2).new_state
    assert base_in_range(state.entities[1], "node_base_t2", game_map)


def test_opposing_enemies_engage_normally_with_unchanged_damage():
    state=convoy(("infantry",))
    game_map=get_game_map(2)
    a=state.entities[0]
    a.update(status="ACTIVE",current_node_id="node_lane_t2_2",simulation_state={})
    initialize_route(a,"node_base_t2",game_map)
    b=copy.deepcopy(a)
    b.update(id="enemy",team_id="b",target_team_id="a",current_node_id="node_lane_t2_1",simulation_state={})
    initialize_route(b,"node_base_t1",game_map)
    state.entities.append(b)
    result=ContinuousEngine.step(state,.2)
    assert len([e for e in result.events if e["type"]=="UNIT_ATTACKED"])==2
    assert [e["current_hp"] for e in result.new_state.entities]==[95,95]


def test_twenty_independent_friendly_queues_keep_advancing():
    count=20
    state=convoy((),count=count)
    game_map=get_game_map(count)
    for team_index,owner in enumerate(state.teams):
        target=str((team_index+1)%count)
        own=[]
        for j in range(5):
            e=copy.deepcopy(pure_state().entities[0])
            e.update(id=f"team-{team_index}-unit-{j}",team_id=owner,target_team_id=target,
                     current_hp=100,max_hp=100,status="QUEUED",current_node_id=game_map.get_spawn_node(team_index+1))
            initialize_spawn(e,own,game_map.get_base_node(int(target)+1),game_map,j+1,state.configuration)
            own.append(e)
        state.entities.extend(own)
    for _ in range(40):
        state=ContinuousEngine.step(state,.2).new_state
    for team_index in range(count):
        own=[e for e in state.entities if e["team_id"]==str(team_index)]
        assert max(e["simulation_state"]["route_distance"] for e in own)>0
        assert all(e["simulation_state"].get("world_position") for e in own)


@pytest.mark.django_db
def test_custom_mobile_types_are_100_hp_while_cannon_hp_and_stats_stay_unchanged():
    match,teams,_,_=room()
    mobile=UnitType.objects.create(code="mobile-scout",name="Scout",category="UNIT",is_starter=True,cost=10,
        base_stats={"hp":250,"damage":7,"range":1,"movement":2})
    assert mobile.base_stats["hp"]==100 and mobile.base_stats["damage"]==7
    _,entity=UnitService.deploy_unit(match,teams[0],mobile.code,str(teams[1].pk))
    assert entity.current_hp==entity.max_hp==100
    cannon=UnitType.objects.get(code="cannon_tower")
    TeamUnlock.objects.create(team=teams[1],unit_type=cannon)
    _,tower=ConstructionService.build_tower(match,teams[1],cannon.code,"node_tower_t2_slot1")
    assert tower.current_hp==tower.max_hp==150 and cannon.base_stats["damage"]==20 and cannon.cost==40


def test_fork_routes_remain_independent_and_reach_both_target_bases():
    game_map=get_game_map(4)
    state=convoy((),count=4)
    for team in state.teams.values():
        team["base_hp"] = 1_000_000
    for index,target in enumerate(["1","2"]):
        e=copy.deepcopy(pure_state("tank").entities[0])
        e.update(id=f"fork-{index}",team_id="0",target_team_id=target,status="QUEUED")
        initialize_spawn(e,state.entities,game_map.get_base_node(int(target)+1),game_map,index+1,state.configuration)
        state.entities.append(e)
    attacked = set()
    for _ in range(160):
        before = {e["id"]: physical_position(e, game_map) for e in state.entities}
        result = ContinuousEngine.step(state,.2)
        state = result.new_state
        attacked.update(event["target_team_id"] for event in result.events if event["type"] == "BASE_DAMAGED")
        for entity in state.entities:
            assert math.dist(before[entity["id"]], physical_position(entity, game_map)) <= movement_speed(entity, state.configuration) * .2 + 1e-6
    assert attacked == {"1", "2"}
    assert base_in_range(state.entities[0], "node_base_t2", game_map)
    assert base_in_range(state.entities[1], "node_base_t3", game_map)
