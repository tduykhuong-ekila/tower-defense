import { create } from "zustand";
import { UnitSimulationState } from "../types/unit";
import {
  ConnectionStatus,
  MatchSnapshotPayload,
  ServerEnvelope,
} from "../types/realtime";
import { Match } from "../types/match";
import { QuestionProgress, TeamQuestion } from "../types/question";
import { RewardOptions } from "../types/reward";
import { CombatEvent } from "../types/combat";
import { ServerMap } from "../game/map";
import { RenderTeam } from "../game/bridge";
import { reconcileCombat } from "../game/systems/reconcile";

function applyLifecycle(match: Match | null, payload: any): Match | null {
  if (!match) return null;
  return { ...match, status: payload.status || match.status,
    phase: payload.phase || payload.to_phase || match.phase,
    configuration: { ...match.configuration,
      ...(payload.current_round ? { current_round: payload.current_round } : {}),
      ...(payload.timer_state ? { timer_state: payload.timer_state } : {}) },
  };
}

export interface EntityState {
  damage?: number;
  attack_interval_seconds?: number | null;
  range?: number;
  movement_speed?: number;
  id: string;
  team_id: string;
  team_name: string;
  unit_code: string;
  unit_name: string;
  entity_kind: "UNIT" | "TOWER" | "SPECIAL";
  current_hp: number;
  max_hp: number;
  current_shield: number;
  level: number;
  status: string;
  current_node_id: string;
  target_team_id: string | null;
  simulation_state?: UnitSimulationState;
  movement_path?: string[];
  simulation_at?: string;
  tick_interval_ms?: number;
}

interface MatchStoreState {
  match: Match | null;
  isHost: boolean;
  teams: RenderTeam[];
  mapData: ServerMap | null;
  entities: EntityState[];
  currentTeamId: string | null;
  coins: number;
  unlockedUnits: string[];
  teamUpgradeLevels: Record<string, Record<string, number>>;
  currentQuestion: TeamQuestion | null;
  questionProgress: QuestionProgress | null;
  lastQuestionSequence: number;
  pendingReward: RewardOptions | null;
  combatLogs: CombatEvent[];
  connectionStatus: ConnectionStatus;
  lastSequenceNumber: number;
  currentRound: number;

  // Actions
  setConnectionStatus: (status: ConnectionStatus) => void;
  setCurrentTeamId: (teamId: string | null) => void;
  applySnapshot: (
    snapshot: MatchSnapshotPayload,
    sequenceNumber?: number,
  ) => void;
  applyEvent: (envelope: ServerEnvelope) => void;
  reset: () => void;
}

