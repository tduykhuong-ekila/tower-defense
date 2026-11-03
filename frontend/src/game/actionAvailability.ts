import { Match } from "../types/match";
import { UnitType } from "../types/unit";
import { RenderEntity, RenderTeam } from "./bridge";

export interface ActionAvailability { allowed: boolean; reason_code?: string; reason?: string }
export interface AvailabilityContext {
  match: Match | null;
  team: RenderTeam | null | undefined;
  spectator: boolean;
  connection: string;
  pending: boolean;
  modal: boolean;
  coins: number;
  entities: RenderEntity[];
  unlocked: string[];
  slots: string[];
  gridPlacement?: boolean;
}
const deny = (reason_code: string, reason: string): ActionAvailability => ({allowed:false, reason_code, reason});
const defaults: Record<string, string[]> = {
  DEPLOY_UNIT: ["PREPARATION", "BUILD_AND_SCOUT", "WAR", "FINAL_ASSAULT"],
  BUILD_TOWER: ["PREPARATION", "BUILD_AND_SCOUT", "WAR"],
};

/** Preliminary UX only. Every mutation is revalidated by the shared server policy. */
export function actionAvailability(c: AvailabilityContext, action = "DEPLOY_UNIT"): ActionAvailability {
  if (c.match?.status === "FINISHED" || c.match?.phase === "RESULTS") return deny("MATCH_FINISHED", "Trận đấu đã kết thúc.");
  const quizAction = ["ANSWER_QUESTION", "CLAIM_REWARD"].includes(action);
  if (c.team?.status === "ELIMINATED" && !quizAction) return deny("TEAM_ELIMINATED", "Đội đã bị loại; bạn đang quan sát.");
  if (c.spectator || !c.team) return deny("SPECTATOR_READ_ONLY", "Bạn đang quan sát trận đấu.");
  if (c.connection !== "connected") return deny("DISCONNECTED", "Đang đồng bộ lại với máy chủ.");
  if (c.pending) return deny("ACTION_ALREADY_PROCESSING", "Đang chờ máy chủ xác nhận thao tác.");
  if (c.modal) return deny("MODAL_OPEN", "Hoàn tất hoặc đóng cửa sổ đang mở.");
  if (c.match?.status === "PAUSED") return deny("MATCH_PAUSED", "Trận đấu đang tạm dừng.");
  if (c.match?.status !== "ACTIVE") return deny("MATCH_NOT_ACTIVE", "Trận đấu chưa bắt đầu.");
  const continuous = c.match.configuration.gameplay_mode === "CONTINUOUS";
  const liveAction = ["DEPLOY_UNIT", "BUILD_TOWER", "TARGET_SELECTED", "ANSWER_QUESTION", "CLAIM_REWARD", "UPGRADE_TEAM_TYPE", "UPGRADE_TOWER", "SELL_TOWER"].includes(action);
  const roundPhase = c.match.configuration.timer_state?.round_phase || "PLANNING";
  const phases = c.match.configuration.action_rules?.allowed_match_phases[action]
    || (continuous ? liveAction ? ["PREPARATION", "WAR"] : ["PREPARATION"] : defaults[action] || defaults.DEPLOY_UNIT);
  if (!phases.includes(c.match.phase)) return deny("INVALID_PHASE", `Giai đoạn ${c.match.phase} không cho phép thao tác này.`);
  const expected = continuous && c.match.phase === "WAR" && liveAction ? "BATTLE" : "PLANNING";
  if (roundPhase !== expected) return deny("INVALID_PHASE", "Thao tác này không được phép trong giai đoạn hiện tại.");
  return {allowed:true};
}

export function maximumDeployment(c: AvailabilityContext, unit: UnitType): number {
  const affordable = unit.cost > 0 ? Math.floor(c.coins / unit.cost) : Number.MAX_SAFE_INTEGER;
  if (unit.code === "infantry") return Math.max(0, affordable);
  const used = c.entities.filter(e => e.team_id === c.team?.id && e.entity_kind === "UNIT"
    && e.unit_code !== "infantry" && e.status !== "DESTROYED").length;
  return Math.max(0, Math.min(affordable, (c.match?.configuration.max_active_units_per_team ?? 5) - used));
}

export function purchaseAvailability(c: AvailabilityContext, unit: UnitType, quantity = 1): ActionAvailability {
  const tower = unit.category === "TOWER";
  const common = actionAvailability(c, tower ? "BUILD_TOWER" : "DEPLOY_UNIT");
  if (!common.allowed) return common;
  if (!(unit.is_starter || unit.is_unlocked || c.unlocked.includes(unit.code)))
    return deny(tower ? "TOWER_LOCKED" : "UNIT_LOCKED", "Trả lời đúng câu hỏi rồi chọn mở khóa công nghệ này.");
  if (!Number.isSafeInteger(quantity) || quantity < 1) return deny("INVALID_QUANTITY", "Số lượng phải là số nguyên từ 1 trở lên.");
  if (!tower && unit.code !== "infantry") {
    const count = c.entities.filter(e => e.team_id === c.team!.id && e.entity_kind === "UNIT"
      && e.unit_code !== "infantry" && e.status !== "DESTROYED").length;
    const limit = c.match!.configuration.max_active_units_per_team;
    if (count + quantity > limit) return deny("UNIT_LIMIT_REACHED", `Không đủ chỗ cho ${quantity} quân; giới hạn ${limit}.`);
  }
  if (c.coins < unit.cost * quantity) return deny("INSUFFICIENT_COINS", `Không đủ xu: cần ${unit.cost * quantity}, hiện có ${c.coins}.`);
  if (tower && !c.gridPlacement && !c.slots.length) return deny("INVALID_POSITION", "Không còn ô xây tháp hợp lệ.");
  return {allowed:true};
}
