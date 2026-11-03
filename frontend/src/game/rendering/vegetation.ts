import { arenaWorld, battlefieldWorld, movementEdges, projectMap, ServerMap, VisualNode } from "../map";

export interface Vegetation { x: number; y: number; key: string; scale: number; flip: boolean; }
export function seeded(seed: number) {
  return () => {seed = (Math.imul(seed, 1664525) + 1013904223) | 0; return (seed >>> 0) / 4294967296;};
}
export function riverX(y: number, world = arenaWorld(null), offsetX = 0, path?: [number, number][]) {
  if (path?.length && path.length > 1) {
    let low = 0, high = path.length - 1;
    if (y <= path[0][1]) high = 1;
    else if (y >= path[high][1]) low = high - 1;
    else {
      while (high - low > 1) {
        const middle = (low + high) >> 1;
        if (path[middle][1] <= y) low = middle; else high = middle;
      }
    }
    const a = path[low], b = path[high];
    return a[0] + (b[0] - a[0]) * ((y - a[1]) / (b[1] - a[1] || 1));
  }
  return world.width * (1030 / 1600) - y * (world.width / world.height) * 0.2535 + Math.sin(y / 145) * 85 + offsetX;
}
function distanceToPolyline(x: number, y: number, path: [number, number][]) {
  let distance = Infinity;
  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1], b = path[i], dx = b[0] - a[0], dy = b[1] - a[1];
    const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    distance = Math.min(distance, Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy));
  }
  return distance;
}
function distanceToSegment(x: number, y: number, a: VisualNode, b: VisualNode) {
  const dx = b.worldX - a.worldX, dy = b.worldY - a.worldY;
  const t = Math.max(0, Math.min(1, ((x-a.worldX)*dx + (y-a.worldY)*dy) / (dx*dx + dy*dy || 1)));
  return Math.hypot(x-a.worldX-t*dx, y-a.worldY-t*dy);
}
export function vegetationClear(data: ServerMap, nodes: Map<string, VisualNode>, x: number, y: number) {
  const world = arenaWorld(data);
  const riverPath = data.placement_grid?.riverPath;
  const riverDistance = riverPath?.length
    ? distanceToPolyline(x, y, riverPath)
    : Math.abs(x-riverX(y, world, data.placement_grid?.riverOffsetX ?? 0));
  if (riverDistance < 95) return false;
  for (const node of nodes.values()) {
    const radius = node.node_type === "base" ? 200 : node.node_type === "spawn" ? 210 : node.node_type === "tower_slot" ? 100 : node.is_passable ? 105 : 65;
    if (Math.hypot(node.worldX-x, node.worldY-y) < radius) return false;
  }
  // Curved roads bulge 8% of the edge length away from their chord.
  for (const edge of movementEdges(data)) {
    const a = nodes.get(edge.from)!, b = nodes.get(edge.to)!;
    if (distanceToSegment(x, y, a, b) < 95 + Math.hypot(b.worldX-a.worldX, b.worldY-a.worldY) * .04) return false;
  }
  // Reserve rally polygons and their outward approach corridors, even in padding.
  const angle = -Math.PI * 3 / 4;
  for (const area of data.staging_areas || []) {
    const node = nodes.get(area.spawn_node_id);
    if (!node) continue;
    const points = area.bounds.map(p => ({x: node.worldX + ((p.x-node.x)*Math.cos(angle)-(p.y-node.y)*Math.sin(angle))*1.5,
      y: node.worldY + ((p.x-node.x)*Math.sin(angle)+(p.y-node.y)*Math.cos(angle))*.86}));
    if (x >= Math.min(...points.map(p=>p.x))-85 && x <= Math.max(...points.map(p=>p.x))+85 &&
        y >= Math.min(...points.map(p=>p.y))-95 && y <= Math.max(...points.map(p=>p.y))+95) return false;
  }
  return true;
}
/** Bounded organic groves, seeded by map topology; no perimeter iteration or collision. */
export function generateVegetation(data: ServerMap, nodes = projectMap(data)): Vegetation[] {
  const bounds = battlefieldWorld(data), world = arenaWorld(data);
  const random = seeded(9173 + data.num_teams * 131 + (data.arena?.version ?? 3));
  const result: Vegetation[] = [];
  const clusters = Math.min(100, Math.round(bounds.width * bounds.height / 100000));
  for (let c = 0; c < clusters; c++) {
    const cx = bounds.x + 90 + random() * (bounds.width-180), cy = bounds.y + 100 + random() * (bounds.height-200);
    const count = 2 + Math.floor(random()*6);
    for (let i = 0; i < count; i++) {
      const angle = random()*Math.PI*2, radius = Math.sqrt(random())*140;
      const x = cx + Math.cos(angle)*radius, y = cy + Math.sin(angle)*radius;
      if (x < bounds.x+50 || x > bounds.x+bounds.width-50 || y < bounds.y+90 || y > bounds.y+bounds.height-50) continue;
      if (!vegetationClear(data, nodes, x, y) || result.some(p=>Math.hypot(p.x-x,p.y-y)<44)) continue;
      const outer = x < 0 || x > world.width || y < 0 || y > world.height;
      const roll = random(), tree = roll < (outer ? .66 : .43);
      const key = tree ? `tree-${Math.floor(random()*3)}` : roll < .92 ? "bush" : "rock";
      result.push({x, y, key, scale: tree ? .38+random()*.32 : .18+random()*.20, flip: random() > .5});
    }
  }
  return result;
}
