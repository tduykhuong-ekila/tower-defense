"""Convert paid Level 4 state before enforcing the three-level schema."""

from django.db import migrations, models
from django.db.models import Q


def cap_legacy_levels(apps, schema_editor):
    Upgrade = apps.get_model("units", "TeamUnitUpgrade")
    Entity = apps.get_model("units", "GameEntity")
    database = schema_editor.connection.alias

    affected = set(
        Upgrade.objects.using(database).filter(level__gt=3)
        .values_list("team_id", "unit_type_id")
    )
    affected.update(
        Entity.objects.using(database).filter(level__gt=3)
        .values_list("team_id", "unit_type_id")
    )
    for team_id, unit_type_id in affected:
        record, _ = Upgrade.objects.using(database).get_or_create(
            team_id=team_id, unit_type_id=unit_type_id, defaults={"level": 3}
        )
        if record.level != 3:
            record.level = 3
            record.save(using=database, update_fields=["level"])
        for entity in Entity.objects.using(database).filter(
            team_id=team_id, unit_type_id=unit_type_id
        ).select_related("unit_type").iterator():
            base = entity.unit_type.base_stats or {}
            if entity.entity_kind == "UNIT":
                code = entity.unit_type.code
                hp = 80 if code in ("infantry", "artillery") else (100 if base.get("movement", 1) > 0 else base.get("hp", 100))
            else:
                hp = base.get("hp", 100)
            new_max = int(hp * 1.30 + 0.5)
            if entity.current_hp > 0 and entity.status in ("ACTIVE", "QUEUED", "DISABLED"):
                entity.current_hp = min(new_max, max(1, int(entity.current_hp / max(1, entity.max_hp) * new_max + 0.5)))
            # Destroyed entities keep their zero HP; no coins or actions are touched.
            entity.max_hp = new_max
            entity.level = 3
            entity.save(using=database, update_fields=["current_hp", "max_hp", "level"])
    # The older entity table had no level constraint. Its combat modifiers
    # already treated nonpositive values as Level 1, so normalize them in place.
    Entity.objects.using(database).filter(level__lt=1).update(level=1)


class Migration(migrations.Migration):
    dependencies = [("units", "0012_cannon_damage")]
    operations = [
        migrations.RunPython(cap_legacy_levels, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="teamunitupgrade", name="team_upgrade_level_1_4"),
        migrations.AddConstraint(
            model_name="teamunitupgrade",
            constraint=models.CheckConstraint(condition=Q(level__gte=1, level__lte=3), name="team_upgrade_level_1_3"),
        ),
        migrations.AddConstraint(
            model_name="gameentity",
            constraint=models.CheckConstraint(condition=Q(level__gte=1, level__lte=3), name="game_entity_level_1_3"),
        ),
    ]
