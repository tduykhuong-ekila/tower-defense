import { ServerMap } from "./map";
import { UnitSimulationState } from "../types/unit";

/** Exact graph-hop coverage, including fractional edge spans; shared by previews and inspection. */
export function graphRange(map: ServerMap, source: string, range: number, simulation: UnitSimulationState = {}) {
  const adjacency = new Map<string, string[]>();
  for (const edge of map.edges) {
    adjacency.set(edge.from, [...(adjacency.get(edge.from) || []), edge.to]);
    adjacency.set(edge.to, [...(adjacency.get(edge.to) || []), edge.from]);
  }
  function distances(start: string) {
    const distances = new Map([[start, 0]]), queue = [start];
    for (let index = 0; index < queue.length; index++) {
      for (const next of adjacency.get(queue[index]) || []) if (!distances.has(next)) {
        distances.set(next, distances.get(queue[index])! + 1); queue.push(next);
      }
    }
    return distances;
  }
  const start = distances(source), end = simulation.next_node_id ? distances(simulation.next_node_id) : start;
  const progress = simulation.next_node_id ? simulation.edge_progress || 0 : 0;
  const distance = (id: string) => simulation.next_node_id
    ? Math.min((start.get(id) ?? Infinity) + progress, (end.get(id) ?? Infinity) + 1 - progress)
    : start.get(id) ?? Infinity;
  const nodes = map.nodes.filter(n => distance(n.node_id) <= range).map(n => n.node_id);
  const passable = new Set(map.nodes.filter(n => n.is_passable).map(n => n.node_id));
  const segments: {from: string; to: string; start: number; end: number}[] = [];
  for (const edge of map.edges) {
    if (!passable.has(edge.from) || !passable.has(edge.to)) continue;
    const a = Math.max(0, Math.min(1, range - distance(edge.from)));
    const b = Math.max(0, Math.min(1, range - distance(edge.to)));
    // Backend tower coverage includes the entire road between adjacent covered nodes.
    const towerSpan = source.startsWith("node_tower_") && range >= 1
      && start.get(edge.from) === 1 && start.get(edge.to) === 1;
    if (towerSpan || a + b >= 1) segments.push({...edge, start: 0, end: 1});
    else {
      if (a > 0) segments.push({...edge, start: 0, end: a});
      if (b > 0) segments.push({...edge, start: 1 - b, end: 1});
    }
  }
  return {nodes, segments};
}