export const useMatchStore = create<MatchStoreState>((set, get) => ({
  match: null,
  isHost: false,
  teams: [],
  mapData: null,
  entities: [],
  currentTeamId: null,
  coins: 100,
  unlockedUnits: ["infantry", "mg_tower"],
  teamUpgradeLevels: {},
  currentQuestion: null,
  questionProgress: null,
  lastQuestionSequence: 0,
  pendingReward: null,
  combatLogs: [],
  connectionStatus: "disconnected",
  lastSequenceNumber: 0,
  currentRound: 1,

  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),

  setCurrentTeamId: (currentTeamId) => set({ currentTeamId }),

  applySnapshot: (snapshot, sequenceNumber = 0) => {
    const state = get();
    if (
      state.match?.id === snapshot.match.id &&
      sequenceNumber < state.lastSequenceNumber
    )
      return;
    if (state.match && state.match.id !== snapshot.match.id) get().reset();
    const viewer = snapshot.viewer || {};
    const teams = snapshot.teams || [];
    const myTeamId = viewer.team_id || get().currentTeamId;

    let myCoins = get().coins;
    if (viewer.coins !== null && viewer.coins !== undefined) {
      myCoins = viewer.coins;
    } else if (myTeamId) {
      const myTeam = teams.find((t: any) => t.id === myTeamId);
      if (myTeam && myTeam.coins !== undefined) myCoins = myTeam.coins;
    }

    set({
      match: snapshot.match as Match,
      isHost: !!viewer.is_host,
      teams,
      mapData: snapshot.map_data || get().mapData,
      entities: (snapshot.entities || []).map(e => ({ ...e,
        simulation_at: e.simulation_at ?? snapshot.simulation_at ?? snapshot.match.configuration?.timer_state?.simulation_at,
        tick_interval_ms: e.tick_interval_ms ?? snapshot.tick_interval_ms,
      })) as EntityState[],
      currentTeamId: myTeamId,
      coins: myCoins,
      unlockedUnits: viewer.unlocked_units || get().unlockedUnits,
      teamUpgradeLevels: snapshot.team_upgrades || {},
      currentQuestion: viewer.current_question || null,
      questionProgress: viewer.question_progress || null,
      lastQuestionSequence: sequenceNumber,
      pendingReward: viewer.pending_reward || null,
      currentRound: snapshot.current_round || 1,
      lastSequenceNumber: Math.max(get().lastSequenceNumber, sequenceNumber),
    });
  },

  applyEvent: (envelope: ServerEnvelope) => {
    const { event_type, sequence_number, payload } = envelope;
    if (event_type === "MATCH_STATE_SNAPSHOT") {
      get().applySnapshot(payload, sequence_number);
      return;
    }
    if (get().match && get().match!.id !== envelope.match_id) return;
    if (sequence_number > 0 && sequence_number <= get().lastSequenceNumber)
      return;

    const quizEvents = ['QUESTION_TIMER_UPDATED', 'QUESTION_ASSIGNED', 'QUESTION_EXPIRED', 'ANSWER_RESULT', 'QUESTION_ANSWERED_CORRECT', 'QUESTION_ANSWERED_INCORRECT', 'REWARD_OPTIONS', 'REWARD_APPLIED', 'REWARD_CLAIMED'];
    if (quizEvents.includes(event_type)) {
      if (payload.team_id && payload.team_id !== get().currentTeamId) {
        set({ lastSequenceNumber: Math.max(get().lastSequenceNumber, sequence_number) });
        return;
      }
      set({ lastQuestionSequence: Math.max(get().lastQuestionSequence, sequence_number), ...(payload.question_progress ? { questionProgress: payload.question_progress } : {}) });
    }

    set((state) => {
      const nextSeq = Math.max(state.lastSequenceNumber, sequence_number || 0);

      switch (event_type) {
        case "MATCH_STATE_SNAPSHOT":
          get().applySnapshot(payload, sequence_number);
          return { lastSequenceNumber: nextSeq };

        case "COINS_UPDATED":
        case "COINS_CREDITED":
        case "COINS_DEBITED": {
          const teamId = payload.team_id;
          const newBal = payload.balance_after ?? payload.new_balance;
          if (newBal !== undefined && teamId === state.currentTeamId) {
            return {
              coins: newBal,
              teams: state.teams.map((t) =>
                t.id === teamId ? { ...t, coins: newBal } : t,
              ),
              lastSequenceNumber: nextSeq,
            };
          }
          return {
            teams: state.teams.map((t) =>
              t.id === teamId ? { ...t, coins: newBal ?? t.coins } : t,
            ),
            lastSequenceNumber: nextSeq,
          };
        }

        case "UNITS_RETARGETED":
        case "ARMY_DEFENSE_ORDERED":
        case "ARMY_RETREAT_ORDERED":
        case "COMBAT_TICK": {
          const events: CombatEvent[] = payload.events || [];
          const result = reconcileCombat(state.teams, state.entities, events, state.currentTeamId, state.coins);
          const updates = new Map<string, any>((payload.entity_updates || []).map((e: any) => [e.id, e]));
          const known = new Set(result.entities.map(e => e.id));
          const arrivals: EntityState[] = [];
          for (const update of updates.values()) {
            if (!known.has(update.id) && update.status !== "DESTROYED" && update.team_id && update.unit_code && update.entity_kind) {
              arrivals.push({team_name: "", target_team_id: null, current_shield: 0, level: 1, ...update});
            }
          }
          return {
            entities: [...result.entities, ...arrivals].map(e => updates.has(e.id)
              ? { ...e, ...updates.get(e.id), simulation_at: payload.simulation_at, tick_interval_ms: payload.tick_interval_ms } : e)
              .filter(e => e.status !== "DESTROYED"),
            teams: result.teams, coins: result.coins,
            combatLogs: [...events, ...state.combatLogs].slice(0, 100),
            lastSequenceNumber: nextSeq,
          };
        }
        case "BATTLE_STARTED":
        case "BATTLE_STOPPED":
        case "MATCH_STARTED":
        case "ROUND_STARTED":
        case "MATCH_PHASE_CHANGED": {
          if (payload.current_round && payload.current_round < state.currentRound) return { lastSequenceNumber: nextSeq };
          return {
            match: applyLifecycle(state.match, payload),
            currentRound: payload.current_round ?? state.currentRound,
            lastSequenceNumber: nextSeq,
          };
        }

        case "QUESTION_TIMER_UPDATED":
          return { currentQuestion: payload.question_state || state.currentQuestion, lastSequenceNumber: nextSeq };
        case "QUESTION_ASSIGNED": {
          return {
            currentQuestion: payload.question_state || (payload.question ? (payload as TeamQuestion) : null),
            pendingReward: null,
            lastSequenceNumber: nextSeq,
          };
        }

        case "ANSWER_RESULT":
        case "QUESTION_ANSWERED_CORRECT":
        case "QUESTION_ANSWERED_INCORRECT": {
          const isCorrect =
            payload.is_correct ?? event_type === "QUESTION_ANSWERED_CORRECT";
          return {
            currentQuestion: payload.question_state || (state.currentQuestion
              ? {
                  ...state.currentQuestion,
                  is_correct: isCorrect,
                  status: isCorrect
                    ? ("PENDING_REWARD" as any)
                    : ("ANSWER_INCORRECT" as any),
                }
              : null),
            pendingReward: payload.question_state ? payload.question_state.reward_options || null : payload.reward_options || state.pendingReward,
            lastSequenceNumber: nextSeq,
          };
        }

        case "REWARD_OPTIONS": {
          return {
            pendingReward: payload as RewardOptions,
            lastSequenceNumber: nextSeq,
          };
        }

        case "QUESTION_EXPIRED":
          return { currentQuestion: payload.question_state || (state.currentQuestion ? {...state.currentQuestion, status: "EXPIRED"} : null), pendingReward: null, lastSequenceNumber: nextSeq };

        case "REWARD_APPLIED":
        case "REWARD_CLAIMED": {
          const newUnlocks = payload.unlocked_unit_code
            ? [...new Set([...state.unlockedUnits, payload.unlocked_unit_code])]
            : state.unlockedUnits;
          const newCoins =
            payload.balance_after !== undefined &&
            payload.team_id === state.currentTeamId
              ? payload.balance_after
              : state.coins;
          return {
            pendingReward: null,
            currentQuestion: payload.question_state || (state.currentQuestion ? {...state.currentQuestion, status: "REWARD_CLAIMED"} : null),
            unlockedUnits: newUnlocks,
            coins: newCoins,
            lastSequenceNumber: nextSeq,
          };
        }

        case "ENTITIES_CREATED": {
          const entities = new Map(state.entities.map(e => [e.id, e]));
          for (const entity of payload.entities || []) entities.set(entity.id, entity);
          return {
            entities: [...entities.values()],
            coins: payload.team_id === state.currentTeamId && payload.coins_after !== undefined
              ? payload.coins_after : state.coins,
            lastSequenceNumber: nextSeq,
          };
        }

        case "UNIT_DEPLOYED": {
          const newEntity: EntityState = {
            id: payload.entity_id,
            team_id: payload.team_id,
            team_name: "",
            unit_code: payload.unit_code,
            unit_name: payload.unit_name || payload.unit_code,
            entity_kind: "UNIT",
            current_hp: payload.current_hp ?? 0,
            max_hp: payload.max_hp ?? 0,
            range: payload.range,
            damage: payload.damage,
            attack_interval_seconds: payload.attack_interval_seconds,
            movement_speed: payload.movement_speed,
            current_shield: 0,
            level: payload.level ?? 1,
            status: payload.status || "QUEUED",
            current_node_id:
              payload.current_node_id || payload.spawn_node || "",
            target_team_id: payload.target_team_id || null,
            simulation_state: payload.simulation_state,
          };
          const updatedCoins =
            payload.coins_after !== undefined &&
            payload.team_id === state.currentTeamId
              ? payload.coins_after
              : state.coins;
          return {
            entities: [
              ...state.entities.filter((e) => e.id !== newEntity.id),
              newEntity,
            ],
            coins: updatedCoins,
            lastSequenceNumber: nextSeq,
          };
        }

        case "TOWER_SOLD":
          return {
            entities: state.entities.filter(e => e.id !== payload.entity_id),
            coins: payload.team_id === state.currentTeamId ? (payload.coins_after ?? state.coins) : state.coins,
            teams: state.teams.map(t => t.id === payload.team_id && payload.coins_after !== undefined ? {...t, coins: payload.coins_after} : t),
            lastSequenceNumber: nextSeq,
          };

        case "TOWER_BUILT": {
          const newTower: EntityState = {
            id: payload.entity_id,
            team_id: payload.team_id,
            team_name: "",
            unit_code: payload.tower_code,
            unit_name: payload.tower_name || payload.tower_code,
            entity_kind: "TOWER",
            current_hp: payload.current_hp ?? 0,
            max_hp: payload.max_hp ?? 0,
            range: payload.range,
            damage: payload.damage,
            attack_interval_seconds: payload.attack_interval_seconds,
            current_shield: 0,
            movement_speed: 0,
            level: payload.level ?? 1,
            status: payload.status || "QUEUED",
            current_node_id: payload.node_id || "",
            simulation_state: payload.simulation_state,
            target_team_id: null,
          };
          const updatedCoins =
            payload.coins_after !== undefined &&
            payload.team_id === state.currentTeamId
              ? payload.coins_after
              : state.coins;
          return {
            entities: [
              ...state.entities.filter((e) => e.id !== newTower.id),
              newTower,
            ],
            coins: updatedCoins,
            lastSequenceNumber: nextSeq,
          };
        }

        case "COMBAT_RESOLVED": {
          if (payload.round_number && payload.round_number < state.currentRound - 1) return { lastSequenceNumber: nextSeq };
          const events: CombatEvent[] = payload.events || [];
          const eliminatedIds: string[] = payload.eliminated_team_ids || [];

          const reconciled = reconcileCombat(
            state.teams,
            state.entities,
            events,
            state.currentTeamId,
            state.coins,
          );
          return {
            ...reconciled,
            match: applyLifecycle(state.match, { ...payload,
              ...(payload.is_match_over ? { status: "FINISHED", phase: "RESULTS" } : {}) }),
            currentRound: payload.current_round ?? ((payload.round_number ?? state.currentRound) + 1),
            combatLogs: [...events, ...state.combatLogs].slice(0, 200),
            teams: reconciled.teams.map((t) =>
              eliminatedIds.includes(t.id) ? { ...t, status: "ELIMINATED" } : t,
            ),
            lastSequenceNumber: nextSeq,
          };
        }

        case "TEAM_UNIT_UPGRADED":
          return {
            teamUpgradeLevels: { ...state.teamUpgradeLevels,
              [payload.team_id]: { ...state.teamUpgradeLevels[payload.team_id],
                [payload.entity_type]: Math.max(state.teamUpgradeLevels[payload.team_id]?.[payload.entity_type] ?? 1, payload.level) } },
            entities: state.entities.map(e => {
              if (e.team_id !== payload.team_id || e.unit_code !== payload.entity_type || e.status === "DESTROYED" || e.current_hp <= 0 || e.level >= payload.level) return e;
              const max = payload.stats.hp;
              return {...e, level: payload.level, max_hp: max,
                current_hp: Math.min(max, Math.max(1, Math.floor(e.current_hp / Math.max(1, e.max_hp) * max + .5))),
                damage: payload.stats.damage, attack_interval_seconds: payload.stats.attack_interval_seconds};
            }),
            lastSequenceNumber: nextSeq,
          };

        case "TOWER_UPGRADED":
          return {
            entities: state.entities.map((e) =>
              e.id === payload.entity_id
                ? { ...e, level: payload.new_level }
                : e,
            ),
            lastSequenceNumber: nextSeq,
          };
        case "BASE_REPAIRED":
          return {
            teams: state.teams.map((t) =>
              t.id === payload.team_id
                ? {
                    ...t,
                    base_hp:
                      payload.base_hp ??
                      payload.base_hp_after ??
                      payload.new_hp ??
                      t.base_hp,
                  }
                : t,
            ),
            lastSequenceNumber: nextSeq,
          };
        case "UNIT_RETARGETED":
          return { entities: reconcileCombat(state.teams, state.entities,
            [{ ...payload, type: "UNIT_RETARGETED" }], state.currentTeamId, state.coins).entities,
            lastSequenceNumber: nextSeq };
        case "EMP_FIRED":
        case "EMP_USED":
          return {
            entities: state.entities.map((e) =>
              e.id === payload.target_entity_id
                ? { ...e, status: "DISABLED" }
                : e,
            ),
            lastSequenceNumber: nextSeq,
          };
        case "BASE_DAMAGED": {
          const targetTeamId = payload.target_team_id || payload.team_id;
          const hpRemain =
            payload.target_hp_remaining ?? payload.base_hp_remaining;
          return {
            teams: state.teams.map((t) =>
              t.id === targetTeamId
                ? { ...t, base_hp: hpRemain ?? t.base_hp }
                : t,
            ),
            lastSequenceNumber: nextSeq,
          };
        }

        case "BASE_DESTROYED":
        case "TEAM_ELIMINATED": {
          const elimId = payload.team_id || payload.eliminated_team_id;
          return {
            teams: state.teams.map((t) =>
              t.id === elimId ? { ...t, base_hp: 0, status: "ELIMINATED" } : t,
            ),
            lastSequenceNumber: nextSeq,
          };
        }

        case "MATCH_PAUSED":
          return {
            match: state.match
              ? applyLifecycle(state.match, { ...payload, status: "PAUSED" })
              : null,
            lastSequenceNumber: nextSeq,
          };

        case "MATCH_RESUMED":
          return {
            match: state.match
              ? applyLifecycle(state.match, { ...payload, status: "ACTIVE" })
              : null,
            lastSequenceNumber: nextSeq,
          };

        case "MATCH_ENDED":
          return {
            // Keep the current dialog's content available for the match-ended message.
            match: state.match
              ? applyLifecycle(state.match, { ...payload, status: "FINISHED", phase: "RESULTS" })
              : null,
            lastSequenceNumber: nextSeq,
          };

        case "LEADERBOARD_UPDATED":
          return { teams: state.teams.map(t => {
            const result = payload.leaderboard?.find((r: any) => r.team_id === t.id);
            return result ? { ...t, score: result.score } : t;
          }), lastSequenceNumber: nextSeq };

        case "MEMBER_JOINED":
        case "MEMBER_READY_CHANGED":
        case "READY_CHANGED": {
          if (payload.team_id && payload.is_ready !== undefined) {
            return {
              teams: state.teams.map((t) =>
                t.id === payload.team_id
                  ? { ...t, is_ready: payload.is_ready }
                  : t,
              ),
              lastSequenceNumber: nextSeq,
            };
          }
          return { lastSequenceNumber: nextSeq };
        }

        default:
          return { lastSequenceNumber: nextSeq };
      }
    });
  },

  reset: () =>
    set({
      match: null,
      isHost: false,
      teams: [],
      mapData: null,
      entities: [],
      currentTeamId: null,
      coins: 100,
      unlockedUnits: ["infantry", "mg_tower"],
      teamUpgradeLevels: {},
      currentQuestion: null,
      questionProgress: null,
      lastQuestionSequence: 0,
      pendingReward: null,
      combatLogs: [],
      connectionStatus: "disconnected",
      lastSequenceNumber: 0,
      currentRound: 1,
    }),
}));
