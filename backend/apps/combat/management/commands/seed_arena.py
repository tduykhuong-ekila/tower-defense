"""Create or reuse a persistent local preview through the real game services."""

import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.combat.benchmark import create_scenario
from apps.matches.management.commands.seed_demo import DEMO_QUESTIONS
from apps.matches.models import Match
from apps.questions.models import Question


class Command(BaseCommand):
    help = "Create/reuse a 2–20-team arena in the dedicated preview database."

    def add_arguments(self, parser):
        parser.add_argument("--teams", type=int, default=20)
        parser.add_argument("--players", type=int, choices=[2, 3, 4], default=2)
        parser.add_argument("--near-capacity", action="store_true")

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != "config.settings.preview":
            raise CommandError("Use --settings=config.settings.preview for the isolated local preview.")
        count = options["teams"]
        if not 2 <= count <= 20:
            raise CommandError("--teams must be between 2 and 20.")
        return self._seed(count, options)

    @transaction.atomic
    def _seed(self, count, options):
        for item in DEMO_QUESTIONS:
            Question.objects.get_or_create(content=item["content"], defaults={
                **{key: value for key, value in item.items() if key != "content"},
                "is_active": True,
            })
        load = "near" if options["near_capacity"] else "standard"
        name = f"Arena preview {count} teams / {options['players']} players / {load}"
        match = Match.objects.filter(name=name).order_by("-created_at").first()
        if match is None:
            scenario = create_scenario(count, options["players"], options["near_capacity"])
            match = scenario.match
            match.name = name
            match.configuration["allow_late_join"] = True
            match.save(update_fields=["name", "configuration"])
            receipt = Path(settings.PREVIEW_DIRECTORY) / f"arena-{count}-{options['players']}-{load}.json"
            # Local fixture credentials are deliberately excluded from source control.
            with open(receipt, "w", opener=lambda path, flags: os.open(path, flags, 0o600)) as out:
                json.dump({"match_id": str(match.id), "room_code": match.room_code,
                           "host_token": scenario.host_token}, out)
            created = "Created"
        else:
            created = "Reused"
        self.stdout.write(f"{created}: {match.id} / room {match.room_code}")
        self.stdout.write(f"Join: http://localhost:5174/join?code={match.room_code}")
