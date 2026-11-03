import { GameEntity, UnitType } from "../types/unit";
import { EntityState } from "../stores/matchStore";
import { ServerMap } from "./map";

export interface RenderTeam {
  id: string;
  name: string;
  base_hp: number;
  initial_base_hp: number;
  base_shield: number;
  status: string;
  coins?: number;
  score?: number;
}
export type RenderEntity = EntityState;
export type InteractionMode =
  | "IDLE"
  | "DEPLOY"
  | "BUILD"
  | "INSPECT"
  | "WAITING"
  | "COMBAT"
  | "MODAL";
export interface SceneState {
  teams: RenderTeam[];
  entities: RenderEntity[];
  mapData: ServerMap | null;
  myTeamId: string | null;
  selectedTargetTeamId: string;
  selectedEntityId: string | null;
  selectedArmyIds?: string[];
  armySelectionMode?: boolean;
  armyControlEnabled?: boolean;
  selectedUnit: UnitType | null;
  validTowerSlots: string[];
  mode: InteractionMode;
  sound: boolean;
  liveBattle?: boolean;
}
export interface CameraFrame { x: number; y: number; width: number; height: number; combat?: { x: number; y: number }; }
export interface SceneMetrics { fps: number; serverEntities: number; entities: number; visibleEntities: number; objects: number; effects: number; slowFrames: number; frameMsMax: number; frameMsP95: number; textureMB: number; }
export interface SceneCallbacks {
  onCameraChange?: (frame: CameraFrame) => void;
  onMetrics?: (metrics: SceneMetrics) => void;
  onNodeClick: (nodeId: string) => void;
  onGridClick?: (row:number,col:number) => void;
  onCancelBuild?: () => void;
  onBaseClick: (teamId: string) => void;
  onEntityClick: (entityId: string, additive?: boolean) => void;
  onArmyContextMenu?: (x: number, y: number) => void;
  onArmySelect?: (ids: string[], additive: boolean, boxed?: boolean) => void;
  onEntityInspect?: (entityId: string | null, x: number, y: number, pinned?: boolean) => void;
  onPlaybackChange: (playing: boolean) => void;
  onLoadError?: () => void;
}
export const EMPTY_SCENE: SceneState = {
  teams: [],
  entities: [],
  mapData: null,
  myTeamId: null,
  selectedTargetTeamId: "",
  selectedEntityId: null,
  selectedUnit: null,
  validTowerSlots: [],
  mode: "IDLE",
  sound: false,
};
export function normalizeEntity(entity: GameEntity): RenderEntity {
  return {
    id: entity.id,
    team_id: entity.team_id,
    team_name: "",
    unit_code: entity.unit_type_code,
    unit_name: entity.name,
    entity_kind: entity.entity_kind,
    current_hp: entity.current_hp,
    max_hp: entity.max_hp,
    range: entity.range,
    damage: entity.damage,
    attack_interval_seconds: entity.attack_interval_seconds,
    movement_speed: entity.movement_speed,
    current_shield: entity.current_shield,
    level: entity.level,
    status: entity.status,
    current_node_id: entity.current_node_id,
    target_team_id: entity.target_team_id || null,
    simulation_state: entity.simulation_state,
  };
}
