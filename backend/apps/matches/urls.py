from django.urls import path

from apps.combat.views import MatchCombatResolveView, MatchMapView, MatchResultsView
from apps.matches.views import (
    MatchAdvancePhaseView,
    MatchApplyPresetView,
    MatchBalancePreviewView,
    MatchByCodeView,
    MatchConfigUpdateView,
    MatchConstraintsView,
    MatchDetailView,
    MatchEndView,
    MatchEventsListView,
    MatchHostTelemetryView,
    MatchJoinView,
    MatchListCreateView,
    MatchLockView,
    MatchMemberAssignView,
    MatchMemberDetailView,
    MatchOverrideAdjustCoinsView,
    MatchOverrideCloseQuestionView,
    MatchPauseView,
    MatchPresetsView,
    MatchRematchView,
    MatchResumeView,
    MatchSnapshotView,
    MatchStartView,
    MatchTeamDetailView,
    MatchTeamListCreateView,
    MatchTeamReadyView,
)
from apps.questions.banks import QuestionBankPreviewView, QuestionBankUploadView
from apps.questions.views import (
    MatchAnswerQuestionView,
    MatchCurrentQuestionView,
    MatchQuestionHistoryView,
    MatchQuestionProgressView,
    QuestionDetailView,
    QuestionListCreateView,
)
from apps.realtime.browser_security import BrowserInspectionReportView
from apps.rewards.views import MatchRewardClaimView, MatchRewardOptionsView
from apps.units.views import (
    MatchArmyCommandView,
    MatchBuildTowerActionView,
    MatchDeployUnitActionView,
    MatchEmpActionView,
    MatchRepairBaseActionView,
    MatchScoutActionView,
    MatchSellTowerActionView,
    MatchTeamStateView,
    MatchTeamUpgradeView,
    MatchUnitListView,
    MatchUpgradeTowerActionView,
    UnitTypeDetailView,
    UnitTypeListCreateView,
)

