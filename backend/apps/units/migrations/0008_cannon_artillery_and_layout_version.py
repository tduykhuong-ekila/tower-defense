from django.db import migrations


def rebalance(apps, schema_editor):
    UnitType = apps.get_model("units", "UnitType")
    GameEntity = apps.get_model("units", "GameEntity")
    Match = apps.get_model("matches", "Match")
    for unit in UnitType.objects.filter(code="cannon_tower", category="TOWER"):
        previous = unit.base_stats.get("range", 3)
        # Existing instances retain their effective range, including custom stats.
        for entity in GameEntity.objects.filter(unit_type=unit).iterator():
            state = dict(entity.simulation_state or {})
            state.setdefault("attack_range", previous)
            GameEntity.objects.filter(pk=entity.pk).update(simulation_state=state)
        UnitType.objects.filter(pk=unit.pk).update(
            base_stats={**unit.base_stats, "range": previous * (2 / 3)},
            description=unit.description.replace(f"{previous:g} node", f"{previous * (2 / 3):g} node"),
        )
    for unit in UnitType.objects.filter(code="artillery", category="UNIT"):
        UnitType.objects.filter(pk=unit.pk).update(base_stats={**unit.base_stats, "hp": 80})
    # Never heal/revive deployed Artillery or move existing foundations/towers.
    for match in Match.objects.all().iterator():
        config = dict(match.configuration or {})
        config.setdefault("arena_layout_version", 3)
        Match.objects.filter(pk=match.pk).update(configuration=config)


class Migration(migrations.Migration):
    dependencies = [("units", "0007_artillery_balance_and_six_slots")]
    operations = [migrations.RunPython(rebalance, migrations.RunPython.noop)]
