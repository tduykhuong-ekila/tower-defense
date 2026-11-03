export interface UnitSimulationState {
  build_cost?: number;
  grid_placement?: {row:number; col:number; widthCells:number; heightCells:number; anchorOffsetY:number};
  order?: "ATTACK" | "RETREAT" | "AT_RALLY" | "DEFEND_BASE";
  destination_rally_id?: string | null;
  command_version?: number;
  attack_range?: number;
  movement_zone?: "STAGING" | "ROUTE";
  world_position?: { x: number; y: number };
  crowd_offset?: { x: number; y: number };
  movement_path?: { x: number; y: number }[];
  movement_state?: "MOVING" | "STOPPED";
  combat_state?: "IDLE" | "ATTACKING";
  attack_target_id?: string | null;
  attack_remaining?: number;
  next_node_id?: string;
  edge_progress?: number;
  approach_node_id?: string;
  staging_distance?: number;
  staging_entry_distance?: number;
  route_nodes?: string[];
  formation_order?: number;
  formation_footprint?: number;
}

export type EntityCategory = 'UNIT' | 'TOWER' | 'SPECIAL';

export type CardVisualStatus =
  | 'LOCKED'
  | 'AVAILABLE_TO_UNLOCK'
  | 'UNLOCKED_AFFORDABLE'
  | 'UNLOCKED_UNAFFORDABLE'
  | 'DEPLOYED'
  | 'DESTROYED';

export interface UpgradeStats { hp: number; damage: number; range: number; movement_speed: number; attack_rate_multiplier: number; attack_interval_seconds: number | null; shield: number; }
export interface UnitType {
  level?: number;
  attack_interval_seconds?: number | null;
  upgrade?: { eligible: boolean; max_level: number; cost: number | null; current_stats: UpgradeStats; next_stats: UpgradeStats | null };
  id: string;
  code: string;
  name: string;
  category: EntityCategory;
  description: string;
  cost: number;
  hp: number;
  damage: number;
  range: number;
  movement?: number;
  movement_speed?: number;
  max_active_units?: number | null;
  strategic_role?: string;
  is_starter?: boolean;
  is_unlockable?: boolean;
  is_active?: boolean;
  is_unlocked?: boolean;
  base_stats?: Record<string, any>;
}

export interface GameEntity {
  damage?: number;
  attack_interval_seconds?: number | null;
  range?: number;
  movement_speed?: number;
  id: string;
  match_id: string;
  team_id: string;
  unit_type_id: string;
  unit_type_code: string;
  name: string;
  entity_kind: EntityCategory;
  current_hp: number;
  max_hp: number;
  current_shield: number;
  level: number;
  status: 'QUEUED' | 'ACTIVE' | 'DISABLED' | 'DESTROYED';
  current_node_id: string;
  target_team_id?: string | null;
  target_team_name?: string | null;
  target_node_id?: string;
  simulation_state?: UnitSimulationState;
  created_at: string;
  destroyed_at?: string | null;
}

export interface GameAction {
  id: string;
  match_id: string;
  team_id: string;
  actor_id?: string | null;
  action_type: 'SELL_TOWER' | 'DEPLOY_UNIT' | 'BUILD_TOWER' | 'UPGRADE_TOWER' | 'UPGRADE_TEAM_TYPE' | 'REPAIR_BASE' | 'SCOUT' | 'EMP' | 'RETARGET' | 'RETREAT_ALL' | 'DEFEND_BASE';
  payload: Record<string, any>;
  status: 'QUEUED' | 'ACCEPTED' | 'RESOLVED' | 'REJECTED' | 'CANCELLED';
  idempotency_key: string;
  created_at: string;
  resolved_at?: string | null;
  failure_reason?: string;
}

export interface EnemyTeamSummary {
  id: string;
  name: string;
  status: string;
  base_hp: number;
  base_shield: number;
}

export interface TeamState {
  round_number?: number;
  action_availability?: Record<string, {allowed: boolean; reason_code: string; reason: string}>;
  team: {
    id: string;
    name: string;
    base_hp: number;
    initial_base_hp: number;
    base_shield: number;
    coins: number;
    score: number;
    status: string;
  };
  unlocked_units: UnitType[];
  entities: GameEntity[];
  limits: {
    active_units: { current: number; max: number | null };
    infantry?: { current: number; max: null };
    other_units?: { current: number; max: number };
    towers: { current: number; max: null };
    repairs_used_this_round: number;
  };
  valid_tower_slots: string[];
  enemy_teams: EnemyTeamSummary[];
  special_actions_enabled: Record<string, boolean>;
  special_action_costs: Record<string, number>;
}
