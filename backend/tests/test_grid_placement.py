"""Grid geometry, authoritative purchases, realtime convergence and real row locks."""

import asyncio
import importlib
import math
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection, connections
from rest_framework.test import APIClient

from apps.combat.balance import attack_damage
from apps.combat.continuous import ContinuousEngine, candidates, distance, entity_index
from apps.combat.continuous_service import public_entity
from apps.combat.engine import CombatState
from apps.combat.map import get_game_map
from apps.combat.navigation import unproject
from apps.combat.targeting import find_unit_target
from apps.economy.models import CoinTransaction
from apps.matches.models import Match, MatchEvent
from apps.realtime.services import RealtimeService
from apps.teams.models import Team
from apps.units.models import GameEntity, TeamUnitUpgrade, TeamUnlock, UnitType
from apps.units.placement import FOOTPRINTS, map_for_match, placement_grid, shield_position_allowed
from apps.units.serializers import GameEntitySerializer, UnitTypeSerializer
from apps.units.services import ConstructionService, TeamUpgradeService
from apps.units.upgrades import effective_stats
from config.asgi import application
from tests.test_continuous_combat import room


def grid_room(**kwargs):
    return room(tower_placement_version=1, arena_layout_version=6, **kwargs)


def valid_cells(grid, owner=1):
    footprint = FOOTPRINTS["mg_tower"]
    for row in range(grid.rows - footprint["heightCells"] + 1):
        for col in range(grid.cols - footprint["widthCells"] + 1):
            if all(
                (
                    grid.owners[r * grid.cols + c] == owner
                    for r in range(row, row + footprint["heightCells"])
                    for c in range(col, col + footprint["widthCells"])
                )
            ):
                yield (row, col)


def build(match, team, row, col, key="build", code="mg_tower"):
    return ConstructionService.build_tower(
        match, team, code, grid_row=row, grid_col=col, idempotency_key=key
    )


@pytest.mark.parametrize("count", [2, 4, 8, 20])
def test_grid_world_mask_all_teams_have_six_disjoint_footprints(count):
    graph = get_game_map(count, 6)
    grid = placement_grid(graph)
    assert not any(n.node_type == "tower_slot" for n in graph.nodes.values())
    for owner in range(1, count + 1):
        occupied = set()
        total = 0
        for row, col in valid_cells(grid, owner):
            cells = {(r, c) for r in range(row, row + 4) for c in range(col, col + 4)}
            if occupied & cells:
                continue
            occupied |= cells
            total += 1
        assert total >= 6, (count, owner, total)
    assert grid.cols * 32 <= grid.width and grid.rows * 32 <= grid.height
    assert graph.validate_map() == (True, [])
    reasons = set(grid.reasons)
    assert {"ROAD", "BASE", "RALLY", "WATER", "TERRITORY"} <= reasons
    for a in range(1, count + 1):
        for b in range(1, count + 1):
            if a != b:
                assert graph.get_path_to_base(graph.get_spawn_node(a), b)


@pytest.mark.django_db
def test_cannon_base_levels_and_migration_preserve_other_fields():
    match, teams, _, _ = grid_room()
    unit = UnitType.objects.get(code="cannon_tower")
    other = UnitType.objects.get(code="artillery")
    original = dict(unit.base_stats)
    original_other = dict(other.base_stats)
    assert unit.base_stats["damage"] == 20
    for level, damage in enumerate([20, 22, 24], 1):
        assert effective_stats(unit, level, match.configuration)["damage"] == damage
        assert attack_damage({"entity_kind": "TOWER", "damage": 20, "level": level}) == damage
    UnitType.objects.filter(pk=unit.pk).update(base_stats={**original, "damage": 30})
    importlib.import_module("apps.units.migrations.0012_cannon_damage").rebalance(apps, None)
    unit.refresh_from_db()
    other.refresh_from_db()
    assert unit.base_stats == original and other.base_stats == original_other
    assert other.base_stats["damage"] == 40


