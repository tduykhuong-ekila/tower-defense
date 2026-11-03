from django.db import migrations


def normalize_mobile_hp(apps, schema_editor):
    UnitType = apps.get_model("units", "UnitType")
    GameEntity = apps.get_model("units", "GameEntity")
    for unit in UnitType.objects.filter(category="UNIT").iterator():
        stats = unit.base_stats or {}
        if stats.get("movement", 1) <= 0:
            continue
        stats = {**stats, "hp": 100}
        UnitType.objects.filter(pk=unit.pk).update(base_stats=stats)
        # Preserve damage already taken. Values above the new maximum are clamped.
        for entity in GameEntity.objects.filter(unit_type_id=unit.pk, entity_kind="UNIT").iterator():
            GameEntity.objects.filter(pk=entity.pk).update(max_hp=100, current_hp=min(100, max(0, entity.current_hp)))


class Migration(migrations.Migration):
    dependencies = [("units", "0004_gameentity_simulation_state")]
    operations = [migrations.RunPython(normalize_mobile_hp, migrations.RunPython.noop)]
