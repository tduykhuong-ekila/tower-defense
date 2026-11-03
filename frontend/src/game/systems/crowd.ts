import type { EntityState } from "../../stores/matchStore";

/** Only identical authoritative positions/appearances can share a visible body.
 * No screen grid or rounding: crossing a cell boundary cannot change this key.
 */
export function coincidentKey(entity: EntityState): string | null {
  const sim = entity.simulation_state, point = sim?.world_position;
  if (entity.unit_code !== "infantry" || !point) return null;
  return `${entity.team_id}:${entity.target_team_id}:${point.x}:${point.y}:${sim.movement_state}:${entity.level}:${entity.current_hp}:${entity.current_shield}`;
}

export function coincidentRepresentatives(
  visuals: Iterable<{data: EntityState; root: {visible: boolean}}>,
  retained: ReadonlySet<string> = new Set(),
) {
  const groups = new Map<string, {id: string; visible: boolean}>();
  for (const visual of visuals) {
    const key = coincidentKey(visual.data);
    if (key === null) continue;
    const previous = groups.get(key);
    // Prefer an existing visible body when a new overlapping unit arrives.
    if (!previous || (retained.has(visual.data.id) && !retained.has(previous.id)) ||
        (!retained.has(previous.id) && !previous.visible && visual.root.visible))
      groups.set(key, {id: visual.data.id, visible: visual.root.visible});
  }
  return new Set([...groups.values()].map(group => group.id));
}