@pytest.mark.django_db
def test_authoritative_position_idempotency_upgrade_events_and_destroyed_release():
    match, teams, _, _ = grid_room()
    team = teams[0]
    unit = UnitType.objects.get(code="cannon_tower")
    TeamUnlock.objects.create(team=team, unit_type=unit)
    TeamUnitUpgrade.objects.create(team=team, unit_type=unit, level=3)
    grid = placement_grid(get_game_map(2, 6))
    row, col = next(valid_cells(grid))
    action, entity = build(match, team, row, col, code=unit.code)
    assert entity.level == 3 and entity.max_hp == 195
    assert effective_stats(unit, entity.level, match.configuration)["damage"] == 24
    assert entity.simulation_state["grid_placement"]["widthCells"] == 3
    assert entity.current_node_id.startswith(
        ("node_lane", "node_spawn", "node_base", "node_center")
    )
    assert build(match, team, row, col, code=unit.code)[1].pk == entity.pk
    team.refresh_from_db()
    assert team.coins == 460
    assert CoinTransaction.objects.filter(team=team, transaction_type="BUILD_TOWER").count() == 1
    for changed in [(row + 1, col), (row, col + 1)]:
        with pytest.raises(ValidationError):
            build(match, team, *changed, key="build", code=unit.code)
        with pytest.raises(ValidationError):
            build(match, team, *changed, key=str(changed), code=unit.code)
    event = MatchEvent.objects.get(match=match, event_type="TOWER_BUILT")
    assert event.payload["simulation_state"] == entity.simulation_state
    assert public_entity(entity)["simulation_state"] == entity.simulation_state
    assert GameEntitySerializer(entity).data["simulation_state"] == entity.simulation_state
    snapshot = RealtimeService.build_snapshot(match)["payload"]
    assert snapshot["map_data"]["placement_grid"] == grid.metadata()
    assert snapshot["entities"][0]["simulation_state"] == entity.simulation_state
    entity.status = "DESTROYED"
    entity.current_hp = 0
    entity.save()
    _, replacement = build(match, team, row, col, key="replacement", code=unit.code)
    assert replacement.pk != entity.pk
    with pytest.raises(ValidationError):
        TeamUpgradeService.purchase(match, team, unit.code, 3, "upgrade")
    replacement.refresh_from_db()
    assert replacement.level == 3
    assert public_entity(replacement)["damage"] == 24
    assert replacement.simulation_state == entity.simulation_state


@pytest.mark.django_db
@pytest.mark.parametrize(
    "invalid", [(-1, 0), (999999, 0), (0, False), (0, 1.5), (0, "3"), (None, None)]
)
def test_strict_coordinates_rejected_without_debit(invalid):
    match, teams, _, _ = grid_room()
    with pytest.raises(ValidationError):
        build(match, teams[0], *invalid)
    teams[0].refresh_from_db()
    assert teams[0].coins == 500
    assert not GameEntity.objects.filter(match=match).exists()


@pytest.mark.django_db
def test_every_exclusion_and_opponent_region_rejects_purchase():
    match, teams, _, _ = grid_room()
    grid = placement_grid(get_game_map(2, 6))
    for reason in ["ROAD", "BASE", "RALLY", "WATER", "TERRAIN", "TERRITORY"]:
        indexes = [i for i, x in enumerate(grid.reasons) if x == reason]
        if not indexes:
            continue
        row, col = divmod(indexes[0], grid.cols)
        with pytest.raises(ValidationError):
            build(match, teams[0], row, col, key=reason)
    row, col = next(valid_cells(grid, 2))
    with pytest.raises(ValidationError):
        build(match, teams[0], row, col, key="enemy")
    with pytest.raises(ValidationError):
        ConstructionService.build_tower(match, teams[0], "mg_tower", "node_tower_t1_slot1")
    teams[0].refresh_from_db()
    assert teams[0].coins == 500


