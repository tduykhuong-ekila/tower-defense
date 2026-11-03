import { Match } from "../types/match";

/** Display server deadlines; this function never advances a round. */
export function planningSeconds(match: Match | null, now: number): number | null {
  if (match?.configuration.gameplay_mode === "CONTINUOUS") return null;
  if (!match || !["BUILD_AND_SCOUT", "WAR", "FINAL_ASSAULT"].includes(match.phase)
    || match.status === "FINISHED") return null;
  const timer = match.configuration.timer_state;
  if (match.status === "PAUSED") return Math.ceil(timer?.round_remaining_seconds ?? 0);
  return timer?.next_round_at ? Math.max(0, Math.ceil((Date.parse(timer.next_round_at) - now) / 1000)) : null;
}
