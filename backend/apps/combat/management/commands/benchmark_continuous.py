"""Opt-in benchmark: creates then deletes its own rooms in the selected database."""
import json
import platform
import resource
import statistics
import time
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection

from apps.combat.benchmark import create_scenario
from apps.combat.continuous_service import ContinuousCombatService
from apps.matches.services import MatchService


class Command(BaseCommand):
    help = "Measure committed continuous ticks for 2/4/8/12/20 teams; deletes benchmark rooms."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)
        parser.add_argument("--ticks", type=int, default=40)
        parser.add_argument("--near-capacity", action="store_true")

    def handle(self, *args, **options):
        report = {"platform": platform.platform(), "database": connection.vendor,
                  "transport": "InMemory Channels without connected clients; browser TCP results are separate",
                  "scenarios": []}
        for count in [2, 4, 8, 12, 20]:
            scenario = create_scenario(count, players_per_team=1,
                near_capacity=options["near_capacity"], gameplay_mode="CONTINUOUS")
            match = MatchService.advance_phase(scenario.match)
            durations, queries, sizes = [], [], []
            try:
                for _ in range(options["ticks"]):
                    match.refresh_from_db()
                    tick_at = datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
                    query_count = 0
                    def count_query(execute, sql, params, many, context):
                        nonlocal query_count
                        query_count += 1
                        return execute(sql, params, many, context)
                    start = time.perf_counter()
                    with connection.execute_wrapper(count_query):
                        ContinuousCombatService.tick(match.pk, tick_at)
                    durations.append((time.perf_counter() - start) * 1000)
                    queries.append(query_count)
                    event = match.events.filter(event_type="COMBAT_TICK").last()
                    sizes.append(len(json.dumps(event.payload).encode()) if event else 0)
                row = {"teams": count, "entities": match.entities.count(), "ticks": options["ticks"],
                       "tick_ms_median": round(statistics.median(durations), 2),
                       "tick_ms_p95": round(sorted(durations)[int(len(durations) * .95)], 2),
                       "tick_ms_max": round(max(durations), 2),
                       "queries_median": statistics.median(queries),
                       "delta_bytes_median": statistics.median(sizes),
                       "process_peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1048576 if platform.system() == "Darwin" else 1024), 1)}
                report["scenarios"].append(row)
                self.stdout.write(json.dumps(row))
            finally:
                match.delete()
        Path(options["output"]).write_text(json.dumps(report, indent=2))
