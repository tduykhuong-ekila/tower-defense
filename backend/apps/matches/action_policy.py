"""One authoritative eligibility policy shared by REST, WebSockets and read models."""

import logging
from dataclasses import asdict, dataclass

from django.core.exceptions import ValidationError

from apps.matches.models import MatchStatus
from apps.units.models import EntityStatus, GameEntity, TeamUnlock

logger = logging.getLogger(__name__)
PLAYABLE_PHASES = ["PREPARATION", "BUILD_AND_SCOUT", "WAR", "FINAL_ASSAULT"]
ACTION_PHASES = {
    "DEPLOY_UNIT": PLAYABLE_PHASES,
    "BUILD_TOWER": ["PREPARATION", "BUILD_AND_SCOUT", "WAR"],
}


@dataclass(frozen=True)
class Availability:
    allowed: bool
    reason_code: str = ""
    reason: str = ""

    def to_dict(self):
        return asdict(self)


class ActionPolicy:
    @staticmethod
    def rules(configuration=None):
        if (configuration or {}).get("gameplay_mode") == "CONTINUOUS":
            return {"allowed_match_phases": {"DEPLOY_UNIT": ["PREPARATION", "WAR"],
                    "BUILD_TOWER": ["PREPARATION", "WAR"], "TARGET_SELECTED": ["PREPARATION", "WAR"]},
                    "allowed_round_phases": {"DEPLOY_UNIT": ["PLANNING", "BATTLE"],
                    "BUILD_TOWER": ["PLANNING", "BATTLE"], "TARGET_SELECTED": ["PLANNING", "BATTLE"]},
                    "planning_phase": "PLANNING",
                    "quiz_match_phases": ["PREPARATION", "WAR"],
                    "quiz_round_phases": ["PLANNING", "BATTLE"]}
        return {"allowed_match_phases": ACTION_PHASES, "planning_phase": "PLANNING"}

    @staticmethod
    def context(match, team, action, actor=None):
        if match.status == MatchStatus.FINISHED or match.phase == "RESULTS":
            return Availability(False, "MATCH_FINISHED", "Trận đấu đã kết thúc.")
        if match.status == MatchStatus.PAUSED:
            return Availability(False, "MATCH_PAUSED", "Trận đấu đang tạm dừng.")
        if match.status != MatchStatus.ACTIVE:
            return Availability(False, "MATCH_NOT_ACTIVE", "Trận đấu chưa bắt đầu.")
        quiz_action = action in ("ANSWER_QUESTION", "CLAIM_REWARD")
        if not team or (team.status != "ACTIVE" and not (team.status == "ELIMINATED" and quiz_action)):
            return Availability(False, "TEAM_ELIMINATED", "Đội đã bị loại khỏi trận đấu.")
        if team.match_id != match.pk or (actor and (actor.team_id != team.pk or actor.role == "SPECTATOR")):
            return Availability(False, "SPECTATOR_READ_ONLY", "Bạn không có quyền điều khiển đội này.")
        continuous = match.configuration.get("gameplay_mode") == "CONTINUOUS"
        live_action = action in ("DEPLOY_UNIT", "BUILD_TOWER", "TARGET_SELECTED", "ANSWER_QUESTION", "CLAIM_REWARD", "UPGRADE_TEAM_TYPE", "UPGRADE_TOWER", "SELL_TOWER")
        round_phase = match.configuration.get("timer_state", {}).get("round_phase", "PLANNING")
        if action in ("RETARGET", "RETREAT_ALL", "DEFEND_BASE"):
            in_battle = match.phase == "WAR" and round_phase == "BATTLE"
            gathering = (
                action == "RETARGET"
                and match.phase == "PREPARATION"
                and match.configuration.get("current_round", 1) == 1
                and round_phase == "PLANNING"
            )
            between_rounds = (
                match.phase == "PREPARATION"
                and match.configuration.get("current_round", 1) > 1
                and round_phase == "PLANNING"
            )
            if not continuous or not (in_battle or gathering or between_rounds):
                return Availability(False, "INVALID_PHASE", "Lệnh quân đội không khả dụng trong giai đoạn hiện tại.")
            return Availability(True)
        if continuous:
            expected = "BATTLE" if match.phase == "WAR" and live_action else "PLANNING"
            phases = ("PREPARATION", "WAR") if live_action else ("PREPARATION",)
            if match.phase not in phases or round_phase != expected:
                return Availability(False, "INVALID_PHASE", "Thao tác này không được phép trong giai đoạn hiện tại.")
        else:
            if round_phase != "PLANNING":
                return Availability(False, "INVALID_PHASE", "Máy chủ đang xử lý giao tranh; chờ vòng lập kế hoạch.")
            if match.phase not in ACTION_PHASES.get(action, PLAYABLE_PHASES):
                return Availability(False, "INVALID_PHASE", f"Giai đoạn {match.phase} không cho phép thao tác này.")
        return Availability(True)

    @staticmethod
    def require(match, team, action, availability):
        if not availability.allowed:
            logger.warning("action_rejected match=%s team=%s round=%s phase=%s action=%s reason=%s",
                match.pk, team.pk if team else None, match.configuration.get("current_round", 1),
                match.configuration.get("timer_state", {}).get("round_phase", "PLANNING"), action,
                availability.reason_code, extra={
                "match_id": str(match.pk), "team_id": str(team.pk) if team else None,
                "round_number": match.configuration.get("current_round", 1),
                "round_phase": match.configuration.get("timer_state", {}).get("round_phase", "PLANNING"),
                "match_phase": match.phase, "action_type": action,
                "reason_code": availability.reason_code,
            })
            raise ValidationError(availability.reason, code=availability.reason_code)

    @classmethod
    def require_context(cls, match, team, action, actor=None):
        cls.require(match, team, action, cls.context(match, team, action, actor))

    @classmethod
    def require_purchase(cls, match, team, action, unit, quantity=1):
        if not unit.is_starter and not TeamUnlock.objects.filter(team=team, unit_type=unit).exists():
            cls.require(match, team, action, Availability(False,
                "TOWER_LOCKED" if action == "BUILD_TOWER" else "UNIT_LOCKED",
                f"'{unit.name}' chưa được mở khóa. Trả lời đúng câu hỏi để mở khóa."))
        # Defensive quantity is bounded only by paid, valid map space. Historical
        # max_towers_per_team values must never limit construction in saved rooms.
        if action != "BUILD_TOWER" and unit.code != "infantry":
            limit = match.configuration.get("max_active_units_per_team", 5)
            count = GameEntity.objects.filter(team=team, entity_kind="UNIT",
                status__in=[EntityStatus.QUEUED, EntityStatus.ACTIVE, EntityStatus.DISABLED]
                ).exclude(unit_type__code="infantry").count()
            if count + quantity > limit:
                cls.require(match, team, action, Availability(False, "UNIT_LIMIT_REACHED",
                    f"Đội đã đạt giới hạn tối đa {limit} đơn vị chiến đấu đang tồn tại."))
        if team.coins < unit.cost * quantity:
            cls.require(match, team, action, Availability(False, "INSUFFICIENT_COINS",
                f"Không đủ coin: cần {unit.cost * quantity}, hiện có {team.coins}."))


def validation_payload(error):
    """Preserve the existing error field and add a machine-readable rejection code."""
    return {"error": str(error), "error_code": getattr(error, "code", None) or "VALIDATION_ERROR"}
