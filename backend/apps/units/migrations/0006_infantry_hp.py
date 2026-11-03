from django.db import migrations


def update_infantry_catalog(apps, schema_editor):
    UnitType = apps.get_model("units", "UnitType")
    for unit in UnitType.objects.filter(code="infantry", category="UNIT"):
        UnitType.objects.filter(pk=unit.pk).update(base_stats={**unit.base_stats, "hp": 80})
    # Entity current_hp/max_hp are deliberate per-instance snapshots. Never
    # rewrite survivors, heal damaged troops, or revive destroyed troops.


class Migration(migrations.Migration):
    dependencies = [("units", "0005_mobile_troop_hp")]
    operations = [migrations.RunPython(update_infantry_catalog, migrations.RunPython.noop)]
