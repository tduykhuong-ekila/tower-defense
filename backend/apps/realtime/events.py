"""
Standardized Event Definitions and Envelope according to GDD §21.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class ServerEventType:
    SESSION_BLOCKED = "SESSION_BLOCKED"
    MATCH_STATE_SNAPSHOT = "MATCH_STATE_SNAPSHOT"
    MATCH_PHASE_CHANGED = "MATCH_PHASE_CHANGED"
    QUESTION_ASSIGNED = "QUESTION_ASSIGNED"
    ANSWER_RESULT = "ANSWER_RESULT"
    REWARD_OPTIONS = "REWARD_OPTIONS"
    REWARD_APPLIED = "REWARD_APPLIED"
    ACTION_ACCEPTED = "ACTION_ACCEPTED"
    ACTION_REJECTED = "ACTION_REJECTED"
    UNIT_DEPLOYED = "UNIT_DEPLOYED"
    ENTITIES_CREATED = "ENTITIES_CREATED"
    UNITS_RETARGETED = "UNITS_RETARGETED"
    ARMY_DEFENSE_ORDERED = "ARMY_DEFENSE_ORDERED"
    ARMY_RETREAT_ORDERED = "ARMY_RETREAT_ORDERED"
    TOWER_BUILT = "TOWER_BUILT"
    TOWER_SOLD = "TOWER_SOLD"
    TEAM_UNIT_UPGRADED = "TEAM_UNIT_UPGRADED"
    COMBAT_RESOLVED = "COMBAT_RESOLVED"
    ENTITY_DESTROYED = "ENTITY_DESTROYED"
    BASE_DAMAGED = "BASE_DAMAGED"
    BASE_DESTROYED = "BASE_DESTROYED"
    COINS_UPDATED = "COINS_UPDATED"
    LEADERBOARD_UPDATED = "LEADERBOARD_UPDATED"
    MATCH_PAUSED = "MATCH_PAUSED"
    MATCH_RESUMED = "MATCH_RESUMED"
    MATCH_ENDED = "MATCH_ENDED"
    PRESENCE_CHANGED = "PRESENCE_CHANGED"
    MEMBER_JOINED = "MEMBER_JOINED"
    MEMBER_READY_CHANGED = "MEMBER_READY_CHANGED"
    TEAM_ELIMINATED = "TEAM_ELIMINATED"
    ADMINISTRATIVE_OVERRIDE = "ADMINISTRATIVE_OVERRIDE"
    MATCH_REMATCH = "MATCH_REMATCH"


class ClientEventType:
    STATE_SYNC_REQUEST = "STATE_SYNC_REQUEST"
    ANSWER_SUBMITTED = "ANSWER_SUBMITTED"
    REWARD_SELECTED = "REWARD_SELECTED"
    DEPLOY_REQUEST = "DEPLOY_REQUEST"
    BUILD_REQUEST = "BUILD_REQUEST"
    UPGRADE_REQUEST = "UPGRADE_REQUEST"
    REPAIR_REQUEST = "REPAIR_REQUEST"
    TARGET_SELECTED = "TARGET_SELECTED"
    READY_CHANGED = "READY_CHANGED"
    SCOUT_REQUEST = "SCOUT_REQUEST"
    EMP_REQUEST = "EMP_REQUEST"
    START_MATCH = "START_MATCH"
    PAUSE_MATCH = "PAUSE_MATCH"
    RESUME_MATCH = "RESUME_MATCH"
    END_MATCH = "END_MATCH"
    ADVANCE_PHASE = "ADVANCE_PHASE"



def format_event_envelope(
    match_id: Any,
    event_type: str,
    sequence_number: int,
    payload: Dict[str, Any],
    event_id: Optional[Any] = None,
    server_timestamp: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Format standard envelope (§21):
    event_id, match_id, event_type, sequence_number, server_timestamp, payload.
    """
    if event_id is None:
        event_id = uuid.uuid4()
    if server_timestamp is None:
        server_timestamp = datetime.now(timezone.utc).isoformat()
    elif isinstance(server_timestamp, datetime):
        server_timestamp = server_timestamp.isoformat()
    else:
        server_timestamp = str(server_timestamp)

    return {
        "event_id": str(event_id),
        "match_id": str(match_id),
        "event_type": event_type,
        "sequence_number": int(sequence_number),
        "state_version": int(sequence_number),
        "server_timestamp": server_timestamp,
        "payload": payload,
    }
