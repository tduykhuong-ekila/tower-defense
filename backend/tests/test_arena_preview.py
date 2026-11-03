import io
import json
import stat

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.matches.models import Match
from apps.questions.models import Question
from apps.units.models import GameEntity


def test_preview_seed_refuses_regular_database_settings():
    with pytest.raises(CommandError, match='isolated local preview'):
        call_command('seed_arena', teams=20)


@pytest.mark.django_db
def test_preview_seed_is_reusable_and_does_not_print_credentials(tmp_path):
    with override_settings(SETTINGS_MODULE='config.settings.preview', PREVIEW_DIRECTORY=tmp_path):
        output = io.StringIO()
        call_command('seed_arena', teams=2, stdout=output)
        match = Match.objects.get()
        assert match.teams.count() == 2
        assert GameEntity.objects.filter(match=match).count() == 16
        assert match.configuration['allow_late_join'] is True
        question_count = Question.objects.count()
        assert question_count >= 40
        receipt_path = tmp_path / 'arena-2-2-standard.json'
        receipt = json.loads(receipt_path.read_text())
        assert receipt['match_id'] == str(match.id)
        assert receipt['host_token'] not in output.getvalue()
        assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
        call_command('seed_arena', teams=2, stdout=output)
        assert Match.objects.count() == 1
        assert GameEntity.objects.filter(match=match).count() == 16
        assert 'Reused:' in output.getvalue()
        assert Question.objects.count() == question_count
        with pytest.raises(CommandError, match='between 2 and 20'):
            call_command('seed_arena', teams=21)