@pytest.mark.django_db
def test_rest_permissions_lock_coins_ignored_cap_and_legacy_compatibility():
    match, teams, tokens, _ = grid_room()
    grid = placement_grid(get_game_map(2, 6))
    row, col = next(valid_cells(grid))
    client = APIClient()
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[0])
    url = f"/api/v1/matches/{match.pk}/actions/build/"
    payload = {
        "unit_type_code_or_id": "mg_tower",
        "grid_row": row,
        "grid_col": col,
        "idempotency_key": "rest",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 200, response.data
    assert (
        client.post(url, payload, format="json").data["entity"]["id"]
        == response.data["entity"]["id"]
    )
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[-1])
    assert client.post(url, payload, format="json").status_code in (400, 403)
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[0])
    teams[0].coins = 0
    teams[0].save()
    payload["idempotency_key"] = "no-money"
    assert client.post(url, payload, format="json").status_code == 400
    teams[0].coins = 1000
    teams[0].save()
    match.configuration["max_towers_per_team"] = 1
    match.save()
    payload["idempotency_key"] = "occupied"
    assert client.post(url, payload, format="json").data["error_code"] == "PLACEMENT_OCCUPIED"
    payload["grid_row"], payload["grid_col"] = next(
        (r,c) for r,c in valid_cells(grid) if abs(r-row)>=4 or abs(c-col)>=4)
    payload["idempotency_key"] = "beyond-old-limit"
    assert client.post(url, payload, format="json").status_code == 200
    legacy, lt, _, _ = room()
    _, tower = ConstructionService.build_tower(legacy, lt[0], "mg_tower", "node_tower_t1_slot1")
    assert tower.simulation_state == {"build_cost": tower.unit_type.cost}
    assert "placement_grid" in map_for_match(legacy, [str(t.pk) for t in lt])


def test_grid_tower_combat_uses_physical_position_and_exact_range():
    graph = get_game_map(2, 6)
    node = graph.nodes["node_lane_t1_2"]
    tower = {
        "id": "tower",
        "team_id": "a",
        "entity_kind": "TOWER",
        "status": "ACTIVE",
        "current_hp": 150,
        "max_hp": 150,
        "level": 1,
        "damage": 20,
        "range": 2,
        "current_node_id": "node_lane_t1_2",
        "simulation_state": {
            "grid_placement": {"row": 2, "col": 2},
            "world_position": {"x": node.x, "y": node.y + 100},
        },
    }
    unit = {
        "id": "unit",
        "team_id": "b",
        "entity_kind": "UNIT",
        "unit_type_code": "infantry",
        "status": "ACTIVE",
        "current_hp": 80,
        "max_hp": 80,
        "level": 1,
        "damage": 10,
        "range": 1,
        "current_node_id": "node_lane_t1_2",
        "simulation_state": {
            "world_position": {"x": node.x, "y": node.y},
            "movement_zone": "ROUTE",
        },
    }
    assert distance(tower, unit, graph) == 1.25
    assert candidates(tower, entity_index([unit]), graph, ["UNIT"]) == [unit]
    state = CombatState(
        1,
        False,
        {
            "a": {"team_index": 1, "status": "ACTIVE", "base_hp": 500},
            "b": {"team_index": 2, "status": "ACTIVE", "base_hp": 500},
        },
        [tower, unit],
        [],
        {"arena_layout_version": 6, "gameplay_mode": "CONTINUOUS",
         "timer_state": {"round_phase": "BATTLE"}},
    )
    result = ContinuousEngine.step(state, 0.2)
    assert any((e["type"] == "TOWER_ATTACKED" and e["damage"] == 20 for e in result.events))
    tower["simulation_state"]["world_position"]["y"] = node.y + 160.01
    assert not candidates(tower, entity_index([unit]), graph, ["UNIT"])

    # Same graph progress, different physical offsets: the out-of-range troop
    # must not reuse its neighbor's cached grid-tower target.
    from copy import deepcopy

    tower["damage"] = 0
    tower["simulation_state"]["world_position"]["y"] = node.y + 100
    near, far = deepcopy(unit), deepcopy(unit)
    near["id"], far["id"] = "a-near", "b-far"
    near["simulation_state"]["world_position"]["y"] = node.y + 120
    far["simulation_state"]["world_position"]["y"] = node.y - 400
    state.entities = [tower, near, far]
    result = ContinuousEngine.step(state, 0)
    assert [
        event["attacker_id"] for event in result.events if event["type"] == "UNIT_ATTACKED"
    ] == ["a-near"]


