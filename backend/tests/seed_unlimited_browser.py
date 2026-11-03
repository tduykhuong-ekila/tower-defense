"""Seed only the disposable, explicitly named unlimited_qa_settings database."""

import json
import os

import django

django.setup()
from django.conf import settings

if settings.SETTINGS_MODULE not in ("config.settings.unlimited_qa", "unlimited_qa_settings"):
    raise RuntimeError("Use config.settings.unlimited_qa, never a normal database")
from apps.combat.map import get_game_map
from apps.matches.serializers import TeamMemberSummarySerializer
from apps.units.models import TeamUnlock, UnitType
from apps.units.placement import map_for_match, placement_grid
from tests.test_continuous_combat import room
from tests.test_unlimited_towers import disjoint_cells

rooms = []
for count, layout in ((2, 6), (4, 6), (8, 6), (20, 6), (2, 5)):
    m, teams, tokens, _ = room(
        count=count,
        initial_coins=10000,
        prep=900,
        battle=900,
        tower_placement_version=1 if layout == 6 else 0,
        arena_layout_version=layout,
    )
    joins = []
    for team, token in zip(teams, tokens):
        member = team.members.first()
        joins.append(
            {"participant_token": token, "member": TeamMemberSummarySerializer(member).data}
        )
        for unit in UnitType.objects.filter(is_starter=False):
            TeamUnlock.objects.get_or_create(team=team, unit_type=unit)
    rooms.append(
        {
            "match": {"id": str(m.pk)},
            "layout": layout,
            "join": joins[0],
            "joins": joins,
            "valid": list(
                {"row": r, "col": c}
                for r, c in disjoint_cells(placement_grid(get_game_map(count, layout)))
            ),
            "all_valid": [
                [
                    {"row": r, "col": c}
                    for r, c in disjoint_cells(placement_grid(get_game_map(count, layout)), owner)
                ]
                for owner in range(1, count + 1)
            ],
            "map": map_for_match(m, [str(t.pk) for t in teams]),
        }
    )
with open(
    "/private/tmp/unlimited-browser-rooms.json", "w", opener=lambda p, f: os.open(p, f, 0o600)
) as f:
    json.dump(rooms, f)
print("Created disposable 2/4/8/20-team QA rooms")
