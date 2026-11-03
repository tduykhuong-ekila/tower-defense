"""Disposable browser fixture: six canonical types, two clients and 2/4/8/20 arenas.
Run from backend with .venv/bin/python tests/roadside_stars_preview.py.
"""
import json
import os
import runpy
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.preview'
import django
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command

with TemporaryDirectory(prefix='roadside-stars-') as directory:
    settings.DATABASES['default']['NAME'] = str(Path(directory) / 'preview.sqlite3')
    settings.MATCH_SCHEDULER_ENABLED = True
    django.setup()
    call_command('migrate', verbosity=0)
    os.environ['GRID_QA_ROOMS'] = '/private/tmp/roadside-stars-rooms.json'
    runpy.run_path('tests/seed_grid_browser.py')
    from apps.combat.build_geometry import segment_rect_distance
    from apps.combat.map import get_game_map
    from apps.matches.models import Match
    from apps.units.placement import placement_grid
    from apps.units.services import ConstructionService, UnitService
    from tests.test_roadside_ranks import export_fixtures
    export_fixtures('../frontend/tests/fixtures/grid-maps.json')
    rooms = json.loads(Path(os.environ['GRID_QA_ROOMS']).read_text())
    for data in rooms:
        match = Match.objects.get(pk=data['match']['id'])
        teams = [match.teams.get(pk=id) for id in data['map']['team_ids']]
        grid = placement_grid(get_game_map(len(teams), 6))
        def distance_to_road(cell):
            r, c = cell['row'], cell['col']
            rect = (c*32-grid.offset[0], r*32-grid.offset[1], (c+3)*32-grid.offset[0], (r+3)*32-grid.offset[1])
            return min(segment_rect_distance(a, b, rect) for a, b in grid.roads) - 28.5
        data['roadside'] = sorted(data['valid'], key=distance_to_road)[:100]
        data['nearestRoadGap'] = distance_to_road(data['roadside'][0])
        for code in ['infantry','tank','artillery']:
            UnitService.deploy_units(match, teams[0], code, str(teams[1].pk), quantity=2)
        UnitService.deploy_units(match, teams[1], 'infantry', str(teams[0].pk), quantity=1)
        occupied = []
        for code in ['cannon_tower','mg_tower','shield_generator']:
            for cell in reversed(data['valid']):
                try:
                    grid.validate(cell['row'], cell['col'], code, 1, occupied)
                except ValidationError:
                    continue
                _, entity = ConstructionService.build_tower(match, teams[0], code, grid_row=cell['row'], grid_col=cell['col'], idempotency_key=code)
                occupied.append(entity)
                break
            else:
                raise RuntimeError(f"No safe fixture placement for {code}")
    Path(os.environ['GRID_QA_ROOMS']).write_text(json.dumps(rooms))
    print('Roadside/stars isolated browser fixtures ready', flush=True)
    call_command('runserver', '127.0.0.1:8018', use_reloader=False, verbosity=0)
