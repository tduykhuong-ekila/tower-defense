export type CombatEventType =
  | 'ACTION_LOCKED'
  | 'UNIT_SPAWNED'
  | 'UNIT_MOVED'
  | 'UNIT_RETARGETED'
  | 'TOWER_ENABLED'
  | 'TEAM_SCORE_UPDATED'
  | 'TOWER_ATTACKED'
  | 'UNIT_ATTACKED'
  | 'BASE_DAMAGED'
  | 'ENTITY_DESTROYED'
  | 'SHIELD_GENERATED'
  | 'SHIELD_EXPIRED'
  | 'BASE_DESTROYED'
  | 'TEAM_ELIMINATED'
  | 'VICTORY_DECLARED'
  | 'INCOME_AWARDED'
  | 'KILL_REWARD_AWARDED'
  | 'COMBAT_RESOLVED';

export interface CombatEvent {
  id?: string;
  type: CombatEventType;
  round_number?: number;
  entity_id?: string;
  team_id?: string;
  team_name?: string;
  attacker_id?: string;
  attacker_team_id?: string;
  tower_id?: string;
  tower_team_id?: string;
  unit_id?: string;
  target_entity_id?: string;
  target_team_id?: string;
  unit_type?: string;
  from_node?: string;
  to_node?: string;
  node_id?: string;
  reached_attack_position?: boolean;
  damage?: number;
  hp_damage?: number;
  shield_absorbed?: number;
  target_hp_remaining?: number;
  base_hp_remaining?: number;
  base_shield_remaining?: number;
  target_shield_remaining?: number;
  shield_amount?: number;
  reason?: string;
  amount?: number;
  new_balance?: number;
  score?: number;
  winner_team_id?: string;
  victory_type?: string;
  description?: string;
}

export interface CombatEntitySnapshot {
  id: string;
  team_id: string;
  unit_type_code: string;
  entity_kind: 'UNIT' | 'TOWER' | 'SPECIAL';
  current_hp: number;
  max_hp: number;
  current_shield: number;
  level: number;
  status: 'ACTIVE' | 'QUEUED' | 'DISABLED' | 'DESTROYED';
  current_node_id: string;
  target_team_id?: string;
  damage?: number;
  range?: number;
}

export interface TeamCombatSnapshot {
  id: string;
  name: string;
  team_index: number;
  base_hp: number;
  initial_base_hp: number;
  base_shield: number;
  coins: number;
  score: number;
  status: 'ACTIVE' | 'ELIMINATED';
}

export interface RoundResult {
  round_number: number;
  events_count?: number;
  events: CombatEvent[];
  eliminated_team_ids: string[];
  winner_team_id?: string | null;
  is_match_over: boolean;
}

export interface MatchResultRecord {
  id: string;
  match_id: string;
  team_id: string;
  team_name: string;
  final_rank: number;
  final_score: number;
  bases_destroyed: number;
  base_damage_dealt: number;
  correct_answers: number;
  remaining_base_hp: number;
  remaining_coins: number;
  surviving_towers: number;
  created_at: string;
}

export interface MatchAward {
  id: string;
  name: string;
  description: string;
  team_id: string;
  team_name: string;
  score: number;
}

export interface MatchResultsApiResponse {
  match_id: string;
  room_code: string;
  status: string;
  phase: string;
  winner_team_id?: string | null;
  winner_team_ids?: string[];
  winner_team_name?: string | null;
  duration_seconds?: number;
  awards?: MatchAward[];
  results: MatchResultRecord[];
}

export interface HostTeamTelemetry {
  id: string;
  name: string;
  status: string;
  base_hp: number;
  base_shield: number;
  coins: number;
  score: number;
  active_units: number;
  active_towers: number;
  remaining_questions: number;
  has_pending_reward: boolean;
  current_question_status?: string | null;
  members: {
    id: string;
    display_name: string;
    role: string;
    is_ready: boolean;
    is_online: boolean;
  }[];
  online_members_count: number;
}

export interface HostTelemetry {
  match_id: string;
  room_code: string;
  name: string;
  status: string;
  phase: string;
  is_locked: boolean;
  phase_remaining_seconds: number;
  current_round: number;
  total_events_count: number;
  teams: HostTeamTelemetry[];
}

export interface MatchPreset {
  id: string;
  name: string;
  description: string;
  configuration: any;
}

export interface BalancePreview {
  total_match_minutes: number;
  estimated_combat_rounds: number;
  round_duration_seconds: number;
  initial_coins: number;
  projected_passive_coins: number;
  max_question_coins: number;
  expected_question_coins: number;
  total_projected_coins_per_team: number;
  initial_base_hp: number;
  max_towers_per_team: number | null; // Retired compatibility field; never a build limit.
  max_active_units_per_team: number;
  pacing: string;
}

