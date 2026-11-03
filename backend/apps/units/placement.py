"""Server-authored square grid in projected artwork coordinates, not camera pixels.

Static cell masks are cached by immutable arena geometry. Match-wide row locking
in ConstructionService serializes occupancy checks, debits and combat destruction.
"""

import math
from functools import lru_cache

from django.core.exceptions import ValidationError

from apps.combat.build_geometry import (
    BASE_BOUNDS,
    TOWER_BOUNDS,
    bounds,
    movement_segments,
    overlaps,
    road_segments,
    segment_intersects_rect,
    segment_rect_distance,
)
from apps.combat.formation import FORMATION_MINIMUM_GAP, SPRITE_BODIES, position_at
from apps.combat.mobile import crowd_offset
from apps.combat.navigation import project, staging_slots, unproject

SHIELD_PLACEMENT = {"width": 660, "height": 510, "offsetY": -17}


def shield_position_allowed(graph, team_index, position):
    base = graph.nodes[graph.get_base_node(team_index)]
    bx, by = project((base.x, base.y))
    x, y = project(position)
    return ((x - bx) / (SHIELD_PLACEMENT["width"] / 2)) ** 2 + ((y - by - SHIELD_PLACEMENT["offsetY"]) / (SHIELD_PLACEMENT["height"] / 2)) ** 2 <= 1 + 1e-9


CELL_SIZE = 32
# The 94px tower texture at origin (.5, .89) fits inside [-48,-84,48,12].
# Cosmetic banners, rank sidecars, shadows and input bounds are not solid bodies.
# Saved grid_placement dimensions/anchors remain authoritative for old occupants.
FOOTPRINTS = {
    code: {"widthCells": 3, "heightCells": 3, "anchorOffsetY": 36}
    for code in ("mg_tower", "cannon_tower", "shield_generator")
}


# Movement bodies and crowd offsets are already in projected artwork pixels.
# MOVEMENT_ENVELOPE keeps the complete live-unit and unusual-offset guard.
# Grid placement uses a narrower envelope at the user's requested limit; troop
# coordinates and physical movement continue to use their full formation.
ROADSIDE_SAFETY_MARGIN = 0.0
STAGING_SAFETY_MARGIN = FORMATION_MINIMUM_GAP * 0.86
LEGACY_PAINTED_ROAD_WIDTHS = (57, 49, 43)
PROTECTED_PAINTED_ROAD_WIDTHS = (92, 80, 70)
PAINTED_ROAD_HALF_WIDTH = PROTECTED_PAINTED_ROAD_WIDTHS[0] / 2
STAGING_BODY_ENVELOPE = (
    min(-w / 2 for w, h, y in SPRITE_BODIES.values()),
    min(y - h / 2 for w, h, y in SPRITE_BODIES.values()),
    max(w / 2 for w, h, y in SPRITE_BODIES.values()),
    max(y + h / 2 for w, h, y in SPRITE_BODIES.values()),
)


def movement_envelope():
    offsets = [project((offset["x"], offset["y"]))
               for offset in (crowd_offset(i) for i in range(1, 16))]
    return (
        min(x - w / 2 for x, _ in offsets for w, h, y in SPRITE_BODIES.values()),
        min(oy + y - h / 2 for _, oy in offsets for w, h, y in SPRITE_BODIES.values()),
        max(x + w / 2 for x, _ in offsets for w, h, y in SPRITE_BODIES.values()),
        max(oy + y + h / 2 for _, oy in offsets for w, h, y in SPRITE_BODIES.values()),
    )


MOVEMENT_ENVELOPE = movement_envelope()
PLACEMENT_MOVEMENT_ENVELOPE = (
    -PAINTED_ROAD_HALF_WIDTH,
    MOVEMENT_ENVELOPE[1],
    PAINTED_ROAD_HALF_WIDTH,
    MOVEMENT_ENVELOPE[3],
)


def _river_x(y, width, height, offset_x):
    return width * (1030 / 1600) - y * (width / height) * 0.2535 + math.sin(y / 145) * 85 + offset_x


