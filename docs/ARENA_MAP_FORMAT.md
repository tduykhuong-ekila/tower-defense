# Arena map contract, version 2

`GET /api/v1/matches/{id}/map/` and `MATCH_STATE_SNAPSHOT.payload.map_data` return the same graph and stable team order. The count is the actual number of teams, including eliminated teams, rather than configured maximum capacity.

```json
{
  "num_teams": 20,
  "team_ids": ["team-uuid-1", "...", "team-uuid-20"],
  "arena": {
    "version": 3, "key": "radial-v3-six-slots-20", "profile": "LARGE",
    "width": 5200, "height": 3152,
    "centerX": 2600, "centerY": 1576,
    "layout_scale": 4, "regions": 5
  },
  "nodes": [
    {"node_id": "node_base_t1", "node_type": "base", "team_index": 1,
     "is_passable": true, "x": 1600, "y": 0}
  ],
  "edges": [{"from": "node_base_t1", "to": "node_lane_t1_1"}]
}
```

The example abbreviates arrays. Each team has `node_base_tN`, `node_spawn_tN`, three `node_lane_tN_K`, `node_center_ring_tN`, three `node_tower_tN_slotK`, and one sector barrier. `node_center` is shared. Tower slots and barriers are impassable for movement; their edges are retained for range calculations. Edges are undirected and serialized in stable sorted order. Empty/single-team lobby previews keep the existing two-branch placeholder until a match can start.

Projection rotates by −3π/4, applies horizontal scale 1.5 and vertical scale 0.86, translates to arena center, and adds 60 pixels vertically. Server coordinates and node IDs remain untouched. Older map payloads without `arena` use the original 1600×1040 fallback. Base, spawn and road coordinates are unchanged. Version 3 adds six validated tower foundations per team and relocates existing slot IDs; see ARTILLERY_TOWER_SLOTS_BATCH_DEPLOYMENT.md.

`regions` describes how many balanced groups of sectors the arena can be divided into (up to five). It does not create separate worlds, ownership permissions or additional gameplay mechanics. Each sector's existing `team_index` determines ownership.

Clients can BFS the passable edges for a route preview. The server revalidates target reachability and owns actual movement. No client-derived path, damage, coin balance or minimap position changes a unit's state.
