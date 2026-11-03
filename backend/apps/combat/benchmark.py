"""Explicit, opt-in local arena scenarios and measurement helpers; never run by gameplay."""
import asyncio
import json
import statistics
import time
from dataclasses import dataclass

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.db import connection, reset_queries
from django.test.utils import CaptureQueriesContext

from apps.combat.map import get_game_map
from apps.combat.services import CombatService
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.teams.models import MemberRole
from apps.units.models import GameEntity
from apps.units.seeds import ensure_standard_units
from apps.units.services import ConstructionService, UnitService


@dataclass
class ArenaScenario:
    match: object
    host_token: str
    teams: list
    members: list
    tokens: list
    spectators: list


def create_scenario(count, players_per_team=2, near_capacity=False, gameplay_mode="LEGACY"):
    ensure_standard_units()
    match, host_token = MatchService.create_match(name=f"Arena measurement {count}", configuration={
        "gameplay_mode": gameplay_mode, "tower_placement_version": 0, "arena_layout_version": 5, "min_teams": 2, "max_teams": 20, "initial_coins": 10000,
        "max_active_units_per_team": 30 if near_capacity else 5,
    })
    teams, members, tokens, spectators = [], [], [], []
    for i in range(count):
        team = MatchService.create_team(match, name=f"Đội {i+1:02d}")
        teams.append(team)
        for j in range(players_per_team):
            member, token = MatchService.join_match(match, display_name=f"Player {i+1}-{j+1}",
                team_id=team.id, role=MemberRole.MENTOR if j == 0 else MemberRole.MENTEE)
            members.append(member)
            tokens.append(token)
        MatchService.set_team_ready(team, True)
    for i in range(2):
        _, token = MatchService.join_match(match, display_name=f"Spectator {i+1}", role=MemberRole.SPECTATOR)
        spectators.append(token)
    MatchService.start_match(match)
    match.refresh_from_db()
    for i, team in enumerate(teams):
        # Real deployment and construction paths; no separate client simulation.
        for j in range(3):
            ConstructionService.build_tower(match, team, 'mg_tower', f'node_tower_t{i+1}_slot{j+1}', idempotency_key=f'{match.id}-t{i}-{j}')
        for j in range(30 if near_capacity else 5):
            UnitService.deploy_unit(match, team, 'infantry', str(teams[(i+1) % count].id), idempotency_key=f'{match.id}-u{i}-{j}')
    return ArenaScenario(match, host_token, teams, members, tokens, spectators)


def measure_scenario(scenario, rounds=5):
    match = scenario.match
    samples, queries, event_bytes = [], [], []
    for _ in range(rounds):
        match.refresh_from_db()
        reset_queries()
        with CaptureQueriesContext(connection) as capture:
            started = time.perf_counter()
            result = CombatService.execute_combat_round(match, expected_round=match.configuration.get('current_round', 1))
            samples.append((time.perf_counter()-started)*1000)
        queries.append(len(capture))
        event_bytes.append(len(json.dumps(result.events, ensure_ascii=False).encode()))
    match.refresh_from_db()
    reset_queries()
    with CaptureQueriesContext(connection) as capture:
        started = time.perf_counter()
        snapshot = RealtimeService.build_snapshot(match, viewer_team_id=str(scenario.teams[0].id))
        snapshot_ms = (time.perf_counter()-started)*1000
    return {
        'teams': len(scenario.teams), 'players': len(scenario.members),
        'entities_created': GameEntity.objects.filter(match=match).count(),
        'round_ms_median': round(statistics.median(samples), 2), 'round_ms_max': round(max(samples), 2),
        'round_queries_max': max(queries), 'event_bytes_max': max(event_bytes),
        'snapshot_ms': round(snapshot_ms, 2), 'snapshot_queries': len(capture),
        'snapshot_bytes': len(json.dumps(snapshot, ensure_ascii=False).encode()),
        'arena': get_game_map(len(scenario.teams)).to_dict()['arena'],
    }


async def measure_connections(scenario):
    """Real authenticated ASGI consumers and Channels groups; no TCP/Redis latency claim."""
    from config.asgi import application

    tokens = scenario.tokens + scenario.spectators + [scenario.host_token]
    comms = [WebsocketCommunicator(application, f'/ws/matches/{scenario.match.id}/?token={token}') for token in tokens]
    async def open_client(comm):
        begin = time.perf_counter()
        connected, _ = await comm.connect(timeout=20)
        assert connected
        snapshot = await comm.receive_json_from(timeout=20)
        assert len(snapshot['payload']['teams']) == len(scenario.teams)
        return (time.perf_counter()-begin)*1000
    try:
        initial = await asyncio.gather(*(open_client(c) for c in comms))
        from apps.realtime.events import ServerEventType
        begin = time.perf_counter()
        await database_sync_to_async(RealtimeService.emit_event)(
            scenario.match, event_type=ServerEventType.MATCH_PHASE_CHANGED, payload={'phase': 'PREPARATION'})
        async def receive_client(comm):
            message = await comm.receive_json_from(timeout=20)
            assert message['event_type'] == ServerEventType.MATCH_PHASE_CHANGED
            return (time.perf_counter()-begin)*1000
        latency = await asyncio.gather(*(receive_client(c) for c in comms))
        return {'clients': len(comms), 'initial_snapshot_ms_median': round(statistics.median(initial), 2),
                'initial_snapshot_ms_max': round(max(initial), 2),
                'inprocess_fanout_ms_median': round(statistics.median(latency), 2),
                'inprocess_fanout_ms_max': round(max(latency), 2)}
    finally:
        await asyncio.gather(*(c.disconnect() for c in comms))
