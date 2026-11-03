import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.economy.models import CoinTransaction, TransactionType
from apps.matches.clock import (
    COMBAT_PHASES,
    continuous_phase_duration,
    is_continuous,
    lifecycle_payload,
    open_continuous_phase,
    open_planning_window,
    timestamp,
)
from apps.matches.defaults import (
    DEFAULT_MAX_TEAMS,
    MIN_MEMBERS_PER_TEAM,
    MIN_TEAMS_TO_START,
    get_default_configuration,
)
from apps.matches.models import Match, MatchEvent, MatchPhase, MatchStatus
from apps.matches.serializers import MatchConfigurationSerializer
from apps.teams.models import MemberRole, Team, TeamMember, TeamStatus
from apps.units.models import TeamUnlock, UnitType

logger = logging.getLogger(__name__)

ROOM_CODE_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
ROOM_CODE_LENGTH = 6

PHASE_SEQUENCE = [
    MatchPhase.LOBBY,
    MatchPhase.PREPARATION,
    MatchPhase.BUILD_AND_SCOUT,
    MatchPhase.WAR,
    MatchPhase.FINAL_ASSAULT,
    MatchPhase.RESULTS,
]


def hash_token(plain_token: str) -> str:
    """Calculate SHA-256 hash for authentication tokens."""
    return hashlib.sha256(plain_token.encode("utf-8")).hexdigest()


def sanitize_payload(payload: dict) -> dict:
    """Strip secret tokens or credentials from audit log payload (§26)."""
    if not isinstance(payload, dict):
        return payload
    sensitive_keys = {
        "participant_token",
        "participant_token_hash",
        "host_token",
        "host_token_hash",
        "token",
        "password",
        "secret",
        "auth_token",
    }
    sanitized = {}
    for k, v in payload.items():
        if k in sensitive_keys:
            continue
        if isinstance(v, dict):
            sanitized[k] = sanitize_payload(v)
        elif isinstance(v, list):
            sanitized[k] = [sanitize_payload(x) if isinstance(x, dict) else x for x in v]
        else:
            sanitized[k] = v
    return sanitized


