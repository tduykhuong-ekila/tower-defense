"""Disposable 20-team PostgreSQL batch benchmark; writes measured QA evidence."""
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test_postgres")
import django
from django.conf import settings
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext, setup_databases, teardown_databases

settings.DATABASES["default"]["TEST"]["NAME"] = "test_td_batch_benchmark"
django.setup()
from apps.combat.continuous_service import ContinuousCombatService
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.units.services import UnitService
from tests.test_continuous_combat import room


def main():
    old = setup_databases(verbosity=0, interactive=False)
    report = {"database": connection.vendor, "scenarios": []}
    try:
        for quantity in (10, 50):
            match, teams, _, _ = room(count=20, initial_coins=5000, battle=60)
            match = MatchService.advance_phase(match)
            gate = Barrier(20)
            def worker(index):
                try:
                    gate.wait(timeout=10)
                    started = time.perf_counter()
                    with CaptureQueriesContext(connection) as queries:
                        _, entities = UnitService.deploy_units(match, teams[index], "infantry", teams[(index+1)%20].pk,
                            quantity=quantity, idempotency_key=f"benchmark-{index}")
                    return {"creation_ms": round((time.perf_counter()-started)*1000, 2),
                            "queries": len(queries), "ids": [str(e.pk) for e in entities]}
                finally:
                    connections.close_all()
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=20) as pool:
                results = list(pool.map(worker, range(20)))
            elapsed = (time.perf_counter()-started)*1000
            ids = [eid for r in results for eid in r["ids"]]
            assert len(ids) == len(set(ids)) == quantity*20
            assert all(t.coins == 5000-15*quantity for t in match.teams.all())
            match.refresh_from_db()
            started = time.perf_counter()
            ContinuousCombatService.tick(match.pk, datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"]))
            tick_ms = (time.perf_counter()-started)*1000
            started = time.perf_counter()
            with CaptureQueriesContext(connection) as queries:
                RealtimeService.build_snapshot(match)
            snapshot_ms = (time.perf_counter()-started)*1000
            events = list(match.events.filter(event_type="ENTITIES_CREATED"))
            report["scenarios"].append({"teams": 20, "concurrent_commands": 20, "quantity_per_command": quantity,
                "entities": len(ids), "all_commands_ms": round(elapsed, 2),
                "command_median_ms": statistics.median(r["creation_ms"] for r in results),
                "command_max_ms": max(r["creation_ms"] for r in results),
                "command_queries_min": min(r["queries"] for r in results),
                "command_queries_max": max(r["queries"] for r in results),
                "creation_events": len(events), "coin_events": match.events.filter(event_type="COINS_UPDATED", payload__transaction_type="DEPLOY_UNIT").count(),
                "creation_event_bytes": sum(len(json.dumps(e.payload).encode()) for e in events),
                "combat_tick_ms": round(tick_ms, 2), "snapshot_ms": round(snapshot_ms, 2),
                "snapshot_queries": len(queries), "duplicates": 0, "coin_divergence": 0})
        path = Path(__file__).resolve().parents[2] / "docs/qa/artillery-slots-batch-benchmark.json"
        path.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        connections.close_all()
        teardown_databases(old, verbosity=0)


if __name__ == "__main__":
    main()
