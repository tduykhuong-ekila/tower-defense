export type MatchStatus = 'LOBBY' | 'ACTIVE' | 'PAUSED' | 'FINISHED';

export type MatchPhase =
  | 'LOBBY'
  | 'PREPARATION'
  | 'BUILD_AND_SCOUT'
  | 'WAR'
  | 'FINAL_ASSAULT'
  | 'RESULTS';

export type ParticipantRole = 'HOST' | 'MENTOR' | 'MENTEE' | 'SPECTATOR';

export interface TeamMember {
  id: string;
  team_id: string | null;
  display_name: string;
  role: ParticipantRole;
  is_ready: boolean;
  joined_at: string;
}

export interface Team {
  id: string;
  match_id: string;
  name: string;
  initial_base_hp: number;
  base_hp: number;
  base_shield: number;
  coins: number;
  score: number;
  status: 'ACTIVE' | 'ELIMINATED';
  is_ready: boolean;
  members: TeamMember[];
  member_count?: number;
  created_at: string;
}

export interface PhaseDurations {
  PREPARATION: number;
  BUILD_AND_SCOUT: number;
  WAR: number;
  FINAL_ASSAULT: number;
  RESULTS: number;
}

export interface ScoringWeights {
  enemy_base_destroyed: number;
  damage_dealt_per_100: number;
  remaining_hp_per_100: number;
  correct_answer: number;
  surviving_tower: number;
  remaining_coins_per_10: number;
}

export interface MatchConfig {
  gameplay_mode?: "LEGACY" | "CONTINUOUS";
  troop_formation_gap?: number;
  total_rounds?: 2 | 3;
  preparation_duration_seconds?: number;
  first_preparation_duration_seconds?: number;
  battle_duration_seconds?: number;
  battle_tick_interval_ms?: number;
  movement_baseline_round_seconds?: number;
  attack_cooldown_seconds?: number;
  current_round?: number;
  action_rules?: { allowed_match_phases: Record<string, string[]>; planning_phase: string };
  timer_state?: {
    phase_started_at?: string;
    phase_ends_at?: string;
    simulation_at?: string;
    next_tick_at?: string;
    phase_remaining_seconds?: number;
    round_started_at?: string;
    next_round_at?: string;
    round_remaining_seconds?: number;
    match_deadline_at?: string;
    round_phase?: "PLANNING" | "BATTLE" | "LOCKED" | "RESOLVING" | "RESULTS";
  };
  min_teams: number;
  max_teams: number;
  min_players_per_team: number;
  max_players_per_team: number;
  initial_base_hp: number;
  initial_coins: number;
  match_duration_seconds: number;
  phase_durations: PhaseDurations;
  round_duration_seconds: number;
  reward_grace_period_seconds: number;
  max_questions_per_team: number;
  correct_answer_coin_reward: number;
  base_income_per_round: number;
  max_towers_per_team: number | null; // Retired compatibility field; never a build limit.
  max_active_units_per_team: number;
  max_deployed_units_per_action: number | null;
  max_tower_placements_per_action: number;
  scoring_weights: ScoringWeights;
  fallback_policy: 'IDLE' | 'RETARGET_NEAREST';
  spectator_visibility: 'FULL' | 'FOG_OF_WAR';
  special_actions_enabled: {
    scout: boolean;
    emp: boolean;
    repair: boolean;
  };
  allow_late_join: boolean;
}

export interface Match {
  id: string;
  room_code: string;
  name: string;
  status: MatchStatus;
  phase: MatchPhase;
  configuration: MatchConfig;
  is_locked: boolean;
  started_at?: string | null;
  ended_at?: string | null;
  created_at: string;
  updated_at: string;
  teams: Team[];
  unassigned_members: TeamMember[];
  all_members: TeamMember[];
  host_token?: string;
}

export interface CreateMatchResponse extends Match {
  host_token: string;
}

export interface JoinMatchResponse {
  member: TeamMember;
  participant_token: string;
  match: Match;
}

export interface RoomConstraints {
  min_teams_to_start: number;
  max_teams: number;
  default_max_teams: number;
  min_members_per_team: number;
}

