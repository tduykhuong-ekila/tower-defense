"""Recovery endpoint/outbox and actual projected formation footprint regressions."""

import copy
from unittest.mock import patch

import pytest
from django.db import transaction
from rest_framework.test import APIClient

from apps.combat.balance import movement_speed
from apps.combat.continuous import ContinuousEngine
from apps.combat.formation import bodies_clear, physical_position
from apps.combat.map import get_game_map
from apps.matches.models import MatchEvent
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.units.services import UnitService
from tests.test_continuous_combat import room
from tests.test_live_battle_gameplay import convoy


@pytest.mark.parametrize("codes", [("tank",) * 5, ("tank", "tank", "artillery")])
def test_compact_projected_body_clearance_survives_curves_and_mixed_anchors(codes):
    state = convoy(codes)
    game_map = get_game_map(2)
    for _ in range(180):
        state = ContinuousEngine.step(state, 0.2).new_state
        ordered = sorted(state.entities, key=lambda e: e["simulation_state"]["formation_order"])
        for front, rear in zip(ordered, ordered[1:]):
            fp = physical_position(front, game_map)
            rp = physical_position(rear, game_map)
            assert bodies_clear(front, rear, fp, rp, state.configuration)


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_unobstructed_arc_travel_time_matches_configured_speed(code):
    state = convoy((code,))
    unit = state.entities[0]
    # Stay far from enemy combat and route end; compare same fixed arc length.
    speed = movement_speed(unit, state.configuration)
    distance = speed * .5
    elapsed = 0
    while unit["simulation_state"]["route_distance"] < distance - 1e-8:
        state = ContinuousEngine.step(state, 0.1).new_state
        unit = state.entities[0]
        elapsed += 0.1
    assert elapsed == pytest.approx(distance / speed, abs=0.1)
    restored = copy.deepcopy(unit)
    assert movement_speed(restored, state.configuration) == speed


@pytest.mark.django_db
def test_snapshot_endpoint_is_versioned_and_scoped_to_verified_viewer():
    match, teams, tokens, _ = room()
    UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    client = APIClient()
    public = client.get(f"/api/v1/matches/{match.pk}/snapshot/").json()
    assert (
        public["state_version"]
        == public["sequence_number"]
        == match.events.latest("sequence_number").sequence_number
    )
    assert len(public["payload"]["entities"]) == 1
    assert all("coins" not in team for team in public["payload"]["teams"])
    own = client.get(
        f"/api/v1/matches/{match.pk}/snapshot/", HTTP_X_PARTICIPANT_TOKEN=tokens[0]
    ).json()
    assert own["payload"]["viewer"]["team_id"] == str(teams[0].pk)
    assert next(t for t in own["payload"]["teams"] if t["id"] == str(teams[0].pk))["coins"] == 485
    assert "coins" not in next(t for t in own["payload"]["teams"] if t["id"] == str(teams[1].pk))


@pytest.mark.django_db(transaction=True)
def test_rollback_never_broadcasts_and_failed_publication_retains_stable_outbox_id(caplog):
    match, _, _, _ = room()
    with patch.object(RealtimeService, "broadcast_match_event") as broadcast:
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                MatchService.record_match_event(
                    match, "UNIT_DEPLOYED", {"entity_id": "rolled-back"}
                )
                raise RuntimeError("rollback")
        broadcast.assert_not_called()
        assert not MatchEvent.objects.filter(match=match, payload__entity_id="rolled-back").exists()
    # Force a transport failure after commit, then retry the exact durable row.
    with patch("apps.realtime.services.get_channel_layer", side_effect=RuntimeError("offline")):
        event = MatchService.record_match_event(match, "UNIT_DEPLOYED", {"entity_id": "stable"})
    event.refresh_from_db()
    assert event.broadcasted_at is None
    failure = next(r for r in caplog.records if "Realtime broadcast failed" in r.message)
    assert failure.match_id == str(match.pk) and failure.sequence == event.sequence_number
    assert failure.entity_id == "stable" and failure.exc_info
    RealtimeService.broadcast_match_event(event)
    event.refresh_from_db()
    assert event.broadcasted_at is not None
