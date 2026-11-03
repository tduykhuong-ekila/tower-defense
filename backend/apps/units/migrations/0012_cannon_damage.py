from django.db import migrations


def rebalance(apps, schema_editor):
    UnitType = apps.get_model("units", "UnitType")
    for unit in UnitType.objects.filter(code="cannon_tower", category="TOWER"):
        UnitType.objects.filter(pk=unit.pk).update(
            base_stats={**unit.base_stats, "damage": 20},
            description=unit.description.replace("sát thương 30/round", "sát thương 20/round"),
        )


class Migration(migrations.Migration):
    dependencies = [("units", "0011_tactical_army_commands")]
    operations = [migrations.RunPython(rebalance, migrations.RunPython.noop)]