urlpatterns = [
    path("matches/<uuid:match_id>/security/inspection/", BrowserInspectionReportView.as_view(), name="browser_inspection_report"),
    path("matches/<uuid:match_id>/actions/army/", MatchArmyCommandView.as_view(), name="match_army_command"),
    path("matches/<uuid:match_id>/upgrades/", MatchTeamUpgradeView.as_view(), name="match_team_upgrade"),
    path("question-banks/upload/", QuestionBankUploadView.as_view(), name="question_bank_upload"),
    path("question-banks/<uuid:bank_id>/preview/", QuestionBankPreviewView.as_view(), name="question_bank_preview"),
    path("matches/<uuid:match_id>/questions/progress/", MatchQuestionProgressView.as_view(), name="question_progress"),
    path("matches/constraints/", MatchConstraintsView.as_view(), name="match_constraints"),
    path("matches/<uuid:match_id>/snapshot/", MatchSnapshotView.as_view(), name="match_snapshot"),
    path("matches/<uuid:match_id>/map/", MatchMapView.as_view(), name="match_map"),
    path("matches/", MatchListCreateView.as_view(), name="match_list_create"),
    path("matches/code/<str:room_code>/", MatchByCodeView.as_view(), name="match_by_code"),
    path("matches/<uuid:match_id>/", MatchDetailView.as_view(), name="match_detail"),
    path("matches/<uuid:match_id>/join/", MatchJoinView.as_view(), name="match_join"),
    path("matches/<uuid:match_id>/start/", MatchStartView.as_view(), name="match_start"),
    path("matches/<uuid:match_id>/pause/", MatchPauseView.as_view(), name="match_pause"),
    path("matches/<uuid:match_id>/resume/", MatchResumeView.as_view(), name="match_resume"),
    path("matches/<uuid:match_id>/end/", MatchEndView.as_view(), name="match_end"),
    path(
        "matches/<uuid:match_id>/advance-phase/",
        MatchAdvancePhaseView.as_view(),
        name="match_advance_phase",
    ),
    path("matches/<uuid:match_id>/lock/", MatchLockView.as_view(), name="match_lock"),
    path(
        "matches/<uuid:match_id>/config/",
        MatchConfigUpdateView.as_view(),
        name="match_config_update",
    ),
    # Lobby management endpoints
    path(
        "matches/<uuid:match_id>/teams/",
        MatchTeamListCreateView.as_view(),
        name="match_teams_create",
    ),
    path(
        "matches/<uuid:match_id>/teams/<uuid:team_id>/",
        MatchTeamDetailView.as_view(),
        name="match_team_detail",
    ),
    path(
        "matches/<uuid:match_id>/teams/<uuid:team_id>/ready/",
        MatchTeamReadyView.as_view(),
        name="match_team_ready",
    ),
    path(
        "matches/<uuid:match_id>/members/<uuid:member_id>/assign/",
        MatchMemberAssignView.as_view(),
        name="match_member_assign",
    ),
    path(
        "matches/<uuid:match_id>/members/<uuid:member_id>/",
        MatchMemberDetailView.as_view(),
        name="match_member_detail",
    ),
    # Phase 2: Questions endpoints (§20)
    path(
        "matches/<uuid:match_id>/questions/current/",
        MatchCurrentQuestionView.as_view(),
        name="match_question_current",
    ),
    path(
        "matches/<uuid:match_id>/questions/<uuid:question_id>/answer/",
        MatchAnswerQuestionView.as_view(),
        name="match_question_answer",
    ),
    path(
        "matches/<uuid:match_id>/questions/history/",
        MatchQuestionHistoryView.as_view(),
        name="match_question_history",
    ),
    # Question Bank management (Host/Admin)
    path("questions/", QuestionListCreateView.as_view(), name="question_list_create"),
    path("questions/<uuid:question_id>/", QuestionDetailView.as_view(), name="question_detail"),
    # Phase 2: Rewards endpoints (§20)
    path(
        "matches/<uuid:match_id>/rewards/claim/",
        MatchRewardClaimView.as_view(),
        name="match_reward_claim",
    ),
    path(
        "matches/<uuid:match_id>/rewards/options/<uuid:team_question_id>/",
        MatchRewardOptionsView.as_view(),
        name="match_reward_options",
    ),
    # Units endpoints (§20)
    path(
        "matches/<uuid:match_id>/units/",
        MatchUnitListView.as_view(),
        name="match_unit_list",
    ),
    path("matches/<uuid:match_id>/actions/sell/", MatchSellTowerActionView.as_view(), name="match_action_sell"),
    # Phase 3: Actions & Economy endpoints (§2.5, §20)
    path(
        "matches/<uuid:match_id>/actions/deploy/",
        MatchDeployUnitActionView.as_view(),
        name="match_action_deploy",
    ),
    path(
        "matches/<uuid:match_id>/actions/build/",
        MatchBuildTowerActionView.as_view(),
        name="match_action_build",
    ),
    path(
        "matches/<uuid:match_id>/actions/upgrade/",
        MatchUpgradeTowerActionView.as_view(),
        name="match_action_upgrade",
    ),
    path(
        "matches/<uuid:match_id>/actions/repair/",
        MatchRepairBaseActionView.as_view(),
        name="match_action_repair",
    ),
    path(
        "matches/<uuid:match_id>/actions/scout/",
        MatchScoutActionView.as_view(),
        name="match_action_scout",
    ),
    path(
        "matches/<uuid:match_id>/actions/emp/",
        MatchEmpActionView.as_view(),
        name="match_action_emp",
    ),
    path(
        "matches/<uuid:match_id>/teams/<uuid:team_id>/state/",
        MatchTeamStateView.as_view(),
        name="match_team_state",
    ),
    # Phase 4: Results & Combat Resolve endpoints (§20, FR-07, FR-10)
    path(
        "matches/<uuid:match_id>/results/",
        MatchResultsView.as_view(),
        name="match_results",
    ),
    path(
        "matches/<uuid:match_id>/combat/resolve/",
        MatchCombatResolveView.as_view(),
        name="match_combat_resolve",
    ),
    path(
        "matches/<uuid:match_id>/events/",
        MatchEventsListView.as_view(),
        name="match_events_list",
    ),
    # Phase 6: Host Console, Overrides, Monitoring & Results (§14.8, §14.9, FR-09, FR-10)
    path(
        "matches/<uuid:match_id>/host-telemetry/",
        MatchHostTelemetryView.as_view(),
        name="match_host_telemetry",
    ),
    path(
        "matches/presets/",
        MatchPresetsView.as_view(),
        name="match_presets",
    ),
    path(
        "matches/<uuid:match_id>/apply-preset/",
        MatchApplyPresetView.as_view(),
        name="match_apply_preset",
    ),
    path(
        "matches/<uuid:match_id>/config/preview/",
        MatchBalancePreviewView.as_view(),
        name="match_config_preview",
    ),
    path(
        "matches/<uuid:match_id>/rematch/",
        MatchRematchView.as_view(),
        name="match_rematch",
    ),
    path(
        "matches/<uuid:match_id>/override/close-question/",
        MatchOverrideCloseQuestionView.as_view(),
        name="match_override_close_question",
    ),
    path(
        "matches/<uuid:match_id>/override/adjust-coins/",
        MatchOverrideAdjustCoinsView.as_view(),
        name="match_override_adjust_coins",
    ),
    # Phase 6: UnitType configuration endpoints for host
    path(
        "unit-types/",
        UnitTypeListCreateView.as_view(),
        name="unit_type_list_create",
    ),
    path(
        "unit-types/<uuid:unit_type_id>/",
        UnitTypeDetailView.as_view(),
        name="unit_type_detail",
    ),
]
