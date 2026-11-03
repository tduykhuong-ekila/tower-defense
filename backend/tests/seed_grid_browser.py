import json
import os
import sys

# Run with DJANGO_SETTINGS_MODULE=config.settings.preview against its isolated database.
import django

django.setup()
from django.conf import settings

if settings.SETTINGS_MODULE != "config.settings.preview":
    raise RuntimeError(
        "Use config.settings.preview; this fixture must never seed a normal game database."
    )
from apps.combat.map import get_game_map
from apps.matches.serializers import TeamMemberSummarySerializer as TeamMemberSerializer
from apps.matches.services import MatchService
from apps.units.models import TeamUnlock, UnitType
from apps.units.placement import map_for_match, placement_grid
from apps.units.seeds import ensure_standard_units

ensure_standard_units()
rooms = []
for count in [2, 4, 8, 20]:
    m, host = MatchService.create_match(
        name=f"Grid browser QA {count}",
        configuration={
            "max_teams": count,
            "initial_coins": 5000,
            "first_preparation_duration_seconds": 900,
            "preparation_duration_seconds": 900,
        },
    )
    teams = []
    joins = []
    for i in range(count):
        t = MatchService.create_team(m, f"Grid Team {i + 1}")
        member, token = MatchService.join_match(m, f"Grid Player {i + 1}", team_id=t.pk)
        MatchService.set_team_ready(t, True)
        teams.append(t)
        joins.append({"participant_token": token, "member": TeamMemberSerializer(member).data})
        for u in UnitType.objects.filter(is_starter=False):
            TeamUnlock.objects.get_or_create(team=t, unit_type=u)
    m = MatchService.start_match(m)
    g = placement_grid(get_game_map(count, 6))
    valid = []
    for r in range(g.rows - 2):
        for c in range(g.cols - 2):
            if all(g.owners[y * g.cols + x] == 1 for y in range(r, r + 3) for x in range(c, c + 3)):
                valid.append({"row": r, "col": c})
    data = {
        "match": {"id": str(m.pk)},
        "host_token": host,
        "join": joins[0],
        "joins": joins,
        "valid": valid,
        "map": map_for_match(m, [str(t.pk) for t in teams]),
    }
    rooms.append(data)
with open(
    os.environ.get("GRID_QA_ROOMS", "/private/tmp/grid-browser-rooms.json"),
    "w",
    opener=lambda path, flags: os.open(path, flags, 0o600),
) as f:
    json.dump(rooms, f)
print("Created isolated grid QA rooms:", [2, 4, 8, 20])
