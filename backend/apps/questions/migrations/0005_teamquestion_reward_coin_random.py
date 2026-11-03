from django.db import migrations, models


def enable_unanswered_bags(apps, schema_editor):
    # Earned rewards stay fixed; unanswered missions adopt the new odds at rollout.
    TeamQuestion = apps.get_model("questions", "TeamQuestion")
    TeamQuestion.objects.filter(status="PENDING_QUESTION").update(reward_coin_random=True)


class Migration(migrations.Migration):
    dependencies = [("questions", "0004_persistent_countdown")]

    operations = [
        migrations.AddField(
            model_name="teamquestion",
            name="reward_coin_random",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(enable_unanswered_bags, migrations.RunPython.noop),
    ]
