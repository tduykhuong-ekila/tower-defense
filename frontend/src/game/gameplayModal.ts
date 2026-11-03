import type { TeamQuestion } from "../types/question";
import type { RewardOptions } from "../types/reward";

export type GameplayModal = "QUESTION" | "REWARD" | null;

/** Keep visibility independent of answer state; terminal states render explicit feedback. */
export function visibleGameplayModal(
  requested: GameplayModal,
  question: TeamQuestion | null,
  _reward: RewardOptions | null,
): GameplayModal {
  if (!question) return null;
  if (requested === "REWARD") {
    if (["EXPIRED", "REWARD_CLAIMED"].includes(question.status)) return "QUESTION";
    // Options can arrive separately from status. Preserve intent while recovering them.
    return "REWARD";
  }
  return requested;
}
