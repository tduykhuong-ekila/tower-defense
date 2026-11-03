"""Defensive orders return home, fight intruders and remain under player control."""
import copy

import pytest
from django.core.exceptions import ValidationError

from apps.combat.continuous import ContinuousEngine
from apps.combat.formation import physical_position, redirect_route
from apps.combat.map import get_game_map
from apps.matches.services import MatchService
from apps.units.commands import ArmyCommandService
from apps.units.serializers import ArmyCommandRequestSerializer
from apps.units.services import UnitService
from tests.test_continuous_combat import pure_state, room


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_return_home_fight_every_hostile_team_and_hold(code):
    state = pure_state(code, node="node_lane_t2_2")
    state.teams["c"] = {**state.teams["b"], "team_index": 3}
    graph = get_game_map(3)
    defender = state.entities[0]
    defender.update(target_team_id=None, current_hp=37)
    defender["simulation_state"] = {"order": "DEFEND_BASE", "attack_remaining": .8}
    assert redirect_route(defender, "node_lane_t1_1", graph)
    before = physical_position(defender, graph)
    for _ in range(400):
        state = ContinuousEngine.step(state, .2).new_state
    defender = state.entities[0]
    assert physical_position(defender, graph) != before
    assert defender["current_node_id"] == "node_lane_t1_1"
    assert defender["simulation_state"]["order"] == "DEFEND_BASE"
    assert defender["current_hp"] == 37
    home = physical_position(defender, graph)
    assert physical_position(ContinuousEngine.step(state, .2).new_state.entities[0], graph) == home
    # Intruders belong to teams that are not assigned attack targets.
    for tid in ("b", "c"):
        intruder = copy.deepcopy(pure_state().entities[0])
        intruder.update(id=f"enemy-{tid}", team_id=tid, target_team_id="a", damage=0,
                        movement=0, current_hp=1, current_node_id="node_lane_t1_1")
        intruder["simulation_state"] = {"order": "AT_RALLY"}
        state.entities.append(intruder)
    events = []
    for _ in range(40):
        result = ContinuousEngine.step(state, .2)
        state = result.new_state
        events.extend(result.events)
    assert {event["target_team_id"] for event in events if event["type"] == "UNIT_ATTACKED"} == {"b", "c"}
    assert not any(event["type"] == "BASE_DAMAGED" for event in events)
    assert state.entities[0]["simulation_state"]["order"] == "DEFEND_BASE"


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_intercept_nearby_enemy_and_return_when_it_leaves(code):
    state = pure_state(code, node="node_lane_t1_1")
    defender = state.entities[0]
    defender["target_team_id"] = None
    defender["simulation_state"]["order"] = "DEFEND_BASE"
    enemy = copy.deepcopy(pure_state(node="node_lane_t1_3").entities[0])
    enemy.update(id="enemy", team_id="b", movement=0, target_team_id="a")
    enemy["simulation_state"] = {"order": "AT_RALLY"}
    state.entities.append(enemy)
    result = ContinuousEngine.step(state, .2)
    moved = result.new_state.entities[0]
    assert moved["simulation_state"]["route_nodes"][-1] == "node_lane_t1_3"
    assert moved["simulation_state"]["route_distance"] > 0
    state = result.new_state
    state.entities[1]["current_node_id"] = "node_lane_t2_1"
    result = ContinuousEngine.step(state, .2)
    assert result.new_state.entities[0]["simulation_state"]["route_nodes"][-1] == "node_lane_t1_1"
    assert not any(event.get("attacker_id") == "unit" for event in result.events)


@pytest.mark.django_db
def test_command_subset_retry_redeployment_and_ownership():
    match, teams, _, _ = room(prep=600, battle=600)
    entities = [UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))[1]
                for _ in range(2)]
    match = MatchService.advance_phase(match)
    first = entities[0]
    first.current_hp = 37
    first.simulation_state["attack_remaining"] = .7
    first.save()
    serializer = ArmyCommandRequestSerializer(data={"command_type": "DEFEND_BASE",
        "unit_ids": [str(first.pk)], "idempotency_key": "guard"})
    assert serializer.is_valid(), serializer.errors
    action, result = ArmyCommandService.issue(match, teams[0], **serializer.validated_data)
    first.refresh_from_db()
    entities[1].refresh_from_db()
    assert result["affected_count"] == 1
    assert first.target_team_id is None
    assert first.current_hp == 37 and first.simulation_state["attack_remaining"] == .7
    assert first.simulation_state["order"] == "DEFEND_BASE"
    assert first.simulation_state["route_nodes"][-1] == "node_lane_t1_1"
    assert entities[1].simulation_state.get("order", "ATTACK") == "ATTACK"
    assert match.events.filter(event_type="ARMY_DEFENSE_ORDERED").count() == 1
    ArmyCommandService.issue(match, teams[0], "RETARGET", "attack", [first.pk], teams[1].pk)
    again, original = ArmyCommandService.issue(match, teams[0], **serializer.validated_data)
    assert again.pk == action.pk and original == result
    first.refresh_from_db()
    assert first.simulation_state["order"] == "ATTACK"
    with pytest.raises(ValidationError):
        ArmyCommandService.issue(match, teams[0], "DEFEND_BASE", "empty")
    with pytest.raises(ValidationError):
        ArmyCommandService.issue(match, teams[1], "DEFEND_BASE", "foreign", [first.pk])