def test_infantry_can_attack_grid_tower_footprint_from_its_one_hop_range():
    graph = get_game_map(2, 6)
    node = graph.nodes["node_lane_t1_2"]
    tower = {
        "id": "enemy-grid-tower",
        "team_id": "b",
        "unit_type_code": "mg_tower",
        "entity_kind": "TOWER",
        "damage": 15,
        "range": 2,
        "current_hp": 100,
        "current_shield": 0,
        "status": "ACTIVE",
        "current_node_id": node.node_id,
        "simulation_state": {
            "grid_placement": {"row": 2, "col": 2, **FOOTPRINTS["mg_tower"]},
            "world_position": {"x": node.x, "y": node.y + 100},
        },
    }
    infantry = {
        "id": "infantry",
        "team_id": "a",
        "target_team_id": "b",
        "unit_type_code": "infantry",
        "entity_kind": "UNIT",
        "damage": 10,
        "range": 1,
        "current_hp": 80,
        "current_shield": 0,
        "status": "ACTIVE",
        "current_node_id": node.node_id,
        "simulation_state": {
            "world_position": {"x": node.x, "y": node.y},
            "movement_zone": "ROUTE",
        },
    }
    assert distance(infantry, tower, graph) == 1.25
    assert candidates(infantry, entity_index([infantry, tower]), graph, ["UNIT", "TOWER"]) == [tower]
    assert find_unit_target(infantry, [tower], graph) == tower

    state = CombatState(
        1,
        False,
        {
            "a": {"team_index": 1, "status": "ACTIVE", "base_hp": 500},
            "b": {"team_index": 2, "status": "ACTIVE", "base_hp": 500},
        },
        [infantry, tower],
        [],
        {"arena_layout_version": 6, "troop_target_priority": ["UNIT", "TOWER"]},
    )
    result = ContinuousEngine.step(state, 0.2)
    hit = next(event for event in result.events if event["type"] == "UNIT_ATTACKED")
    assert hit["target_entity_id"] == "enemy-grid-tower"


@pytest.mark.django_db(transaction=True)
def test_concurrent_overlap_real_postgres_only_one_debit():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    match, teams, _, _ = grid_room()
    grid = placement_grid(get_game_map(2, 6))
    row, col = next(valid_cells(grid))
    barrier = Barrier(2)

    def attempt(index):
        connections.close_all()
        try:
            m = Match.objects.get(pk=match.pk)
            t = Team.objects.get(pk=teams[0].pk)
            barrier.wait(timeout=10)
            try:
                return str(build(m, t, row, col, key=f"race-{index}")[1].pk)
            except ValidationError:
                return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [0, 1]))
    assert sum((bool(r) for r in results)) == 1
    assert GameEntity.objects.filter(match=match).count() == 1
    assert (
        CoinTransaction.objects.filter(team=teams[0], transaction_type="BUILD_TOWER").count() == 1
    )
    teams[0].refresh_from_db()
    assert teams[0].coins == 475


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_grid_build_two_teams_spectator_battle_and_reconnect():
    from datetime import timedelta

    from tests.test_continuous_combat import advance, until

    match, teams, tokens, _ = await database_sync_to_async(grid_room)(prep=2, battle=30)
    grid = placement_grid(get_game_map(2, 6))
    row, col = next(valid_cells(grid))

    async def connect(token):
        client = WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={token}")
        assert (await client.connect())[0]
        await until(client, "MATCH_STATE_SNAPSHOT")
        return client

    clients = list(await asyncio.gather(*(connect(t) for t in [tokens[0], tokens[1], tokens[-1]])))
    try:
        await clients[0].send_json_to(
            {
                "event_type": "BUILD_REQUEST",
                "payload": {
                    "tower_code": "mg_tower",
                    "grid_row": row,
                    "grid_col": col,
                    "idempotency_key": "socket-build",
                },
            }
        )
        received = await asyncio.gather(*(until(c, "TOWER_BUILT") for c in clients))
        assert len({r["payload"]["entity_id"] for r in received}) == 1
        assert all(
            (r["payload"]["simulation_state"]["grid_placement"]["row"] == row for r in received)
        )
        await database_sync_to_async(advance)(match, match.started_at + timedelta(seconds=2.2))
        row2, col2 = next(
            ((r, c) for r, c in valid_cells(grid) if abs(r - row) >= 4 or abs(c - col) >= 4)
        )
        await clients[0].send_json_to(
            {
                "event_type": "BUILD_REQUEST",
                "payload": {
                    "tower_code": "mg_tower",
                    "grid_row": row2,
                    "grid_col": col2,
                    "idempotency_key": "battle-build",
                },
            }
        )
        await asyncio.gather(*(until(c, "TOWER_BUILT") for c in clients))
        await clients[0].disconnect()
        clients[0] = await connect(tokens[0])
        await clients[0].send_json_to({"event_type": "STATE_SYNC_REQUEST", "payload": {}})
        snapshot = (await until(clients[0], "MATCH_STATE_SNAPSHOT"))["payload"]
        assert len(snapshot["entities"]) == 2
        assert all((e["simulation_state"]["grid_placement"] for e in snapshot["entities"]))
    finally:
        await asyncio.gather(*(c.disconnect() for c in clients))


