"""Increase active attack towers' range by one node."""

from django.db import migrations


ATTACK_TOWER_CODES = ("mg_tower", "cannon_tower")


def shift_tower_ranges(apps, schema_editor, amount):
    UnitType = apps.get_model("units", "UnitType")
    GameEntity = apps.get_model("units", "GameEntity")
    database = schema_editor.connection.alias

    for unit in UnitType.objects.using(database).filter(
        code__in=ATTACK_TOWER_CODES, category="TOWER"
    ).iterator():
        stats = dict(unit.base_stats or {})
        stats["range"] = stats.get("range", 2) + amount
        description = unit.description or ""
        if unit.code == "cannon_tower":
            old_phrase, new_phrase = (
                ("tầm bắn lên tới 2 node", "tầm bắn lên tới 3 node")
                if amount > 0 else
                ("tầm bắn lên tới 3 node", "tầm bắn lên tới 2 node")
            )
            description = description.replace(old_phrase, new_phrase)
        UnitType.objects.using(database).filter(pk=unit.pk).update(
            base_stats=stats, description=description
        )

        # Some existing Cannon Towers carry a per-instance range snapshot. Shift
        # it too, so live towers and new towers both gain the requested range.
        for entity in GameEntity.objects.using(database).filter(unit_type_id=unit.pk).iterator():
            state = dict(entity.simulation_state or {})
            if "attack_range" not in state:
                continue
            state["attack_range"] += amount
            GameEntity.objects.using(database).filter(pk=entity.pk).update(simulation_state=state)


def increase_ranges(apps, schema_editor):
    shift_tower_ranges(apps, schema_editor, 1)


def restore_ranges(apps, schema_editor):
    shift_tower_ranges(apps, schema_editor, -1)


class Migration(migrations.Migration):
    dependencies = [("units", "0013_three_upgrade_levels")]

    operations = [migrations.RunPython(increase_ranges, restore_ranges)]
