"""Losing a base must not remove or disable the team's surviving army."""
import pytest

from apps.combat.continuous import ContinuousEngine
from tests.test_continuous_combat import pure_state


def with_destroyed_base(code, node="node_spawn_t1"):
    state = pure_state(code, node=node)
    state.teams["a"]["base_hp"] = 0
    state.teams["c"] = {**state.teams["b"], "team_index": 3}
    return state


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
@pytest.mark.parametrize("status", ["ACTIVE", "QUEUED"])
def test_surviving_troops_keep_hp_and_move_after_base_destruction(code, status):
    state = with_destroyed_base(code)
    state.entities[0]["status"] = status
    hp = state.entities[0]["current_hp"]
    result = ContinuousEngine.step(state, .2)
    assert result.eliminated_team_ids == ["a"]
    assert not result.is_match_over
    assert result.new_state.teams["a"]["status"] == "ELIMINATED"
    assert not any(event["type"] == "ENTITY_DESTROYED" for event in result.events)
    first = result.new_state.entities[0]
    assert first["status"] == "ACTIVE"
    assert first["current_hp"] == hp
    following = ContinuousEngine.step(result.new_state, .2)
    unit = following.new_state.entities[0]
    assert unit["status"] == "ACTIVE"
    assert unit["current_hp"] == hp
    assert unit["simulation_state"]["route_distance"] > first["simulation_state"]["route_distance"]
    assert not following.eliminated_team_ids


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery", "mg_tower"])
def test_survivors_keep_attacking_and_can_still_be_damaged(code):
    state = with_destroyed_base(code, node="node_lane_t2_3")
    survivor = state.entities[0]
    survivor.update(entity_kind="TOWER" if code == "mg_tower" else "UNIT", movement=0)
    enemy = {**survivor, "id": "enemy", "team_id": "b", "unit_type_code": "tank",
             "entity_kind": "UNIT", "current_hp": 10000, "target_team_id": "a",
             "damage": 1, "simulation_state": {"order": "ATTACK" if code == "mg_tower" else "DEFEND_BASE"}}
    state.entities.append(enemy)
    result = ContinuousEngine.step(state, .2)
    hp_after_destruction = result.new_state.entities[0]["current_hp"]
    enemy_hp = result.new_state.entities[1]["current_hp"]
    events = []
    for _ in range(12):
        result = ContinuousEngine.step(result.new_state, .2)
        events.extend(result.events)
    by_id = {entity["id"]: entity for entity in result.new_state.entities}
    assert by_id["unit"]["status"] == "ACTIVE"
    assert by_id["unit"]["current_hp"] < hp_after_destruction
    assert by_id["enemy"]["current_hp"] < enemy_hp
    assert any(event.get("attacker_id") == "unit" for event in events)


def test_disabled_tower_recovers_after_base_destruction():
    state = with_destroyed_base("mg_tower", node="node_center")
    tower = state.entities[0]
    tower.update(entity_kind="TOWER", status="DISABLED")
    tower["simulation_state"] = {"disabled_remaining": .4}
    result = ContinuousEngine.step(state, .2)
    assert result.new_state.entities[0]["status"] == "DISABLED"
    following = ContinuousEngine.step(result.new_state, .2)
    assert following.new_state.entities[0]["status"] == "ACTIVE"
    assert any(event["type"] == "TOWER_ENABLED" for event in following.events)