def _five_team_territory_free_river(graph, width, height):
    """Follow the eastern scenery outside the complete building-territory ellipse.

    Reserve the full 420*scale territory radius, rather than only rally grounds
    or roads. The extra 160 map units protect both 48px banks and tower artwork.
    """
    padding = round(max(240, height * 0.14))
    top, bottom = -padding - 1024, height + round(max(640, height * 0.42)) + 1024
    center_y = height / 2 + 60
    radius = 420 * graph.layout_scale + 160
    path = []
    for y in range(top, bottom + 1, 8):
        # This smooth envelope stays outside the projected territory ellipse,
        # including its top/bottom tips, without abrupt right-angle bends.
        local_y = (y - center_y) / 0.86
        x = width / 2 + 1.5 * radius / math.sqrt(1 + (local_y / radius) ** 4)
        path.append([x, y])
    path.insert(0, [path[0][0], top - 32])
    path.append([path[-1][0], path[-1][1] + 32])
    return path


def _river_path_away_from_parallel_roads(graph, width, height, offset_x):
    """Keep a broad buildable corridor between the three-team river and roads."""
    step = 32
    vertical_padding = round(max(240, height * 0.14))
    ys = list(range(-vertical_padding, height + vertical_padding + 1, step))
    offsets = tuple(range(-1024, 1025, step))
    offset_index = {value: index for index, value in enumerate(offsets)}
    delta_offsets = (-64, -32, 0, 32, 64)
    delta_index = {value: index for index, value in enumerate(delta_offsets)}
    road_axes = []
    for first, last in movement_segments(graph):
        a = (first[0] + width / 2, first[1] + height / 2 + 60)
        b = (last[0] + width / 2, last[1] + height / 2 + 60)
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length:
            road_axes.append((a, b, dx / length, dy / length))

    def baseline(y):
        return _river_x(y, width, height, offset_x)

    bases = [baseline(y) for y in ys]

    def parallel_penalty(x0, y0, x1, y1):
        river_dx, river_dy = x1 - x0, y1 - y0
        river_length = math.hypot(river_dx, river_dy) or 1
        river_dx, river_dy = river_dx / river_length, river_dy / river_length
        midpoint = ((x0 + x1) / 2, (y0 + y1) / 2)
        worst = 0.0
        for a, b, road_dx, road_dy in road_axes:
            segment_dx, segment_dy = b[0] - a[0], b[1] - a[1]
            t = max(0, min(1, ((midpoint[0] - a[0]) * segment_dx +
                               (midpoint[1] - a[1]) * segment_dy) /
                           (segment_dx * segment_dx + segment_dy * segment_dy or 1)))
            distance = math.hypot(midpoint[0] - a[0] - t * segment_dx,
                                  midpoint[1] - a[1] - t * segment_dy)
            if distance >= 720:
                continue
            alignment = abs(river_dx * road_dx + river_dy * road_dy)
            if alignment <= 0.70:
                continue
            proximity = (720 - distance) / 720
            penalty = 9000 * ((alignment - 0.70) / 0.30) * proximity * proximity
            worst = max(worst, penalty)
        return worst

    zero_index = offset_index[0]
    zero_delta = delta_index[0]
    costs = {(zero_index, zero_delta): 0.0}
    parents = [None]
    edge_cost_cache = {}
    for row in range(1, len(ys)):
        next_costs = {}
        row_parents = {}
        y0, y1 = ys[row - 1], ys[row]
        for current_offset in offsets:
            if row == len(ys) - 1 and current_offset != 0:
                continue
            current_index = offset_index[current_offset]
            deviation_cost = current_offset * current_offset * 0.0015
            for delta in delta_offsets:
                previous_offset = current_offset - delta
                previous_index = offset_index.get(previous_offset)
                if previous_index is None:
                    continue
                state = (current_index, delta_index[delta])
                best_cost, best_parent = math.inf, None
                edge_key = (row, previous_index, current_index)
                if edge_key not in edge_cost_cache:
                    x0, x1 = bases[row - 1] + previous_offset, bases[row] + current_offset
                    edge_cost_cache[edge_key] = parallel_penalty(x0, y0, x1, y1)
                edge_cost = edge_cost_cache[edge_key]
                for previous_delta in delta_offsets:
                    parent = (previous_index, delta_index[previous_delta])
                    previous_cost = costs.get(parent)
                    if previous_cost is None:
                        continue
                    bend_cost = (delta - previous_delta) ** 2 * 0.08
                    slope_cost = delta * delta * 0.08
                    candidate = previous_cost + edge_cost + deviation_cost + bend_cost + slope_cost
                    if candidate < best_cost:
                        best_cost, best_parent = candidate, parent
                if best_parent is not None:
                    next_costs[state] = best_cost
                    row_parents[state] = best_parent
        costs = next_costs
        parents.append(row_parents)

    end_states = [(state, cost) for state, cost in costs.items() if state[0] == zero_index]
    if not end_states:
        return [[baseline(y), y] for y in ys]
    state = min(end_states, key=lambda item: (item[1], item[0][1]))[0]
    selected_offsets = [0] * len(ys)
    selected_offsets[-1] = offsets[state[0]]
    for row in range(len(ys) - 1, 0, -1):
        state = parents[row][state]
        selected_offsets[row - 1] = offsets[state[0]]
    return [[bases[row] + selected_offsets[row], y] for row, y in enumerate(ys)]


