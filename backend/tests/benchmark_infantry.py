"""Opt-in 20-team Infantry benchmark; always uses a disposable SQLite database.

Run from backend: .venv/bin/python tests/benchmark_infantry.py
"""
import copy
import json
import logging
import os
import platform
import resource
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"

import django
from django.conf import settings
from django.core.management import call_command
from django.db import connection


def measure(samples):
    return {"median": round(statistics.median(samples), 2),
            "p95": round(sorted(samples)[min(len(samples) - 1, int(len(samples) * .95))], 2),
            "max": round(max(samples), 2)}


def main():
    with TemporaryDirectory(prefix="infantry-benchmark-") as directory:
        settings.DATABASES["default"]["NAME"] = str(Path(directory) / "benchmark.sqlite3")
        django.setup()
        logging.disable(logging.WARNING)
        call_command("migrate", verbosity=0)
        from apps.combat.continuous import ContinuousEngine
        from apps.combat.continuous_service import ContinuousCombatService
        from apps.matches.services import MatchService
        from apps.units.services import UnitService
        from tests.test_continuous_combat import room
        from tests.test_live_battle_gameplay import convoy

        report = {"platform": platform.platform(), "teams": 20, "database": "disposable SQLite",
                  "transport": "InMemory Channels, no browser subscribers", "scenarios": []}
        for quantity in [20, 50, 100]:
            match, teams, _, _ = room(count=20, prep=300, battle=300, initial_coins=10000)
            for i, team in enumerate(teams):
                for j in range(quantity):
                    UnitService.deploy_unit(match, team, "infantry", str(teams[(i + 1) % 20].pk), idempotency_key=f"{i}-{j}")
            match = MatchService.advance_phase(match)
            samples, cpus, queries, sizes = [], [], [], []
            for _ in range(20):
                match.refresh_from_db()
                at = datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
                query_count = 0
                def count_query(execute, sql, params, many, context):
                    nonlocal query_count
                    query_count += 1
                    return execute(sql, params, many, context)
                start, cpu = time.perf_counter(), time.process_time()
                with connection.execute_wrapper(count_query):
                    assert ContinuousCombatService.tick(match.pk, at)
                samples.append((time.perf_counter() - start) * 1000)
                cpus.append((time.process_time() - cpu) * 1000)
                queries.append(query_count)
                event = match.events.filter(event_type="COMBAT_TICK").latest("sequence_number")
                sizes.append(len(json.dumps(event.payload).encode()))
            # Separate dense combat benchmark exercises opposing armies together.
            dense = convoy(("infantry",) * quantity, count=20)
            source = dense.entities
            dense.entities = []
            for i, team in enumerate(dense.teams):
                for j, template in enumerate(source):
                    unit = copy.deepcopy(template)
                    unit.update(id=f"{i}-{j}", team_id=team, target_team_id=str((i + 1) % 20),
                                current_node_id="node_center", current_hp=1000000,
                                simulation_state={})
                    dense.entities.append(unit)
            dense_times = []
            for _ in range(10):
                start = time.perf_counter()
                dense = ContinuousEngine.step(dense, .2).new_state
                dense_times.append((time.perf_counter() - start) * 1000)
            row = {"infantry_per_team": quantity, "aggregate_entities": quantity * 20,
                   "committed_ticks": 20, "tick_ms": measure(samples), "cpu_ms_per_tick": measure(cpus),
                   "queries_median": statistics.median(queries), "delta_bytes_median": statistics.median(sizes),
                   "estimated_payload_kb_per_second_per_viewer": round(statistics.median(sizes) * 5 / 1024, 2),
                   "dense_combat_engine_ms": measure(dense_times),
                   "process_peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1048576 if platform.system() == "Darwin" else 1024), 1)}
            report["scenarios"].append(row)
            print(json.dumps(row), flush=True)
            match.delete()
        output = Path(__file__).resolve().parents[2] / "docs/qa/infantry-backend-benchmark.json"
        output.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
