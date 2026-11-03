"""Current balance, parallel mixed troops and versioned geometry acceptance."""
import copy
import importlib
import json
import math
from datetime import datetime

import pytest
from django.apps import apps
from rest_framework.test import APIClient

from apps.combat.balance import attack_cooldown, entity_attack_range, movement_speed
from apps.combat.continuous import ContinuousEngine, candidates, distance, entity_index
from apps.combat.continuous_service import ContinuousCombatService
from apps.combat.formation import physical_position, route_lengths
from apps.combat.map import GameMap, get_game_map
from apps.combat.navigation import project
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.units.models import GameEntity, UnitType
from apps.units.serializers import GameEntitySerializer, UnitTypeSerializer
from apps.units.services import ConstructionService, UnitService
from tests.test_artillery_slots_batch import unlock
from tests.test_continuous_combat import room
from tests.test_live_battle_gameplay import convoy
from tests.test_troop_movement_combat import combat_column


@pytest.mark.django_db
def test_catalog_and_instances_use_current_balance_without_other_stat_changes():
    match, teams, _, _ = room()
    unlock(teams[0], "artillery")
    unlock(teams[0], "cannon_tower")
    _, artillery = UnitService.deploy_units(match, teams[0], "artillery", teams[1].pk, quantity=2)
    _, cannon = ConstructionService.build_tower(match, teams[0], "cannon_tower", "node_tower_t1_slot6")
    catalog = {u.code: UnitTypeSerializer(u, context={"match": match}).data for u in UnitType.objects.all()}
    assert tuple(catalog["cannon_tower"][k] for k in ("range", "hp", "damage", "cost")) == (3, 150, 20, 40)
    assert tuple(catalog["artillery"][k] for k in ("movement_speed", "hp", "range", "damage", "cost")) == (5, 80, 1.5, 20, 45)
    assert tuple(catalog["infantry"][k] for k in ("movement_speed", "hp", "range", "damage", "cost")) == (5.5, 80, 1, 5, 15)
    assert tuple(catalog["tank"][k] for k in ("movement_speed", "hp", "range", "damage", "cost")) == (4, 110, 1, 12.5, 35)
    assert all(e.current_hp == e.max_hp == 80 for e in artillery)
    assert all(GameEntitySerializer(e).data["movement_speed"] == 5 for e in artillery)
    assert entity_attack_range(cannon) == 3
    assert attack_cooldown({"unit_type_code": "cannon_tower"}, match.configuration) == 2
    assert attack_cooldown({"unit_type_code": "mg_tower"}, match.configuration) == 1.8
    assert attack_cooldown({"unit_type_code": "artillery"}, match.configuration) == 2
    public = RealtimeService.build_snapshot(match)["payload"]["entities"]
    assert all(e["max_hp"] == 80 and e["movement_speed"] == 5 and e["range"] == 1.5 for e in public if e["unit_code"] == "artillery")


@pytest.mark.parametrize("progress,eligible", [(0, True), (.00001, False), (.5, False), (1, False)])
def test_cannon_target_boundary_is_two_hops_including_partial_edges(progress, eligible):
    graph = get_game_map(2)
    cannon = {"id": "cannon", "team_id": "a", "entity_kind": "TOWER", "current_node_id": "node_tower_t2_slot1", "range": 2}
    target = {"id": "target", "team_id": "b", "entity_kind": "UNIT", "status": "ACTIVE", "current_hp": 100,
              "current_node_id": "node_lane_t2_3", "simulation_state": {"next_node_id": "node_center_ring_t2", "edge_progress": progress}}
    assert distance(cannon, target, graph) == pytest.approx(2 + progress)
    assert bool(candidates(cannon, entity_index([target]), graph, ["UNIT"])) is eligible


