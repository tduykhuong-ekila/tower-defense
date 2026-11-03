from django.db import migrations
from django.db.models import Max


def reconcile(apps, schema_editor):
    Entity = apps.get_model("units", "GameEntity")
    Upgrade = apps.get_model("units", "TeamUnitUpgrade")
    # Preserve paid legacy tower upgrades; promote each type to its highest owned level.
    for row in Entity.objects.filter(level__gt=1).values("team_id", "unit_type_id").annotate(highest=Max("level")):
        level = min(4, row["highest"])
        Upgrade.objects.update_or_create(team_id=row["team_id"], unit_type_id=row["unit_type_id"], defaults={"level": level})
        for entity in Entity.objects.filter(team_id=row["team_id"], unit_type_id=row["unit_type_id"],
                                             status__in=["ACTIVE", "QUEUED", "DISABLED"], current_hp__gt=0).select_related("unit_type"):
            hp = entity.unit_type.base_stats.get("hp", 100)
            new_max = int(hp * {1: 1, 2: 1.15, 3: 1.3, 4: 1.5}[level] + .5)
            entity.current_hp = min(new_max, max(1, int(entity.current_hp / max(1, entity.max_hp) * new_max + .5)))
            entity.max_hp, entity.level = new_max, level
            entity.save(update_fields=["current_hp", "max_hp", "level"])


class Migration(migrations.Migration):
    dependencies = [("units", "0009_alter_gameaction_action_type_teamunitupgrade")]
    operations = [migrations.RunPython(reconcile, migrations.RunPython.noop)]
