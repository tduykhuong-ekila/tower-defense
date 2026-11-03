from rest_framework import serializers

from apps.matches.defaults import (
    DEFAULT_MAX_TEAMS,
    DEFAULT_PHASE_DURATIONS,
    DEFAULT_SCORING_WEIGHTS,
    DEFAULT_SPECIAL_ACTION_COSTS,
    DEFAULT_SPECIAL_ACTIONS,
    MAX_TEAMS,
    MIN_MEMBERS_PER_TEAM,
    MIN_TEAMS_TO_START,
    get_default_configuration,
)
from apps.matches.models import Match
from apps.teams.models import MemberRole, Team, TeamMember


class PhaseDurationsSerializer(serializers.Serializer):
    PREPARATION = serializers.IntegerField(min_value=10, default=180)
    BUILD_AND_SCOUT = serializers.IntegerField(min_value=10, default=420)
    WAR = serializers.IntegerField(min_value=10, default=720)
    FINAL_ASSAULT = serializers.IntegerField(min_value=10, default=300)
    RESULTS = serializers.IntegerField(min_value=10, default=180)


class ScoringWeightsSerializer(serializers.Serializer):
    enemy_base_destroyed = serializers.IntegerField(min_value=0, default=100)
    damage_dealt_per_100 = serializers.IntegerField(min_value=0, default=10)
    remaining_hp_per_100 = serializers.IntegerField(min_value=0, default=5)
    correct_answer = serializers.IntegerField(min_value=0, default=3)
    surviving_tower = serializers.IntegerField(min_value=0, default=5)
    remaining_coins_per_10 = serializers.IntegerField(min_value=0, default=1)


class SpecialActionsEnabledSerializer(serializers.Serializer):
    scout = serializers.BooleanField(default=True)
    emp = serializers.BooleanField(default=True)
    repair = serializers.BooleanField(default=True)
    upgrade = serializers.BooleanField(default=True)


class SpecialActionCostsSerializer(serializers.Serializer):
    scout = serializers.IntegerField(min_value=0, default=10)
    emp = serializers.IntegerField(min_value=0, default=30)
    repair = serializers.IntegerField(min_value=0, default=20)
    upgrade = serializers.IntegerField(min_value=0, default=25)