def movement_cell_blocked(rect, a, b, envelope=MOVEMENT_ENVELOPE, safety_margin=None):
    # Minkowski expansion: segment intersects a cell iff a moving body can touch it.
    left, top, right, bottom = envelope
    gap = ROADSIDE_SAFETY_MARGIN if safety_margin is None else safety_margin
    expanded = (rect[0] - right - gap, rect[1] - bottom - gap,
                rect[2] - left + gap, rect[3] - top + gap)
    return segment_intersects_rect(a, b, expanded)


def painted_cell_blocked(rect, a, b, curve_tolerance=0, half_width=PAINTED_ROAD_HALF_WIDTH):
    return segment_rect_distance(a, b, rect) <= (
        half_width + curve_tolerance + ROADSIDE_SAFETY_MARGIN
    )


def road_cell_blocked(rect, a, b, curve_tolerance=0, half_width=PAINTED_ROAD_HALF_WIDTH):
    """Combined straight-lane rule; curves use painted_cell_blocked only."""
    return movement_cell_blocked(rect, a, b) or painted_cell_blocked(
        rect, a, b, curve_tolerance, half_width
    )


def enabled(match):
    return match.configuration.get("tower_placement_version", 0) == 1


class PlacementGrid:
    def __init__(self, graph):
        self.graph = graph
        self.width = max(1600, math.ceil(1200 * graph.layout_scale + 400))
        self.height = max(1040, math.ceil(688 * graph.layout_scale + 400))
        self.cols, self.rows = self.width // CELL_SIZE, self.height // CELL_SIZE
        self.offset = (self.width / 2, self.height / 2 + 60)
        self.roads = road_segments(graph)
        self.movement_roads = list(movement_segments(graph))
        self.painted_road_widths = (
            PROTECTED_PAINTED_ROAD_WIDTHS
            if graph.layout_version >= 6 else LEGACY_PAINTED_ROAD_WIDTHS
        )
        self.painted_half_width = self.painted_road_widths[0] / 2
        # Keep the three-team river out of the green team's outer roadside build corridor.
        self.river_offset_x = -250 if graph.layout_version >= 7 and graph.num_teams == 3 else 0
        self.geometry_revision = 17 if graph.layout_version >= 7 and graph.num_teams == 5 else 11
        self.equal_sectors = graph.layout_version >= 7 and graph.num_teams in (6, 7)
        if self.equal_sectors:
            self.geometry_revision = 19 if graph.num_teams == 6 else 18
        self.placement_movement_envelope = (
            PLACEMENT_MOVEMENT_ENVELOPE
            if graph.layout_version >= 6 else MOVEMENT_ENVELOPE
        )
        self.road_cells = set()
        # Natural shoulders vary up to 8% wider than their nominal stroke.
        self.curve_tolerance = self.painted_half_width * .08
        for a, b, movement in [(*segment, True) for segment in self.movement_roads] + [
            (*segment, False) for segment in self.roads
        ]:
            clearance = (max(abs(v) for v in self.placement_movement_envelope) if movement else
                         self.painted_half_width + self.curve_tolerance) + ROADSIDE_SAFETY_MARGIN
            for row in range(
                max(0, math.floor((min(a[1], b[1]) - clearance + self.offset[1]) / CELL_SIZE) - 1),
                min(self.rows, math.ceil((max(a[1], b[1]) + clearance + self.offset[1]) / CELL_SIZE) + 1),
            ):
                for col in range(
                    max(0, math.floor((min(a[0], b[0]) - clearance + self.offset[0]) / CELL_SIZE) - 1),
                    min(self.cols, math.ceil((max(a[0], b[0]) + clearance + self.offset[0]) / CELL_SIZE) + 1),
                ):
                    if (row, col) in self.road_cells:
                        continue
                    left, top = col * CELL_SIZE - self.offset[0], row * CELL_SIZE - self.offset[1]
                    rect = (left, top, left + CELL_SIZE, top + CELL_SIZE)
                    blocked = movement_cell_blocked(rect, a, b, self.placement_movement_envelope) if movement else painted_cell_blocked(
                        rect, a, b, self.curve_tolerance, self.painted_half_width
                    )
                    if blocked:
                        self.road_cells.add((row, col))
        self.river_path = (
            _river_path_away_from_parallel_roads(graph, self.width, self.height, self.river_offset_x)
            if graph.layout_version >= 7 and graph.num_teams == 3 else None
        )
        if graph.layout_version >= 7 and graph.num_teams in (5, 6, 7):
            self.river_path = _five_team_territory_free_river(graph, self.width, self.height)
        self.river_cells = set()
        if self.river_path:
            for a, b in zip(self.river_path, self.river_path[1:]):
                for row in range(
                    max(0, math.floor((min(a[1], b[1]) - 48) / CELL_SIZE)),
                    min(self.rows, math.ceil((max(a[1], b[1]) + 48) / CELL_SIZE)),
                ):
                    for col in range(
                        max(0, math.floor((min(a[0], b[0]) - 48) / CELL_SIZE)),
                        min(self.cols, math.ceil((max(a[0], b[0]) + 48) / CELL_SIZE)),
                    ):
                        rect = (col * CELL_SIZE, row * CELL_SIZE,
                                (col + 1) * CELL_SIZE, (row + 1) * CELL_SIZE)
                        if segment_rect_distance(a, b, rect) <= 49:
                            self.river_cells.add((row, col))
        self.bases = [
            bounds(project((n.x, n.y)), BASE_BOUNDS)
            for n in graph.nodes.values()
            if n.node_type == "base"
        ]
        self.barriers = [
            project((n.x, n.y)) for n in graph.nodes.values() if n.node_type == "barrier"
        ]
        self.rally_cells = set()
        # The previous single bounding rectangle per team reserved large empty
        # pockets near its road. Sweep the maximum body over every possible
        # vehicle parking-slot approach instead. Six endpoint offsets cover the
        # entire 5×3 crowd patch because their 54×50 boxes overlap between them.
        for i in range(1, graph.num_teams + 1):
            spawn_id = graph.get_spawn_node(i)
            spawn = graph.nodes[spawn_id]
            center = project((spawn.x, spawn.y))
            for slot in staging_slots(graph, spawn_id):
                start = project(slot)
                for dx in (-44, 0, 44):
                    for dy in (-16, 16):
                        end = (center[0] + dx, center[1] + dy)
                        clearance = max(abs(v) for v in STAGING_BODY_ENVELOPE) + STAGING_SAFETY_MARGIN
                        for row in range(
                            max(0, math.floor((min(start[1], end[1]) - clearance + self.offset[1]) / CELL_SIZE) - 1),
                            min(self.rows, math.ceil((max(start[1], end[1]) + clearance + self.offset[1]) / CELL_SIZE) + 1),
                        ):
                            for col in range(
                                max(0, math.floor((min(start[0], end[0]) - clearance + self.offset[0]) / CELL_SIZE) - 1),
                                min(self.cols, math.ceil((max(start[0], end[0]) + clearance + self.offset[0]) / CELL_SIZE) + 1),
                            ):
                                if (row, col) in self.rally_cells:
                                    continue
                                left = col * CELL_SIZE - self.offset[0]
                                top = row * CELL_SIZE - self.offset[1]
                                rect = (left, top, left + CELL_SIZE, top + CELL_SIZE)
                                if movement_cell_blocked(rect, start, end, STAGING_BODY_ENVELOPE, STAGING_SAFETY_MARGIN):
                                    self.rally_cells.add((row, col))
        self.owners, self.reasons = [], []
        for row in range(self.rows):
            for col in range(self.cols):
                owner, reason = self.classify(row, col)
                self.owners.append(owner)
                self.reasons.append(reason)
        if self.equal_sectors:
            self._balance_building_areas()
        self.runs = []
        for row in range(self.rows):
            col = 0
            while col < self.cols:
                owner, start = self.owners[row * self.cols + col], col
                while col < self.cols and self.owners[row * self.cols + col] == owner:
                    col += 1
                if owner:
                    self.runs.append([row, start, col, owner])

    def _balance_building_areas(self):
        """Equalize usable land, tower footprints and shield footprints.

        A square grid, upright bases and parking clearances cannot have exact radial
        rotation symmetry. Trim only otherwise safe cells at the outer edges;
        never reopen a road, water, base or rally exclusion to meet a quota.
        """
        offsets = [dr * self.cols + dc for dr in range(3) for dc in range(3)]
        areas = []
        for team in range(1, self.graph.num_teams + 1):
            cells = {i for i, owner in enumerate(self.owners) if owner == team}
            anchors = {
                row * self.cols + col
                for row in range(self.rows - 2) for col in range(self.cols - 2)
                if all(row * self.cols + col + offset in cells for offset in offsets)
            }
            shields = set()
            for anchor in anchors:
                row, col = divmod(anchor, self.cols)
                point = self.anchor(row, col, FOOTPRINTS["shield_generator"])
                local = unproject((point[0] - self.offset[0], point[1] - self.offset[1]))
                if shield_position_allowed(self.graph, team, local):
                    shields.add(anchor)
            support = {cell: set() for cell in cells}
            for anchor in anchors:
                for offset in offsets:
                    support[anchor + offset].add(anchor)
            areas.append((cells, anchors, shields, support))

        def rank(cell):
            row, col = divmod(cell, self.cols)
            x = (col + .5) * CELL_SIZE - self.offset[0]
            y = (row + .5) * CELL_SIZE - self.offset[1]
            return x * x + y * y, cell

        def remove(cell, area):
            cells, anchors, shields, support = area
            cells.remove(cell)
            self.owners[cell], self.reasons[cell] = 0, "TERRITORY"
            for anchor in tuple(support[cell]):
                anchors.remove(anchor)
                shields.discard(anchor)
                for offset in offsets:
                    support[anchor + offset].remove(anchor)

        # Preserve the same shield opportunities while balancing ordinary towers.
        shield_target = min(len(area[2]) for area in areas)
        for area in areas:
            cells, anchors, shields, support = area
            while len(shields) > shield_target:
                candidates = [cell for cell in cells
                              if 0 < len(support[cell] & shields) <= len(shields) - shield_target]
                if not candidates:
                    raise RuntimeError(f"Cannot balance {self.graph.num_teams}-team shield footprints")
                remove(max(candidates, key=rank), area)

        tower_target = min(len(area[1]) for area in areas)
        for area in areas:
            cells, anchors, shields, support = area
            while len(anchors) > tower_target:
                candidates = [cell for cell in cells
                              if not support[cell] & shields
                              and 0 < len(support[cell]) <= len(anchors) - tower_target]
                if not candidates:
                    raise RuntimeError(f"Cannot balance {self.graph.num_teams}-team tower footprints")
                remove(max(candidates, key=rank), area)

        cell_target = min(len(area[0]) for area in areas)
        for area in areas:
            cells, anchors, shields, support = area
            # These fringe cells support no complete footprint, so trimming them
            # leaves both construction quotas unchanged.
            candidates = sorted((cell for cell in cells if not support[cell]), key=rank, reverse=True)
            excess = len(cells) - cell_target
            if len(candidates) < excess:
                raise RuntimeError(f"Cannot balance {self.graph.num_teams}-team building land")
            for cell in candidates[:excess]:
                remove(cell, area)

    def classify(self, row, col):
        left, top = col * CELL_SIZE - self.offset[0], row * CELL_SIZE - self.offset[1]
        rect = (left, top, left + CELL_SIZE, top + CELL_SIZE)
        corners = [
            (left, top),
            (left + CELL_SIZE, top),
            (left, top + CELL_SIZE),
            (left + CELL_SIZE, top + CELL_SIZE),
        ]
        owners = []
        for point in corners:
            if self.equal_sectors:
                # Match the circular roads in artwork space, rather than dividing
                # an ellipse into sectors of unequal visible area.
                angle = -math.pi * 3 / 4
                x = (point[0] * math.cos(angle) + point[1] * math.sin(angle)) / .86
                y = (-point[0] * math.sin(angle) + point[1] * math.cos(angle)) / .86
            else:
                x, y = unproject(point)
            radius = math.hypot(x, y)
            if not 140 * self.graph.layout_scale <= radius <= 420 * self.graph.layout_scale:
                return 0, "TERRITORY"
            angle = math.atan2(y, x) % (2 * math.pi)
            owners.append(
                int(math.floor(angle * self.graph.num_teams / (2 * math.pi) + 0.5))
                % self.graph.num_teams
                + 1
            )
        if len(set(owners)) != 1:
            return 0, "TERRITORY"
        if any(overlaps(rect, base) for base in self.bases):
            return 0, "BASE"
        if (row, col) in self.rally_cells:
            return 0, "RALLY"
        point = left + CELL_SIZE / 2, top + CELL_SIZE / 2
        # Existing straight troop routes and the painted quadratic road/bridge.
        # Exact rectangle tests keep the complete troop envelope and painted curve clear.
        if (row, col) in self.road_cells:
            return 0, "ROAD"
        if any(math.dist(point, b) <= 40 + CELL_SIZE / math.sqrt(2) for b in self.barriers):
            return 0, "TERRAIN"
        if (row, col) in self.river_cells:
            return 0, "WATER"
        if not self.river_path:
            # Legacy maps use riverX. The derivative bound covers all y within the cell.
            x, y = point[0] + self.offset[0], point[1] + self.offset[1]
            river_x = (
                self.width * (1030 / 1600)
                - y * (self.width / self.height) * 0.2535
                + math.sin(y / 145) * 85
                + self.river_offset_x
            )
            slope = self.width / self.height * 0.2535 + 85 / 145
            if abs(x - river_x) <= 48 + CELL_SIZE / 2 * (1 + slope):
                return 0, "WATER"
        return owners[0], ""

    def metadata(self):
        metadata = {
            "version": 1,
            "shieldPlacement": SHIELD_PLACEMENT,
            "geometryRevision": self.geometry_revision,
            "riverOffsetX": self.river_offset_x,
            "cellSize": CELL_SIZE,
            "roadClearance": {
                "movementEnvelope": list(MOVEMENT_ENVELOPE),
                "placementEnvelope": list(self.placement_movement_envelope),
                "bodies": {code: list(body) for code, body in SPRITE_BODIES.items()},
                "paintedHalfWidth": self.painted_half_width,
                "paintedWidths": list(self.painted_road_widths),
                "safetyMargin": ROADSIDE_SAFETY_MARGIN,
                "stagingSafetyMargin": STAGING_SAFETY_MARGIN,
                "curveTolerance": self.curve_tolerance,
                "movementFollowsPaintedCurves": False,
            },
            "originX": 0,
            "originY": 0,
            "cols": self.cols,
            "rows": self.rows,
            "footprints": FOOTPRINTS,
            "buildableRuns": self.runs,
        }
        if self.river_path:
            metadata["riverPath"] = self.river_path
        return metadata

    def rectangle(self, row, col, footprint):
        return (
            col * CELL_SIZE,
            row * CELL_SIZE,
            (col + footprint["widthCells"]) * CELL_SIZE,
            (row + footprint["heightCells"]) * CELL_SIZE,
        )

    def anchor(self, row, col, footprint):
        rect = self.rectangle(row, col, footprint)
        return ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2 + footprint["anchorOffsetY"])

    def validate(self, row, col, code, team_index, entities):
        def reject(reason):
            raise ValidationError(f"Không thể xây tại ô này: {reason}.", code=f"PLACEMENT_{reason}")

        if type(row) is not int or type(col) is not int:
            reject("COORDINATES")
        footprint = FOOTPRINTS.get(code)
        if not footprint:
            reject("FOOTPRINT")
        if (
            row < 0
            or col < 0
            or row + footprint["heightCells"] > self.rows
            or col + footprint["widthCells"] > self.cols
        ):
            reject("BOUNDS")
        for r in range(row, row + footprint["heightCells"]):
            for c in range(col, col + footprint["widthCells"]):
                i = r * self.cols + c
                if self.owners[i] != team_index:
                    reject(self.reasons[i] or "TERRITORY")
        rect = self.rectangle(row, col, footprint)
        projected = tuple(v - self.offset[i % 2] for i, v in enumerate(rect))
        checked_envelopes = set()
        for entity in entities:
            state = entity.simulation_state or {}
            if getattr(entity, "entity_kind", "TOWER") == "UNIT":
                # Saved vehicles can carry a parking offset along their route.
                # Preserve those positions and protect their entire possible
                # forward/reverse route, in addition to the standard corridor.
                offset = state.get("crowd_offset")
                if offset:
                    x, y = project((offset["x"], offset["y"]))
                    w, h, oy = SPRITE_BODIES.get(entity.unit_type.code, (54, 50, -27))
                    envelope = (x-w/2, y+oy-h/2, x+w/2, y+oy+h/2)
                    contained = all(a <= b+1e-8 for a, b in zip(MOVEMENT_ENVELOPE[:2], envelope[:2])) and all(
                        a >= b-1e-8 for a, b in zip(MOVEMENT_ENVELOPE[2:], envelope[2:]))
                    if not contained and envelope not in checked_envelopes:
                        checked_envelopes.add(envelope)
                        if any(movement_cell_blocked(projected, a, b, envelope) for a, b in self.movement_roads):
                            reject("ROAD")
                if state.get("movement_zone") == "STAGING" and state.get("world_position"):
                    node = self.graph.nodes.get(entity.current_node_id)
                    if node:
                        point = state["world_position"]
                        start = project((point["x"], point["y"]))
                        shift = state.get("crowd_offset") or {"x": 0, "y": 0}
                        target = position_at(
                            {"current_node_id": entity.current_node_id, "simulation_state": state},
                            max(0, state.get("staging_entry_distance", 0)), self.graph,
                        )
                        end = project((target[0] + shift["x"], target[1] + shift["y"]))
                        w, h, oy = SPRITE_BODIES.get(entity.unit_type.code, (54, 50, -27))
                        body = (-w/2, oy-h/2, w/2, oy+h/2)
                        if movement_cell_blocked(projected, start, end, body, STAGING_SAFETY_MARGIN):
                            reject("RALLY")
                continue
            grid = state.get("grid_placement")
            if grid:
                other = self.rectangle(grid["row"], grid["col"], grid)
            else:
                p = state.get("world_position")
                node = self.graph.nodes.get(entity.current_node_id)
                if not p and not node:
                    continue
                position = project((p["x"], p["y"]) if p else (node.x, node.y))
                other = bounds(
                    (position[0] + self.offset[0], position[1] + self.offset[1]), TOWER_BOUNDS
                )
            if overlaps(rect, other, margin=0):
                reject("OCCUPIED")
        anchor = self.anchor(row, col, footprint)
        x, y = unproject((anchor[0] - self.offset[0], anchor[1] - self.offset[1]))
        if code == "shield_generator" and not shield_position_allowed(self.graph, team_index, (x, y)):
            raise ValidationError("Máy tạo khiên phải nằm trong vòng khiên quanh căn cứ.", code="PLACEMENT_SHIELD_RANGE")
        # A stable passable node remains a coarse combat spatial bucket. Actual
        # targeting/rendering uses world_position for grid towers, not this node.
        node = min(
            (n for n in self.graph.nodes.values() if n.is_passable),
            key=lambda n: ((n.x - x) ** 2 + (n.y - y) ** 2, n.node_id),
        )
        return node.node_id, {
            "world_position": {"x": x, "y": y},
            "grid_placement": {"row": row, "col": col, **footprint},
        }


@lru_cache(maxsize=64)
def placement_grid(graph):
    return PlacementGrid(graph)


def map_for_match(match, team_ids):
    from apps.combat.map import get_game_map

    graph = get_game_map(max(2, len(team_ids)), match.configuration.get("arena_layout_version", 3))
    data = graph.to_dict(team_ids)
    # Offer free grid construction on saved arenas too, using their original
    # geometry. Existing foundations/entities/routes keep their exact positions.
    data["placement_grid"] = placement_grid(graph).metadata()
    data["arena"]["key"] += f"-grid-v1-r{data['placement_grid']['geometryRevision']}"
    return data
