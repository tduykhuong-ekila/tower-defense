/** Shared artwork paths for React cards and the textures loaded by BootScene. */
import { upgradeLevel } from "./upgradeLevel";
export const ENTITY_NAMES: Record<string, string> = {
  infantry: "Bộ binh",
  tank: "Xe tăng",
  artillery: "Pháo binh",
  mg_tower: "Tháp súng máy",
  cannon_tower: "Tháp đại bác",
  shield_generator: "Tháp tạo khiên",
};

export function entityArtwork(code: string, teamIndex = 0, level = 1): string | undefined {
  if (!Object.prototype.hasOwnProperty.call(ENTITY_NAMES, code)) return undefined;
  // Infantry shares one approved face and outfit family across all teams.
  void teamIndex;
  const current = upgradeLevel(level);
  const extension = ["mg_tower", "cannon_tower", "tank", "artillery", "infantry", "shield_generator"].includes(code) ? "png" : "svg";
  return `/assets/woodland/${code}${current > 1 ? `-lv${current}` : ""}.${extension}`;
}

/** One consistent soldier model is shared by every team and all infantry states. */
export const infantryTexture = (level: number) => `infantry-soldier-${upgradeLevel(level)}`;
export const infantryRunTexture = (level: number) => `infantry-run-lv${upgradeLevel(level)}`;
export const infantryRunAnimation = (level: number) => `walk-infantry-${upgradeLevel(level)}`;