class MatchConfigurationSerializer(serializers.Serializer):
    # Missing mode denotes an existing legacy configuration, never migrate mid-match.
    gameplay_mode = serializers.ChoiceField(choices=["LEGACY", "CONTINUOUS"], default="LEGACY")
    # Missing version belongs to a stored room; new-room defaults explicitly use 7.
    tower_placement_version = serializers.ChoiceField(choices=[0, 1], default=0)
    arena_layout_version = serializers.ChoiceField(choices=[3, 4, 5, 6, 7], default=3)
    total_rounds = serializers.ChoiceField(choices=[2, 3], default=3)
    preparation_duration_seconds = serializers.IntegerField(min_value=1, max_value=900, default=180)
    first_preparation_duration_seconds = serializers.IntegerField(min_value=1, max_value=900, default=120)
    battle_duration_seconds = serializers.IntegerField(min_value=1, max_value=1800, default=300)
    battle_tick_interval_ms = serializers.IntegerField(min_value=100, max_value=1000, default=200)
    attack_cooldown_seconds = serializers.FloatField(min_value=0.2, max_value=60, default=2)
    movement_baseline_round_seconds = serializers.IntegerField(min_value=1, max_value=200, default=30)
    troop_formation_gap = serializers.FloatField(min_value=0, max_value=100, default=2)
    troop_target_priority = serializers.ListField(
        child=serializers.ChoiceField(choices=["UNIT", "TOWER"]),
        min_length=2, max_length=2, default=["TOWER", "UNIT"],
    )

    def validate_troop_target_priority(self, value):
        if set(value) != {"UNIT", "TOWER"}:
            raise serializers.ValidationError("Include UNIT and TOWER exactly once.")
        return value
    # Teams & Players
    min_teams = serializers.IntegerField(
        min_value=MIN_TEAMS_TO_START, max_value=MAX_TEAMS, default=MIN_TEAMS_TO_START
    )
    max_teams = serializers.IntegerField(
        min_value=MIN_TEAMS_TO_START, max_value=MAX_TEAMS, default=DEFAULT_MAX_TEAMS
    )
    # Retained in stored configurations for compatibility; membership minimum is fixed.
    min_players_per_team = serializers.IntegerField(read_only=True)
    max_players_per_team = serializers.IntegerField(min_value=1, max_value=10, default=4)

    # Base Stats
    initial_base_hp = serializers.IntegerField(min_value=10, max_value=5000, default=500)
    initial_coins = serializers.IntegerField(min_value=0, max_value=10000, default=100)

    # Match & Phase Timers
    match_duration_seconds = serializers.IntegerField(min_value=1, max_value=10800, default=1800)
    phase_durations = PhaseDurationsSerializer(default=DEFAULT_PHASE_DURATIONS)
    round_duration_seconds = serializers.IntegerField(min_value=10, max_value=200, default=30)
    reward_grace_period_seconds = serializers.IntegerField(min_value=0, max_value=60, default=15)

    # Economy & Questions
    max_questions_per_team = serializers.IntegerField(min_value=1, max_value=50, default=8)
    correct_answer_coin_reward = serializers.ChoiceField(choices=[20, 30], default=30)
    base_income_per_round = serializers.IntegerField(min_value=0, max_value=200, default=10)

    # Unit & Tower Limits
    max_towers_per_team = serializers.SerializerMethodField()  # Retired compatibility field.

    max_active_units_per_team = serializers.IntegerField(min_value=1, max_value=30, default=5)
    max_deployed_units_per_action = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    max_tower_placements_per_action = serializers.IntegerField(min_value=1, max_value=5, default=1)

    # Scoring & Victory
    scoring_weights = ScoringWeightsSerializer(default=DEFAULT_SCORING_WEIGHTS)

    # Policies
    fallback_policy = serializers.ChoiceField(
        choices=["IDLE", "RETARGET_NEAREST"],
        default="RETARGET_NEAREST",
    )
    spectator_visibility = serializers.ChoiceField(
        choices=["FULL", "FOG_OF_WAR"],
        default="FULL",
    )
    special_actions_enabled = SpecialActionsEnabledSerializer(default=DEFAULT_SPECIAL_ACTIONS)
    special_action_costs = SpecialActionCostsSerializer(default=DEFAULT_SPECIAL_ACTION_COSTS)
    allow_late_join = serializers.BooleanField(default=False)

    def get_max_towers_per_team(self, obj):
        return None

    def validate(self, data):
        data["max_towers_per_team"] = None
        grid = data.get("tower_placement_version", 0) == 1
        grid_arena = data.get("arena_layout_version", 3) >= 6
        if grid != grid_arena:
            raise serializers.ValidationError({"tower_placement_version": "Grid placement requires arena layout 6 or later; legacy placement requires layouts 3–5."})
        min_teams = data.get("min_teams", MIN_TEAMS_TO_START)
        max_teams = data.get("max_teams", DEFAULT_MAX_TEAMS)
        if min_teams > max_teams:
            raise serializers.ValidationError({"min_teams": "min_teams cannot exceed max_teams."})

        data["min_players_per_team"] = MIN_MEMBERS_PER_TEAM
        min_players = MIN_MEMBERS_PER_TEAM
        max_players = data.get("max_players_per_team", 4)
        if min_players > max_players:
            raise serializers.ValidationError(
                {"min_players_per_team": "min_players_per_team cannot exceed max_players_per_team."}
            )

        phase_durations = data.get("phase_durations", {})
        total_phase = sum(phase_durations.values())
        match_duration = data.get("match_duration_seconds", 1800)
        # Check if match_duration matches the sum of phases (allow reasonable leeway or auto-align)
        if total_phase > 0 and total_phase != match_duration:
            # Sync match_duration_seconds to the exact sum of phase durations
            data["match_duration_seconds"] = total_phase

        if data.get("gameplay_mode") == "CONTINUOUS":
            data["match_duration_seconds"] = (
                data["first_preparation_duration_seconds"]
                + (data["total_rounds"] - 1) * data["preparation_duration_seconds"]
                + data["total_rounds"] * data["battle_duration_seconds"]
            )
        return data


class TeamMemberSummarySerializer(serializers.ModelSerializer):
    team_id = serializers.UUIDField(source="team.id", read_only=True, allow_null=True)

    class Meta:
        model = TeamMember
        fields = [
            "id",
            "team_id",
            "display_name",
            "role",
            "is_ready",
            "joined_at",
        ]
        read_only_fields = fields


class TeamDetailSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Match detail/list is public, including lookup by room code. During play
        # private balances come from authenticated team state / host telemetry.
        if instance.match.status != "LOBBY":
            data.pop("coins", None)
        if data.get("gameplay_mode") == "CONTINUOUS":
            data["match_duration_seconds"] = (
                data["first_preparation_duration_seconds"]
                + (data["total_rounds"] - 1) * data["preparation_duration_seconds"]
                + data["total_rounds"] * data["battle_duration_seconds"]
            )
        return data

    members = TeamMemberSummarySerializer(many=True, read_only=True)
    member_count = serializers.IntegerField(source="members.count", read_only=True)

    class Meta:
        model = Team
        fields = [
            "id",
            "match_id",
            "name",
            "initial_base_hp",
            "base_hp",
            "base_shield",
            "coins",
            "score",
            "status",
            "is_ready",
            "members",
            "member_count",
            "created_at",
        ]
        read_only_fields = fields


class MatchDetailSerializer(serializers.ModelSerializer):
    question_bank_id = serializers.UUIDField(read_only=True, allow_null=True)
    configuration = serializers.SerializerMethodField()
    teams = TeamDetailSerializer(many=True, read_only=True)
    unassigned_members = serializers.SerializerMethodField()
    all_members = TeamMemberSummarySerializer(source="members", many=True, read_only=True)

    class Meta:
        model = Match
        fields = [
            "id",
            "room_code",
            "name",
            "status",
            "phase",
            "configuration",
            "question_bank_id",
            "is_locked",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
            "teams",
            "unassigned_members",
            "all_members",
        ]
        read_only_fields = fields

    def get_configuration(self, obj):
        from apps.matches.action_policy import ActionPolicy
        return {**obj.configuration, "min_players_per_team": MIN_MEMBERS_PER_TEAM,
                "action_rules": ActionPolicy.rules(obj.configuration)}

    def get_unassigned_members(self, obj):
        members = [m for m in obj.members.all() if m.team_id is None]
        return TeamMemberSummarySerializer(members, many=True).data


class CreateMatchRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, default="Battle Arena")
    configuration = serializers.DictField(required=False, default=dict)
    question_bank_id = serializers.UUIDField(required=False)
    question_bank_token = serializers.CharField(min_length=32, max_length=128, required=False, write_only=True)
    creation_token = serializers.CharField(min_length=32, max_length=128, required=False, write_only=True)

    def validate(self, data):
        if bool(data.get("question_bank_id")) != bool(data.get("question_bank_token")):
            raise serializers.ValidationError("question_bank_id và question_bank_token phải đi cùng nhau.")
        return data

    def validate_configuration(self, value):
        base_config = get_default_configuration()
        if value:
            # Deep merge incoming config into defaults
            def deep_update(target, source):
                for k, v in source.items():
                    if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                        deep_update(target[k], v)
                    else:
                        target[k] = v

            deep_update(base_config, value)

        config_serializer = MatchConfigurationSerializer(data=base_config)
        config_serializer.is_valid(raise_exception=True)
        return config_serializer.validated_data


class JoinMatchRequestSerializer(serializers.Serializer):
    room_code = serializers.CharField(max_length=8, required=False)
    display_name = serializers.CharField(min_length=1, max_length=50)
    team_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    new_team_name = serializers.CharField(min_length=1, max_length=50, required=False)
    role = serializers.ChoiceField(
        choices=[MemberRole.MENTOR, MemberRole.MENTEE, MemberRole.SPECTATOR],
        default=MemberRole.MENTEE,
    )

    def validate(self, data):
        if data.get("new_team_name"):
            if data.get("team_id"):
                raise serializers.ValidationError("Chọn đội có sẵn hoặc tạo đội mới.")
            if data["role"] == MemberRole.SPECTATOR:
                raise serializers.ValidationError("Chỉ mentee và mentor có thể tạo đội.")
        return data


class CreateTeamRequestSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=50)


class UpdateTeamRequestSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=50)


class AssignMemberRequestSerializer(serializers.Serializer):
    team_id = serializers.UUIDField(required=False, allow_null=True)
    role = serializers.ChoiceField(
        choices=MemberRole.choices,
        required=False,
    )
