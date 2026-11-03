"""Disposable DB benchmark; quantities are scenarios, never gameplay caps.
Run: PYTHONPATH=. .venv/bin/python tests/benchmark_unlimited_towers.py OUTPUT.json
"""

import json
import os
import statistics
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
import django

django.setup()
from django.db import connection, reset_queries
from django.test.utils import CaptureQueriesContext, setup_databases, teardown_databases

from apps.combat.continuous import ContinuousEngine, candidates, entity_index
from apps.combat.continuous_service import public_entity
from apps.combat.engine import CombatState
from apps.combat.map import get_game_map
from apps.matches.models import MatchEvent
from apps.realtime.services import RealtimeService
from apps.units.models import GameEntity
from apps.units.placement import placement_grid
from apps.units.services import ConstructionService, UnitService
from tests.test_continuous_combat import room
from tests.test_grid_placement import valid_cells


def disjoint(grid, owner):
    used = set()
    for row, col in valid_cells(grid, owner):
        cells = {(r, c) for r in range(row, row + 3) for c in range(col, col + 3)}
        if not cells & used:
            used |= cells
            yield row, col


def run(count, quantity):
    match, teams, _, _ = room(
        count=count, initial_coins=10000, tower_placement_version=1, arena_layout_version=6
    )
    grid = placement_grid(get_game_map(count, 6))
    timing = []
    for owner, team in enumerate(teams, 1):
        cells = list(disjoint(grid, owner))
        assert len(cells) >= quantity, (count, owner, len(cells))
        for i, (r, c) in enumerate(cells[:quantity]):
            reset_queries()
            start = time.perf_counter()
            with CaptureQueriesContext(connection) as queries:
                ConstructionService.build_tower(
                    match, team, "mg_tower", grid_row=r, grid_col=c, idempotency_key=f"bench-{i}"
                )
            timing.append((time.perf_counter() - start) * 1000)
            construction_queries = len(queries)
        UnitService.deploy_units(match, team, "infantry", str(teams[owner % count].pk), quantity=10)
    reset_queries()
    with CaptureQueriesContext(connection) as snapshot_queries:
        start = time.perf_counter()
        snapshot = RealtimeService.build_snapshot(match)
        snapshot_ms = (time.perf_counter() - start) * 1000
    # Use the same hydration as production ticks.
    state = CombatState(
        1,
        False,
        {
            str(t.pk): {
                "team_index": i,
                "base_hp": t.base_hp,
                "base_shield": 0,
                "initial_base_hp": t.initial_base_hp,
                "status": t.status,
                "coins": 1000,
            }
            for i, t in enumerate(teams, 1)
        },
        [
            {**e.unit_type.base_stats, **public_entity(e), "unit_type_code": e.unit_type.code}
            for e in GameEntity.objects.filter(match=match).select_related("unit_type")
        ],
        [],
        match.configuration,
    )
    ticks, attacks = [], 0
    for _ in range(50):
        start = time.perf_counter()
        result = ContinuousEngine.step(state, 0.2)
        ticks.append((time.perf_counter() - start) * 1000)
        attacks += sum(e["type"] in ("TOWER_ATTACKED", "UNIT_ATTACKED") for e in result.events)
        state = result.new_state
    graph = get_game_map(count, 6)
    index = entity_index(state.entities)
    start = time.perf_counter()
    for e in state.entities:
        candidates(e, index, graph, ["UNIT", "TOWER"])
    lookup_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    for _ in range(100):
        try:
            grid.validate(
                *cells[0],
                "mg_tower",
                count,
                GameEntity.objects.filter(match=match, entity_kind__in=["TOWER", "SPECIAL", "UNIT"],
                    status__in=["ACTIVE", "QUEUED", "DISABLED"]).select_related("unit_type").only(
                    "entity_kind", "simulation_state", "current_node_id", "unit_type__code"
                ),
            )
        except Exception as error:
            if getattr(error, "code", "") != "PLACEMENT_OCCUPIED":
                raise
    collision_ms = (time.perf_counter() - start) * 10
    return dict(
        teams=count,
        towers_per_team=quantity,
        entities=len(state.entities),
        construction_median_ms=round(statistics.median(timing), 3),
        construction_last_ms=round(timing[-1], 3),
        construction_queries=construction_queries,
        collision_mean_ms=round(collision_ms, 3),
        candidate_pass_ms=round(lookup_ms, 3),
        tick_median_ms=round(statistics.median(ticks), 3),
        tick_max_ms=round(max(ticks), 3),
        attacks=attacks,
        snapshot_ms=round(snapshot_ms, 3),
        snapshot_queries=len(snapshot_queries),
        snapshot_bytes=len(json.dumps(snapshot).encode()),
        tower_event_bytes=len(
            json.dumps(
                MatchEvent.objects.filter(match=match, event_type="TOWER_BUILT").first().payload
            ).encode()
        ),
    )


if __name__ == "__main__":
    old = setup_databases(verbosity=0, interactive=False)
    try:
        results = []
        for n, q in [(2, 10), (2, 25), (2, 50), (4, 50), (20, 10), (20, 25)]:
            row = run(n, q)
            results.append(row)
            print(json.dumps(row), flush=True)
        with open(sys.argv[1], "w") as output:
            json.dump(results, output, indent=2)
    finally:
        teardown_databases(old, verbosity=0)
