"""Reward previews share effective catalog stats and locked eligibility."""
from types import SimpleNamespace

import pytest

from apps.rewards.services import RewardService
from apps.units.models import TeamUnlock, UnitType
from apps.units.serializers import UnitTypeSerializer
from tests.test_continuous_combat import room


@pytest.mark.django_db
def test_reward_previews_use_effective_catalog_stats_and_exclude_unlocked():
    match, teams, _, _ = room()
    question = SimpleNamespace(id="preview", team=teams[0], reward_coin_amount=30)
    options = RewardService.get_reward_options(question)
    assert options["coin_amount"] == 30
    codes = {unit["code"] for unit in options["eligible_units"]}
    assert {"tank", "artillery", "cannon_tower", "shield_generator"} <= codes
    for preview in options["eligible_units"]:
        unit = UnitType.objects.get(code=preview["code"])
        catalog = UnitTypeSerializer(unit, context={"team": teams[0], "match": match}).data
        assert all(preview[field] == catalog[field] for field in ("hp", "damage", "range", "movement_speed", "cost"))
        assert not preview["is_unlocked"]
    artillery = next(u for u in options["eligible_units"] if u["code"] == "artillery")
    assert (artillery["hp"], artillery["movement_speed"], artillery["range"]) == (80, 5, 1.5)
    TeamUnlock.objects.create(team=teams[0], unit_type=UnitType.objects.get(code="tank"))
    assert "tank" not in {u["code"] for u in RewardService.get_reward_options(question)["eligible_units"]}
