from typing import List

from apps.teams.models import Team


class MapDefinition:
    """
    Minimal map topology & node definition for server-side validation (§9, §46).
    Supports 2–20 teams with the shared authoritative arena.
    Full graph routing & Phaser visual synchronization will expand in Phase 4 & 5.
    """

    LEGACY_FOUNDATIONS_PER_TEAM = 6  # Saved node IDs only; never a construction cap.

    @classmethod
    def get_team_index(cls, team: Team) -> int:
        """
        Determines deterministic team index (0 to N-1) within the match based on creation order.
        """
        ordered_ids = list(
            Team.objects.filter(match_id=team.match_id)
            .order_by("created_at", "id")
            .values_list("id", flat=True)
        )
        try:
            return ordered_ids.index(team.id)
        except ValueError:
            return 0

    @classmethod
    def get_team_base_node(cls, team: Team) -> str:
        idx = cls.get_team_index(team)
        return f"node_base_t{idx + 1}"

    @classmethod
    def get_team_spawn_node(cls, team: Team) -> str:
        idx = cls.get_team_index(team)
        return f"node_spawn_t{idx + 1}"

    @classmethod
    def get_valid_tower_slots(cls, team: Team) -> List[str]:
        """
        Returns legacy tower slots; grid matches have no fixed construction slots.
        """
        if team.match.configuration.get("tower_placement_version", 0) == 1:
            return []
        idx = cls.get_team_index(team)
        prefix = f"node_tower_t{idx + 1}"
        return [f"{prefix}_slot{slot_i}" for slot_i in range(1, cls.LEGACY_FOUNDATIONS_PER_TEAM + 1)]

    @classmethod
    def is_valid_tower_slot(cls, team: Team, node_id: str) -> bool:
        """
        Checks whether node_id belongs to the team's permitted tower placement slots.
        """
        if not node_id:
            return False
        valid_slots = cls.get_valid_tower_slots(team)
        return node_id in valid_slots

    @classmethod
    def is_target_reachable(cls, source_team: Team, target_team: Team) -> bool:
        """
        Verifies lane reachability between two teams (§9.4).
        In the connected star-ring / radial map topology, all distinct active teams
        are connected through the central arena lane nodes.
        """
        if source_team.id == target_team.id:
            return False
        if source_team.match_id != target_team.match_id:
            return False
        from apps.combat.map import get_game_map

        ordered = list(Team.objects.filter(match_id=source_team.match_id)
                       .order_by("created_at", "id").values_list("id", flat=True))
        graph = get_game_map(len(ordered), source_team.match.configuration.get("arena_layout_version", 3))
        return bool(graph.get_path_to_base(
            graph.get_spawn_node(ordered.index(source_team.id) + 1),
            ordered.index(target_team.id) + 1,
        ))
