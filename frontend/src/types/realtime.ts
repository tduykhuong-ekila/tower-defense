export interface ServerEnvelope<T = any> {
  event_id: string;
  match_id: string;
  event_type: string;
  sequence_number: number;
  state_version?: number;
  server_timestamp: string;
  payload: T;
}

export interface MatchSnapshotPayload {
  simulation_at?: string | null;
  tick_interval_ms?: number;
  map_data?: import('../game/map').ServerMap;
  match: {
    id: string;
    name: string;
    room_code: string;
    status: string;
    phase: string;
    is_locked: boolean;
    created_at: string;
    configuration: any;
  };
  teams: Array<{
    id: string;
    name: string;
    base_hp: number;
    initial_base_hp: number;
    base_shield: number;
    score: number;
    status: 'ACTIVE' | 'ELIMINATED';
    is_ready: boolean;
    coins?: number;
    members_count: number;
    active_units_count: number;
    towers_count: number;
    unlocked_units?: string[];
    members?: Array<{
      id: string;
      display_name: string;
      role: string;
      is_ready: boolean;
    }>;
  }>;
  entities: Array<{
    id: string;
    team_id: string;
    team_name: string;
    unit_code: string;
    unit_name: string;
    entity_kind: 'UNIT' | 'TOWER' | 'SPECIAL';
    current_hp: number;
    max_hp: number;
    range?: number;
    current_shield: number;
    level: number;
    status: string;
    current_node_id: string;
    target_team_id: string | null;
    simulation_state?: import('./unit').UnitSimulationState;
    simulation_at?: string;
    tick_interval_ms?: number;
  }>;
  current_round: number;
  combat_stats: Record<string, any>;
  team_upgrades?: Record<string, Record<string, number>>;
  viewer: {
    is_host: boolean;
    team_id: string | null;
    coins: number | null;
    unlocked_units: string[];
    current_question: any | null;
    pending_reward: any | null;
    question_progress?: import('./question').QuestionProgress | null;
  };
}

export type ConnectionStatus = 'connected' | 'syncing' | 'reconnecting' | 'disconnected';
