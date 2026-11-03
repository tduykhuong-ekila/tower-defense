"""Run only against a disposable local database: creates and deletes measurement matches."""
import asyncio
import json
import platform
import resource
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from apps.combat.benchmark import create_scenario, measure_connections, measure_scenario


class Command(BaseCommand):
    help = 'Measure 4/8/12/16/20-team arenas in the configured disposable database.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--teams', type=int, nargs='+', default=[4, 8, 12, 16, 20])
        parser.add_argument('--keep', action='store_true', help='Keep scenarios for browser inspection.')

    def handle(self, *args, **options):
        settings.DEBUG = False
        report = {'platform': platform.platform(), 'database': 'configured local database',
                  'transport': 'ASGI WebsocketCommunicator + InMemoryChannelLayer (no TCP or Redis)', 'scenarios': []}
        for count in options['teams']:
            for near in [False, True]:
                before_cpu = time.process_time()
                started = time.perf_counter()
                initialization_queries = 0
                def count_query(execute, sql, params, many, context):
                    nonlocal initialization_queries
                    initialization_queries += 1
                    return execute(sql, params, many, context)
                with connection.execute_wrapper(count_query):
                    scenario = create_scenario(count, 4 if count >= 16 else 2, near)
                init_ms = (time.perf_counter()-started)*1000
                result = measure_scenario(scenario)
                result.update({'near_capacity': near, 'initialization_ms': round(init_ms, 2), 'initialization_queries': initialization_queries})
                result['connections'] = asyncio.run(measure_connections(scenario))
                result['cpu_seconds'] = round(time.process_time()-before_cpu, 3)
                # macOS ru_maxrss is bytes; Linux reports KiB.
                result['process_peak_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1048576 if platform.system() == 'Darwin' else 1024), 1)
                report['scenarios'].append(result)
                self.stdout.write(f'{count} teams, near={near}: {result["round_ms_median"]}ms, snapshot {result["snapshot_bytes"]} bytes')
                if not options['keep']:
                    scenario.match.delete()
                else:
                    self.stdout.write(f'Preview match: {scenario.match.id}')
        Path(options['output']).write_text(json.dumps(report, indent=2, ensure_ascii=False))
