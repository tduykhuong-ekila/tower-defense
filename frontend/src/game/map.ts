/** Server graph is authoritative. This module only projects nodes into artwork coordinates. */
export interface ServerMapNode {
  node_id: string;
  node_type: "base" | "spawn" | "lane" | "center" | "tower_slot" | "barrier";
  team_index: number | null;
  is_passable: boolean;
  x: number;
  y: number;
}
export interface ServerMap {
  placement_grid?: import("./placement").PlacementGrid;
  num_teams: number;
  arena?: { version: number; key: string; profile: string; width: number; height: number; centerX: number; centerY: number; layout_scale: number; regions: number };
  team_ids: string[];
  staging_areas?: { spawn_node_id: string; bounds: { x: number; y: number }[]; parking_points?: { x: number; y: number }[] }[];
  rally_areas?: { team_index: number; team_id: string | null; spawn_node_id: string; entry_node_id: string; spawn_point: { x: number; y: number }; radius: number }[];
  nodes: ServerMapNode[];
  edges: { from: string; to: string }[];
}
export interface VisualNode extends ServerMapNode {
  id: string;
  worldX: number;
  worldY: number;
}
export const WORLD = { width: 1600, height: 1040, centerX: 800, centerY: 520 };
export const PALETTE = [
  "#55a5cc",
  "#d66552",
  "#87b65d",
  "#d4a64b",
  "#b487cd",
  "#55bbb0",
  "#d28caa",
  "#89a9df",
  "#cba06b",
  "#b6c762",
  "#bd8070",
  "#88b5a3",
  "#e6b8df", "#6794e8", "#ed9758", "#83cbd4", "#bca2ed", "#dfcc77", "#c66c94", "#8fbdc9",
];
export const TEAM_SYMBOLS = ["◆", "✦", "●", "▲", "✚", "☾", "✿", "■", "♜", "✧", "⬟", "✹", "◇", "✶", "◎", "△", "✛", "◐", "❖", "▣"];
export function teamLabel(index: number) { return `${TEAM_SYMBOLS[index] || "◆"} ${index + 1}`; }
export function arenaWorld(data: ServerMap | null) { return data?.arena || WORLD; }

export interface WorldBounds { x: number; y: number; width: number; height: number; centerX: number; centerY: number; }
/** Visual navigation margin only. Server arena coordinates and graph stay untouched. */
export function battlefieldWorld(data: ServerMap | null): WorldBounds {
  const arena = arenaWorld(data);
  const horizontal = Math.round(Math.max(320, arena.width * 0.12));
  const topPadding = Math.round(Math.max(240, arena.height * 0.14));
  // Keep extra terrain below the arena so the bottom of the battlefield can
  // scroll clear of the tactical command dock.
  const bottomPadding = Math.round(Math.max(640, arena.height * 0.42));
  const y = -topPadding;
  const height = arena.height + topPadding + bottomPadding;
  return { x: -horizontal, y, width: arena.width + horizontal * 2,
    height, centerX: arena.centerX, centerY: y + height / 2 };
}

/** Clip the actual viewport intersection, including negative-origin padding. */
export function minimapViewport(world: WorldBounds, frame: { x: number; y: number; width: number; height: number }) {
  const x = Math.max(world.x, frame.x), y = Math.max(world.y, frame.y);
  return { x, y, width: Math.max(0, Math.min(world.x + world.width, frame.x + frame.width) - x),
    height: Math.max(0, Math.min(world.y + world.height, frame.y + frame.height) - y) };
}

export function minimapPoint(world: WorldBounds, u: number, v: number) {
  return { x: world.x + Math.max(0, Math.min(1, u)) * world.width,
    y: world.y + Math.max(0, Math.min(1, v)) * world.height };
}


