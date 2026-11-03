"""
Map Topology and Fixed-Lane Graph for Combat Engine (§9, §19, D1, D5).
Supports every integer from 2 to 20 teams in one connected arena.
Provides deterministic routing, distance calculation, tower ranges, and JSON export.
"""

import heapq
from collections import deque
from typing import Dict, List, Optional, Set, Tuple


class MapNode:
    def __init__(
        self,
        node_id: str,
        node_type: str,  # 'base', 'spawn', 'lane', 'center', 'tower_slot', 'barrier'
        team_index: Optional[int] = None,  # 1-indexed team number (1 to N), None if neutral
        is_passable: bool = True,
        x: float = 0.0,
        y: float = 0.0,
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.team_index = team_index
        self.is_passable = is_passable
        self.x = x
        self.y = y

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "team_index": self.team_index,
            "is_passable": self.is_passable,
            "x": self.x,
            "y": self.y,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MapNode":
        return cls(
            node_id=data["node_id"],
            node_type=data["node_type"],
            team_index=data.get("team_index"),
            is_passable=data.get("is_passable", True),
            x=data.get("x", 0.0),
            y=data.get("y", 0.0),
        )


class GameMap:
    """
    Authoritative Server-Side Map Graph.
    Generates a deterministic symmetric radial star-ring topology (§9.1).
    """

    def __init__(self, num_teams: int = 4, layout_version: int = 4):
        if num_teams < 2 or num_teams > 20:
            raise ValueError(f"num_teams must be between 2 and 20, got {num_teams}")
        self.num_teams = num_teams
        if layout_version not in (3, 4, 5, 6, 7):
            raise ValueError(f"Unsupported arena layout version: {layout_version}")
        self.layout_version = layout_version
        # Pixel clearance expands; graph hops, IDs and gameplay are unchanged.
        self.layout_scale = max(1.0, num_teams / 5.0)
        if layout_version >= 5:
            self.layout_scale = max(1.4, self.layout_scale)
        if layout_version >= 6:
            self.layout_scale = max(3.6, num_teams / 2.5)
        if layout_version >= 7 and num_teams == 3:
            # Three radial teams need a little more room for balanced roads and build corridors.
            self.layout_scale = 4.2
        if layout_version >= 7 and num_teams in (6, 7):
            # Equal screen-space sectors need enough room for each build area.
            self.layout_scale = 4.8
        self._distances_by_source: Dict[str, Dict[str, int]] = {}
        self.nodes: Dict[str, MapNode] = {}
        self.adjacency: Dict[str, Set[str]] = {}
        # Pre-calculated shortest paths and distances
        self._distance_matrix: Dict[Tuple[str, str], int] = {}
        self._predefined_paths: Dict[Tuple[str, str], List[str]] = {}
        self._tower_coverage: Dict[str, Set[str]] = {}

        self._build_topology()
        if self.layout_version >= 7 and self.num_teams in (5, 6, 7):
            self._balance_projected_roads()
        if self.layout_version >= 7 and self.num_teams == 3:
            # Balance the screen-space roads and nearby building area across three teams.
            branch_scales = {2: 0.90, 3: 1.12}
            for node in self.nodes.values():
                branch_scale = branch_scales.get(node.team_index)
                if branch_scale and node.node_type in ("base", "lane", "spawn", "center"):
                    node.x *= branch_scale
                    node.y *= branch_scale
        if 4 <= self.layout_version < 6:
            self._move_slots_closer_to_roads()
        if self.layout_version == 5:
            from apps.combat.build_geometry import BuildGeometry
            BuildGeometry(self).place()
        self._precompute_graph()

    def _balance_projected_roads(self):
        """Lay out equal road sectors in the projected battlefield plane.

        A regular polygon in map coordinates becomes a flattened polygon after
        projection, stretching some teams' sand roads much more than others.
        Build the polygon in artwork coordinates and invert the projection so
        rendering, road clearance, rally areas and navigation share its geometry.
        The vertical projection scale keeps the roads inside the existing arena.
        """
        import math

        from apps.combat.navigation import unproject

        rotation = -math.pi * 3 / 4
        for node in self.nodes.values():
            radius = math.hypot(node.x, node.y) * 0.86
            angle = math.atan2(node.y, node.x) + rotation
            node.x, node.y = unproject((radius * math.cos(angle), radius * math.sin(angle)))

    def _move_slots_closer_to_roads(self):
        """Pull each foundation 15% toward its nearest painted road/bridge axis.

        Work in Phaser's projected pixels so clearance protects actual artwork.
        Back off the pull where another road, base or foundation limits it.
        Coverage edges and every passable node remain unchanged.
        """
        import math

        from apps.combat.navigation import project, unproject

        segments = []
        for u, neighbors in sorted(self.adjacency.items()):
            for v in sorted(neighbors):
                first, last = self.nodes[u], self.nodes[v]
                if u >= v or not first.is_passable or not last.is_passable:
                    continue
                a, b = project((first.x, first.y)), project((last.x, last.y))
                control = ((a[0]+b[0])/2+(b[1]-a[1])*.08,
                           (a[1]+b[1])/2-(b[0]-a[0])*.08)
                points = [((1-t)**2*a[0]+2*(1-t)*t*control[0]+t*t*b[0],
                           (1-t)**2*a[1]+2*(1-t)*t*control[1]+t*t*b[1])
                          for t in (step/16 for step in range(17))]
                segments.extend([(a, b), *zip(points, points[1:])])

        def closest(point, a, b):
            dx, dy = b[0]-a[0], b[1]-a[1]
            t = max(0, min(1, ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy or 1)))
            return a[0]+t*dx, a[1]+t*dy

        slots = [n for n in self.nodes.values() if n.node_type == "tower_slot"]
        obstacles = [(project((n.x, n.y)), 70 if n.node_type == "base" else 40)
                     for n in self.nodes.values() if n.node_type in ("base", "barrier")]
        for slot in slots:
            point = project((slot.x, slot.y))
            nearest = min((closest(point, a, b) for a, b in segments), key=lambda p: math.dist(point, p))
            # Deterministic local tuning, never a uniform X/Y translation.
            for pull in (.15, .125, .10, .075, .05, .025, .01):
                candidate = tuple(p+(q-p)*pull for p, q in zip(point, nearest))
                if any(math.dist(candidate, p) < radius for p, radius in obstacles):
                    continue
                if any(math.dist(candidate, project((other.x, other.y))) < 54 for other in slots if other is not slot):
                    continue
                if any(math.dist(candidate, closest(candidate, a, b)) < 57.1 for a, b in segments):
                    continue
                slot.x, slot.y = unproject(candidate)
                break

    def _add_node(self, node: MapNode):
        self.nodes[node.node_id] = node
        if node.node_id not in self.adjacency:
            self.adjacency[node.node_id] = set()

    def _add_edge(self, u: str, v: str, bidirectional: bool = True):
        if u not in self.adjacency:
            self.adjacency[u] = set()
        if v not in self.adjacency:
            self.adjacency[v] = set()
        self.adjacency[u].add(v)
        if bidirectional:
            self.adjacency[v].add(u)

    def _build_topology(self):
        """
        Constructs the fixed-lane radial topology for N teams.
        For each team i (1..N):
          - Base: node_base_t{i}
          - Attack position / Lane 1: node_lane_t{i}_1 (adjacent to base)
          - Lane 2: node_lane_t{i}_2
          - Lane 3: node_lane_t{i}_3
          - Spawn: node_spawn_t{i} (connects into node_lane_t{i}_2)
          - Center Ring: node_center_ring_t{i} (connects to lane_3, central hub, and adjacent ring nodes)
          - Tower slots:
              slot1: near lane 1 & 2
              slot2: near lane 2 & 3
              slot3: near lane 3 & center ring
        """
        import math

        # 1. Central Hub
        center_hub_id = "node_center"
        self._add_node(MapNode(center_hub_id, "center", team_index=None, is_passable=True, x=0.0, y=0.0))

        # 2. Build each team's branch
        for i in range(1, self.num_teams + 1):
            angle = 2.0 * math.pi * (i - 1) / self.num_teams

            base_id = f"node_base_t{i}"
            lane1_id = f"node_lane_t{i}_1"
            lane2_id = f"node_lane_t{i}_2"
            lane3_id = f"node_lane_t{i}_3"
            spawn_id = f"node_spawn_t{i}"
            ring_id = f"node_center_ring_t{i}"

            # Radii for layout coordinates
            r_base = 400.0 * self.layout_scale
            r_lane1 = 320.0 * self.layout_scale
            r_lane2 = 240.0 * self.layout_scale
            r_lane3 = 160.0 * self.layout_scale
            r_ring = 80.0 * self.layout_scale

            # Base node
            self._add_node(MapNode(base_id, "base", team_index=i, is_passable=True,
                                   x=r_base * math.cos(angle), y=r_base * math.sin(angle)))
            # Lane 1 (Attack position for base)
            self._add_node(MapNode(lane1_id, "lane", team_index=i, is_passable=True,
                                   x=r_lane1 * math.cos(angle), y=r_lane1 * math.sin(angle)))
            # Lane 2
            self._add_node(MapNode(lane2_id, "lane", team_index=i, is_passable=True,
                                   x=r_lane2 * math.cos(angle), y=r_lane2 * math.sin(angle)))
            # Lane 3
            self._add_node(MapNode(lane3_id, "lane", team_index=i, is_passable=True,
                                   x=r_lane3 * math.cos(angle), y=r_lane3 * math.sin(angle)))
            # Spawn (offset slightly to the side of lane 2)
            spawn_angle = angle + min(0.15, math.pi / self.num_teams * 0.5)
            self._add_node(MapNode(spawn_id, "spawn", team_index=i, is_passable=True,
                                   x=r_lane2 * math.cos(spawn_angle), y=r_lane2 * math.sin(spawn_angle)))
            # Center ring node
            self._add_node(MapNode(ring_id, "center", team_index=i, is_passable=True,
                                   x=r_ring * math.cos(angle), y=r_ring * math.sin(angle)))

            # Lane connections
            self._add_edge(base_id, lane1_id)
            self._add_edge(lane1_id, lane2_id)
            self._add_edge(lane2_id, lane3_id)
            self._add_edge(lane3_id, ring_id)
            self._add_edge(spawn_id, lane2_id)  # Units spawn and merge into lane 2 towards center
            self._add_edge(ring_id, center_hub_id)

            # Three equal roadside bands, with a foundation on each flank.
            # IDs 1–3 retain their original coverage links; 4–6 mirror those links.
            # Per-band lateral clearance avoids bases, painted roads, bridges and rally gates.
            # The growing arena keeps even the inner pair inside its team's sector.
            lanes = [(lane1_id, lane2_id), (lane2_id, lane3_id), (lane3_id, ring_id)]
            for side_index, side in enumerate((-1, 1) if self.layout_version < 6 else ()):
                for band, radius in enumerate((350.0, 270.0, 190.0)):
                    slot_id = f"node_tower_t{i}_slot{side_index * 3 + band + 1}"
                    radial = radius * self.layout_scale
                    lateral = side * (108.0, 108.0, 88.0)[band]
                    self._add_node(MapNode(slot_id, "tower_slot", team_index=i, is_passable=False,
                        x=radial * math.cos(angle) - lateral * math.sin(angle),
                        y=radial * math.sin(angle) + lateral * math.cos(angle)))
                    for lane in lanes[band]:
                        self._add_edge(slot_id, lane)

            # Barrier node between sectors (impassable node §9.1)
            barrier_angle = angle + (math.pi / self.num_teams)
            barrier_id = f"node_barrier_t{i}"
            self._add_node(MapNode(barrier_id, "barrier", team_index=None, is_passable=False,
                                   x=250.0 * self.layout_scale * math.cos(barrier_angle), y=250.0 * self.layout_scale * math.sin(barrier_angle)))
            # Connect barrier to adjacent ring nodes to be part of the topological graph, but marked impassable
            self._add_edge(barrier_id, ring_id)

        # 3. Interconnect central ring nodes cyclically
        for i in range(1, self.num_teams + 1):
            next_i = (i % self.num_teams) + 1
            ring_a = f"node_center_ring_t{i}"
            ring_b = f"node_center_ring_t{next_i}"
            self._add_edge(ring_a, ring_b)

    def _precompute_graph(self):
        """
        Precomputes all-pairs shortest paths on the passable subgraph using physical edge lengths.
        Movement paths only use passable nodes.
        Range calculations also compute distances including tower slots.
        """
        all_node_ids = sorted(self.nodes.keys())

        # Physical distance, rather than hop count, chooses movement routes.
        # Range and targeting retain their separate hop-distance matrix below.
        for start_node in all_node_ids:
            if not self.nodes[start_node].is_passable:
                continue
            queue = [(0.0, start_node)]
            costs = {start_node: 0.0}
            predecessors = {start_node: None}
            while queue:
                cost, current = heapq.heappop(queue)
                if cost > costs[current] + 1e-9:
                    continue
                a = self.nodes[current]
                for neighbor in sorted(self.adjacency.get(current, ())):
                    b = self.nodes[neighbor]
                    if not b.is_passable:
                        continue
                    candidate = cost + ((b.x - a.x) ** 2 + (b.y - a.y) ** 2) ** 0.5
                    if candidate < costs.get(neighbor, float("inf")) - 1e-9:
                        costs[neighbor] = candidate
                        predecessors[neighbor] = current
                        heapq.heappush(queue, (candidate, neighbor))
            for destination in costs:
                route, node = [], destination
                while node is not None:
                    route.append(node)
                    node = predecessors[node]
                self._predefined_paths[(start_node, destination)] = list(reversed(route))

        # 2. General distance matrix for range & targeting (includes towers and all nodes)
        for start_node in all_node_ids:
            queue = deque([start_node])
            visited = {start_node: 0}

            while queue:
                curr = queue.popleft()
                curr_dist = visited[curr]

                for neighbor in sorted(self.adjacency.get(curr, [])):
                    if neighbor not in visited:
                        visited[neighbor] = curr_dist + 1
                        queue.append(neighbor)

            self._distances_by_source[start_node] = visited
            for dest, dist in visited.items():
                self._distance_matrix[(start_node, dest)] = dist

    def distance(self, node_a: str, node_b: str) -> int:
        """Hop distance between two nodes along the graph."""
        if node_a == node_b:
            return 0
        return self._distance_matrix.get((node_a, node_b), 999999)

    def nodes_in_range(self, source_node: str, range_val: float) -> Set[str]:
        """All nodes within range_val hops from source_node."""
        return {dst for dst, dist in self._distances_by_source.get(source_node, {}).items()
                if dist <= range_val}

    def path(self, from_node: str, to_node: str) -> List[str]:
        """
        Returns pre-determined deterministic path from from_node to to_node.
        Excludes impassable nodes for movement paths.
        """
        # Siege routes append a firing edge; callers must not mutate the shared
        # shortest-path cache (including the one-node path back to a base).
        return list(self._predefined_paths.get((from_node, to_node), ()))

    def shortest_physical_path(self, from_node: str, to_node: str) -> List[str]:
        """Return the passable route with the least map-coordinate travel distance."""
        return self.path(from_node, to_node)

    def get_base_node(self, team_index: int) -> str:
        return f"node_base_t{team_index}"

    def get_spawn_node(self, team_index: int) -> str:
        return f"node_spawn_t{team_index}"

    def attack_position(self, base_node: str) -> str:
        """
        Returns the attack position node right in front of the base (§10.4).
        For node_base_t{i}, the attack position is node_lane_t{i}_1.
        """
        if base_node.startswith("node_base_t"):
            team_str = base_node.replace("node_base_t", "")
            return f"node_lane_t{team_str}_1"
        return base_node

    def get_path_to_base(self, from_node: str, target_team_index: int) -> List[str]:
        """
        Deterministic march path for a combat unit targeting an enemy base.
        The path terminates at the attack position (node_lane_t{target}_1) where the unit attacks the base.
        """
        atk_pos = f"node_lane_t{target_team_index}_1"
        return self.path(from_node, atk_pos)

    def validate_map(self) -> Tuple[bool, List[str]]:
        """
        Validates graph integrity:
        - All bases reachable from all spawn points.
        - No orphan nodes (every node has at least 1 edge).
        - Impassable nodes cannot be traversed by movement path.
        """
        errors = []

        # Check orphan nodes
        for node_id, neighbors in self.adjacency.items():
            if not neighbors:
                errors.append(f"Orphan node found: {node_id}")

        # Check reachability between every spawn and every other team's base
        for s_idx in range(1, self.num_teams + 1):
            spawn = self.get_spawn_node(s_idx)
            for t_idx in range(1, self.num_teams + 1):
                if s_idx == t_idx:
                    continue
                atk_pos = f"node_lane_t{t_idx}_1"
                p = self.path(spawn, atk_pos)
                if not p or p[0] != spawn or p[-1] != atk_pos:
                    errors.append(f"Base {t_idx} attack position unreachable from spawn {s_idx}")

        errors.extend(self.validate_build_geometry())
        return (len(errors) == 0, errors)

    def validate_build_geometry(self):
        """Check actual projected foundations against every road, base and obstacle.

        Projection matches Phaser. Construction platforms clear 57px from painted roads and bridge axes,
        70px from bases; foundation centers clear 54px each other.
        Decorative river water is covered by raised stone platforms on the client.
        """
        if self.layout_version >= 6:
            return []  # Grid masks validate terrain; new maps have no fixed foundations.
        import math
        def project(node):
            angle = -3 * math.pi / 4
            return ((node.x * math.cos(angle) - node.y * math.sin(angle)) * 1.5,
                    (node.x * math.sin(angle) + node.y * math.cos(angle)) * .86)
        def segment_distance(p, a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            t = max(0, min(1, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / (dx*dx+dy*dy or 1)))
            return math.dist(p, (a[0]+t*dx, a[1]+t*dy))
        errors = []
        slots = [n for n in self.nodes.values() if n.node_type == "tower_slot"]
        if self.layout_version == 5:
            from apps.combat.build_geometry import BuildGeometry
            errors.extend(BuildGeometry(self).validate())
        roads = [(self.nodes[u], self.nodes[v]) for u, neighbors in self.adjacency.items()
                 for v in neighbors if u < v and self.nodes[u].is_passable and self.nodes[v].is_passable]
        # Sand roads, bridge axes and troop paths use identical straight edges.
        road_paths = []
        for first, last in roads:
            a, b = project(first), project(last)
            bounds = (min(a[0], b[0])-57, max(a[0], b[0])+57,
                      min(a[1], b[1])-57, max(a[1], b[1])+57)
            road_paths.append((bounds, [(a, b)]))
        width = max(1600, math.ceil(1200 * self.layout_scale + 400))
        height = max(1040, math.ceil(688 * self.layout_scale + 400))
        for i in range(1, self.num_teams + 1):
            if sum(n.team_index == i for n in slots) != 6:
                errors.append(f"Team {i} must have six build slots")
        for index, slot in enumerate(slots):
            point = project(slot)
            wx, wy = width / 2 + point[0], height / 2 + 60 + point[1]
            if not (34 < wx < width-34 and 34 < wy < height-34):
                errors.append(f"Slot outside map: {slot.node_id}")
            if any(segment_distance(point, a, b) < 57
                   for bounds, segments in road_paths
                   if bounds[0] <= point[0] <= bounds[1] and bounds[2] <= point[1] <= bounds[3]
                   for a, b in segments):
                errors.append(f"Slot intersects road/bridge: {slot.node_id}")
            for node in self.nodes.values():
                clearance = 70 if node.node_type == "base" else 40 if node.node_type == "barrier" else 0
                if clearance and math.dist(point, project(node)) < clearance:
                    errors.append(f"Slot intersects {node.node_type}: {slot.node_id}")
            if any(math.dist(point, project(other)) < 54 for other in slots[index+1:]):
                errors.append(f"Overlapping foundations: {slot.node_id}")
        return errors

    def to_dict(self, team_ids=None) -> dict:
        """Serializes map graph to JSON-friendly dictionary."""
        from apps.combat.navigation import staging_bounds, staging_slots
        edges = []
        visited_edges = set()
        for u, neighbors in self.adjacency.items():
            for v in neighbors:
                edge_pair = tuple(sorted([u, v]))
                if edge_pair not in visited_edges:
                    visited_edges.add(edge_pair)
                    edges.append({"from": edge_pair[0], "to": edge_pair[1]})

        import math

        width = max(1600, math.ceil(1200 * self.layout_scale + 400))
        height = max(1040, math.ceil(688 * self.layout_scale + 400))
        return {
            "num_teams": self.num_teams,
            "team_ids": team_ids or [],
            "arena": {
                "version": self.layout_version, "key": f"radial-v{self.layout_version}-{'grid' if self.layout_version >= 6 else 'six-slots'}-{self.num_teams}",
                "profile": "SMALL" if self.num_teams <= 5 else "MEDIUM" if self.num_teams <= 12 else "LARGE",
                "width": width, "height": height,
                "centerX": width / 2, "centerY": height / 2,
                "layout_scale": self.layout_scale,
                "regions": min(5, math.ceil(self.num_teams / 4)),
            },
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "staging_areas": [{"spawn_node_id": self.get_spawn_node(i),
                               "bounds": [{"x": x, "y": y} for x, y in staging_bounds(self, self.get_spawn_node(i))],
                               "parking_points": [{"x": x, "y": y} for x, y in staging_slots(self, self.get_spawn_node(i))]}
                              for i in range(1, self.num_teams + 1)],
            "rally_areas": [{
                "team_index": i,
                "team_id": team_ids[i - 1] if team_ids and i <= len(team_ids) else None,
                "spawn_node_id": self.get_spawn_node(i),
                "entry_node_id": self.get_spawn_node(i),
                "spawn_point": {"x": self.nodes[self.get_spawn_node(i)].x,
                                "y": self.nodes[self.get_spawn_node(i)].y},
                "radius": max(math.dist(point, (self.nodes[self.get_spawn_node(i)].x,
                                                 self.nodes[self.get_spawn_node(i)].y))
                              for point in staging_slots(self, self.get_spawn_node(i))),
            } for i in range(1, self.num_teams + 1)],
            "edges": sorted(edges, key=lambda e: (e["from"], e["to"])),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameMap":
        num_teams = data.get("num_teams", 4)
        game_map = cls(num_teams=num_teams, layout_version=data.get("arena", {}).get("version", 3))
        return game_map


# Cache maps by team count
_MAP_CACHE: Dict[Tuple[int, int], GameMap] = {}


def get_game_map(num_teams: int = 4, layout_version: int = 4) -> GameMap:
    key = (num_teams, layout_version)
    if key not in _MAP_CACHE:
        gm = GameMap(num_teams=num_teams, layout_version=layout_version)
        valid, errors = gm.validate_map()
        if not valid:
            raise RuntimeError(f"Map validation failed for {num_teams} teams: {errors}")
        _MAP_CACHE[key] = gm
    return _MAP_CACHE[key]
