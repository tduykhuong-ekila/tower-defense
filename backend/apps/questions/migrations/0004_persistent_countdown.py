from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def resume_hidden(apps, schema_editor):
    TeamQuestion = apps.get_model("questions", "TeamQuestion")
    now = timezone.now()
    for question in TeamQuestion.objects.filter(status="PENDING_QUESTION", timer_status="PAUSED", match__status="ACTIVE"):
        # A legacy paused session retains its remaining budget at rollout.
        question.timer_status = "RUNNING"
        question.timer_started_at = now
        question.expires_at = now + timedelta(milliseconds=question.remaining_ms)
        question.viewing_leases = {}
        question.timer_version += 1
        question.save()


class Migration(migrations.Migration):
    dependencies = [("questions", "0003_teamquestion_remaining_ms_and_more")]
    operations = [migrations.RunPython(resume_hidden, migrations.RunPython.noop)]
