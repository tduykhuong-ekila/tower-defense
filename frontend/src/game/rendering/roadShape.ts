export interface RoadPoint { x: number; y: number }

/** A continuous sand corridor contains the shortest straight walking line.
 * Bends use only the spare road width, leaving the 12px troop offset plus 3px
 * inside yellow sand. Stable edge IDs make the same map look identical on reload.
 */
export function naturalRoad(a: RoadPoint, b: RoadPoint, key: string, sandWidth: number): RoadPoint[] {
  const dx = b.x - a.x, dy = b.y - a.y;
  const length = Math.hypot(dx, dy);
  const seed = [...key].reduce((sum, ch, i) => sum + ch.charCodeAt(0) * (i + 1), 0);
  const phase = (seed % 628) / 100;
  const amplitude = Math.max(0, Math.min(sandWidth / 2 - 15, length * .06));
  return Array.from({length: 33}, (_, i) => {
    const t = i / 32;
    const bend = amplitude * Math.sin(Math.PI * t) ** 2 *
      (.72 * Math.sin(2 * Math.PI * t + phase) + .28 * Math.sin(Math.PI * t + phase * .43));
    return {x: a.x + dx * t - dy / (length || 1) * bend,
      y: a.y + dy * t + dx / (length || 1) * bend};
  });
}

/** Wider patches soften the shoulders without narrowing the safe sand corridor. */
export function roadWidthScale(index: number, key: string) {
  const phase = key.length * .73;
  return 1 + .04 * (1 + Math.sin(index * .67 + phase));
}
