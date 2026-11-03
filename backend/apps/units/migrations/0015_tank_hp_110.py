"""Raise the standard Tank catalog HP to 110 without changing deployed units."""

from django.db import migrations


def set_tank_hp(apps, schema_editor, hp):
    UnitType = apps.get_model("units", "UnitType")
    database = schema_editor.connection.alias
    for unit in UnitType.objects.using(database).filter(code="tank", category="UNIT").iterator():
        stats = dict(unit.base_stats or {})
        stats["hp"] = hp
        UnitType.objects.using(database).filter(pk=unit.pk).update(base_stats=stats)


def increase_tank_hp(apps, schema_editor):
    set_tank_hp(apps, schema_editor, 110)


def restore_tank_hp(apps, schema_editor):
    set_tank_hp(apps, schema_editor, 100)


class Migration(migrations.Migration):
    dependencies = [("units", "0014_increase_attack_tower_range")]

    operations = [migrations.RunPython(increase_tank_hp, restore_tank_hp)]
