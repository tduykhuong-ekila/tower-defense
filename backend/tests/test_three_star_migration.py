"""The schema conversion keeps paid legacy matches playable at Level 3."""

from importlib import import_module

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from apps.units.models import GameEntity, TeamUnitUpgrade, UnitType
from apps.units.services import UnitService
from tests.test_continuous_combat import room


@pytest.mark.django_db(transaction=True)
def test_level_four_migration_preserves_hp_ratio_and_destroyed_state():
    old = ("units", "0012_cannon_damage")
    new = ("units", "0013_three_upgrade_levels")
    executor = MigrationExecutor(connection)
    executor.migrate([old])
    try:
        match, teams, _, _ = room(initial_coins=1000)
        infantry = UnitType.objects.get(code="infantry")
        TeamUnitUpgrade.objects.create(team=teams[0], unit_type=infantry, level=4)
        _, entity = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
        entity.level, entity.max_hp, entity.current_hp = 4, 120, 40
        entity.save(update_fields=["level", "max_hp", "current_hp"])
        wreck = GameEntity.objects.create(
            match=match, team=teams[0], unit_type=infantry, entity_kind="UNIT",
            level=4, max_hp=120, current_hp=0, status="DESTROYED",
        )
        invalid_old = GameEntity.objects.create(
            match=match, team=teams[1], unit_type=infantry, entity_kind="UNIT",
            level=0, max_hp=80, current_hp=20, status="ACTIVE",
        )
        executor = MigrationExecutor(connection)
        executor.migrate([new])
        entity.refresh_from_db()
        wreck.refresh_from_db()
        invalid_old.refresh_from_db()
        assert (entity.level, entity.max_hp, entity.current_hp) == (3, 104, 35)
        assert (wreck.level, wreck.max_hp, wreck.current_hp, wreck.status) == (3, 104, 0, "DESTROYED")
        assert (invalid_old.level, invalid_old.max_hp, invalid_old.current_hp) == (1, 80, 20)
        assert TeamUnitUpgrade.objects.get(team=teams[0], unit_type=infantry).level == 3
        # Re-running the conversion cannot heal units or charge/refund coins.
        migration = import_module("apps.units.migrations.0013_three_upgrade_levels")
        with connection.schema_editor() as schema_editor:
            migration.cap_legacy_levels(executor.loader.project_state([new]).apps, schema_editor)
        entity.refresh_from_db()
        assert entity.current_hp == 35
        with pytest.raises(IntegrityError), transaction.atomic():
            TeamUnitUpgrade.objects.filter(team=teams[0], unit_type=infantry).update(level=4)
        with pytest.raises(IntegrityError), transaction.atomic():
            TeamUnitUpgrade.objects.filter(team=teams[0], unit_type=infantry).update(level=0)
        with pytest.raises(IntegrityError), transaction.atomic():
            GameEntity.objects.filter(pk=entity.pk).update(level=0)
        with pytest.raises(IntegrityError), transaction.atomic():
            GameEntity.objects.filter(pk=entity.pk).update(level=4)
    finally:
        MigrationExecutor(connection).migrate([new])
