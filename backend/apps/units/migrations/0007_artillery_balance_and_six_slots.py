from django.db import migrations


def rebalance(apps, schema_editor):
    UnitType = apps.get_model("units", "UnitType")
    GameEntity = apps.get_model("units", "GameEntity")
    Match = apps.get_model("matches", "Match")
    for unit in UnitType.objects.filter(code="artillery", category="UNIT"):
        previous_range = unit.base_stats.get("range", 3)
        for entity in GameEntity.objects.filter(unit_type=unit).iterator():
            state = dict(entity.simulation_state or {})
            state.setdefault("attack_range", previous_range)
            GameEntity.objects.filter(pk=entity.pk).update(simulation_state=state)
        UnitType.objects.filter(pk=unit.pk).update(
            base_stats={**unit.base_stats, "hp": 70, "range": previous_range * .5},
            description=unit.description.replace("3 node", "1.5 node"),
        )
    # Never rewrite entity HP: damaged survivors and destroyed instances stay intact.
    for match in Match.objects.all().iterator():
        config = {**match.configuration, "max_towers_per_team": 6,
                  "max_deployed_units_per_action": None}
        Match.objects.filter(pk=match.pk).update(configuration=config)


class Migration(migrations.Migration):
    dependencies = [("units", "0006_infantry_hp"),
                    ("matches", "0003_match_creation_token_hash_match_question_bank")]
    operations = [migrations.RunPython(rebalance, migrations.RunPython.noop)]