def test_configuration_rejects_incompatible_grid_and_legacy_arenas():
    from apps.matches.defaults import get_default_configuration
    from apps.matches.serializers import MatchConfigurationSerializer

    config = get_default_configuration()
    assert MatchConfigurationSerializer(data=config).is_valid()
    for change in [{"tower_placement_version": 0}, {"arena_layout_version": 5}]:
        assert not MatchConfigurationSerializer(data={**config, **change}).is_valid()
    legacy = {**config, "tower_placement_version": 0, "arena_layout_version": 5}
    assert MatchConfigurationSerializer(data=legacy).is_valid()


def shield_range_cells(grid, owner):
    """Find buildable positions on both sides of this team's shield boundary."""
    cells = {}
    for row, col in valid_cells(grid, owner):
        anchor = grid.anchor(row, col, FOOTPRINTS["shield_generator"])
        position = unproject((anchor[0] - grid.offset[0], anchor[1] - grid.offset[1]))
        cells.setdefault(shield_position_allowed(grid.graph, owner, position), (row, col))
        if len(cells) == 2:
            break
    return cells.get(True), cells.get(False)


@pytest.mark.parametrize("count", [2, 4, 8, 20])
def test_shield_generator_requires_position_inside_base_shield(count):
    graph = get_game_map(count, 6)
    grid = placement_grid(graph)
    for owner in range(1, count + 1):
        near, far = shield_range_cells(grid, owner)
        assert near and far, (count, owner)
        grid.validate(*near, "shield_generator", owner, [])
        with pytest.raises(ValidationError) as error:
            grid.validate(*far, "shield_generator", owner, [])
        assert error.value.code == "PLACEMENT_SHIELD_RANGE"
        grid.validate(*far, "mg_tower", owner, [])


@pytest.mark.django_db
@pytest.mark.parametrize("count", [2, 5, 20])
def test_shield_build_api_rejects_outside_range_without_debit_and_accepts_inside(count):
    match, teams, tokens, _ = grid_room(count=count)
    team = teams[-1]
    unit = UnitType.objects.get(code="shield_generator")
    TeamUnlock.objects.create(team=team, unit_type=unit)
    grid = placement_grid(get_game_map(count, 6))
    near, far = shield_range_cells(grid, count)
    assert near and far
    client = APIClient()
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[count-1])
    url = f"/api/v1/matches/{match.pk}/actions/build/"
    payload = {"unit_type_code_or_id": unit.code, "grid_row": far[0], "grid_col": far[1],
               "idempotency_key": "shield-outside"}
    transactions_before = CoinTransaction.objects.filter(team=team).count()
    response = client.post(url, payload, format="json")
    assert response.status_code == 400, response.data
    assert response.data["error_code"] == "PLACEMENT_SHIELD_RANGE"
    team.refresh_from_db()
    assert team.coins == 500
    assert not GameEntity.objects.filter(team=team).exists()
    assert CoinTransaction.objects.filter(team=team).count() == transactions_before
    assert not match.events.filter(event_type="TOWER_BUILT").exists()

    payload.update(grid_row=near[0], grid_col=near[1], idempotency_key="shield-inside")
    response = client.post(url, payload, format="json")
    assert response.status_code == 200, response.data
    entity = GameEntity.objects.get(team=team)
    position = entity.simulation_state["world_position"]
    assert shield_position_allowed(grid.graph, count, (position["x"], position["y"]))
    assert entity.simulation_state["grid_placement"]["row"] == near[0]
    assert entity.simulation_state["grid_placement"]["col"] == near[1]
    retry = client.post(url, payload, format="json")
    assert retry.status_code == 200 and retry.data["entity"]["id"] == response.data["entity"]["id"]
    team.refresh_from_db()
    assert team.coins == 500 - unit.cost
    assert GameEntity.objects.filter(team=team).count() == 1
    assert CoinTransaction.objects.filter(team=team, transaction_type="BUILD_TOWER").count() == 1
    assert match.events.filter(event_type="TOWER_BUILT").count() == 1
