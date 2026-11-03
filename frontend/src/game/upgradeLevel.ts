export const MAX_UPGRADE_LEVEL = 3;
export type UpgradeLevel = 1 | 2 | 3;

export function upgradeLevel(value = 1): UpgradeLevel {
  return Math.max(1, Math.min(MAX_UPGRADE_LEVEL, Math.trunc(value) || 1)) as UpgradeLevel;
}

/** Five-point polygon shared by the Phaser star texture renderer. */
export function starPoints(cx: number, cy: number, outer = 5): [number, number][] {
  return Array.from({length: 10}, (_, index) => {
    const angle = -Math.PI / 2 + index * Math.PI / 5;
    const radius = index % 2 ? outer * 0.48 : outer;
    return [cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius];
  });
}

export function showBattleStars(code: string, zoom: number) {
  return zoom >= (code === "infantry" ? 0.9 : code.endsWith("tower") || code === "shield_generator" ? 0.55 : 0.7);
}
