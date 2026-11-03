import type { EntityState } from "../stores/matchStore";
import type { RenderTeam } from "./bridge";
import { ENTITY_NAMES } from "./entityArtwork";

export function attackTargetInfo(entity: EntityState, entities: EntityState[], teams: RenderTeam[]) {
  const id = entity.simulation_state?.attack_target_id;
  if (entity.status !== "ACTIVE" || entity.current_hp <= 0 ||
      entity.simulation_state?.combat_state !== "ATTACKING" || !id) return null;
  if (id.startsWith("base:")) {
    const team = teams.find(t => t.id === id.slice(5));
    if (!team || team.status !== "ACTIVE" || team.base_hp <= 0) return null;
    return {id, name: "Căn cứ", teamName: team.name, hp: team.base_hp,
      maxHp: team.initial_base_hp, shield: team.base_shield};
  }
  const target = entities.find(e => e.id === id);
  if (!target || target.status !== "ACTIVE" || target.current_hp <= 0) return null;
  return {id, name: ENTITY_NAMES[target.unit_code] || target.unit_name || target.unit_code,
    teamName: teams.find(t => t.id === target.team_id)?.name || target.team_name,
    hp: target.current_hp, maxHp: target.max_hp, shield: target.current_shield};
}