@pytest.mark.parametrize("count", [2, 4, 8, 20])
def test_ten_mixed_troops_advance_same_tick_at_their_own_speed_and_restore(count):
    state = convoy(("infantry",)*5 + ("tank",)*3 + ("artillery",)*2, count=count)
    state.configuration["movement_baseline_round_seconds"] = 30
    graph = get_game_map(count)
    starts = {e["id"]: physical_position(e, graph) for e in state.entities}
    assert len(set(starts.values())) == 10
    for _ in range(5):
        before = copy.deepcopy(state.entities)
        state = ContinuousEngine.step(state, .2).new_state
        for old, entity in zip(before, state.entities):
            sim = entity["simulation_state"]
            assert entity["status"] == "ACTIVE" and sim["movement_state"] == "MOVING"
            assert sim["route_distance"] - old["simulation_state"]["route_distance"] == pytest.approx(movement_speed(entity, state.configuration)*.2)
            assert math.dist(physical_position(old, graph), physical_position(entity, graph)) <= movement_speed(entity, state.configuration)*.2+1e-6
            assert all(graph.nodes[n].is_passable for n in sim["route_nodes"])
        state.entities = json.loads(json.dumps(state.entities))
    assert len({id(e["simulation_state"]) for e in state.entities}) == 10


@pytest.mark.parametrize("lead_code", ["infantry", "tank", "artillery"])
def test_attacking_unit_does_not_lock_mixed_army(lead_code):
    state = combat_column((lead_code, "infantry", "tank", "artillery"), lead_range=3)
    starts = {e["id"]: e["simulation_state"].get("route_distance", 0) for e in state.entities}
    after = ContinuousEngine.step(state, .1).new_state
    assert after.entities[0]["simulation_state"]["combat_state"] == "ATTACKING"
    assert after.entities[0]["simulation_state"]["route_distance"] == starts["u-0"]
    for entity in after.entities[1:4]:
        assert entity["simulation_state"]["route_distance"] - starts[entity["id"]] == pytest.approx(movement_speed(entity, state.configuration)*.1)


@pytest.mark.django_db
def test_balance_migration_preserves_hp_cooldowns_custom_ranges_and_layout():
    match, teams, _, _ = room()
    match.configuration.pop("arena_layout_version")
    match.save(update_fields=["configuration"])
    cannon = UnitType.objects.get(code="cannon_tower")
    UnitType.objects.filter(pk=cannon.pk).update(base_stats={**cannon.base_stats, "range": 6, "damage": 37})
    old_cannon = GameEntity.objects.create(match=match, team=teams[0], unit_type=cannon, entity_kind="TOWER", current_hp=41, max_hp=150,
        current_node_id="node_tower_t1_slot1", simulation_state={"attack_remaining": .6})
    artillery = UnitType.objects.get(code="artillery")
    old = [GameEntity.objects.create(match=match, team=teams[0], unit_type=artillery, current_hp=hp, max_hp=70, status=status,
        current_node_id="node_spawn_t1", simulation_state={"attack_range": 1.5, "attack_remaining": .8}) for hp, status in [(39,"ACTIVE"), (0,"DESTROYED")]]
    importlib.import_module("apps.units.migrations.0008_cannon_artillery_and_layout_version").rebalance(apps, None)
    cannon.refresh_from_db()
    old_cannon.refresh_from_db()
    match.refresh_from_db()
    assert cannon.base_stats["range"] == 4 and cannon.base_stats["damage"] == 37
    assert entity_attack_range(old_cannon) == 6 and old_cannon.simulation_state["attack_remaining"] == .6
    for entity, hp in zip(old, [39, 0]):
        entity.refresh_from_db()
        assert entity.current_hp == hp and entity.max_hp == 70
        assert entity.simulation_state == {"attack_range": 1.5, "attack_remaining": .8}
    assert match.configuration["arena_layout_version"] == 3
    payload = RealtimeService.build_snapshot(match)["payload"]
    # Saved geometry stays identical; grid metadata is now additive for old maps.
    saved_map = copy.deepcopy(payload["map_data"])
    assert saved_map.pop("placement_grid")
    saved_map["arena"]["key"] = saved_map["arena"]["key"].removesuffix("-grid-v1-r6")
    assert saved_map == get_game_map(2,3).to_dict([str(t.pk) for t in teams])
    assert APIClient().get(f"/api/v1/matches/{match.pk}/map/").json() == payload["map_data"]
    new_match, _ = MatchService.create_match()
    assert new_match.configuration["arena_layout_version"] == 7


