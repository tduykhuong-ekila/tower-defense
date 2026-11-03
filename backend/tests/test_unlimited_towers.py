"""Paid, unlimited construction through real services, sockets and PostgreSQL locks."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.exceptions import ValidationError
from django.db import connection, connections

from apps.combat.map import get_game_map
from apps.economy.models import CoinTransaction
from apps.matches.models import Match
from apps.teams.models import Team, TeamMember
from apps.units.models import GameEntity, TeamUnitUpgrade, UnitType
from apps.units.placement import placement_grid
from apps.units.serializers import UnitTypeSerializer
from apps.units.services import TeamUpgradeService
from config.asgi import application
from tests.test_continuous_combat import until
from tests.test_grid_placement import build, grid_room, valid_cells


def disjoint_cells(grid, owner=1):
    used = set()
    for row, col in valid_cells(grid, owner):
        cells = {(r, c) for r in range(row, row + 3) for c in range(col, col + 3)}
        if not used & cells:
            used |= cells
            yield row, col


@pytest.mark.django_db
@pytest.mark.parametrize("count", [2, 4, 8, 20])
def test_all_teams_build_beyond_six_pay_and_inherit_upgrade(count):
    match, teams, _, _ = grid_room(count=count, initial_coins=2000)
    # Simulate a stored historical cap; it must have no effect.
    match.configuration["max_towers_per_team"] = 1
    match.save()
    grid = placement_grid(get_game_map(count, 6))
    unit = UnitType.objects.get(code="mg_tower")
    for owner, team in enumerate(teams, 1):
        TeamUnitUpgrade.objects.create(team=team, unit_type=unit, level=3)
        ids = set()
        for i, cell in enumerate(list(disjoint_cells(grid, owner))[:10]):
            _, tower = build(match, team, *cell, key=f"tower-{i}")
            ids.add(tower.pk)
            assert tower.level == 3
        assert len(ids) == 10
        team.refresh_from_db()
        assert team.coins == 2000 - 10 * unit.cost
        assert (
            CoinTransaction.objects.filter(team=team, transaction_type="BUILD_TOWER").count() == 10
        )
        assert (
            UnitTypeSerializer(unit, context={"match": match, "team": team}).data[
                "max_active_units"
            ]
            is None
        )
    assert GameEntity.objects.filter(match=match).count() == count * 10


@pytest.mark.django_db
@pytest.mark.parametrize(
    "failure",
    ["locked", "coins", "phase", "team", "actor", "enemy", "footprint", "request", "conflict"],
)
def test_failed_build_leaves_economy_and_occupancy_unchanged(failure):
    match, teams, _, _ = grid_room()
    team = teams[0]
    grid = placement_grid(get_game_map(2, 6))
    cells = list(disjoint_cells(grid))
    row, col = cells[0]
    code, key, actor = "mg_tower", "invalid", None
    if failure == "locked":
        code = "cannon_tower"
    if failure == "coins":
        Team.objects.filter(pk=team.pk).update(coins=0)
    if failure == "phase":
        Match.objects.filter(pk=match.pk).update(status="PAUSED")
    if failure == "team":
        Team.objects.filter(pk=team.pk).update(status="ELIMINATED")
    if failure == "actor":
        actor = TeamMember.objects.filter(team=teams[1]).first()
    if failure == "enemy":
        row, col = next(disjoint_cells(grid, 2))
    if failure == "footprint":
        # Top-left is owned; at least one other footprint cell crosses an exclusion.
        row, col = next(
            (r, c)
            for r in range(grid.rows - 3)
            for c in range(grid.cols - 3)
            if grid.owners[r * grid.cols + c] == 1
            and any(
                grid.owners[y * grid.cols + x] != 1
                for y in range(r, r + 3)
                for x in range(c, c + 3)
            )
        )
    if failure == "request":
        key = ""
    if failure == "conflict":
        build(match, team, row, col, key=key)
        row, col = cells[1]
    team.refresh_from_db()
    before = (
        team.coins,
        GameEntity.objects.filter(match=match).count(),
        CoinTransaction.objects.filter(team=team).count(),
    )
    from apps.units.services import ConstructionService

    with pytest.raises(ValidationError):
        ConstructionService.build_tower(
            match, team, code, grid_row=row, grid_col=col, idempotency_key=key, actor=actor
        )
    team.refresh_from_db()
    assert before == (
        team.coins,
        GameEntity.objects.filter(match=match).count(),
        CoinTransaction.objects.filter(team=team).count(),
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("scenario", ["overlap", "different", "retry", "last-coins"])
def test_concurrent_teammates_real_postgres(scenario):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    match, teams, _, _ = grid_room(initial_coins=25 if scenario == "last-coins" else 1000)
    cells = list(disjoint_cells(placement_grid(get_game_map(2, 6))))
    gate = Barrier(2)

    def attempt(i):
        connections.close_all()
        try:
            m = Match.objects.get(pk=match.pk)
            t = Team.objects.get(pk=teams[0].pk)
            gate.wait(timeout=10)
            cell = cells[i] if scenario in ("different", "last-coins") else cells[0]
            try:
                return str(
                    build(m, t, *cell, key="retry" if scenario == "retry" else f"build-{i}")[1].pk
                )
            except ValidationError:
                return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [0, 1]))
    expected = 2 if scenario == "different" else 1
    assert len(set(results) - {None}) == expected
    assert GameEntity.objects.filter(match=match).count() == expected
    assert (
        CoinTransaction.objects.filter(team=teams[0], transaction_type="BUILD_TOWER").count()
        == expected
    )
    teams[0].refresh_from_db()
    assert teams[0].coins == (25 if scenario == "last-coins" else 1000) - 25 * expected


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_eighth_tower_battle_realtime_upgrade_retry_and_reconnect():
    match, teams, tokens, _ = await database_sync_to_async(grid_room)(initial_coins=3000)
    await database_sync_to_async(Match.objects.filter(pk=match.pk).update)(
        phase="WAR",
        configuration={
            **match.configuration,
            "timer_state": {**match.configuration["timer_state"], "round_phase": "BATTLE"},
        },
    )
    cells = list(disjoint_cells(placement_grid(get_game_map(2, 6))))

    async def connect(token):
        c = WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={token}")
        assert (await c.connect())[0]
        await until(c, "MATCH_STATE_SNAPSHOT")
        return c

    clients = list(await asyncio.gather(*(connect(t) for t in tokens)))
    try:
        for i, cell in enumerate(cells[:8]):
            await clients[0].send_json_to(
                {
                    "event_type": "BUILD_REQUEST",
                    "payload": {
                        "tower_code": "mg_tower",
                        "grid_row": cell[0],
                        "grid_col": cell[1],
                        "idempotency_key": f"socket-{i}",
                    },
                }
            )
            events = await asyncio.gather(*(until(c, "TOWER_BUILT") for c in clients))
            assert len({e["payload"]["entity_id"] for e in events}) == 1
            assert events[0]["payload"]["coins_after"] == 3000 - (i + 1) * 25
        await database_sync_to_async(TeamUpgradeService.purchase)(
            match, teams[0], "mg_tower", 1, "upgrade"
        )
        updates = await asyncio.gather(*(until(c, "TEAM_UNIT_UPGRADED") for c in clients))
        assert all(
            e["payload"]["team_id"] == str(teams[0].pk) and e["payload"]["level"] == 2
            for e in updates
        )
        tower = await database_sync_to_async(build)(match, teams[0], *cells[8], key="ninth")
        assert tower[1].level == 2
        assert (await database_sync_to_async(build)(match, teams[0], *cells[8], key="ninth"))[
            1
        ].pk == tower[1].pk
        await asyncio.gather(*(until(c, "TOWER_BUILT") for c in clients))
        await clients[1].disconnect()
        clients[1] = await connect(tokens[1])
        await clients[1].send_json_to({"event_type": "STATE_SYNC_REQUEST", "payload": {}})
        snapshot = (await until(clients[1], "MATCH_STATE_SNAPSHOT"))["payload"]
        assert len(snapshot["entities"]) == 9
        assert all(
            e["level"] == 2 and e["simulation_state"]["grid_placement"]
            for e in snapshot["entities"]
        )
        # A second team retains its own rank when it constructs.
        cell = next(disjoint_cells(placement_grid(get_game_map(2, 6)), 2))
        _, enemy = await database_sync_to_async(build)(match, teams[1], *cell, key="enemy")
        assert enemy.level == 1
    finally:
        await asyncio.gather(*(c.disconnect() for c in clients))


@pytest.mark.parametrize("count", [2, 4, 8, 20])
def test_spatial_targets_equal_brute_force_at_edges_and_all_ranges(count):
    import random

    from apps.combat.continuous import candidates, entity_index, target_distance

    graph = get_game_map(count, 6)
    rng = random.Random(2400 + count)
    nodes = [n for n in graph.nodes.values() if n.is_passable]
    entities = []
    for i in range(300):
        node = rng.choice(nodes)
        entities.append(
            {
                "id": str(i),
                "team_id": str(i % count),
                "entity_kind": "TOWER" if i % 3 else "UNIT",
                "status": "DESTROYED" if i % 11 == 0 else "DISABLED" if i % 13 == 0 else "ACTIVE",
                "current_hp": 0 if i % 11 == 0 else 80,
                "current_node_id": node.node_id,
                "range": rng.choice([0.5, 1, 1.5, 2, 3, 6]),
                "simulation_state": {
                    "world_position": {
                        "x": node.x + rng.uniform(-160, 160),
                        "y": node.y + rng.uniform(-160, 160),
                    },
                    **({"grid_placement": {"row": 1, "col": 1}} if i % 3 else {}),
                    **({"movement_zone": "STAGING"} if i % 17 == 0 else {}),
                },
            }
        )
    # Include exact-boundary targets in negative-coordinate buckets.
    for i, x in enumerate([-160, -80, 0, 80, 160]):
        entities.append(
            {
                "id": f"edge-{i}",
                "team_id": str(i % 2),
                "entity_kind": "TOWER",
                "status": "ACTIVE",
                "current_hp": 80,
                "current_node_id": nodes[0].node_id,
                "range": 2,
                "simulation_state": {
                    "grid_placement": {"row": 1, "col": 1},
                    "world_position": {"x": x, "y": -80},
                },
            }
        )
    index = entity_index(entities)
    for attacker in [e for e in entities if e["simulation_state"].get("grid_placement")]:
        expected = {
            e["id"]
            for e in entities
            if e["team_id"] != attacker["team_id"]
            and e["current_hp"] > 0
            and e["status"] in ("ACTIVE", "DISABLED")
            and e["simulation_state"].get("movement_zone") != "STAGING"
            # Compare against the exact tower-footprint range rule used after
            # spatial pruning, rather than center-to-center distance.
            and target_distance(attacker, e, graph) <= attacker["range"]
        }
        assert {e["id"] for e in candidates(attacker, index, graph, ["TOWER", "UNIT"])} == expected


def test_retired_capacity_input_is_ignored_and_published_as_null():
    from apps.matches.defaults import get_default_configuration
    from apps.matches.serializers import MatchConfigurationSerializer

    for cap in (1, 6, 50, None):
        serializer = MatchConfigurationSerializer(
            data={**get_default_configuration(), "max_towers_per_team": cap}
        )
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["max_towers_per_team"] is None
        assert serializer.data["max_towers_per_team"] is None


@pytest.mark.django_db
@pytest.mark.parametrize("layout", [3, 4, 5])
@pytest.mark.parametrize("count", [2, 4, 8, 20])
def test_saved_arenas_gain_grid_without_moving_foundations_or_routes(layout, count):
    from apps.units.placement import map_for_match
    from apps.units.services import ConstructionService
    from tests.test_continuous_combat import room

    match, teams, _, _ = room(count=count, initial_coins=10000, arena_layout_version=layout)
    graph = get_game_map(count, layout)
    before_nodes = {key: (n.x, n.y) for key, n in graph.nodes.items()}
    before_route = graph.get_path_to_base(graph.get_spawn_node(1), 2)
    for i in range(1, 7):
        ConstructionService.build_tower(
            match, teams[0], "mg_tower", f"node_tower_t1_slot{i}", idempotency_key=f"foundation-{i}"
        )
    original = {
        str(e.pk): (e.current_node_id, e.simulation_state)
        for e in GameEntity.objects.filter(match=match)
    }
    # Every remaining physical footprint is available; compact legacy arenas
    # may already be full, which must fail geometry rather than quantity.
    built = 0
    for row, col in disjoint_cells(placement_grid(graph)):
        try:
            build(match, teams[0], row, col, key=f"grid-{built}")
        except ValidationError as error:
            assert error.code == "PLACEMENT_OCCUPIED"
            continue
        built += 1
    assert GameEntity.objects.filter(match=match).count() == 6 + built
    if count == 2 and layout == 5:
        assert built >= 4  # This saved arena has enough real space beyond six.
    for entity in GameEntity.objects.filter(match=match, pk__in=original):
        assert (entity.current_node_id, entity.simulation_state) == original[str(entity.pk)]
    data = map_for_match(match, [str(t.pk) for t in teams])
    assert data["placement_grid"] == placement_grid(graph).metadata()
    assert before_nodes == {key: (n.x, n.y) for key, n in graph.nodes.items()}
    assert before_route == graph.get_path_to_base(graph.get_spawn_node(1), 2)
    match.refresh_from_db()
    teams[0].refresh_from_db()
    assert match.configuration["arena_layout_version"] == layout
    assert match.configuration["tower_placement_version"] == 0
    assert teams[0].coins == 10000 - (6 + built) * 25
