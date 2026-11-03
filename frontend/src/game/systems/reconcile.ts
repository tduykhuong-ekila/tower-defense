import { CombatEvent } from "../../types/combat";
import { EntityState } from "../../stores/matchStore";
import { RenderTeam } from "../bridge";

/** Apply only values sent by the server; never calculate combat damage or income locally. */
export function reconcileCombat(
  teams: RenderTeam[],
  entities: EntityState[],
  events: CombatEvent[],
  myTeamId: string | null,
  coins: number,
) {
  let nextTeams = teams.map((t) => ({ ...t })),
    nextEntities = entities.map((e) => ({ ...e })),
    nextCoins = coins;
  for (const e of events) {
    if (e.type === "TEAM_SCORE_UPDATED" && e.score !== undefined)
      nextTeams = nextTeams.map(t => t.id === e.team_id ? { ...t, score: e.score } : t);
    if (e.type === "UNIT_RETARGETED")
      nextEntities = nextEntities.map((v) => v.id === e.entity_id
        ? { ...v, target_team_id: e.target_team_id || null } : v);
    if (e.type === "TOWER_ENABLED")
      nextEntities = nextEntities.map((v) => v.id === e.entity_id ? { ...v, status: "ACTIVE" } : v);
    if (e.type === "UNIT_MOVED")
      nextEntities = nextEntities.map((v) =>
        v.id === e.entity_id && e.to_node
          ? { ...v, current_node_id: e.to_node }
          : v,
      );
    if (e.type === "UNIT_SPAWNED")
      nextEntities = nextEntities.map((v) =>
        v.id === e.entity_id
          ? {
              ...v,
              status: "ACTIVE",
              current_node_id: e.node_id || v.current_node_id,
            }
          : v,
      );
    if (e.type === "TOWER_ATTACKED" || e.type === "UNIT_ATTACKED")
      nextEntities = nextEntities.map((v) =>
        v.id === e.target_entity_id && e.target_hp_remaining !== undefined
          ? { ...v, current_hp: e.target_hp_remaining,
              current_shield: e.target_shield_remaining ?? v.current_shield }
          : v,
      );
    if (e.type === "ENTITY_DESTROYED")
      nextEntities = nextEntities.filter((v) => v.id !== e.entity_id);
    if (e.type === "BASE_DAMAGED")
      nextTeams = nextTeams.map((t) =>
        t.id === e.target_team_id
          ? { ...t, base_hp: e.base_hp_remaining ?? t.base_hp,
              base_shield: e.base_shield_remaining ?? t.base_shield }
          : t,
      );
    if (e.type === "BASE_DESTROYED" || e.type === "TEAM_ELIMINATED")
      nextTeams = nextTeams.map((t) =>
        t.id === e.team_id ? { ...t, base_hp: 0, status: "ELIMINATED" } : t,
      );
    if (e.type === "SHIELD_GENERATED" || e.type === "SHIELD_EXPIRED")
      nextTeams = nextTeams.map((t) =>
        t.id === e.team_id
          ? {
              ...t,
              base_shield:
                e.type === "SHIELD_EXPIRED"
                  ? 0
                  : (e.shield_amount ?? t.base_shield),
            }
          : t,
      );
    if ((e.type === "INCOME_AWARDED" || e.type === "KILL_REWARD_AWARDED") && e.new_balance !== undefined) {
      nextTeams = nextTeams.map((t) =>
        t.id === e.team_id ? { ...t, coins: e.new_balance } : t,
      );
      if (e.team_id === myTeamId) nextCoins = e.new_balance;
    }
  }
  return { teams: nextTeams, entities: nextEntities, coins: nextCoins };
}
