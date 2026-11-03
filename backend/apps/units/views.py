from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.matches.action_policy import ActionPolicy, validation_payload
from apps.matches.models import Match
from apps.matches.permissions import get_authenticated_member, is_host_of_match
from apps.questions.views import resolve_team_for_request
from apps.teams.models import MemberRole, Team
from apps.units.models import (
    ActionStatus,
    ActionType,
    EntityCategory,
    EntityStatus,
    GameAction,
    GameEntity,
    UnitType,
)
from apps.units.serializers import (
    BuildTowerRequestSerializer,
    DeployUnitRequestSerializer,
    EmpRequestSerializer,
    GameActionSerializer,
    GameEntitySerializer,
    RepairBaseRequestSerializer,
    ScoutRequestSerializer,
    SellTowerRequestSerializer,
    UnitTypeAdminSerializer,
    UnitTypeSerializer,
    UpgradeTowerRequestSerializer,
)
from apps.units.services import ConstructionService, UnitService


class MatchUnitListView(APIView):
    """
    GET /api/v1/matches/{match_id}/units/
    List all configured combat units & defensive structures, including unlock status for caller team.
    """

    def get(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        units = UnitType.objects.filter(is_active=True).order_by("cost", "name")
        return Response(
            UnitTypeSerializer(units, many=True, context={"team": team, "match": match}).data
        )


class MatchDeployUnitActionView(APIView):
    """
    POST /api/v1/matches/{match_id}/actions/deploy/
    Deploy a batch of combat units towards a specified enemy base (§9.4, §8.5, §20).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        if member and member.role == MemberRole.SPECTATOR:
            return Response(
                {"error": "Khán giả (Spectator) không có quyền triển khai quân."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = DeployUnitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            action, entities = UnitService.deploy_units(
                match=match,
                team=team,
                unit_type_code_or_id=data["unit_type_code_or_id"],
                target_team_id=data["target_team_id"],
                actor=member,
                idempotency_key=data.get("idempotency_key"),
                quantity=data["quantity"],
                spawn_node_id=data.get("spawn_node_id"),
            )
        except ValidationError as e:
            return Response(validation_payload(e), status=status.HTTP_400_BAD_REQUEST)

        team.refresh_from_db(fields=["coins"])
        return Response(
            {
                "action": GameActionSerializer(action).data,
                "entity": GameEntitySerializer(entities[0]).data if entities else None,
                "entities": GameEntitySerializer(entities, many=True).data,
                "quantity": action.payload.get("quantity", 1),
                "team_coins": team.coins,
            },
            status=status.HTTP_200_OK,
        )


class MatchBuildTowerActionView(APIView):
    """
    POST /api/v1/matches/{match_id}/actions/build/
    Build a defensive tower on a valid, unoccupied slot in team territory (§9.3).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        if member and member.role == MemberRole.SPECTATOR:
            return Response(
                {"error": "Khán giả (Spectator) không có quyền xây dựng."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = BuildTowerRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            action, entity = ConstructionService.build_tower(
                match=match,
                team=team,
                unit_type_code_or_id=data["unit_type_code_or_id"],
                node_id=data["node_id"],
                grid_row=data.get("grid_row"), grid_col=data.get("grid_col"),
                actor=member,
                idempotency_key=data.get("idempotency_key"),
            )
        except ValidationError as e:
            return Response(validation_payload(e), status=status.HTTP_400_BAD_REQUEST)

        team.refresh_from_db(fields=["coins"])
        return Response(
            {
                "action": GameActionSerializer(action).data,
                "entity": GameEntitySerializer(entity).data if entity else None,
                "team_coins": team.coins,
            },
            status=status.HTTP_200_OK,
        )


class MatchSellTowerActionView(APIView):
    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if member and member.role == MemberRole.SPECTATOR:
            return Response({"error": "Khán giả không có quyền bán tháp."}, status=status.HTTP_403_FORBIDDEN)
        if err:
            return err
        serializer = SellTowerRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            action, entity = ConstructionService.sell_tower(
                match, team, actor=member, **serializer.validated_data)
        except ValidationError as error:
            return Response(validation_payload(error), status=status.HTTP_400_BAD_REQUEST)
        team.refresh_from_db(fields=["coins"])
        return Response({"action": GameActionSerializer(action).data,
                         "entity": GameEntitySerializer(entity).data,
                         "refund": action.payload["refund"], "team_coins": team.coins})


class MatchUpgradeTowerActionView(APIView):
    """
    POST /api/v1/matches/{match_id}/actions/upgrade/
    Compatibility route: upgrade the selected tower type for the entire team (levels 1–3).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        if member and member.role == MemberRole.SPECTATOR:
            return Response(
                {"error": "Khán giả (Spectator) không có quyền nâng cấp."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = UpgradeTowerRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            action, entity = ConstructionService.upgrade_tower(
                match=match,
                team=team,
                entity_id=data["entity_id"],
                actor=member,
                idempotency_key=data.get("idempotency_key"),
            )
        except ValidationError as e:
            return Response(validation_payload(e), status=status.HTTP_400_BAD_REQUEST)

        team.refresh_from_db(fields=["coins"])
        return Response(
            {
                "action": GameActionSerializer(action).data,
                "entity": GameEntitySerializer(entity).data if entity else None,
                "team_coins": team.coins,
            },
            status=status.HTTP_200_OK,
        )


class MatchRepairBaseActionView(APIView):
    """
    POST /api/v1/matches/{match_id}/actions/repair/
    Repair team base (+50 HP, max 1 repair per round) (§8.4).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        if member and member.role == MemberRole.SPECTATOR:
            return Response(
                {"error": "Khán giả (Spectator) không có quyền sửa chữa căn cứ."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RepairBaseRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            action = ConstructionService.repair_base(
                match=match,
                team=team,
                actor=member,
                idempotency_key=data.get("idempotency_key"),
            )
        except ValidationError as e:
            return Response(validation_payload(e), status=status.HTTP_400_BAD_REQUEST)

        team.refresh_from_db(fields=["coins", "base_hp"])
        return Response(
            {
                "action": GameActionSerializer(action).data,
                "team_base_hp": team.base_hp,
                "team_coins": team.coins,
            },
            status=status.HTTP_200_OK,
        )


class MatchScoutActionView(APIView):
    """
    POST /api/v1/matches/{match_id}/actions/scout/
    Scout an opponent's defenses (§8.4).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        if member and member.role == MemberRole.SPECTATOR:
            return Response(
                {"error": "Khán giả không có quyền thực hiện trinh sát."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ScoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            action, scout_data = ConstructionService.scout(
                match=match,
                team=team,
                target_team_id=data["target_team_id"],
                actor=member,
                idempotency_key=data.get("idempotency_key"),
            )
        except ValidationError as e:
            return Response(validation_payload(e), status=status.HTTP_400_BAD_REQUEST)

        team.refresh_from_db(fields=["coins"])
        return Response(
            {
                "action": GameActionSerializer(action).data,
                "scout_data": scout_data,
                "team_coins": team.coins,
            },
            status=status.HTTP_200_OK,
        )


class MatchEmpActionView(APIView):
    """
    POST /api/v1/matches/{match_id}/actions/emp/
    EMP disables one enemy defensive tower for 1 round (§8.4).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        if member and member.role == MemberRole.SPECTATOR:
            return Response(
                {"error": "Khán giả không có quyền phóng xung điện EMP."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = EmpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            action, entity = ConstructionService.emp(
                match=match,
                team=team,
                target_entity_id=data["target_entity_id"],
                actor=member,
                idempotency_key=data.get("idempotency_key"),
            )
        except ValidationError as e:
            return Response(validation_payload(e), status=status.HTTP_400_BAD_REQUEST)

        team.refresh_from_db(fields=["coins"])
        return Response(
            {
                "action": GameActionSerializer(action).data,
                "entity": GameEntitySerializer(entity).data if entity else None,
                "team_coins": team.coins,
            },
            status=status.HTTP_200_OK,
        )


class MatchTeamStateView(APIView):
    """
    GET /api/v1/matches/{match_id}/teams/{team_id}/state/
    Team authoritative state snapshot (coins, unlocks, entities, capacity limits).
    Restricted strictly to members of the team and match host (§19.7, §2.5).
    """

    def get(self, request, match_id, team_id):
        match = get_object_or_404(Match, pk=match_id)
        team = get_object_or_404(Team, pk=team_id, match=match)

        is_host = is_host_of_match(request, match)
        member = get_authenticated_member(request, match)

        # Team member or host authorization check
        if not is_host:
            if not member or str(member.team_id) != str(team.id):
                return Response(
                    {"error": "Chỉ thành viên của đội hoặc Quản trị phòng mới có quyền xem trạng thái đội."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        units = UnitType.objects.filter(is_active=True).order_by("cost", "name")
        active_entities = GameEntity.objects.filter(
            team=team,
            status__in=[EntityStatus.ACTIVE, EntityStatus.QUEUED, EntityStatus.DISABLED],
        ).order_by("-created_at")

        active_units_count = active_entities.filter(entity_kind=EntityCategory.UNIT).count()
        infantry_count = active_entities.filter(entity_kind=EntityCategory.UNIT, unit_type__code="infantry").count()
        active_towers_count = active_entities.filter(entity_kind=EntityCategory.TOWER).count()

        max_units = match.configuration.get("max_active_units_per_team", 5)

        recent_repairs_count = GameAction.objects.filter(
            team=team,
            action_type=ActionType.REPAIR_BASE,
            status=ActionStatus.ACCEPTED,
        ).count()

        enemy_teams = [
            {
                "id": str(t.id),
                "name": t.name,
                "status": t.status,
                "base_hp": t.base_hp,
                "base_shield": t.base_shield,
            }
            for t in match.teams.exclude(pk=team.pk)
        ]

        state_data = {
            "round_number": match.configuration.get("current_round", 1),
            "action_availability": {
                action: ActionPolicy.context(match, team, action, member).to_dict()
                for action in ("DEPLOY_UNIT", "BUILD_TOWER", "ANSWER_QUESTION", "CLAIM_REWARD", "REPAIR_BASE", "SCOUT", "EMP", "UPGRADE_TOWER", "UPGRADE_TEAM_TYPE", "SELL_TOWER")
            },
            "team": {
                "id": str(team.id),
                "name": team.name,
                "base_hp": team.base_hp,
                "initial_base_hp": team.initial_base_hp,
                "base_shield": team.base_shield,
                "coins": team.coins,
                "score": team.score,
                "status": team.status,
            },
            "unlocked_units": UnitTypeSerializer(units, many=True, context={"team": team, "match": match}).data,
            "entities": GameEntitySerializer(active_entities, many=True, context={"match": match}).data,
            "limits": {
                "active_units": {"current": active_units_count, "max": None},
                "infantry": {"current": infantry_count, "max": None},
                "other_units": {"current": active_units_count - infantry_count, "max": max_units},
                "towers": {"current": active_towers_count, "max": None},
                "repairs_used_this_round": recent_repairs_count,
            },
            "valid_tower_slots": [],  # All arenas now publish authoritative grid metadata.
            "enemy_teams": enemy_teams,
            "special_actions_enabled": match.configuration.get("special_actions_enabled", {}),
            "special_action_costs": match.configuration.get("special_action_costs", {}),
        }

        return Response(state_data, status=status.HTTP_200_OK)


class UnitTypeListCreateView(APIView):
    """
    GET /api/v1/unit-types/ - List all combat unit and tower configurations (Host/Admin) (§2.3).
    POST /api/v1/unit-types/ - Create a new unit type configuration.
    """

    def get(self, request):
        qs = UnitType.objects.all().order_by("category", "cost")
        cat = request.query_params.get("category")
        if cat:
            qs = qs.filter(category=cat.upper())
        return Response(UnitTypeSerializer(qs, many=True).data)

    def post(self, request):
        serializer = UnitTypeAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        unit = serializer.save()
        return Response(UnitTypeSerializer(unit).data, status=status.HTTP_201_CREATED)


class UnitTypeDetailView(APIView):
    """
    GET /api/v1/unit-types/{id}/ - Retrieve unit type details.
    PATCH /api/v1/unit-types/{id}/ - Update unit stats, cost, active status (Host/Admin) (§2.3).
    DELETE /api/v1/unit-types/{id}/ - Delete unit type.
    """

    def get(self, request, unit_type_id):
        unit = get_object_or_404(UnitType, pk=unit_type_id)
        return Response(UnitTypeSerializer(unit).data)

    def patch(self, request, unit_type_id):
        unit = get_object_or_404(UnitType, pk=unit_type_id)
        serializer = UnitTypeAdminSerializer(unit, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        unit = serializer.save()
        return Response(UnitTypeSerializer(unit).data)

    def delete(self, request, unit_type_id):
        unit = get_object_or_404(UnitType, pk=unit_type_id)
        unit.delete()
        return Response({"message": "UnitType deleted successfully."})



class MatchTeamUpgradeView(APIView):
    def post(self, request, match_id):
        from apps.units.serializers import TeamUpgradeRequestSerializer
        from apps.units.services import TeamUpgradeService
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err
        serializer = TeamUpgradeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            action, payload = TeamUpgradeService.purchase(match, team, actor=member, **serializer.validated_data)
        except ValidationError as error:
            return Response(validation_payload(error), status=400)
        return Response({"action": GameActionSerializer(action).data, **payload})


class MatchArmyCommandView(APIView):
    def post(self, request, match_id):
        from apps.units.commands import ArmyCommandService
        from apps.units.serializers import ArmyCommandRequestSerializer

        match = get_object_or_404(Match, pk=match_id)
        team, member, error = resolve_team_for_request(request, match)
        if error:
            return error
        serializer = ArmyCommandRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            action, result = ArmyCommandService.issue(match, team, actor=member, **serializer.validated_data)
        except ValidationError as exc:
            return Response(validation_payload(exc), status=400)
        return Response({"action": GameActionSerializer(action).data, **result})
