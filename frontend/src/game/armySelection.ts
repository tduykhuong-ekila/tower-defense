import type { InteractionMode, RenderEntity } from './bridge';

export function controllableTroops(entities: RenderEntity[], teamId: string | null) {
  return entities.filter(e => e.team_id === teamId && e.entity_kind === 'UNIT' &&
    e.current_hp > 0 && ['ACTIVE', 'QUEUED'].includes(e.status) && (e.movement_speed ?? 1) > 0);
}

export function updateArmySelection(previous: string[], ids: string[], additive: boolean, toggle = false) {
  if (!additive) return [...new Set(ids)];
  const next = new Set(previous);
  for (const id of ids) {
    if (toggle && next.has(id)) next.delete(id); else next.add(id);
  }
  return [...next];
}

export type ArmyStatusFilter = 'ALL' | 'ATTACK' | 'RETREAT' | 'AT_RALLY';

export function filterArmy(troops: RenderEntity[], filter: ArmyStatusFilter) {
  return filter === 'ALL' ? troops : troops.filter(unit => (unit.simulation_state?.order || 'ATTACK') === filter);
}

/** Toggle a whole type without accidentally removing other selected types. */
export function selectArmyGroup(previous: string[], ids: string[], multiple: boolean) {
  if (!multiple) return [...new Set(ids)];
  const allSelected = ids.length > 0 && ids.every(id => previous.includes(id));
  return allSelected ? previous.filter(id => !ids.includes(id)) : updateArmySelection(previous, ids, true);
}

/** Empty selected-only commands must never become the API's implicit all-army retreat. */
export function armyCommandRequest(command: 'RETARGET' | 'RETREAT_ALL' | 'DEFEND_BASE', ids: string[], target: string) {
  if (!ids.length || (command === 'RETARGET' && !target)) return null;
  return {command_type: command, unit_ids: [...new Set(ids)],
    ...(command === 'RETARGET' ? {target_team_id: target} : {})};
}

/** Trackpads pan by default; Shift or the explicit box tool opts into selection. */
export function shouldStartArmyBox(input: {
  enabled: boolean; mode: InteractionMode; touch: boolean; leftButton: boolean;
  shift: boolean; boxTool: boolean; panKey: boolean;
}) {
  return input.enabled && !['MODAL', 'WAITING'].includes(input.mode) && !input.panKey &&
    (input.touch || input.leftButton) && (input.boxTool || (!input.touch && input.shift));
}