class MatchService:
    @staticmethod
    def creation_host_token(creation_token):
        from django.utils.crypto import salted_hmac

        return "ht_" + salted_hmac("match-creation", creation_token, algorithm="sha256").hexdigest()

    @staticmethod
    def generate_room_code() -> str:
        """
        Generate a human-readable 6-character room code excluding easily confused characters (O/0, I/1/L).
        Ensures uniqueness among active matches (LOBBY, ACTIVE, PAUSED).
        """
        for _ in range(100):
            code = "".join(secrets.choice(ROOM_CODE_CHARS) for _ in range(ROOM_CODE_LENGTH))
            active_exists = Match.objects.filter(
                room_code=code,
                status__in=[MatchStatus.LOBBY, MatchStatus.ACTIVE, MatchStatus.PAUSED],
            ).exists()
            if not active_exists:
                return code
        raise RuntimeError("Failed to generate a unique room code after 100 attempts.")

    @staticmethod
    @transaction.atomic(savepoint=False)
    def record_match_event(match: Match, event_type: str, payload: dict) -> MatchEvent:
        """Record an immutable match event with a strictly monotonic sequence number."""
        # Lock the match row to ensure sequence number monotonicity
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        last_event = (
            MatchEvent.objects.filter(match=match_locked).order_by("-sequence_number").first()
        )
        next_seq = (last_event.sequence_number + 1) if last_event else 1

        clean_payload = sanitize_payload(payload or {})
        if event_type in {"QUESTION_TIMER_UPDATED", "QUESTION_ASSIGNED", "QUESTION_EXPIRED", "QUESTION_ANSWERED_CORRECT", "QUESTION_ANSWERED_INCORRECT", "REWARD_CLAIMED"} and clean_payload.get("team_question_id"):
            from apps.questions.models import TeamQuestion
            from apps.questions.serializers import TeamQuestionSerializer
            from apps.questions.services import QuestionService

            tq = TeamQuestion.objects.select_related("question", "team").get(pk=clean_payload["team_question_id"], match=match_locked)
            clean_payload["question_state"] = dict(TeamQuestionSerializer(tq).data)
            clean_payload["question_progress"] = QuestionService.progress(match_locked, tq.team)
        event = MatchEvent.objects.create(
            match=match_locked,
            sequence_number=next_seq,
            event_type=event_type,
            payload=clean_payload,
        )

        logger.debug("Realtime event created", extra={
            "match_id": str(match.pk), "match_group": f"match.{match.pk}",
            "event_id": str(event.pk), "event_type": event_type,
            "sequence": next_seq, "entity_id": clean_payload.get("entity_id"),
        })

        def _broadcast():
            from apps.realtime.services import RealtimeService

            RealtimeService.broadcast_match_event(event)

        transaction.on_commit(_broadcast)

        return event

    @classmethod
    @transaction.atomic
    def create_match(
        cls,
        name: str = "Battle Arena",
        configuration: Optional[dict] = None,
        created_by=None,
        question_bank=None,
        creation_token=None,
    ) -> Tuple[Match, str]:
        """
        Create a new match in LOBBY phase and return (Match, plain_host_token).
        The plain host token is returned only once to the host creator.
        """
        if creation_token:
            existing = Match.objects.filter(creation_token_hash=hash_token(creation_token)).first()
            if existing:
                return existing, cls.creation_host_token(creation_token)
        final_config = get_default_configuration()
        if configuration:
            # Merge with defaults
            for key, val in configuration.items():
                if (
                    isinstance(val, dict)
                    and key in final_config
                    and isinstance(final_config[key], dict)
                ):
                    final_config[key].update(val)
                else:
                    final_config[key] = val

        # Validate configuration
        config_serializer = MatchConfigurationSerializer(data=final_config)
        config_serializer.is_valid(raise_exception=True)
        validated_config = config_serializer.validated_data

        room_code = cls.generate_room_code()
        plain_host_token = cls.creation_host_token(creation_token) if creation_token else f"ht_{secrets.token_urlsafe(32)}"
        token_hash = hash_token(plain_host_token)

        match = Match.objects.create(
            name=name,
            room_code=room_code,
            status=MatchStatus.LOBBY,
            phase=MatchPhase.LOBBY,
            configuration=validated_config,
            host_token_hash=token_hash,
            created_by=created_by,
            question_bank=question_bank,
            creation_token_hash=hash_token(creation_token) if creation_token else None,
        )

        cls.record_match_event(
            match=match,
            event_type="MATCH_CREATED",
            payload={"match_id": str(match.id), "room_code": room_code, "name": name},
        )

        return match, plain_host_token

    @classmethod
    @transaction.atomic
    def create_team(cls, match: Match, name: str) -> Team:
        """Create a new team in the match during LOBBY phase."""
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        if match_locked.status != MatchStatus.LOBBY:
            raise ValidationError("Teams can only be created while match is in LOBBY.")

        max_teams = match_locked.configuration.get("max_teams", DEFAULT_MAX_TEAMS)
        current_teams_count = match_locked.teams.count()
        if current_teams_count >= max_teams:
            raise ValidationError(f"Maximum number of teams ({max_teams}) reached for this match.")

        name = name.strip()
        if not name:
            raise ValidationError("Team name cannot be blank.")

        if match_locked.teams.filter(name__iexact=name).exists():
            raise ValidationError(f"A team named '{name}' already exists in this match.")

        init_hp = match_locked.configuration.get("initial_base_hp", 500)
        init_coins = match_locked.configuration.get("initial_coins", 100)

        team = Team.objects.create(
            match=match_locked,
            name=name,
            initial_base_hp=init_hp,
            base_hp=init_hp,
            base_shield=0,
            coins=init_coins,
            score=0,
            status=TeamStatus.ACTIVE,
            is_ready=False,
        )

        cls.record_match_event(
            match=match_locked,
            event_type="TEAM_CREATED",
            payload={"team_id": str(team.id), "team_name": team.name},
        )

        return team

    @classmethod
    @transaction.atomic
    def update_team(cls, team: Team, name: str) -> Team:
        """Update team details during LOBBY phase."""
        match_locked = Match.objects.select_for_update().get(pk=team.match_id)
        if match_locked.status != MatchStatus.LOBBY:
            raise ValidationError("Teams can only be modified while match is in LOBBY.")

        name = name.strip()
        if not name:
            raise ValidationError("Team name cannot be blank.")

        if match_locked.teams.filter(name__iexact=name).exclude(pk=team.pk).exists():
            raise ValidationError(f"A team named '{name}' already exists in this match.")

        team.name = name
        team.save()

        cls.record_match_event(
            match=match_locked,
            event_type="TEAM_UPDATED",
            payload={"team_id": str(team.id), "name": team.name},
        )
        return team

    @classmethod
    @transaction.atomic
    def delete_team(cls, team: Team) -> None:
        """Delete a team during LOBBY phase."""
        match_locked = Match.objects.select_for_update().get(pk=team.match_id)
        if match_locked.status != MatchStatus.LOBBY:
            raise ValidationError("Teams can only be deleted while match is in LOBBY.")

        team_id = str(team.id)
        team_name = team.name

        # Unassign members belonging to this team
        team.members.update(team=None)
        team.delete()

        cls.record_match_event(
            match=match_locked,
            event_type="TEAM_DELETED",
            payload={"team_id": team_id, "name": team_name},
        )

    @classmethod
    @transaction.atomic
    def join_match(
        cls,
        match: Match,
        display_name: str,
        team_id: Optional[str] = None,
        role: str = MemberRole.MENTEE,
        user=None,
        new_team_name: Optional[str] = None,
    ) -> Tuple[TeamMember, str]:
        """
        Participant joins a match. Returns (TeamMember, plain_participant_token).
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        display_name = display_name.strip()
        if not display_name:
            raise ValidationError("Display name cannot be blank.")

        # Recover the same participant before checking restrictions for new joins.
        # The match row lock serializes simultaneous joins with the same name.
        existing = list(match_locked.members.filter(display_name=display_name).exclude(
            role=MemberRole.HOST,
        )[:2])
        if len(existing) > 1:
            raise ValidationError("Tên hiển thị bị trùng trong phòng. Vui lòng nhờ Host đổi tên để vào lại đúng phiên.")
        if existing:
            member = existing[0]
            plain_token = f"pt_{secrets.token_urlsafe(32)}"
            member.token_hash = hash_token(plain_token)
            member.save(update_fields=["token_hash"])
            return member, plain_token

        if match_locked.is_locked:
            raise ValidationError("This match is locked and no longer accepting participants.")

        allow_late_join = match_locked.configuration.get("allow_late_join", False)
        if match_locked.status != MatchStatus.LOBBY and not allow_late_join:
            raise ValidationError("Cannot join a match that has already started.")

        target_team = None
        if new_team_name is not None:
            if team_id or role not in (MemberRole.MENTOR, MemberRole.MENTEE):
                raise ValidationError("Chọn đội có sẵn hoặc tạo đội mới với vai trò mentee/mentor.")
            team_id = cls.create_team(match_locked, new_team_name).id
        if team_id:
            try:
                target_team = match_locked.teams.get(pk=team_id)
            except Team.DoesNotExist:
                raise ValidationError("Specified team does not exist in this match.")

            # Validate role & capacity if joining directly into a team
            if role == MemberRole.MENTOR:
                if target_team.members.filter(role=MemberRole.MENTOR).exists():
                    raise ValidationError("This team already has a Mentor.")

            max_players = match_locked.configuration.get("max_players_per_team", 4)
            if target_team.members.count() >= max_players:
                raise ValidationError(
                    f"Team '{target_team.name}' has reached maximum player capacity ({max_players})."
                )

        plain_token = f"pt_{secrets.token_urlsafe(32)}"
        token_hash = hash_token(plain_token)

        member = TeamMember.objects.create(
            match=match_locked,
            team=target_team,
            user=user,
            display_name=display_name,
            role=role,
            is_ready=False,
            token_hash=token_hash,
        )
        if target_team and match_locked.status == MatchStatus.LOBBY:
            Team.objects.filter(pk=target_team.pk).update(is_ready=False)

        cls.record_match_event(
            match=match_locked,
            event_type="MEMBER_JOINED",
            payload={
                "member_id": str(member.id),
                "display_name": member.display_name,
                "role": member.role,
                "team_id": str(target_team.id) if target_team else None,
            },
        )

        return member, plain_token

    @classmethod
    @transaction.atomic
    def assign_member(
        cls,
        member: TeamMember,
        team_id: Optional[str] = None,
        role: Optional[str] = None,
        is_override: bool = False,
        reason: str = "",
    ) -> TeamMember:
        """
        Assign or reassign a member to a team and/or change role during LOBBY,
        or during active match via administrative override (§2.1, §26).
        """
        match_locked = Match.objects.select_for_update().get(pk=member.match_id)
        member = TeamMember.objects.get(pk=member.pk, match=match_locked)
        if match_locked.status != MatchStatus.LOBBY and not is_override:
            raise ValidationError("Member assignment can only be modified in LOBBY.")

        target_role = role or member.role
        old_team_id = member.team_id

        target_team = None
        if team_id is not None:
            if team_id == "" or team_id is False:
                target_team = None
            else:
                try:
                    target_team = match_locked.teams.get(pk=team_id)
                except Team.DoesNotExist:
                    raise ValidationError("Specified team does not exist in this match.")

                max_players = match_locked.configuration.get("max_players_per_team", 4)
                if member.team_id != target_team.id and target_team.members.count() >= max_players:
                    raise ValidationError(
                        f"Team '{target_team.name}' has reached maximum capacity ({max_players})."
                    )

                if target_role == MemberRole.MENTOR:
                    mentor_exists = (
                        target_team.members.filter(role=MemberRole.MENTOR)
                        .exclude(pk=member.pk)
                        .exists()
                    )
                    if mentor_exists:
                        raise ValidationError("This team already has a Mentor.")

            member.team = target_team

        if role:
            if role == MemberRole.MENTOR and member.team:
                mentor_exists = (
                    member.team.members.filter(role=MemberRole.MENTOR)
                    .exclude(pk=member.pk)
                    .exists()
                )
                if mentor_exists:
                    raise ValidationError("This team already has a Mentor.")
            member.role = role

        member.save()
        if match_locked.status == MatchStatus.LOBBY:
            Team.objects.filter(pk__in=[old_team_id, member.team_id]).update(is_ready=False)

        if match_locked.status != MatchStatus.LOBBY and is_override:
            cls.record_match_event(
                match=match_locked,
                event_type="ADMINISTRATIVE_OVERRIDE",
                payload={
                    "override_type": "REASSIGN_PARTICIPANT",
                    "member_id": str(member.id),
                    "display_name": member.display_name,
                    "from_team_id": str(old_team_id) if old_team_id else None,
                    "to_team_id": str(member.team.id) if member.team else None,
                    "role": member.role,
                    "reason": reason or "Administrative member reassignment",
                },
            )
        else:
            cls.record_match_event(
                match=match_locked,
                event_type="MEMBER_ASSIGNED",
                payload={
                    "member_id": str(member.id),
                    "team_id": str(member.team.id) if member.team else None,
                    "role": member.role,
                },
            )
        return member

    @classmethod
    @transaction.atomic
    def remove_member(
        cls,
        member: TeamMember,
        is_override: bool = False,
        reason: str = "",
    ) -> None:
        """
        Remove/kick a member from the match.
        Allowed during LOBBY; allowed during active match only via administrative override (§2.1, §26).
        """
        match_locked = Match.objects.select_for_update().get(pk=member.match_id)
        if match_locked.status != MatchStatus.LOBBY and not is_override:
            raise ValidationError("Cannot remove member after match has started.")

        member_id = str(member.id)
        display_name = member.display_name
        member.delete()

        if match_locked.status != MatchStatus.LOBBY and is_override:
            cls.record_match_event(
                match=match_locked,
                event_type="ADMINISTRATIVE_OVERRIDE",
                payload={
                    "override_type": "KICK_PARTICIPANT",
                    "member_id": member_id,
                    "display_name": display_name,
                    "reason": reason or "Administrative participant kick",
                },
            )
        else:
            cls.record_match_event(
                match=match_locked,
                event_type="MEMBER_REMOVED",
                payload={"member_id": member_id, "display_name": display_name},
            )

    @classmethod
    @transaction.atomic
    def set_team_ready(cls, team: Team, is_ready: bool) -> Team:
        """Toggle or set team ready status during LOBBY."""
        match_locked = Match.objects.select_for_update().get(pk=team.match_id)
        if match_locked.status != MatchStatus.LOBBY:
            raise ValidationError("Ready status can only be toggled during LOBBY.")

        team.is_ready = is_ready
        team.save()

        cls.record_match_event(
            match=match_locked,
            event_type="READY_CHANGED",
            payload={"team_id": str(team.id), "is_ready": is_ready},
        )
        return team

    @classmethod
    @transaction.atomic
    def set_member_ready(cls, member: TeamMember, is_ready: bool) -> TeamMember:
        """Toggle or set individual member ready status during LOBBY."""
        match_locked = Match.objects.select_for_update().get(pk=member.match_id)
        if match_locked.status != MatchStatus.LOBBY:
            raise ValidationError("Ready status can only be toggled during LOBBY.")

        member.is_ready = is_ready
        member.save()

        cls.record_match_event(
            match=match_locked,
            event_type="MEMBER_READY_CHANGED",
            payload={"member_id": str(member.id), "is_ready": is_ready},
        )
        return member

    @classmethod
    @transaction.atomic
    def update_configuration(cls, match: Match, new_config: dict) -> Match:
        """Update match configuration during LOBBY phase."""
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        if match_locked.status != MatchStatus.LOBBY:
            raise ValidationError("Configuration can only be updated during LOBBY.")

        # Deep merge new_config with current config
        current = match_locked.configuration
        for key, val in new_config.items():
            if isinstance(val, dict) and key in current and isinstance(current[key], dict):
                current[key].update(val)
            else:
                current[key] = val

        serializer = MatchConfigurationSerializer(data=current)
        serializer.is_valid(raise_exception=True)
        if match_locked.teams.count() > serializer.validated_data["max_teams"]:
            raise ValidationError("Capacity cannot be lower than the existing team count.")
        match_locked.configuration = serializer.validated_data
        match_locked.save()

        cls.record_match_event(
            match=match_locked,
            event_type="CONFIG_UPDATED",
            payload={"configuration": match_locked.configuration},
        )
        return match_locked

    @classmethod
    @transaction.atomic
    def set_locked(cls, match: Match, is_locked: bool) -> Match:
        """Lock or unlock match from accepting new participants."""
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        match_locked.is_locked = is_locked
        match_locked.save()

        cls.record_match_event(
            match=match_locked,
            event_type="MATCH_LOCK_CHANGED",
            payload={"is_locked": is_locked},
        )
        return match_locked

    @classmethod
    @transaction.atomic
    def start_match(cls, match: Match) -> Match:
        """
        Validate requirements and transition match from LOBBY to ACTIVE (PREPARATION phase).
        Initializes team stats (base_hp, coins) according to authoritative configuration.
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        if match_locked.status != MatchStatus.LOBBY:
            raise ValidationError(
                f"Cannot start match with status '{match_locked.status}'. Must be LOBBY."
            )

        # Re-validate configuration
        config_serializer = MatchConfigurationSerializer(data=match_locked.configuration)
        config_serializer.is_valid(raise_exception=True)
        config = config_serializer.validated_data

        min_teams = config.get("min_teams", MIN_TEAMS_TO_START)
        teams = list(match_locked.teams.order_by("created_at", "id").prefetch_related("members"))
        if len(teams) > config.get("max_teams", DEFAULT_MAX_TEAMS):
            raise ValidationError("Team count exceeds configured arena capacity.")
        from apps.combat.map import get_game_map

        if len(teams) >= 2:
            valid, errors = get_game_map(len(teams), config.get("arena_layout_version", 3)).validate_map()
            if not valid:
                raise ValidationError(errors)
        if len(teams) < min_teams:
            raise ValidationError(
                f"Cannot start match: At least {min_teams} teams required (currently {len(teams)})."
            )

        # Check each team is ready and has minimum required players
        min_players = MIN_MEMBERS_PER_TEAM
        unready_teams = []
        understaffed_teams = []

        for team in teams:
            if not team.is_ready:
                unready_teams.append(team.name)
            # Hosts/spectators are not active players, nor are foreign-match memberships.
            players = sum(
                member.match_id == match_locked.id
                and member.role in (MemberRole.MENTOR, MemberRole.MENTEE)
                for member in team.members.all()
            )
            if players < min_players:
                understaffed_teams.append(f"{team.name} ({players}/{min_players})")

        if understaffed_teams:
            raise ValidationError(
                f"Cannot start match: The following teams do not have enough players: {', '.join(understaffed_teams)}."
            )

        if unready_teams:
            raise ValidationError(
                f"Cannot start match: The following teams are not ready: {', '.join(unready_teams)}."
            )

        # Initialize base HP and coins for all teams from config (§2.3)
        initial_hp = config.get("initial_base_hp", 500)
        initial_coins = config.get("initial_coins", 100)

        starter_units = list(UnitType.objects.filter(is_starter=True, is_active=True))

        for team in teams:
            team.initial_base_hp = initial_hp
            team.base_hp = initial_hp
            team.base_shield = 0
            team.coins = initial_coins
            team.score = 0
            team.status = TeamStatus.ACTIVE
            team.save()

            # Record initial coins transaction (§2.1, §19.11)
            CoinTransaction.objects.get_or_create(
                match=match_locked,
                team=team,
                transaction_type=TransactionType.INITIAL,
                defaults={
                    "amount": initial_coins,
                    "balance_after": initial_coins,
                    "description": "Initial team starting coins",
                },
            )

            # Auto-unlock starter units (§7.1, §8.1)
            for s_unit in starter_units:
                TeamUnlock.objects.get_or_create(
                    team=team,
                    unit_type=s_unit,
                )

        # Update match status and phase
        now = timezone.now()
        match_locked.status = MatchStatus.ACTIVE
        match_locked.phase = MatchPhase.PREPARATION
        match_locked.started_at = now
        prep_dur = config.get("phase_durations", {}).get(MatchPhase.PREPARATION, 180)
        config["current_round"] = 1
        config["timer_state"] = {
            "round_phase": "PLANNING",
            "phase_started_at": now.isoformat(),
            "phase_remaining_seconds": prep_dur,
            "match_deadline_at": (now + timedelta(
                seconds=config.get("match_duration_seconds", 1800)
            )).isoformat(),
        }
        match_locked.configuration = config
        if is_continuous(config):
            open_continuous_phase(match_locked, now)
        match_locked.save()

        cls.record_match_event(
            match=match_locked,
            event_type="MATCH_STARTED",
            payload={
                "started_at": match_locked.started_at.isoformat(),
                "phase": match_locked.phase,
                "team_count": len(teams),
                **lifecycle_payload(match_locked),
            },
        )
        return match_locked

    @classmethod
    @transaction.atomic
    def pause_match(cls, match: Match) -> Match:
        """
        Pause an ongoing active match (§11, FR-09).
        Stops phase timer, round scheduler, passive income;
        Closes currently open team questions per §11;
        Saves remaining phase duration accurately.
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        if match_locked.status != MatchStatus.ACTIVE:
            raise ValidationError(f"Cannot pause match in status '{match_locked.status}'.")

        now = timezone.now()
        config = match_locked.configuration or {}
        timer_state = config.get("timer_state", {})
        timer_state["paused_at"] = now.isoformat()

        # Compute accurate remaining seconds in current phase
        phase_durs = config.get("phase_durations", {})
        total_phase_dur = continuous_phase_duration(config, match_locked.phase) if is_continuous(config) else phase_durs.get(match_locked.phase, 180)
        phase_started_str = timer_state.get("phase_started_at")
        if phase_started_str:
            try:
                started_dt = datetime.fromisoformat(phase_started_str)
                elapsed = max(0, int((now - started_dt).total_seconds()))
                remaining = max(0, total_phase_dur - elapsed)
            except Exception:
                remaining = total_phase_dur
        else:
            remaining = total_phase_dur

        timer_state["phase_remaining_seconds"] = remaining
        next_round = timestamp(timer_state.get("next_round_at"))
        if next_round:
            timer_state["round_remaining_seconds"] = max(0, (next_round - now).total_seconds())
        config["timer_state"] = timer_state
        match_locked.configuration = config
        match_locked.status = MatchStatus.PAUSED
        match_locked.save()

        from apps.questions.timers import freeze_for_match
        freeze_for_match(match_locked, now)

        cls.record_match_event(
            match=match_locked,
            event_type="MATCH_PAUSED",
            payload={
                "status": match_locked.status,
                "paused_at": now.isoformat(),
                "phase_remaining_seconds": remaining,
                **lifecycle_payload(match_locked),
            },
        )
        return match_locked

    @classmethod
    @transaction.atomic
    def resume_match(cls, match: Match) -> Match:
        """
        Resume a paused match (§11, FR-09).
        Accurately restores remaining phase time.
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        if match_locked.status != MatchStatus.PAUSED:
            raise ValidationError(f"Cannot resume match in status '{match_locked.status}'.")

        now = timezone.now()
        from apps.questions.timers import resume_for_match
        resume_for_match(match_locked, now)
        config = match_locked.configuration or {}
        timer_state = config.get("timer_state", {})
        remaining = timer_state.get("phase_remaining_seconds", 60)
        timer_state["resumed_at"] = now.isoformat()
        paused_at = timestamp(timer_state.get("paused_at")) or now
        pause_duration = max(timedelta(), now - paused_at)
        for key in ("next_round_at", "round_started_at", "match_deadline_at", "phase_ends_at", "next_tick_at", "simulation_at"):
            deadline = timestamp(timer_state.get(key))
            if deadline:
                timer_state[key] = (deadline + pause_duration).isoformat()
        config["reward_deadlines"] = {
            key: (timestamp(value) + pause_duration).isoformat()
            for key, value in config.get("reward_deadlines", {}).items()
        }
        timer_state.pop("paused_at", None)
        timer_state.pop("round_remaining_seconds", None)

        phase_durs = config.get("phase_durations", {})
        total_phase_dur = continuous_phase_duration(config, match_locked.phase) if is_continuous(config) else phase_durs.get(match_locked.phase, 180)
        timer_state["phase_started_at"] = (
            now - timedelta(seconds=max(0, total_phase_dur - remaining))
        ).isoformat()
        config["timer_state"] = timer_state
        match_locked.configuration = config
        match_locked.status = MatchStatus.ACTIVE
        match_locked.save()

        cls.record_match_event(
            match=match_locked,
            event_type="MATCH_RESUMED",
            payload={
                "status": match_locked.status,
                "resumed_at": now.isoformat(),
                "phase_remaining_seconds": remaining,
                **lifecycle_payload(match_locked),
            },
        )
        return match_locked

    @classmethod
    @transaction.atomic
    def end_match(cls, match: Match) -> Match:
        """
        End a match early or upon completion (§19.13, FR-09, FR-10).
        Finalizes match and immediately creates immutable MatchResult snapshot.
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        if match_locked.status == MatchStatus.FINISHED:
            return match_locked

        now = timezone.now()
        match_locked.status = MatchStatus.FINISHED
        match_locked.phase = MatchPhase.RESULTS
        match_locked.ended_at = now
        match_locked.save()

        from apps.combat.scoring import ScoringService
        ScoringService.finalize_match(match_locked)

        return match_locked

    @classmethod
    @transaction.atomic
    def advance_phase(
        cls,
        match: Match,
        target_phase: Optional[str] = None,
        is_override: bool = False,
        reason: str = "",
        effective_at: Optional[datetime] = None,
    ) -> Match:
        """
        Advance match phase along valid state machine sequence or via administrative override (§2.1, §26).
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)

        if match_locked.status not in [MatchStatus.ACTIVE, MatchStatus.LOBBY, MatchStatus.PAUSED]:
            raise ValidationError(
                f"Cannot advance phase for match in status '{match_locked.status}'."
            )

        if is_continuous(match_locked.configuration):
            if match_locked.status != MatchStatus.ACTIVE:
                raise ValidationError("Continuous phase transitions require an active match.")
            if is_override or target_phase:
                expected = "WAR" if match_locked.phase == "PREPARATION" else (
                    "RESULTS" if match_locked.configuration.get("current_round", 1) >= match_locked.configuration.get("total_rounds", 3) else "PREPARATION")
                if target_phase != expected:
                    raise ValidationError(f"Expected continuous phase {expected}.")
            if is_override:
                cls.record_match_event(match_locked, "ADMINISTRATIVE_OVERRIDE", {
                    "override_type": "ADVANCE_PHASE", "from_phase": match_locked.phase,
                    "to_phase": target_phase, "reason": reason or "Administrative phase override",
                })
            return cls.advance_continuous_phase(match_locked, effective_at or timezone.now())

        current_phase = match_locked.phase

        if is_override:
            if not target_phase or target_phase not in PHASE_SEQUENCE:
                raise ValidationError(f"Target phase '{target_phase}' is not a valid phase.")
            next_phase = target_phase
            cls.record_match_event(
                match=match_locked,
                event_type="ADMINISTRATIVE_OVERRIDE",
                payload={
                    "override_type": "ADVANCE_PHASE",
                    "from_phase": current_phase,
                    "to_phase": next_phase,
                    "reason": reason or "Administrative phase override",
                },
            )
        else:
            try:
                current_idx = PHASE_SEQUENCE.index(current_phase)
            except ValueError:
                raise ValidationError(f"Current phase '{current_phase}' is not recognized.")

            if current_idx >= len(PHASE_SEQUENCE) - 1:
                raise ValidationError("Match is already at the final phase (RESULTS).")

            expected_next = PHASE_SEQUENCE[current_idx + 1]
            if target_phase is not None and target_phase != expected_next:
                raise ValidationError(
                    f"Invalid phase transition: Cannot jump from '{current_phase}' to '{target_phase}'. Expected '{expected_next}'."
                )
            next_phase = expected_next

        now = effective_at or timezone.now()
        match_locked.phase = next_phase
        config = match_locked.configuration or {}
        phase_durs = config.get("phase_durations", {})
        dur = phase_durs.get(next_phase, 180)
        timer_state = config.get("timer_state", {})
        timer_state["phase_started_at"] = now.isoformat()
        timer_state["phase_remaining_seconds"] = dur
        config["timer_state"] = timer_state
        # Preserve the current planning window across consecutive combat phases.
        if next_phase in COMBAT_PHASES:
            if current_phase not in COMBAT_PHASES or not timer_state.get("next_round_at"):
                open_planning_window(config, now)
            if match_locked.status == MatchStatus.PAUSED:
                timer_state["paused_at"] = timezone.now().isoformat()
                timer_state["round_remaining_seconds"] = config.get("round_duration_seconds", 30)
        else:
            timer_state.pop("next_round_at", None)
            timer_state.pop("round_started_at", None)


        # Earned rewards remain pending across phase changes until the team claims.
        match_locked.configuration = config

        if match_locked.phase == MatchPhase.RESULTS:
            match_locked.status = MatchStatus.FINISHED
            if not match_locked.ended_at:
                match_locked.ended_at = timezone.now()
            match_locked.save()
            from apps.combat.scoring import ScoringService
            ScoringService.finalize_match(match_locked)
        else:
            match_locked.save()

        cls.record_match_event(
            match=match_locked,
            event_type="MATCH_PHASE_CHANGED",
            payload=lifecycle_payload(match_locked),
        )
        return match_locked

    @classmethod
    @transaction.atomic
    def override_close_stuck_question(
        cls,
        match: Match,
        team_question_id: str,
        reason: str = "",
    ) -> None:
        """
        Administrative override: Close a stuck/abandoned question for a team (§11, §26).
        Marks the question as EXPIRED and records an ADMINISTRATIVE_OVERRIDE event.
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        from apps.questions.models import QuestionStatus, TeamQuestion

        try:
            tq = TeamQuestion.objects.select_for_update().get(
                pk=team_question_id,
                match=match_locked,
            )
        except TeamQuestion.DoesNotExist:
            raise ValidationError("Specified TeamQuestion not found in this match.")

        old_status = tq.status
        tq.status = QuestionStatus.EXPIRED
        tq.save(update_fields=["status"])

        cls.record_match_event(
            match=match_locked,
            event_type="ADMINISTRATIVE_OVERRIDE",
            payload={
                "override_type": "CLOSE_STUCK_QUESTION",
                "team_question_id": str(tq.id),
                "team_id": str(tq.team_id),
                "old_status": old_status,
                "new_status": tq.status,
                "reason": reason or "Administrative close of stuck question",
            },
        )

    @classmethod
    @transaction.atomic
    def override_adjust_coins(
        cls,
        match: Match,
        team_id: str,
        amount: int,
        reason: str = "",
    ) -> CoinTransaction:
        """
        Administrative override: Adjust a team's coin balance (§7, §26).
        Used to fix network errors or undo faulty rewards.
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        try:
            team = match_locked.teams.select_for_update().get(pk=team_id)
        except Team.DoesNotExist:
            raise ValidationError("Team not found in this match.")

        new_balance = team.coins + amount
        if new_balance < 0:
            raise ValidationError("Coin adjustment would cause negative balance.")

        team.coins = new_balance
        team.save(update_fields=["coins"])

        tx = CoinTransaction.objects.create(
            match=match_locked,
            team=team,
            amount=amount,
            balance_after=new_balance,
            transaction_type=TransactionType.ADMIN_OVERRIDE,
            reference_type="OVERRIDE",
            description=reason or "Administrative coin adjustment",
        )

        cls.record_match_event(
            match=match_locked,
            event_type="ADMINISTRATIVE_OVERRIDE",
            payload={
                "override_type": "ADJUST_COINS",
                "team_id": str(team.id),
                "amount": amount,
                "balance_after": new_balance,
                "reason": reason or "Administrative coin adjustment",
            },
        )
        return tx

    @classmethod
    @transaction.atomic
    def apply_preset(cls, match: Match, preset_id: str) -> Match:
        """
        Applies a configuration preset (only allowed during LOBBY) (§2.3).
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        if match_locked.status != MatchStatus.LOBBY:
            raise ValidationError("Presets can only be applied while match is in LOBBY.")

        from apps.matches.defaults import MATCH_PRESETS

        if preset_id not in MATCH_PRESETS:
            raise ValidationError(f"Preset '{preset_id}' is not recognized.")

        preset = MATCH_PRESETS[preset_id]
        new_config = preset["configuration"]
        return cls.update_configuration(match_locked, new_config)

    @classmethod
    @transaction.atomic
    def create_rematch(cls, match: Match) -> Tuple[Match, str]:
        """
        Creates a new match retaining teams, members, and configuration (§14.9, FR-10).
        Broadcasts MATCH_REMATCH to current clients with new match identifiers.
        """
        old_match = Match.objects.select_for_update().get(pk=match.pk)
        new_room_code = cls.generate_room_code()
        plain_host_token = secrets.token_hex(32)

        import copy

        new_config = copy.deepcopy(old_match.configuration)
        for key in ("combat_stats", "awards", "timer_state", "current_round", "active_shields",
                    "entity_effects", "reward_deadlines", "elimination_winner_id"):
            new_config.pop(key, None)

        new_match = Match.objects.create(
            name=f"{old_match.name} (Rematch)",
            room_code=new_room_code,
            status=MatchStatus.LOBBY,
            phase=MatchPhase.LOBBY,
            configuration=new_config,
            host_token_hash=hash_token(plain_host_token),
            created_by=old_match.created_by,
            question_bank=old_match.question_bank,
        )

        init_hp = new_config.get("initial_base_hp", 500)
        init_coins = new_config.get("initial_coins", 100)

        for old_team in old_match.teams.all():
            new_team = Team.objects.create(
                match=new_match,
                name=old_team.name,
                initial_base_hp=init_hp,
                base_hp=init_hp,
                base_shield=0,
                coins=init_coins,
                score=0,
                status=TeamStatus.ACTIVE,
                is_ready=False,
            )
            for old_member in old_team.members.all():
                p_token = secrets.token_hex(32)
                TeamMember.objects.create(
                    match=new_match,
                    team=new_team,
                    user=old_member.user,
                    display_name=old_member.display_name,
                    role=old_member.role,
                    token_hash=hash_token(p_token),
                    is_ready=False,
                )

        cls.record_match_event(
            match=old_match,
            event_type="MATCH_REMATCH",
            payload={
                "old_match_id": str(old_match.id),
                "new_match_id": str(new_match.id),
                "new_room_code": new_match.room_code,
            },
        )

        return new_match, plain_host_token

    @classmethod
    def get_host_telemetry(cls, match: Match) -> dict:
        """
        Aggregates realtime monitoring feed for Host Dashboard (§14.8, §2.2).
        Includes team metrics, question counts, units/towers counts, and presence.
        """
        from apps.questions.models import QuestionStatus
        from apps.units.models import EntityCategory, EntityStatus, GameEntity

        config = match.configuration or {}
        from apps.questions.services import QuestionService
        max_q = QuestionService.question_total(match)
        teams = match.teams.all().order_by("created_at")

        teams_telemetry = []
        for t in teams:
            active_units = GameEntity.objects.filter(
                team=t,
                entity_kind=EntityCategory.UNIT,
                status=EntityStatus.ACTIVE,
            ).count()

            active_towers = GameEntity.objects.filter(
                team=t,
                entity_kind=EntityCategory.TOWER,
                status=EntityStatus.ACTIVE,
            ).count()

            assigned_q_count = t.assigned_questions.count()
            remaining_q = max(0, max_q - assigned_q_count)

            pending_reward = t.assigned_questions.filter(
                status=QuestionStatus.PENDING_REWARD
            ).exists()

            current_q = t.assigned_questions.filter(
                status__in=[QuestionStatus.PENDING_QUESTION, QuestionStatus.PENDING_REWARD]
            ).first()

            members_data = [
                {
                    "id": str(m.id),
                    "display_name": m.display_name,
                    "role": m.role,
                    "is_ready": m.is_ready,
                    "is_online": True,
                }
                for m in t.members.all()
            ]

            teams_telemetry.append({
                "id": str(t.id),
                "name": t.name,
                "status": t.status,
                "base_hp": t.base_hp,
                "base_shield": t.base_shield,
                "coins": t.coins,
                "score": t.score,
                "active_units": active_units,
                "active_towers": active_towers,
                "remaining_questions": remaining_q,
                "has_pending_reward": pending_reward,
                "current_question_status": current_q.status if current_q else None,
                "members": members_data,
                "online_members_count": len(members_data),
            })

        timer_state = config.get("timer_state", {})
        remaining_seconds = timer_state.get("phase_remaining_seconds", 0)
        if match.status == MatchStatus.ACTIVE and timer_state.get("phase_started_at"):
            try:
                started = datetime.fromisoformat(timer_state["phase_started_at"])
                phase_dur = continuous_phase_duration(config, match.phase) if is_continuous(config) else config.get("phase_durations", {}).get(match.phase, 180)
                elapsed = max(0, int((timezone.now() - started).total_seconds()))
                remaining_seconds = max(0, phase_dur - elapsed)
            except Exception:
                pass

        total_events = match.events.count()

        return {
            "match_id": str(match.id),
            "room_code": match.room_code,
            "name": match.name,
            "status": match.status,
            "phase": match.phase,
            "is_locked": match.is_locked,
            "phase_remaining_seconds": remaining_seconds,
            "current_round": config.get("current_round", 1),
            "total_events_count": total_events,
            "teams": teams_telemetry,
        }



    @classmethod
    def advance_continuous_phase(cls, match, now):
        """Caller owns the match row lock. Never reset surviving entities/resources."""
        config = match.configuration
        previous = match.phase
        if previous == "PREPARATION":
            match.phase = MatchPhase.WAR
        elif previous == "WAR":
            from apps.units.models import GameAction
            GameAction.objects.filter(match=match, status__in=["ACCEPTED", "QUEUED"]).update(status="RESOLVED", resolved_at=now)
            # Exactly one income award per completed major battle (never per tick).
            from apps.economy.services import EconomyService
            for team in match.teams.filter(status="ACTIVE").order_by("id"):
                amount = config.get("base_income_per_round", 10)
                if amount:
                    EconomyService.credit(team, amount, TransactionType.PASSIVE_INCOME,
                        reference_type="MAJOR_ROUND", reference_id=str(config.get("current_round", 1)))
            cls.record_match_event(match, "BATTLE_STOPPED", lifecycle_payload(match))
            if config.get("current_round", 1) >= config.get("total_rounds", 3):
                return cls.end_match(match)
            config["current_round"] = config.get("current_round", 1) + 1
            match.phase = MatchPhase.PREPARATION
        else:
            raise ValidationError("Invalid continuous match phase.")
        open_continuous_phase(match, now)
        match.save(update_fields=["phase", "configuration", "updated_at"])
        cls.record_match_event(match, "MATCH_PHASE_CHANGED", {"from_phase": previous, "to_phase": match.phase, **lifecycle_payload(match)})
        cls.record_match_event(match, "BATTLE_STARTED" if match.phase == "WAR" else "ROUND_STARTED", lifecycle_payload(match))
        return match
