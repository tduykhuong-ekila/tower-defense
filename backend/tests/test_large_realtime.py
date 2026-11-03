"""Large envelopes cross both channel-layer and WebSocket limits safely."""
import asyncio
import json

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.db import connections

from apps.matches.services import MatchService
from config.asgi import application
from tests.test_continuous_combat import room, until


async def assembled(client):
    parts, transfer = [], None
    while True:
        packet = await client.receive_json_from(timeout=10)
        assert packet["event_type"] == "JSON_CHUNK"
        assert len(json.dumps(packet).encode()) < 128 * 1024
        payload = packet["payload"]
        transfer = transfer or payload["id"]
        assert payload["id"] == transfer and payload["index"] == len(parts)
        parts.append(payload["data"])
        if len(parts) == payload["total"]:
            return json.loads("".join(parts))


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_two_megabyte_event_reference_stays_scoped_and_reassembles_identically():
    match, teams, tokens, _ = await database_sync_to_async(room)(prep=300)
    clients = [WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={tokens[i]}") for i in range(2)]
    try:
        for client in clients:
            assert (await client.connect())[0]
            await until(client, "MATCH_STATE_SNAPSHOT")
        data = "Infantry Bộ binh 🚀" * 100000
        event = await database_sync_to_async(MatchService.record_match_event)(match, "LARGE_TEST", {
            "team_id": str(teams[0].pk), "coins_after": 123, "data": data})
        a, b = await asyncio.gather(*(assembled(client) for client in clients))
        assert a["event_id"] == b["event_id"] == str(event.pk)
        assert a["sequence_number"] == b["sequence_number"] == event.sequence_number
        assert a["payload"]["data"] == b["payload"]["data"] == data
        assert a["payload"]["coins_after"] == 123 and "coins_after" not in b["payload"]
    finally:
        await asyncio.gather(*(client.disconnect() for client in clients))
        await database_sync_to_async(connections.close_all)()