export function projectMap(data: ServerMap): Map<string, VisualNode> {
  const world = arenaWorld(data);
  const a = (-Math.PI * 3) / 4;
  return new Map(
    data.nodes.map((n) => [
      n.node_id,
      {
        ...n,
        id: n.node_id,
        worldX: world.centerX + (n.x * Math.cos(a) - n.y * Math.sin(a)) * 1.5,
        worldY:
          world.centerY + 60 + (n.x * Math.sin(a) + n.y * Math.cos(a)) * 0.86,
      },
    ]),
  );
}
export function teamIndex(data: ServerMap | null, teamId: string): number {
  return data?.team_ids.indexOf(teamId) ?? -1;
}
export function movementEdges(data: ServerMap) {
  const nodes = new Map(data.nodes.map((n) => [n.node_id, n]));
  return data.edges.filter(
    (e) => nodes.get(e.from)?.is_passable && nodes.get(e.to)?.is_passable,
  );
}
export function canPlaceTower(
  nodeId: string,
  validSlots: string[],
  entities: { current_node_id: string; status: string; entity_kind: string }[],
) {
  return (
    validSlots.includes(nodeId) &&
    !entities.some(
      (e) =>
        e.entity_kind === "TOWER" &&
        e.status !== "DESTROYED" &&
        e.current_node_id === nodeId,
    )
  );
}
export function isPointerClick(
  start: { x: number; y: number },
  end: { x: number; y: number },
  multiTouch = false,
) {
  return !multiTouch && Math.hypot(end.x - start.x, end.y - start.y) < 7;
}
export function visualPath(
  nodes: Map<string, VisualNode>,
  from: string,
  to: string,
) {
  const a = nodes.get(from),
    b = nodes.get(to);
  return a && b
    ? [
        { x: a.worldX, y: a.worldY },
        { x: b.worldX, y: b.worldY },
      ]
    : [];
}

export function routeToTeam(data: ServerMap, sourceId: string, targetId: string): string[] {
  return roadPath(data, `node_spawn_t${teamIndex(data, sourceId) + 1}`, `node_lane_t${teamIndex(data, targetId) + 1}_1`);
}

export function roadPath(data: ServerMap, start: string, end: string): string[] {
  const adjacency = new Map<string, string[]>();
  for (const e of movementEdges(data)) {
    adjacency.set(e.from, [...(adjacency.get(e.from) || []), e.to]);
    adjacency.set(e.to, [...(adjacency.get(e.to) || []), e.from]);
  }
  const nodes = new Map(data.nodes.map(node => [node.node_id, node]));
  if (!nodes.get(start)?.is_passable || !nodes.get(end)?.is_passable) return [];
  const costs = new Map([[start, 0]]), parent = new Map<string, string | null>([[start, null]]);
  const pending = new Set([start]);
  while (pending.size) {
    const id = [...pending].sort((a, b) => costs.get(a)! - costs.get(b)! || a.localeCompare(b))[0];
    pending.delete(id);
    if (id === end) {
      const path: string[] = []; let step: string | null = end;
      while (step) { path.unshift(step); step = parent.get(step) || null; }
      return path;
    }
    const a = nodes.get(id)!;
    for (const next of (adjacency.get(id) || []).sort()) {
      const b = nodes.get(next)!;
      const candidate = costs.get(id)! + Math.hypot(b.x - a.x, b.y - a.y);
      if (candidate < (costs.get(next) ?? Infinity) - 1e-9) {
        costs.set(next, candidate); parent.set(next, id); pending.add(next);
      }
    }
  }
  return [];
}

/** Fit expanded arenas inside the area left visible by the HUD. */
export function overviewCamera(width: number, height: number, world: typeof WORLD & { x?: number; y?: number }) {
  const expanded = world.width > WORLD.width || world.height > WORLD.height;
  const left = expanded ? 14 : 0;
  const right = expanded ? (width >= 700 ? 274 : 14) : 0;
  const top = expanded ? Math.min(height * 0.2, width < 600 ? 118 : 146) : 0;
  const bottom = expanded ? Math.min(height * 0.32, width < 600 ? 242 : 218) : 0;
  const area = { x: left, y: top, width: Math.max(1, width-left-right), height: Math.max(1, height-top-bottom) };
  const zoom = Math.min(area.width/world.width, area.height/world.height);
  const centerX = world.centerX + (width/2 - (area.x + area.width/2))/zoom;
  const centerY = world.centerY + (height/2 - (area.y + area.height/2))/zoom;
  // Phaser must allow the requested off-center viewport. Symmetric letterbox
  // bounds would clamp it back under the HUD when the viewport exceeds the world.
  const x = Math.min(world.x ?? 0, centerX-width/zoom/2);
  const y = Math.min(world.y ?? 0, centerY-height/zoom/2);
  const bounds = {x, y, width:Math.max((world.x ?? 0)+world.width,centerX+width/zoom/2)-x,
    height:Math.max((world.y ?? 0)+world.height,centerY+height/zoom/2)-y};
  return {zoom, area, centerX, centerY, bounds};
}
