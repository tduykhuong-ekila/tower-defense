import { UnitSimulationState } from "../../types/unit";
import { VisualNode } from "../map";

/** Project the server's actual position, including staging and local passing. */
export function formationPosition(node: VisualNode, state: UnitSimulationState | undefined, nodes: Map<string, VisualNode>) {
  if (state?.world_position) {
    const dx = state.world_position.x - node.x, dy = state.world_position.y - node.y;
    const angle = -Math.PI * 3 / 4;
    return {x: node.worldX + (dx * Math.cos(angle) - dy * Math.sin(angle)) * 1.5,
            y: node.worldY + (dx * Math.sin(angle) + dy * Math.cos(angle)) * .86};
  }
  const nextId = state?.next_node_id || state?.approach_node_id;
  const next = nextId ? nodes.get(nextId) : undefined;
  if (!next) return {x:node.worldX,y:node.worldY};
  const mapLength = Math.max(1e-9, Math.hypot(next.x - node.x, next.y - node.y));
  const progress = state?.staging_distance ? -state.staging_distance / mapLength : Math.min(1,Math.max(0,state?.edge_progress || 0));
  return {x:node.worldX + (next.worldX-node.worldX)*progress,
          y:node.worldY + (next.worldY-node.worldY)*progress};
}