def road_distance(point, graph):
    segments = []
    for u, neighbors in graph.adjacency.items():
        for v in neighbors:
            if u >= v or not graph.nodes[u].is_passable or not graph.nodes[v].is_passable:
                continue
            a, b = (project((graph.nodes[n].x, graph.nodes[n].y)) for n in (u,v))
            control = ((a[0]+b[0])/2+(b[1]-a[1])*.08, (a[1]+b[1])/2-(b[0]-a[0])*.08)
            points = [((1-t)**2*a[0]+2*(1-t)*t*control[0]+t*t*b[0], (1-t)**2*a[1]+2*(1-t)*t*control[1]+t*t*b[1]) for t in (i/16 for i in range(17))]
            segments.extend([(a,b), *zip(points, points[1:])])
    def separation(a,b):
        dx,dy=b[0]-a[0],b[1]-a[1]
        t=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy or 1)))
        return math.dist(point,(a[0]+t*dx,a[1]+t*dy))
    return min(separation(a,b) for a,b in segments)


@pytest.mark.parametrize("count", range(2,21))
def test_all_six_slots_move_closer_with_safe_versioned_deterministic_geometry(count):
    old, new = get_game_map(count,3), get_game_map(count,4)
    assert new.validate_map() == (True, [])
    assert new.to_dict()["arena"]["version"] == 4
    assert GameMap.from_dict(old.to_dict()).to_dict() == old.to_dict()
    assert GameMap.from_dict(new.to_dict()).to_dict() == new.to_dict()
    assert old.adjacency == new.adjacency
    for key,node in new.nodes.items():
        prior=old.nodes[key]
        if node.node_type != "tower_slot":
            assert node.to_dict() == prior.to_dict()
            continue
        before=road_distance(project((prior.x,prior.y)),new)
        after=road_distance(project((node.x,node.y)),new)
        assert 57 <= after < before
        assert .84 < after/before < 1
        assert not node.is_passable


@pytest.mark.parametrize("progress,expected_hp", [(0, 50), (.00001, 80)])
def test_cannon_fires_only_inside_new_range_with_unchanged_damage_and_cooldown(progress, expected_hp):
    state = convoy(())
    cannon = {"id": "cannon", "team_id": "a", "unit_type_code": "cannon_tower", "entity_kind": "TOWER",
              "range": 2, "damage": 30, "current_hp": 150, "max_hp": 150, "status": "ACTIVE",
              "current_node_id": "node_tower_t1_slot1", "simulation_state": {}}
    target = {"id": "target", "team_id": "b", "target_team_id": "a", "unit_type_code": "infantry", "entity_kind": "UNIT",
              "range": 0, "damage": 0, "movement": 0, "current_hp": 80, "max_hp": 80, "status": "ACTIVE",
              "current_node_id": "node_lane_t1_3", "simulation_state": {"next_node_id": "node_center_ring_t1", "edge_progress": progress}}
    state.entities = [cannon, target]
    result = ContinuousEngine.step(state, .2)
    entities = {e["id"]: e for e in result.new_state.entities}
    assert entities["target"]["current_hp"] == expected_hp
    assert entities["cannon"]["current_hp"] == 150
    shots = [e for e in result.events if e["type"] == "TOWER_ATTACKED"]
    assert len(shots) == (1 if expected_hp == 50 else 0)
    if shots:
        assert shots[0]["damage"] == 30
        assert entities["cannon"]["simulation_state"]["attack_remaining"] == 2
        again = ContinuousEngine.step(result.new_state, .2)
        assert not any(e["type"] == "TOWER_ATTACKED" for e in again.events)
