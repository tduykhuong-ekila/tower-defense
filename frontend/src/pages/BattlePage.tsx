import { GameItemCardContent } from "../components/game/GameItemCardContent";
import { UnitLevelStars } from "../components/game/UnitLevelStars";
import { towerSalePrice } from "../game/towerSale";
import { resolveAttackTarget } from "../game/defaultAttackTarget";
import { MAX_UPGRADE_LEVEL, upgradeLevel } from "../game/upgradeLevel";
import { resolveUpgradeType, UpgradeSelection } from "../game/upgradeSelection";
import { placementReason } from "../game/placement";
import { TeamUpgradeModal } from "../components/game/TeamUpgradeModal";
import { AttackTargetPicker } from "../components/game/AttackTargetPicker";
import { ArmyContextMenu } from "../components/game/ArmyContextMenu";
import { ArmyCommandPanel } from "../components/game/ArmyCommandPanel";
import { armyCommandRequest, controllableTroops, updateArmySelection } from "../game/armySelection";
import { EntityInfoCard, inspectEntity } from "../components/game/EntityInfoCard";
import { ENTITY_NAMES as NAMES } from "../game/entityArtwork";
import { EntityIllustration } from "../components/game/EntityIllustration";
import { useCallback, useEffect, useMemo, useRef, useState, SetStateAction } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BookOpen,
  Check,
  ChevronRight,
  Coins,
  Crosshair,
  Flag,
  Focus,
  Heart,
  Home,
  Maximize,
  Minimize,
  Pause,
  Play,
  Radio,
  ScrollText,
  Settings,
  Shield,
  SkipForward,
  Swords,
  Volume2,
  VolumeX,
  Wrench,
  X,
  Zap,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { PhaserGame, PhaserGameRef } from "../game/PhaserGame";
import {
  InteractionMode,
  normalizeEntity,
  SceneCallbacks,
  SceneState,
} from "../game/bridge";
import { canPlaceTower, PALETTE, teamLabel, projectMap, ServerMap, teamIndex } from "../game/map";
import { playFeedback } from "../game/sound";
import { planningSeconds } from "../game/roundClock";
import { actionAvailability, AvailabilityContext, purchaseAvailability, maximumDeployment } from "../game/actionAvailability";
import { GameplayModal, visibleGameplayModal } from "../game/gameplayModal";
import { api, getActiveMember, getAuthToken } from "../services/api";
import { wsClient } from "../services/websocket";
import { useMatchStore } from "../stores/matchStore";
import { Match } from "../types/match";
import { TeamState, UnitType } from "../types/unit";
import { RewardClaim, RewardOptions, RewardType } from "../types/reward";
import { ServerEnvelope } from "../types/realtime";
import { TeamQuestion } from "../types/question";
import { DeploymentQuantity } from "../components/DeploymentQuantity";
import { useModalFocus } from "../components/useModalFocus";
import { QuestionModal } from "../components/QuestionModal";
import { RewardSelectionModal } from "../components/RewardSelectionModal";
import "../game/game.css";
import { ArenaNavigation, ArenaNavigationRef, TeamDirectory } from "../components/arena/ArenaNavigation";

const PHASES: Record<string, string> = {
  LOBBY: "Phòng chờ",
  PREPARATION: "Chuẩn bị",
  BUILD_AND_SCOUT: "Xây dựng & trinh sát",
  WAR: "Giao tranh",
  FINAL_ASSAULT: "Tổng tiến công",
  RESULTS: "Kết quả",
};
type Drawer = "TEAMS" | "LOG" | "SETTINGS" | null;

function formatClock(seconds: number) {
  const safe = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(safe / 60).toString().padStart(2, "0")}:${(safe % 60).toString().padStart(2, "0")}`;
}

export function BattlePage() {
  const { matchId: routeId } = useParams();
  const [matchId, setMatchId] = useState<string | null>(
    routeId || sessionStorage.getItem("tower_active_match_id"),
  );
  const [details, setDetails] = useState<Match | null>(null);
  const [map, setMap] = useState<ServerMap | null>(null);
  const [catalog, setCatalog] = useState<UnitType[]>([]);
  const [teamState, setTeamState] = useState<TeamState | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [tab, setTab] = useState<"UNIT" | "TOWER" | "SPECIAL">("UNIT");
  const [selected, setSelected] = useState<UnitType | null>(null);
  const [quantityInput, setQuantityInput] = useState("1");
  const quantity = Number(quantityInput);
  const navigation = useRef<ArenaNavigationRef>(null);
  const [deploymentTargetId, setDeploymentTargetId] = useState("");
  const [deploymentOrder, setDeploymentOrder] = useState<"ATTACK" | "DEFEND_BASE">("ATTACK");
  const [commandTargetId, setCommandTargetId] = useState("");
  const [armyMenu, setArmyMenu] = useState<{x: number; y: number; targetsOnly?: boolean} | null>(null);
  const [targetPicker, setTargetPicker] = useState<"DEPLOY" | "COMMAND" | null>(null);
  const [dockCollapsed, setDockCollapsed] = useState(false);
  const [commandView, setCommandView] = useState<"DEPLOY" | "ARMY">("DEPLOY");
  const [multipleSelection, setMultipleSelection] = useState(false);
  const targetScope = useRef("");
  const [inspected, setInspected] = useState<string | null>(null);
  const [selectedArmyIds, setSelectedArmyIds] = useState<string[]>([]);
  const [armySelectionMode, setArmySelectionMode] = useState(false);
  const [retreatOpen, setRetreatOpen] = useState(false);
  const [retreatSnapshot, setRetreatSnapshot] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [sound, setSound] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [question, setQuestionRaw] = useState<TeamQuestion | null>(null);
  const setQuestion = useCallback((value: SetStateAction<TeamQuestion | null>) => setQuestionRaw(previous => {
    const next = typeof value === "function" ? value(previous) : value;
    if (!next) return previous; // Only explicit match/team changes clear the local session.
    if (previous && (next.sequence_number < previous.sequence_number ||
      (next.id === previous.id && (next.timer?.version ?? 0) < (previous.timer?.version ?? 0)))) return previous;
    return next;
  }), []);
  const [rewardFallback, setReward] = useState<RewardOptions | null>(null);
  const reward = question?.status === "PENDING_REWARD"
    ? question.reward_options || (rewardFallback?.team_question_id === question.id ? rewardFallback : null)
    : null;
  const [upgradeSelection, setUpgradeSelection] = useState<UpgradeSelection | null>(null);
  const upgradeOpen = upgradeSelection !== null;
  const [modal, setModal] = useState<GameplayModal>(null);
  const [rewardRevealing, setRewardRevealing] = useState(false);
  const visibleModal = rewardRevealing ? "REWARD" : visibleGameplayModal(modal, question, reward);
  useEffect(() => {
    if (modal !== visibleModal) setModal(visibleModal);
  }, [modal, visibleModal]);
  const [answerPending, setAnswerPending] = useState(false);
  const [toast, setToast] = useState<{
    text: string;
    kind: "success" | "error" | "info";
  } | null>(null);
  const [phaseBanner, setPhaseBanner] = useState<{ title: string; detail: string; tone: "prep" | "battle" | "climax" } | null>(null);
  const [rewardBurst, setRewardBurst] = useState(false);
  const [scout, setScout] = useState<{
    target_team_name: string;
    towers?: { name: string; code: string; hp: number; level: number }[];
  } | null>(null);
  const phaser = useRef<PhaserGameRef>(null),
    root = useRef<HTMLDivElement>(null);
  const deploymentDialog = useRef<HTMLElement>(null);
  useModalFocus(selected?.category === "UNIT" && commandView === "DEPLOY", deploymentDialog, () => setSelected(null));
  const actionLock = useRef(false),
    answerLock = useRef(false),
    toastTimer = useRef<ReturnType<typeof setTimeout>>(),
    phaseBannerTimer = useRef<ReturnType<typeof setTimeout>>(),
    soundRef = useRef(sound);
  soundRef.current = sound;
  const refreshRef = useRef<() => Promise<void>>(async () => {});
  const refreshVersion = useRef(0);
  const activeMatch = useRef(matchId);
  activeMatch.current = matchId;
  useEffect(
    () => () => {
      activeMatch.current = null;
      refreshVersion.current++;
    },
    [],
  );
  const store = useMatchStore();
  const member = getActiveMember();
  // Match details and realtime snapshots reflect assignments made after join,
  // while sessionStorage can still contain the original unassigned record.
  const serverMember = member
    ? (details?.all_members || details?.teams.flatMap((team) => team.members) || [])
        .find((candidate) => candidate.id === member.id)
    : undefined;
  const snapshotTeamId =
    store.match?.id === matchId ? store.currentTeamId : null;
  const teamId = serverMember
    ? serverMember.team_id
    : snapshotTeamId || member?.team_id || null;
  const myTeam =
    store.teams.find((t) => t.id === teamId) ||
    details?.teams.find((t) => t.id === teamId);
  const match =
    store.match?.id === matchId ? { ...details, ...store.match } : details;
  const mapData = store.mapData || map;
  const teams = store.teams.length ? store.teams : details?.teams || [];
  const coins = teamId ? store.coins : 0;
  const quizSpectator = !teamId || !myTeam || member?.role === "SPECTATOR";
  const spectator = quizSpectator || myTeam?.status === "ELIMINATED";
  const hasHost = store.isHost;
  const phase = match?.phase || "LOBBY";
  const active = match?.status === "ACTIVE";
  const timer = match?.configuration?.timer_state;
  const roundRemaining = planningSeconds(match as Match | null, now);
  const continuous = match?.configuration.gameplay_mode === "CONTINUOUS";
  const currentRound = match?.configuration.current_round || store.currentRound || 1;
  const totalRounds = match?.configuration.total_rounds || 3;
  const phaseDuration =
    match?.configuration?.phase_durations?.[
      phase as keyof NonNullable<Match["configuration"]["phase_durations"]>
    ];
  const remaining =
    match?.status === "PAUSED"
      ? timer?.phase_remaining_seconds
      : continuous && timer?.phase_ends_at
        ? Math.max(0, Math.ceil((Date.parse(timer.phase_ends_at) - now) / 1000))
      : timer?.phase_started_at && phaseDuration !== undefined
        ? Math.max(
            0,
            phaseDuration -
              Math.floor((now - Date.parse(timer.phase_started_at)) / 1000),
          )
        : undefined;
  const timerLabel =
    remaining === undefined
      ? ""
      : `${Math.floor(remaining / 60)
          .toString()
          .padStart(2, "0")}:${(remaining % 60).toString().padStart(2, "0")}`;
  const climaxDuration = currentRound >= totalRounds ? 30 : currentRound === 1 ? 15 : 20;
  const isClimax = !!(continuous && active && phase === "WAR" && remaining !== undefined
    && remaining > 0 && remaining <= climaxDuration);
  const secondsUntilClimax = remaining === undefined ? null : Math.max(0, remaining - climaxDuration);
  const continuousStage = !continuous ? null : phase === "PREPARATION"
    ? currentRound === 1 ? "gathering" : "resupply"
    : phase === "WAR" ? isClimax ? "climax" : "battle" : "other";
  const phaseTitle = !continuous ? PHASES[phase]
    : continuousStage === "gathering" ? "TẬP KẾT • CHƯA GIAO CHIẾN"
      : continuousStage === "resupply" ? "TIẾP TẾ • GIAO TRANH VẪN TIẾP DIỄN"
        : continuousStage === "climax" ? "CAO TRÀO"
          : continuousStage === "battle" ? "GIAO TRANH ĐANG DIỄN RA" : PHASES[phase];
  const enemies = teams.filter(
    (t) => t.id !== teamId && t.status !== "ELIMINATED",
  );
  // A catalog selection owns the ready/build panel; inspection remains a separate map state.
  const selectedEntity = selected ? undefined : store.entities.find((e) => e.id === inspected);
  const selectedUpgradeType = selectedEntity ? resolveUpgradeType(selectedEntity, teamId, catalog) : null;
  const friendlyTroops = controllableTroops(store.entities, teamId);
  const selectedArmySet = useMemo(() => new Set(selectedArmyIds), [selectedArmyIds]);
  const selectedArmy = friendlyTroops.filter(e => selectedArmySet.has(e.id));
  const armyBattle = !!(continuous && active && phase === "WAR" && !spectator);
  const armyGathering = !!(continuous && active && phase === "PREPARATION" && currentRound === 1 && !spectator);
  const armyRetreatPrep = !!(continuous && active && phase === "PREPARATION" && currentRound > 1 && !spectator);
  const armySelectionEnabled = armyBattle || armyGathering || armyRetreatPrep;
  useEffect(() => {
    const ids = new Set(controllableTroops(store.entities, teamId).map(e => e.id));
    setSelectedArmyIds(previous => previous.every(id => ids.has(id)) ? previous : previous.filter(id => ids.has(id)));
  }, [store.entities, teamId]);
  useEffect(() => {
    if (!armySelectionEnabled) { setSelectedArmyIds([]); setArmySelectionMode(false); setMultipleSelection(false); setRetreatOpen(false); setCommandTargetId(""); setTargetPicker(null); setCommandView("DEPLOY"); }
  }, [armySelectionEnabled, teamId]);
  useEffect(() => {
    if (!armyBattle && !armyGathering) {
      setCommandTargetId("");
      setTargetPicker(previous => previous === "COMMAND" ? null : previous);
    }
  }, [armyBattle, armyGathering]);
  useEffect(() => {
    setArmyMenu(null);
  }, [selectedArmyIds, phase, teamId, commandView, selected, visibleModal, upgradeOpen, targetPicker, retreatOpen]);
  // Deselecting the last troop restores the deployment dock.
  useEffect(() => {
    if (commandView === "ARMY" && !selectedArmy.length && !retreatOpen && !armyMenu) {
      setCommandView("DEPLOY");
      setDockCollapsed(false);
    }
  }, [commandView, selectedArmy.length, retreatOpen, armyMenu]);
  const inspectedTeam = selected ? undefined : teams.find((t) => t.id === inspected);
  const selectedStats =
    catalog.find((u) => u.code === (selectedEntity?.unit_code || selected?.code)) || selected;
  const occupied = store.entities.filter(
    (e) =>
      e.entity_kind === "TOWER" &&
      e.team_id === teamId &&
      e.status !== "DESTROYED",
  );
  const availableSlots = (mapData?.placement_grid ? [] : teamState?.valid_tower_slots || []).filter((id) =>
    canPlaceTower(id, teamState?.valid_tower_slots || [], store.entities),
  );
  const availabilityContext: AvailabilityContext = {
    match: match as Match | null, team: myTeam, spectator: quizSpectator,
    connection: store.connectionStatus, pending, modal: !!visibleModal || upgradeOpen || !!targetPicker || retreatOpen,
    coins, entities: store.entities, unlocked: store.unlockedUnits, slots: availableSlots, gridPlacement: !!mapData?.placement_grid,
  };
  const deploymentAvailability = selected ? purchaseAvailability(availabilityContext, selected, selected.category === "UNIT" ? quantity : 1) : {allowed: false, reason: ""};
  const maximumQuantity = selected?.category === "UNIT" ? maximumDeployment(availabilityContext, selected) : 0;
  const commonAvailability = actionAvailability(availabilityContext);
  const canDeploy = commonAvailability.allowed;
  const canBuild = actionAvailability(availabilityContext, "BUILD_TOWER").allowed;
  const blocked = !commonAvailability.allowed;
  const mode: InteractionMode = visibleModal || upgradeOpen || retreatOpen || targetPicker || armyMenu
    ? "MODAL"
    : pending
      ? "WAITING"
      : playing
        ? "COMBAT"
        : selected && deploymentAvailability.allowed
          ? selected.category === "TOWER"
            ? "BUILD"
            : "DEPLOY"
          : inspected
            ? "INSPECT"
            : "IDLE";

  const notify = useCallback(
    (text: string, kind: "success" | "error" | "info" = "info") => {
      clearTimeout(toastTimer.current);
      setToast({ text, kind });
      toastTimer.current = setTimeout(() => setToast(null), 4500);
    },
    [],
  );
  const announcePhase = useCallback((title: string, detail: string, tone: "prep" | "battle" | "climax") => {
    clearTimeout(phaseBannerTimer.current);
    setPhaseBanner({ title, detail, tone });
    phaseBannerTimer.current = setTimeout(() => setPhaseBanner(null), tone === "climax" ? 6000 : 4500);
    if (soundRef.current) playFeedback(tone === "prep" ? "select" : "success");
  }, []);
  const lastClimaxState = useRef<boolean | null>(null);
  const lastClimaxRemaining = useRef<number | null>(null);
  useEffect(() => {
    if (!continuous || !active || phase !== "WAR") {
      lastClimaxState.current = null;
      lastClimaxRemaining.current = null;
      return;
    }
    if (lastClimaxState.current === null) {
      lastClimaxState.current = isClimax;
      lastClimaxRemaining.current = remaining ?? null;
      return;
    }
    if (isClimax && !lastClimaxState.current) {
      announcePhase("CAO TRÀO BẮT ĐẦU", "Bộ binh và xe tăng bắn nhanh hơn 10% • tháp nhận 2/3 sát thương", "climax");
    }
    if (isClimax && remaining !== undefined && lastClimaxRemaining.current !== null
        && lastClimaxRemaining.current > 5 && remaining <= 5) {
      announcePhase("CÒN 5 GIÂY CAO TRÀO", "Chuẩn bị cho vòng chiến đấu tiếp theo", "climax");
    }
    lastClimaxState.current = isClimax;
    lastClimaxRemaining.current = remaining ?? null;
  }, [continuous, active, phase, currentRound, isClimax, remaining, announcePhase]);
  const refresh = useCallback(async () => {
    if (!matchId) return;
    const version = ++refreshVersion.current;
    const current = () =>
      activeMatch.current === matchId && refreshVersion.current === version;
    const startSequence = useMatchStore.getState().lastSequenceNumber;
    const [matchData, mapData, units] = await Promise.all([
      api.getMatch(matchId),
      api.getMap(matchId),
      api.getMatchUnits(matchId),
    ]);
    if (!current()) return;
    setDetails(matchData);
    setMap(mapData);
    setCatalog(units);
    useMatchStore.setState((s) =>
      s.lastSequenceNumber === startSequence
        ? {
            match: matchData,
            currentRound:
              matchData.configuration.current_round || s.currentRound,
          }
        : {},
    );
    if (teamId && matchData.teams.some((t) => t.id === teamId)) {
      const stateSequence = useMatchStore.getState().lastSequenceNumber;
      const state = await api.getTeamState(matchId, teamId);
      if (!current()) return;
      setTeamState(state);
      // Ignore REST results overtaken by a newer socket event.
      useMatchStore.setState((s) =>
        s.lastSequenceNumber === stateSequence
          ? {
              coins: state.team.coins,
              currentTeamId: teamId,
              entities: [
                ...s.entities.filter((e) => e.team_id !== teamId),
                ...state.entities.map(normalizeEntity),
              ],
              teams: s.teams.map((t) =>
                t.id === teamId ? { ...t, ...state.team } : t,
              ),
            }
          : {},
      );
      const questionSequence = useMatchStore.getState().lastQuestionSequence;
      const [q, progress] = await Promise.all([api.getCurrentQuestion(matchId), api.getQuestionProgress(matchId)]);
      if (!current()) return;
      if (useMatchStore.getState().lastQuestionSequence !== questionSequence) {
        const latest = useMatchStore.getState();
        setQuestion(latest.currentQuestion);
        setReward(latest.pendingReward);
      } else if (q && "id" in q) {
        setQuestion(previous => previous?.id === q.id && (previous.timer?.version ?? 0) > (q.timer?.version ?? 0) ? previous : q);
        setReward(q.reward_options || null);
        useMatchStore.setState({
          currentQuestion: q,
          pendingReward: q.reward_options || null,
          questionProgress: progress,
        });
      } else {
        setQuestion(null);
        setReward(null);
        useMatchStore.setState({ currentQuestion: null, pendingReward: null, questionProgress: progress });
      }
    }
  }, [matchId, teamId]);
  refreshRef.current = refresh;
  useEffect(() => {
    if (routeId) {
      setMatchId(routeId);
      return;
    }
    if (!matchId)
      api
        .listMatches()
        .then((matches) => {
          if (matches.length) setMatchId(matches[0].id);
          else setLoading(false);
        })
        .catch(() => {
          setLoadError(
            "Không thể kết nối máy chủ. Kiểm tra backend và thử lại.",
          );
          setLoading(false);
        });
  }, [routeId, matchId]);

  useEffect(() => {
    if (!matchId) return;
    let alive = true;
    activeMatch.current = matchId;
    setLoading(true);
    setLoadError("");
    useMatchStore.getState().reset();
    setQuestionRaw(null);
    setReward(null);
    setModal(null);
    setRewardRevealing(false);
    useMatchStore.getState().setCurrentTeamId(teamId);
    const onStatus = (data: {
      status: "connected" | "syncing" | "reconnecting" | "disconnected";
    }) => useMatchStore.getState().setConnectionStatus(data.status);
    const onEvent = (_payload: unknown, envelope: ServerEnvelope) => {
      const s = useMatchStore.getState();
      if (envelope.match_id !== matchId) return;
      if (envelope.event_type === "COMBAT_RESOLVED" && envelope.payload.round_number < s.currentRound - 1) {
        return;
      }
      // WebSocketClient has already applied the authoritative reducer. Everything
      // below is a UI observer; a Phaser error cannot discard a gameplay event.
      if (envelope.event_type === "COMBAT_RESOLVED")
        phaser.current?.playCombatEvents(envelope.payload.events || []);
      if (envelope.event_type === "COMBAT_TICK") {
        const known = new Set(s.entities.map(e => e.id));
        if ((envelope.payload.entity_updates || []).some((e: { id: string; status: string; team_id?: string; unit_code?: string; entity_kind?: string }) => e.status !== "DESTROYED" && !known.has(e.id) && !(e.team_id && e.unit_code && e.entity_kind)))
          wsClient.requestSync();
        phaser.current?.playLiveEvents(envelope.payload.events || []);
      }
      const next = useMatchStore.getState();
      const continuousMatch = next.match?.configuration.gameplay_mode === "CONTINUOUS";
      if (continuousMatch && envelope.event_type === "MATCH_STARTED") {
        const seconds = next.match?.configuration.first_preparation_duration_seconds ?? 120;
        announcePhase("TẬP KẾT • VÒNG 1 SẮP BẮT ĐẦU", `Chưa giao chiến • bắt đầu sau ${formatClock(seconds)}`, "prep");
      }
      if (continuousMatch && envelope.event_type === "ROUND_STARTED") {
        const round = envelope.payload.current_round || next.currentRound;
        const seconds = next.match?.configuration.preparation_duration_seconds ?? 180;
        announcePhase(`TIẾP TẾ • VÒNG ${round}`, `Giao tranh vẫn tiếp diễn • vòng mới sau ${formatClock(seconds)}`, "prep");
      }
      if (continuousMatch && envelope.event_type === "BATTLE_STARTED") {
        const round = envelope.payload.current_round || next.currentRound;
        announcePhase(`VÒNG ${round} BẮT ĐẦU`, "Giao tranh đang diễn ra • hãy bảo vệ căn cứ", "battle");
      }
      if (envelope.event_type === "MATCH_ENDED") {
        setSelected(null);
        notify("Trận đấu đã kết thúc. Đóng cửa sổ để xem kết quả.");
      }
      if (envelope.event_type === "MATCH_STATE_SNAPSHOT") {
        phaser.current?.skipCombat();
        setPlaying(false);
        setQuestion(next.currentQuestion);
        setReward(next.pendingReward);
      } else if (
        [
          "QUESTION_TIMER_UPDATED",
          "QUESTION_ASSIGNED",
          "QUESTION_EXPIRED",
          "ANSWER_RESULT",
          "QUESTION_ANSWERED_CORRECT",
          "QUESTION_ANSWERED_INCORRECT",
          "REWARD_OPTIONS",
          "REWARD_APPLIED",
          "REWARD_CLAIMED",
        ].includes(envelope.event_type)
      ) {
        if (!envelope.payload.team_id || envelope.payload.team_id === teamId) {
          setQuestion(next.currentQuestion);
          setReward(next.pendingReward);
        }
        if (["REWARD_APPLIED", "REWARD_CLAIMED"].includes(envelope.event_type) && envelope.payload.team_id === teamId) {
          void refreshRef.current().catch(() => {});
        }
      }
      if (envelope.event_type === "ANSWER_RESULT" && ["REWARD_CLAIMED", "EXPIRED"].includes(envelope.payload.status))
        void refreshRef.current().catch(() => {});
      if (
        [
          "QUESTION_EXPIRED",
          "UNIT_UNLOCKED",
          "BASE_REPAIRED",
          "TOWER_UPGRADED",
          "TEAM_UNIT_UPGRADED",
          "EMP_USED",
          "MATCH_PAUSED",
          "MATCH_RESUMED",
          "MATCH_ENDED",
          "COMBAT_RESOLVED",
        ].includes(envelope.event_type)
      )
        void refreshRef.current().catch(() => {});
    };
    wsClient.on("connection_change", onStatus);
    wsClient.on("any", onEvent);
    if (member || getAuthToken()) wsClient.connect(matchId);
    // Lobby navigation can reuse an already subscribed socket whose initial
    // snapshot belonged to the old page. Restore the complete board after reset.
    wsClient.requestSync();
    useMatchStore.getState().setConnectionStatus(wsClient.getStatus());
    refreshRef
      .current()
      .catch((e) => {
        if (alive) setLoadError(e.message || "Không tải được trận đấu.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
      wsClient.off("connection_change", onStatus);
      wsClient.off("any", onEvent);
      wsClient.disconnect();
    };
  }, [matchId, teamId, announcePhase]);
  useEffect(() => {
    const scope = `${matchId}:${teamId}`;
    if (!teams.some(team => team.id === teamId)) return;
    if (targetScope.current !== scope) {
      targetScope.current = scope;
      setDeploymentTargetId(resolveAttackTarget(teams, teamId, ""));
      setCommandTargetId("");
      setTargetPicker(null);
      setSelectedArmyIds([]); setArmySelectionMode(false); setMultipleSelection(false);
      setCommandView("DEPLOY"); setRetreatOpen(false); setRetreatSnapshot([]); setDockCollapsed(false);
    } else {
      // Invalidated targets require an explicit choice, never an automatic redirect.
      if (deploymentTargetId && !teams.some(team => team.id === deploymentTargetId && team.id !== teamId && team.status === "ACTIVE" && team.base_hp > 0))
        setDeploymentTargetId("");
      if (commandTargetId && !teams.some(team => team.id === commandTargetId && team.id !== teamId && team.status === "ACTIVE" && team.base_hp > 0))
        setCommandTargetId("");
    }
  }, [teams, deploymentTargetId, commandTargetId, teamId, matchId]);
  useEffect(
    () => () => {
      clearTimeout(toastTimer.current);
    },
    [],
  );
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) {
        if (armyMenu) { setArmyMenu(null); return; }
        if (targetPicker || retreatOpen || visibleModal || upgradeOpen) return;
        setSelected(null);
        setInspected(null);
        setSelectedArmyIds([]);
        setArmySelectionMode(false);
        setMultipleSelection(false);
        setCommandTargetId("");
        setDrawer(null);
        // Dialog Escape is handled by its focus trap and authoritative close action.
      }
    };
    const fullscreenChange = () => setFullscreen(!!document.fullscreenElement);
    window.addEventListener("keydown", handler);
    document.addEventListener("fullscreenchange", fullscreenChange);
    return () => {
      window.removeEventListener("keydown", handler);
      document.removeEventListener("fullscreenchange", fullscreenChange);
    };
  }, [pending, targetPicker, retreatOpen, visibleModal, upgradeOpen, armyMenu]);

  const action = useCallback(
    async (run: () => Promise<unknown>, success: string, keepSelection = false) => {
      if (actionLock.current || blocked) return;
      phaser.current?.skipCombat();
      setPlaying(false);
      actionLock.current = true;
      setPending(true);
      try {
        await run();
        if (!keepSelection) setSelected(null);
        notify(success, "success");
        if (sound) playFeedback("success");
        wsClient.requestSync();
        await refreshRef.current();
      } catch (e) {
        notify(
          e instanceof Error ? e.message : "Thao tác chưa thành công.",
          "error",
        );
        wsClient.requestSync();
        void refreshRef.current().catch(() => {});
        if (sound) playFeedback("error");
      } finally {
        actionLock.current = false;
        setPending(false);
      }
    },
    [blocked, notify, sound],
  );
  const place = useCallback(
    (nodeId: string, cell?: {row:number;col:number}) => {
      if (!selected || blocked || !matchId || !mapData) return;
      const availability = purchaseAvailability(availabilityContext, selected, selected.category === "UNIT" ? quantity : 1);
      if (!availability.allowed) { notify(availability.reason || "Chưa thể thực hiện thao tác.", "error"); return; }
      if (coins < selected.cost) {
        notify("Đội chưa đủ xu. Trả lời câu hỏi để nhận thêm.", "error");
        return;
      }
      if (selected.category === "TOWER") {
        if (
          !canBuild ||
          !(mapData.placement_grid && cell ? !placementReason(mapData, cell, selected.code, teamId || "", store.entities) : canPlaceTower(
            nodeId,
            teamState?.valid_tower_slots || [],
            store.entities,
          ))
        ) {
          notify("Chọn một ô xây tháp còn trống trong lãnh thổ đội.", "error");
          return;
        }
        void action(
          () =>
            api.buildTower(matchId, {
              unit_type_code_or_id: selected.code,
              ...(cell ? {grid_row:cell.row,grid_col:cell.col} : {node_id:nodeId}),
              idempotency_key: crypto.randomUUID(),
            }),
          `Đã xây ${NAMES[selected.code] || selected.name}.`,
        );
      } else {
        const spawn = `node_spawn_t${teamIndex(mapData, teamId || "") + 1}`;
        if (!canDeploy || nodeId !== spawn) {
          notify("Chọn điểm tập kết có mũi tên của đội để xuất quân.", "error");
          return;
        }
        if (deploymentOrder === "ATTACK" && !deploymentTargetId) {
          notify("Chọn căn cứ đối thủ làm mục tiêu.", "error");
          return;
        }
        void action(
          () =>
            api.deployUnit(matchId, {
              unit_type_code_or_id: selected.code,
              target_team_id: deploymentOrder === "ATTACK" ? deploymentTargetId : undefined,
              order: deploymentOrder,
              quantity,
              spawn_node_id: spawn,
              idempotency_key: crypto.randomUUID(),
            }),
          `Đã triển khai ${quantity} ${NAMES[selected.code] || selected.name}${deploymentOrder === "DEFEND_BASE" ? " bảo vệ căn cứ" : ""}.`,
        );
      }
    },
    [
      selected,
      quantity,
      blocked,
      matchId,
      mapData,
      coins,
      canBuild,
      canDeploy,
      teamState,
      store.entities,
      deploymentTargetId,
      deploymentOrder,
      teamId,
      action,
      notify,
      occupied.length,
    ],
  );
  const selectBase = useCallback((id: string) => {
    setInspected(id);
    if (commandView === "DEPLOY" && selected?.category === "UNIT" && !spectator &&
      teams.some(team => team.id === id && team.id !== teamId && team.status === "ACTIVE" && team.base_hp > 0)) {
      setDeploymentTargetId(id);
    } else if (commandView === "ARMY" && selectedArmyIds.length && (armyBattle || armyGathering || armyRetreatPrep) && !spectator &&
      teams.some(team => team.id === id && team.id !== teamId && team.status === "ACTIVE" && team.base_hp > 0)) {
      setCommandTargetId(id);

    }
  }, [commandView, selected?.category, selectedArmyIds.length, armyBattle, armyGathering, armyRetreatPrep, spectator, teams, teamId]);
  const callbacks = useMemo<SceneCallbacks>(
    () => ({
      onNodeClick: place,
      onGridClick: (row,col) => place("",{row,col}),
      onCancelBuild: () => setSelected(null),
      onBaseClick: selectBase,
      onEntityInspect: inspectEntity,
      onEntityClick: (id, additive = false) => {
        setDockCollapsed(false);
        setSelected(null);
        setInspected(id);
        if (armySelectionEnabled && controllableTroops(useMatchStore.getState().entities, teamId).some(e => e.id === id)) {
          setCommandView("ARMY");
          setCommandTargetId("");
          setSelectedArmyIds(previous => updateArmySelection(previous, [id], additive || multipleSelection, true));
        } else { setCommandView("DEPLOY"); setSelectedArmyIds([]); setArmySelectionMode(false); setMultipleSelection(false); }
      },
      onArmyContextMenu: (x, y) => { if (armySelectionEnabled) setArmyMenu({x, y}); },
      onArmySelect: (ids, additive, boxed = false) => {
        if (!armySelectionEnabled) return;
        if (boxed) setArmySelectionMode(false);
        if (!ids.length && multipleSelection) return;
        setCommandView("ARMY");
        if (ids.length) setDockCollapsed(false);
        setCommandTargetId("");
        const allowed = new Set(controllableTroops(useMatchStore.getState().entities, teamId).map(e => e.id));
        setSelectedArmyIds(previous => updateArmySelection(previous, ids.filter(id => allowed.has(id)), additive || multipleSelection));
        setInspected(null);
        setSelected(null);
      },
      onCameraChange: frame => navigation.current?.camera(frame),
      onMetrics: metrics => navigation.current?.metrics(metrics),
      onPlaybackChange: setPlaying,
      onLoadError: () =>
        notify("Một hình ảnh chưa tải được. Hãy tải lại trang.", "error"),
    }),
    [place, selectBase, teamId, teams, notify, armySelectionEnabled, multipleSelection, armyRetreatPrep, armyBattle],
  );
  const sceneState = useMemo<SceneState>(
    () => ({
      teams,
      entities: store.entities,
      mapData,
      myTeamId: teamId,
      selectedTargetTeamId: commandView === "ARMY" ? commandTargetId : deploymentTargetId,
      selectedEntityId: inspected,
      selectedArmyIds,
      armySelectionMode,
      armyControlEnabled: armySelectionEnabled,
      selectedUnit: selected ? catalog.find(unit => unit.code === selected.code) || selected : null,
      validTowerSlots: teamState?.valid_tower_slots || [],
      mode,
      sound,
      liveBattle: continuous && active && phase === "WAR",
    }),
    [
      teams,
      store.entities,
      mapData,
      teamId,
      deploymentTargetId,
      inspected,
      selectedArmyIds, armySelectionMode, armySelectionEnabled, commandView, commandTargetId,
      selected, catalog,
      teamState,
      mode,
      sound,
      continuous, active, phase,
    ],
  );
  const selectUnit = (unit: UnitType) => {
    setDockCollapsed(false);
    setCommandView("DEPLOY");
    setMultipleSelection(false);
    setCommandTargetId("");
    setArmySelectionMode(false);
    setSelectedArmyIds([]);
    setQuantityInput("1");
    const availability = purchaseAvailability(availabilityContext, unit);
    if (!availability.allowed) { notify(availability.reason || "Chưa thể thực hiện thao tác."); return; }
    if (playing) { phaser.current?.skipCombat(); setPlaying(false); }
    setSelected(selected?.id === unit.id ? null : unit);
    if (selected?.id !== unit.id && mapData) {
      const nodeId = unit.category === "UNIT" || mapData.placement_grid ? `node_spawn_t${myIndex + 1}` : availableSlots[0];
      const node = projectMap(mapData).get(nodeId);
      if (node) phaser.current?.navigate(node.worldX, node.worldY, 0.8);
    }
    setInspected(null);
    if (sound) playFeedback("select");
  };
  const issueArmyCommand = async (command_type: "RETARGET" | "RETREAT_ALL" | "DEFEND_BASE", unitIds = selectedArmy.map(e => e.id), targetId = commandTargetId) => {
    const allowed = armyBattle || (command_type === "RETARGET" ? armyGathering || armyRetreatPrep : armyRetreatPrep);
    if (!matchId || !allowed || actionLock.current || store.connectionStatus !== "connected" || visibleModal || upgradeOpen) return;
    const request = armyCommandRequest(command_type, unitIds, targetId);
    if (!request) { notify("Chọn quân và mục tiêu hợp lệ trước khi ra lệnh.", "error"); return; }
    const alive = new Set(controllableTroops(useMatchStore.getState().entities, teamId).map(e => e.id));
    if (unitIds.some(id => !alive.has(id))) {
      notify("Nhóm quân đã thay đổi. Hãy kiểm tra và ra lệnh lại.", "info");
      setRetreatOpen(false); wsClient.requestSync(); return;
    }
    actionLock.current = true;
    setPending(true);
    try {
      const result = await api.armyCommand(matchId, {...request, idempotency_key: crypto.randomUUID()});
      setRetreatOpen(false);
      if (command_type !== "RETARGET") setCommandTargetId("");
      notify(`Đã ${command_type === "RETARGET" ? "đổi mục tiêu cho" : command_type === "DEFEND_BASE" ? "ra lệnh bảo vệ căn cứ cho" : "ra lệnh rút cho"} ${result.affected_count} quân.`, "success");
      wsClient.requestSync();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Không thể ra lệnh quân đội.", "error");
      setRetreatOpen(false);
      wsClient.requestSync();
    } finally { actionLock.current = false; setPending(false); }
  };
  const submitAnswer = async (answer: string) => {
    if (!matchId || !question || answerLock.current)
      throw new Error("Câu trả lời đang được xử lý.");
    answerLock.current = true;
    setAnswerPending(true);
    try {
      const q = await api.submitAnswer(matchId, question.id, answer);
      setQuestion(previous => previous?.id === q.id && (previous.timer?.version ?? 0) > (q.timer?.version ?? 0) ? previous : q);
      if (q.reward_options) setReward(q.reward_options);
      return q;
    } finally {
      answerLock.current = false;
      setAnswerPending(false);
    }
  };
  const claimReward = (type: RewardType, unitId?: string, key?: string) => {
    if (!matchId || !question)
      throw new Error("Không có phần thưởng đang chờ.");
    return api.claimReward(matchId, {
      team_question_id: question.id,
      reward_type: type,
      unit_type_id: unitId,
      idempotency_key: key,
    });
  };
  const rewardSuccess = (claim: RewardClaim) => {
    useMatchStore.setState({ coins: claim.team_coins });
    setModal(null);
    setReward(null);
    setQuestion(previous => previous ? {...previous, status: "REWARD_CLAIMED"} : null);
    notify(
      claim.reward_type === "COIN"
        ? claim.coin_amount === 60 ? "May mắn! Đội nhận được +60 coin!" : `Đội nhận được +${claim.coin_amount} coin!`
        : `Đã mở khóa ${claim.unlocked_unit?.name || "công nghệ mới"}.`,
      "success",
    );
    setRewardBurst(true);
    setTimeout(() => setRewardBurst(false), 1600);
    if (sound) playFeedback("success");
    void refreshRef.current().catch(() => {});
    wsClient.requestSync();
  };
  const viewerId = useRef(crypto.randomUUID());
  const quizOperation = useRef(false);
  const quizDismissed = useRef(false);
  const acceptQuestion = useCallback((q: TeamQuestion) => {
    setQuestion(previous => previous?.id === q.id && (previous.timer?.version ?? 0) > (q.timer?.version ?? 0) ? previous : q);
    setReward(q.reward_options || null);
  }, []);
  const closeQuiz = () => {
    if (answerLock.current) return;
    // Visibility never waits for a timer mutation. A pending OPEN must not reopen
    // a dialog dismissed while the next question was being assigned.
    quizDismissed.current = true;
    setModal(null);
    if (matchId && question?.status === "PENDING_QUESTION") {
      void api.questionAction(matchId, question.id, "CLOSE", viewerId.current)
        .then(q => {if ("id" in q) acceptQuestion(q);})
        .catch(() => { /* The original deadline continues even offline. */ });
    }
  };
  const openQuiz = async () => {
    if (!matchId || quizOperation.current) return;
    quizOperation.current = true;
    quizDismissed.current = false;
    try {
      const opened = await api.questionAction(matchId, question?.id || null, "OPEN_SESSION", viewerId.current);
      if (opened.previous_question_expired) notify("Câu hỏi trước đã hết thời gian; không có phần thưởng.");
      if ("id" in opened) {
        acceptQuestion(opened);
        if (!quizDismissed.current) setModal(opened.status === "PENDING_REWARD" ? "REWARD" : "QUESTION");
      } else notify("Đã hoàn thành bộ câu hỏi.");
    } catch (e) { notify(e instanceof Error ? e.message : "Không thể mở câu hỏi.", "error"); }
    finally { quizOperation.current = false; }
  };
  useEffect(() => {
    if (!matchId || !question || question.status !== "PENDING_QUESTION" || visibleModal !== "QUESTION" || !active) return;
    const id = question.id;
    let alive = true;
    const send = async (action: "HEARTBEAT" | "OPEN" | "CLOSE") => {
      try {
        const q = await api.questionAction(matchId, id, action, viewerId.current);
        if (alive && "id" in q) {
          acceptQuestion(q);
          if (action === "HEARTBEAT" && q.status === "PENDING_QUESTION" && q.timer?.status === "PAUSED" && !document.hidden && !quizOperation.current) {
            const resumed = await api.questionAction(matchId, id, "OPEN", viewerId.current);
            if (alive && "id" in resumed) acceptQuestion(resumed);
          }
        }
      } catch { /* Reconnect recovers the same absolute server deadline. */ }
    };
    const heartbeat = setInterval(() => { if (!document.hidden) void send("HEARTBEAT"); }, 4000);
    const visibility = () => { void send(document.hidden ? "CLOSE" : "OPEN"); };
    const pagehide = () => { void send("CLOSE"); };
    const connection = ({status}: {status: string}) => { if (status === "connected" && !document.hidden) void send("OPEN"); };
    wsClient.on("connection_change", connection);
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", pagehide);
    return () => {
      alive = false;
      clearInterval(heartbeat);
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", pagehide);
      wsClient.off("connection_change", connection);
      void send("CLOSE");
    };
  }, [matchId, question?.id, question?.status, visibleModal, active, acceptQuestion]);
  const special = (kind: "repair" | "scout" | "emp" | "upgrade") => {
    if (!matchId) return;
    const key = crypto.randomUUID();
    if (kind === "repair")
      void action(
        () => api.repairBase(matchId, { idempotency_key: key }),
        "Đã gia cố căn cứ.",
      );
    if (kind === "scout")
      void action(async () => {
        const res = await api.scout(matchId, {
          target_team_id: deploymentTargetId,
          idempotency_key: key,
        });
        setScout(res.scout_data);
      }, "Trinh sát hoàn tất.");
    if (kind === "emp" && selectedEntity)
      void action(
        () =>
          api.emp(matchId, {
            target_entity_id: selectedEntity.id,
            idempotency_key: key,
          }),
        "Đã vô hiệu hóa tháp đối thủ trong một vòng.",
      );
    if (kind === "upgrade" && selectedEntity)
      void action(
        () =>
          api.upgradeTower(matchId, {
            entity_id: selectedEntity.id,
            idempotency_key: key,
          }),
        "Đã nâng cấp tháp.",
      );
  };
  const sellAvailability = actionAvailability(availabilityContext, "SELL_TOWER");
  const sellableTower = selectedEntity?.entity_kind === "TOWER" && selectedEntity.team_id === teamId
    && ["ACTIVE", "DISABLED"].includes(selectedEntity.status) && selectedEntity.current_hp > 0;
  const sellPrice = selectedEntity ? towerSalePrice(selectedEntity, catalog.find(u => u.code === selectedEntity.unit_code)?.cost) : 0;
  const sellTower = async (entityId = selectedEntity?.id) => {
    const tower = store.entities.find(e => e.id === entityId);
    if (!matchId || !tower || tower.entity_kind !== "TOWER" || tower.team_id !== teamId
      || !["ACTIVE", "DISABLED"].includes(tower.status) || tower.current_hp <= 0
      || !sellAvailability.allowed || actionLock.current) return;
    actionLock.current = true;
    setPending(true);
    try {
      const result = await api.sellTower(matchId, {entity_id: tower.id, idempotency_key: crypto.randomUUID()});
      setInspected(null);
      notify(`Đã bán tháp, nhận ${result.refund} xu.`, "success");
      wsClient.requestSync();
      await refreshRef.current();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Không thể bán tháp.", "error");
      wsClient.requestSync();
    } finally { actionLock.current = false; setPending(false); }
  };
  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await root.current?.requestFullscreen();
    } catch {
      notify("Trình duyệt chưa cho phép chế độ toàn màn hình.");
    }
  };
  const myIndex = Math.max(0, teamIndex(mapData, teamId || ""));
  const troopCount = store.entities.filter(
    (e) => e.team_id === teamId && e.entity_kind === "UNIT",
  ).length;
  const unitCards = catalog.filter((u) => u.category === tab).map(u => ({ ...u,
    level: (teamId ? store.teamUpgradeLevels[teamId]?.[u.code] : undefined) ?? u.level,
  }));
  const specialAvailability = (kind: "repair" | "scout" | "emp" | "upgrade") => {
    const allowed = actionAvailability(availabilityContext, {repair:"REPAIR_BASE",scout:"SCOUT",emp:"EMP",upgrade:"UPGRADE_TOWER"}[kind]);
    if (!allowed.allowed) return allowed;
    if (!teamState?.special_actions_enabled[kind]) return {allowed:false, reason:"Thao tác này đã bị tắt trong cấu hình."};
    const cost = teamState.special_action_costs[kind];
    if (cost === undefined || coins < cost) return {allowed:false, reason:`Không đủ xu; cần ${cost ?? "—"}.`};
    if (kind === "repair" && (myTeam?.base_hp || 0) >= (myTeam?.initial_base_hp || 0)) return {allowed:false, reason:"Căn cứ đang đầy máu."};
    if (kind === "repair" && teamState.round_number === store.currentRound && teamState.limits.repairs_used_this_round > 0) return {allowed:false, reason:"Đã sửa chữa trong vòng này; chờ vòng kế tiếp."};
    if (kind === "emp" && (!selectedEntity || selectedEntity.team_id === teamId || selectedEntity.entity_kind !== "TOWER" || selectedEntity.status !== "ACTIVE")) return {allowed:false, reason:"Chọn một tháp địch đang hoạt động."};
    return {allowed:true, reason:""};
  };
  const statusText = pending
    ? "Đang chờ xác nhận…"
    : !commonAvailability.allowed
      ? commonAvailability.reason
      : selected
        ? selected.category === "TOWER"
          ? mapData?.placement_grid ? "Chọn vị trí trên lưới để xây tháp" : "Chọn ô xây tháp được đánh dấu"
          : "Chọn số lượng và mục tiêu, rồi bấm Xuất lính"
        : spectator
          ? "Bạn đang quan sát trận đấu"
          : `Vòng ${store.currentRound} · ${continuous && phase === "WAR" ? "Giao tranh liên tục" : "Lập kế hoạch"}: chọn quân hoặc công sự để chỉ huy`;

  return (
    <div className="woodland-game" ref={root}>
      <PhaserGame ref={phaser} state={sceneState} callbacks={callbacks} />
      {mapData && <ArenaNavigation ref={navigation} map={mapData} teams={teams} ownId={teamId} targetId={commandView === "ARMY" ? commandTargetId : deploymentTargetId}
        onSelect={id => { selectBase(id); phaser.current?.focusBase(id); }}
        onNavigate={(x,y) => phaser.current?.navigate(x,y)} onFit={() => phaser.current?.fit()}
        onOwn={() => phaser.current?.focusBase()} onCombat={() => phaser.current?.focusCombat()}
        onZoomIn={() => phaser.current?.zoomIn()} onZoomOut={() => phaser.current?.zoomOut()} />}

      <div className="game-vignette" />
      <header className="game-top">
        <div className="kingdom-panel fantasy-frame">
          <Link to="/" className="kingdom-crest" aria-label="Về trang chủ">
            <Shield size={28} />
            <span>TD</span>
          </Link>
          <div className="kingdom-info">
            <small>{spectator ? "ĐÀI QUAN SÁT" : "BẢO VỆ CĂN CỨ"}</small>
            <strong>{myTeam?.name || "Thủ thành chiến thuật"}</strong>
            <div className="kingdom-resources">
              <span>
                <Heart size={15} />
                {myTeam?.base_hp ?? "—"}
                <em>/{myTeam?.initial_base_hp ?? 500}</em>
              </span>
              <span className="gold">
                <Coins size={16} />
                {teamId && !loading ? coins : "—"}
                <em>xu</em>
              </span>
              {(myTeam?.base_shield || 0) > 0 && (
                <span>
                  <Shield size={14} />
                  {myTeam?.base_shield}
                </span>
              )}
            </div>
          </div>
          {rewardBurst && <span className="coin-burst">+ phần thưởng</span>}
        </div>
        <div className={`round-standard ${continuous ? "continuous-stage" : ""} ${isClimax ? "is-climax" : ""}`} data-stage={continuousStage || "legacy"}>
          <div className="standard-ornament">◆</div>
          <small>THUNG LŨNG LÁ XANH</small>
          <h1>Vòng {currentRound.toString().padStart(2, "0")}{continuous ? ` / ${totalRounds}` : ""}</h1>
          <span className="round-stage-line">
            <strong className="round-stage-label">{match?.status === "PAUSED" ? "ĐÃ TẠM DỪNG" : phaseTitle}</strong>
            {timerLabel && <b className="phase-clock">
              <small>{match?.status === "PAUSED" ? "CÒN LẠI" : continuousStage === "gathering" ? "VÒNG 1 BẮT ĐẦU SAU" : continuousStage === "resupply" ? `VÒNG ${currentRound} BẮT ĐẦU SAU` : continuousStage === "battle" || continuousStage === "climax" ? "VÒNG KẾT THÚC SAU" : ""}</small>
              {timerLabel}
            </b>}
          </span>
          {continuous && (active || match?.status === "PAUSED") && <small className={`phase-detail ${isClimax ? "climax-detail" : ""}`} aria-live="off">
            {match?.status === "PAUSED" ? "Đồng hồ và giao tranh đang tạm dừng"
              : continuousStage === "gathering" ? "Quân đang tập kết • có thể chọn quân và đổi mục tiêu"
                : continuousStage === "resupply" ? "Giao tranh vẫn tiếp diễn • có thể triển khai, xây dựng và rút quân"
                  : isClimax ? `Cao trào còn ${timerLabel} • bộ binh/xe tăng bắn nhanh +10% • tháp nhận 2/3 sát thương`
                    : continuousStage === "battle" && secondsUntilClimax !== null ? `Cao trào bắt đầu sau ${formatClock(secondsUntilClimax)}` : ""}
          </small>}
          {roundRemaining !== null && (
            <small className="planning-clock" aria-live="off">
              {match?.status === "PAUSED"
                ? `Tạm dừng · còn ${roundRemaining}s`
                : roundRemaining > 0 ? `Lập kế hoạch · giao tranh sau ${roundRemaining}s` : "Đang chờ máy chủ xử lý vòng"}
            </small>
          )}
          <div className="round-stitches" />
        </div>
        <div className="top-tools">
          <span
            className={`connection-dot ${store.connectionStatus}`}
            title={
              store.connectionStatus === "connected"
                ? "Đã kết nối máy chủ"
                : store.connectionStatus === "syncing"
                  ? "Đang đồng bộ trạng thái trận đấu"
                : !member && !getAuthToken()
                  ? "Chưa tham gia phòng"
                  : "Đang mất kết nối"
            }
          >
            <Radio size={13} />
            <span>
              {store.connectionStatus === "connected"
                ? "Trực tuyến"
                : store.connectionStatus === "syncing"
                  ? "Đang đồng bộ"
                : !member && !getAuthToken()
                  ? "Chưa tham gia"
                  : "Đang kết nối"}
            </span>
          </span>
          <div className="tool-buttons">
            <button
              className="game-icon"
              title={sound ? "Tắt âm thanh" : "Bật âm thanh"}
              aria-label={sound ? "Tắt âm thanh" : "Bật âm thanh"}
              onClick={() => {
                setSound(!sound);
                if (!sound) playFeedback("select");
              }}
            >
              {sound ? <Volume2 /> : <VolumeX />}
            </button>
            <button
              className="game-icon"
              title="Cài đặt & hướng dẫn"
              aria-label="Cài đặt & hướng dẫn"
              onClick={() =>
                setDrawer(drawer === "SETTINGS" ? null : "SETTINGS")
              }
            >
              <Settings />
            </button>
            <button
              className="game-icon"
              title="Toàn màn hình"
              aria-label="Toàn màn hình"
              onClick={toggleFullscreen}
            >
              {fullscreen ? <Minimize /> : <Maximize />}
            </button>
          </div>
        </div>
      </header>
      {phaseBanner && <div className={`phase-transition-banner ${phaseBanner.tone}`} role="status" aria-live="polite">
        <strong>{phaseBanner.title}</strong>
        <span>{phaseBanner.detail}</span>
      </div>}
      {match?.status === "FINISHED" && (
        <div className="match-outcome fantasy-frame" role="status">
          <strong>Trận đấu đã kết thúc</strong>
          <Link to={`/results/${matchId}`}>Xem kết quả và bảng xếp hạng →</Link>
        </div>
      )}
      <div className="battle-team-sidebar">
      <aside className="team-banners" aria-label="Các căn cứ">
        {teams.filter(t => teams.length <= 6 || t.id === teamId || t.id === deploymentTargetId).map((t) => { const i = teams.findIndex(team => team.id === t.id); return (
          <button
            key={t.id}
            className={`team-banner ${t.id === deploymentTargetId ? "targeted" : ""} ${t.status === "ELIMINATED" ? "eliminated" : ""}`}
            style={{ "--team-color": PALETTE[i % PALETTE.length] } as React.CSSProperties}
            onClick={() => {
              selectBase(t.id);
            }}
            aria-label={`Xem căn cứ ${t.name}`}
          >
            <Shield size={16} />
            <div>
              <strong>{teamLabel(i)} · {t.name}</strong>
              <span>
                <i
                  style={{
                    width: `${Math.max(0, t.base_hp / t.initial_base_hp) * 100}%`,
                  }}
                />
              </span>
            </div>
            <small>{t.base_hp}</small>
            {t.id === teamId && <em>BẠN</em>}
          </button>
        ); })}
      </aside>
      </div>
      <button
        aria-describedby={store.questionProgress ? "quest-team-progress" : undefined}
        aria-label={
          question?.status === "PENDING_REWARD"
            ? "Nhận phần thưởng"
            : question?.status === "PENDING_QUESTION"
              ? "Mở câu hỏi tri thức"
              : question ? "Xem kết quả câu hỏi" : "Mở thử thách kiến thức"
        }
        title={!actionAvailability(availabilityContext, "ANSWER_QUESTION").allowed
          ? actionAvailability(availabilityContext, "ANSWER_QUESTION").reason
          : question ? "Mở câu hỏi hoặc nhận phần thưởng" : "Mở thử thách kiến thức tiếp theo"}
        className={`quest-card fantasy-frame ${question?.status === "PENDING_REWARD" ? "reward-ready" : ""}`}
        disabled={!actionAvailability(availabilityContext, "ANSWER_QUESTION").allowed}
        onClick={() => void openQuiz()}
      >
        <span className="quest-book">
          <BookOpen size={27} />
          {question && <i />}
        </span>
        <span>
          <small>NHIỆM VỤ TRI THỨC</small>
          <strong>
            {question?.status === "PENDING_REWARD"
              ? "Nhận phần thưởng"
              : question?.status === "PENDING_QUESTION"
                ? "Câu hỏi đang chờ"
                : question ? "Xem kết quả câu hỏi" : "Bắt đầu thử thách"}
          </strong>
          <em>
            {store.questionProgress
              ? `${store.questionProgress.answered}/${store.questionProgress.total} đã trả lời · ${store.questionProgress.correct} đúng · ${store.questionProgress.remaining} còn lại`
              : question?.status === "PENDING_REWARD"
              ? "Chọn xu hoặc công nghệ"
              : question ? "Trả lời đúng · Nhận xu hoặc mở khóa" : "Mở câu hỏi để nhận phần thưởng cho đội"}
          </em>
        </span>
        <ChevronRight size={18} />
        {store.questionProgress && <b id="quest-team-progress" className="quest-progress-badge"
          aria-label={`${store.questionProgress.answered}/${store.questionProgress.total} đã trả lời, ${store.questionProgress.correct} đúng, ${store.questionProgress.remaining} còn lại`}>
          {store.questionProgress.answered}/{store.questionProgress.total}
        </b>}
      </button>
      {!member && !getAuthToken() && details && (
        <Link
          className="join-battle-link gold-button"
          to={`/join?code=${details.room_code}`}
        >
          Tham gia trận đấu <ChevronRight size={15} />
        </Link>
      )}
      <div className="camera-tools">
        <button className="game-icon" aria-label="Phóng to" title="Phóng to" onClick={() => phaser.current?.zoomIn()}><ZoomIn /></button>
        <button className="game-icon" aria-label="Thu nhỏ" title="Thu nhỏ" onClick={() => phaser.current?.zoomOut()}><ZoomOut /></button>
        <button
          className="game-icon"
          aria-label="Xem toàn bản đồ"
          title="Xem toàn bản đồ"
          onClick={() => phaser.current?.fit()}
        >
          <Focus />
        </button>
        <button
          className="game-icon"
          disabled={!teamId}
          aria-label="Về căn cứ của đội"
          title="Về căn cứ của đội"
          onClick={() => phaser.current?.focusBase()}
        >
          <Home />
        </button>
        <span>
          Kéo để di chuyển
          <br />
          Cuộn để thu phóng
        </span>
      </div>
      {toast && (
        <div className={`game-toast ${toast.kind}`} role="status">
          {toast.kind === "success" ? (
            <Check size={18} />
          ) : (
            <ScrollText size={18} />
          )}
          <span>{toast.text}</span>
          <button aria-label="Đóng thông báo" onClick={() => setToast(null)}>
            <X size={15} />
          </button>
        </div>
      )}
      {(loading || loadError || !matchId) && (
        <div className="battle-state fantasy-frame">
          <Shield size={40} />
          <h2>
            {loading
              ? "Đang mở cổng chiến trường…"
              : loadError
                ? "Chưa vào được chiến trường"
                : "Chiến trường đang chờ bạn"}
          </h2>
          <p>
            {loadError ||
              (!loading
                ? "Tạo hoặc tham gia phòng để bắt đầu cuộc chiến cùng đồng đội."
                : "Đang tải bản đồ và trạng thái từ máy chủ.")}
          </p>
          {loadError ? (
            <button
              className="gold-button"
              onClick={() => {
                setLoading(true);
                setLoadError("");
                void refreshRef
                  .current()
                  .catch((e) => setLoadError(e.message))
                  .finally(() => setLoading(false));
              }}
            >
              Thử lại
            </button>
          ) : (
            !loading && (
              <Link className="gold-button" to="/join">
                Vào phòng đấu <ChevronRight size={16} />
              </Link>
            )
          )}
        </div>
      )}
      {drawer && (
        <aside className="game-drawer fantasy-frame">
          <div className="drawer-heading">
            <h2>
              {drawer === "TEAMS"
                ? "Các đội tham chiến"
                : drawer === "LOG"
                  ? "Nhật ký chiến trường"
                  : "Tùy chọn chiến trường"}
            </h2>
            <button
              className="plain-close"
              aria-label="Đóng bảng"
              onClick={() => setDrawer(null)}
            >
              <X size={20} />
            </button>
          </div>
          {drawer === "TEAMS" && <TeamDirectory teams={teams} ownId={teamId} targetId={deploymentTargetId}
            onSelect={id => {
              selectBase(id);
              phaser.current?.focusBase(id);
              setDrawer(null);
            }} />}
          {drawer === "LOG" && (
            <div className="combat-log">
              {store.combatLogs.length ? (
                store.combatLogs.slice(0, 50).map((e, i) => (
                  <div key={i}>
                    <small>VÒNG {e.round_number || store.currentRound}</small>
                    <span>
                      {(
                        {
                          UNIT_MOVED: "Quân tiến lên tuyến trước",
                          TOWER_ATTACKED: "Tháp phòng thủ khai hỏa",
                          UNIT_ATTACKED: "Các đơn vị giao tranh",
                          BASE_DAMAGED: "Căn cứ trúng đòn",
                          ENTITY_DESTROYED: "Một đơn vị bị tiêu diệt",
                          INCOME_AWARDED: "Đội nhận thu nhập",
                          SHIELD_GENERATED: "Khiên bảo vệ được kích hoạt",
                        } as Record<string, string>
                      )[e.type] || e.type}
                    </span>
                    {(e.hp_damage ?? e.damage) !== undefined && (
                      <b>−{e.hp_damage ?? e.damage} HP</b>
                    )}
                  </div>
                ))
              ) : (
                <p>Chưa có giao tranh trong trận đấu này.</p>
              )}
            </div>
          )}
          {drawer === "SETTINGS" && (
            <div className="settings-content">
              <p>
                Chọn thẻ quân hoặc công sự, sau đó chọn vị trí được đánh dấu
                trên bản đồ. Khi đang chọn lính, bấm căn cứ đối thủ để chọn mục tiêu cho lính mới. Dùng bảng Chỉ huy để đổi hướng quân đã xuất.
              </p>
              <p>
                Kéo chuột hoặc một ngón để di chuyển. Cuộn chuột hoặc chụm hai
                ngón để thu phóng. Phím Esc hủy lựa chọn.
              </p>
              <button
                className="drawer-team"
                onClick={() => {
                  wsClient.requestSync();
                  void refreshRef
                    .current()
                    .catch((e) => notify(e.message, "error"));
                }}
              >
                <Radio size={18} />
                Đồng bộ lại với máy chủ
              </button>
              {hasHost && matchId && (
                <>
                  <button
                    className="drawer-team"
                    onClick={async () => {
                      try {
                        if (match?.status === "PAUSED")
                          await api.resumeMatch(matchId);
                        else await api.pauseMatch(matchId);
                        wsClient.requestSync();
                      } catch (e) {
                        notify(
                          e instanceof Error
                            ? e.message
                            : "Không đổi được trạng thái.",
                          "error",
                        );
                      }
                    }}
                  >
                    {match?.status === "PAUSED" ? (
                      <Play size={18} />
                    ) : (
                      <Pause size={18} />
                    )}{" "}
                    {match?.status === "PAUSED"
                      ? "Tiếp tục trận đấu"
                      : "Tạm dừng trận đấu"}
                  </button>
                  <button
                    className="drawer-team"
                    disabled={continuous || pending || playing || !active}
                    onClick={async () => {
                      if (actionLock.current) return;
                      actionLock.current = true;
                      setPending(true);
                      try {
                        await api.resolveCombat(matchId, store.currentRound);
                      } catch (e) {
                        notify(
                          e instanceof Error
                            ? e.message
                            : "Không bắt đầu được vòng chiến đấu.",
                          "error",
                        );
                      } finally {
                        actionLock.current = false;
                        setPending(false);
                      }
                    }}
                  >
                    <Swords size={18} />
                    Bắt đầu vòng tiếp theo
                  </button>
                  <Link className="drawer-team" to="/host">
                    <Settings size={18} />
                    Bảng điều khiển Host
                  </Link>
                </>
              )}
              <Link className="drawer-team" to="/lobby">
                <ArrowLeft size={18} />
                Về phòng chờ
              </Link>
            </div>
          )}
        </aside>
      )}
      {scout && (
        <aside className="scout-report fantasy-frame">
          <button
            className="plain-close"
            aria-label="Đóng báo cáo"
            onClick={() => setScout(null)}
          >
            <X size={18} />
          </button>
          <Crosshair size={23} />
          <h3>Trinh sát: {scout.target_team_name}</h3>
          <p>
            {scout.towers?.length
              ? `${scout.towers.length} công sự được phát hiện`
              : "Không phát hiện công sự"}
          </p>
          {scout.towers?.map((t, i) => (
            <small key={i}>
              {NAMES[t.code] || t.name} · {t.hp} HP <UnitLevelStars level={t.level} size="compact" />
            </small>
          ))}
        </aside>
      )}
      <footer className="command-area">
        <div className="command-status">
          <span className={pending ? "status-pending" : ""}>
            <i />
            {statusText}
          </span>
          {playing ? (
            <button onClick={() => phaser.current?.skipCombat()}>
              <SkipForward size={14} />
              Bỏ qua diễn hoạt
            </button>
          ) : selected ? (
            <button onClick={() => setSelected(null)}>
              <X size={14} />
              Hủy chọn <kbd>Esc</kbd>
            </button>
          ) : (
            <small>PHÒNG {match?.room_code || "—"}</small>
          )}
        </div>
        {armyMenu && selectedArmy.length > 0 && <ArmyContextMenu
          position={armyMenu} selected={selectedArmy} enemies={enemies} targetsOnly={armyMenu.targetsOnly}
          onDefend={() => {setArmyMenu(null); void issueArmyCommand("DEFEND_BASE");}}
          canRetarget={armyBattle || armyGathering || armyRetreatPrep} canRetreat={!armyGathering}
          disabled={pending || store.connectionStatus !== "connected"}
          onClose={() => setArmyMenu(null)}
          onAttack={targetId => {
            setArmyMenu(null); setCommandTargetId(targetId);
            void issueArmyCommand("RETARGET", selectedArmy.map(unit => unit.id), targetId);
          }}
          onRetreat={() => {
            setArmyMenu(null); setDockCollapsed(false);
            if (selectedArmy.length > 1 && selectedArmy.length === friendlyTroops.length) {
              setRetreatSnapshot(selectedArmy.map(unit => unit.id)); setRetreatOpen(true);
            } else void issueArmyCommand("RETREAT_ALL");
          }}
          onClear={() => {setArmyMenu(null); setSelectedArmyIds([]); setInspected(null);}} />}
        {armySelectionEnabled && commandView !== "ARMY" && <nav className="command-context-tabs" aria-label="Tác vụ quân đội">
          <button className="dock-collapse-toggle" aria-expanded={!dockCollapsed} aria-controls="battle-command-dock"
            onClick={() => setDockCollapsed(value => !value)}>{dockCollapsed ? "Mở lệnh" : "Thu gọn"}</button>
        </nav>}
        <div id="battle-command-dock" hidden={dockCollapsed && armySelectionEnabled && commandView !== "ARMY"} className={`command-dock fantasy-frame ${commandView === "ARMY" && armySelectionEnabled ? "army-active" : `purchase-active ${tab === "UNIT" ? "unit-purchase" : ""}`}`}>
          {commandView !== "ARMY" || !armySelectionEnabled ? <>
          <div className="command-category">
            <button
              className={tab === "UNIT" ? "active" : ""}
              onClick={() => {
                setTab("UNIT");
                setSelected(null);
              }}
            >
              <Swords size={21} />
              <span>QUÂN ĐỘI</span>
            </button>
            <button
              className={tab === "TOWER" ? "active" : ""}
              onClick={() => {
                setTab("TOWER");
                setSelected(null);
              }}
            >
              <Shield size={21} />
              <span>CÔNG SỰ</span>
            </button>
            <button disabled={spectator || !!visibleModal || !active} onClick={() => {setUpgradeSelection({entityType: catalog.find(u => u.upgrade?.eligible)?.code}); void refreshRef.current().catch(() => {});}}><Wrench size={21}/><span>NÂNG CẤP</span></button>
            {/* <button
              className={tab === "SPECIAL" ? "active" : ""}
              onClick={() => {
                setTab("SPECIAL");
                setSelected(null);
              }}
            >
              <Zap size={21} />
              <span>CHIẾN THUẬT</span>
            </button> */}
          </div>
          <div className="arsenal">
            {tab !== "SPECIAL" ? (
              unitCards.map((u) => {
                const unlocked = u.is_starter || u.is_unlocked || store.unlockedUnits.includes(u.code);
                const availability = purchaseAvailability(availabilityContext, u);
                return (
                  <button
                    key={u.id}
                    className={`arsenal-card game-item-card ${u.category === "TOWER" ? "fortification-card" : ""} ${selected?.id === u.id ? "selected" : ""} ${!unlocked ? "locked" : ""}`}
                    disabled={!availability.allowed}
                    data-reason-code={availability.reason_code || ""}
                    aria-pressed={selected?.id === u.id}
                    aria-label={`${NAMES[u.code] || u.name} · ${unlocked ? `${u.cost} xu` : "Mở khóa"} · Cấp ${upgradeLevel(u.level)} trên 3`}
                    title={availability.reason || undefined}
                    onClick={() => selectUnit(u)}
                    onMouseEnter={e => inspectEntity(u.id, e.currentTarget.getBoundingClientRect().left, e.currentTarget.getBoundingClientRect().top - 270, false, u)}
                    onMouseLeave={() => inspectEntity(null, 0, 0)}
                    onFocus={e => inspectEntity(u.id, e.currentTarget.getBoundingClientRect().left, e.currentTarget.getBoundingClientRect().top - 270, false, u)}
                    onBlur={() => inspectEntity(null, 0, 0)}
                  >
                    <GameItemCardContent unit={u} teamIndex={myIndex} unlocked={unlocked} />
                    {selected?.id === u.id && (
                      <span className="card-check" aria-hidden="true">
                        <Check size={11} />
                      </span>
                    )}
                  </button>
                );
              })
            ) : (
              <div className="special-cards">
                {(["repair", "scout", "emp"] as const).map((kind) => {
                  const cost = teamState?.special_action_costs[kind];
                  const availability = specialAvailability(kind);
                  return (
                    <button
                      key={kind}
                      className="special-card"
                      disabled={!availability.allowed}
                      title={availability.reason || ""}
                      onClick={() => special(kind)}
                    >
                      {kind === "repair" ? (
                        <Wrench />
                      ) : kind === "scout" ? (
                        <Crosshair />
                      ) : (
                        <Zap />
                      )}
                      <strong>
                        {kind === "repair"
                          ? "Gia cố"
                          : kind === "scout"
                            ? "Trinh sát"
                            : "Xung EMP"}
                      </strong>
                      <span>
                        <Coins size={13} />
                        {cost ?? "—"}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <div className="selection-info">
            {selectedEntity || (selected?.category !== "UNIT" && selected) || inspectedTeam ? (
              <>
                <div className="selection-title">
                  <small>
                    {selectedEntity
                      ? "ĐƠN VỊ ĐANG CHỌN"
                      : inspectedTeam
                        ? "THÔNG TIN CĂN CỨ"
                        : selected?.category === "TOWER"
                          ? "BẢN VẼ CÔNG SỰ"
                          : "SẴN SÀNG TRIỂN KHAI"}
                  </small>
                  <h2>
                    {inspectedTeam?.name ||
                      NAMES[
                        selectedEntity?.unit_code || selected?.code || ""
                      ] ||
                      selectedEntity?.unit_name ||
                      selected?.name}
                  </h2>
                </div>
                <div className="selection-stats">
                  <span>
                    <Heart size={14} />
                    {inspectedTeam
                      ? inspectedTeam.base_hp
                      : selectedEntity
                        ? `${selectedEntity.current_hp}/${selectedEntity.max_hp}`
                        : selectedStats?.hp}
                  </span>
                  {!inspectedTeam && (
                    <>
                      <span>
                        <Swords size={14} />
                        {selectedEntity?.damage ?? selectedStats?.damage ?? "—"}
                      </span>
                      <span>
                        <Crosshair size={14} />
                        {selectedEntity?.range ?? selectedEntity?.simulation_state?.attack_range ?? selectedStats?.range ?? "—"}
                        <em>node</em>
                      </span>
                      {(selectedEntity?.entity_kind === "UNIT" || selected?.category === "UNIT") && (
                        <span>Tốc độ {selectedEntity?.movement_speed ?? selectedStats?.movement_speed ?? "—"}</span>
                      )}
                    </>
                  )}
                </div>
                {selected && selected.category === "TOWER" && (
                  <div className="slot-controls">
                    <span>{mapData?.placement_grid ? <>{NAMES[selected.code] || selected.name} <UnitLevelStars level={selectedStats?.level ?? selected.level} size="compact" /> · {selected.cost} xu · Tầm {selected.range}</> : "Ô xây dựng"}</span>
                    {mapData?.placement_grid && <small>Di chuyển chuột đến vị trí muốn xây và nhấp để đặt trụ. Chạm hai lần cùng ô để xây. Kéo để di chuyển, chụm để thu phóng.</small>}
                    <button onClick={() => setSelected(null)}>Hủy xây (Esc)</button>
                    {availableSlots.map((id) => (
                      <button
                        key={id}
                        disabled={blocked || !canBuild || !purchaseAvailability(availabilityContext, selected).allowed}
                        onClick={() => place(id)}
                      >
                        Vị trí {id.match(/slot(\d+)/)?.[1]}
                      </button>
                    ))}
                    {!mapData?.placement_grid && !availableSlots.length && <small>Không còn ô trống</small>}
                  </div>
                )}
                {selectedEntity && (
                  <p className="entity-status">
                    {teams.find((t) => t.id === selectedEntity.team_id)?.name} ·{" "}
                    {selectedEntity.status === "QUEUED"
                      ? "Đang tập kết"
                      : selectedEntity.status === "DISABLED"
                        ? "Đang bị vô hiệu hóa"
                        : "Đang hoạt động"}
                    {selectedEntity.entity_kind === "TOWER" &&
                      <UnitLevelStars level={selectedEntity.level} size="compact" />}
                  </p>
                )}
                {selectedEntity && selectedUpgradeType && <button className="upgrade-button" disabled={blocked || selectedEntity.level >= MAX_UPGRADE_LEVEL} onClick={() => setUpgradeSelection({entityType: selectedUpgradeType, sourceEntityId: selectedEntity.id})}>{selectedEntity.level >= MAX_UPGRADE_LEVEL ? "CẤP TỐI ĐA" : "NÂNG CẤP TOÀN ĐỘI"} <UnitLevelStars level={selectedEntity.level} size="compact" /></button>}
                {sellableTower && <button className="upgrade-button" disabled={!sellAvailability.allowed}
                  title={sellAvailability.reason || "Giá xây gốc × HP còn lại / HP tối đa, làm tròn xuống"}
                  onClick={() => void sellTower()}>BÁN THÁP · +{sellPrice} XU</button>}
                {inspectedTeam && (
                  <p className="entity-status">
                    Khiên {inspectedTeam.base_shield} ·{" "}
                    {inspectedTeam.status === "ELIMINATED"
                      ? "Đã bị loại"
                      : inspectedTeam.id === teamId
                        ? "Căn cứ của đội bạn"
                        : "Căn cứ đối thủ"}
                  </p>
                )}
              </>
            ) : (
              <div className="command-empty">
                <span className="empty-crest">
                  <Swords size={24} />
                </span>
                <div>
                  <small>BẢNG CHỈ HUY</small>
                  <h2>
                    {spectator ? "Quan sát chiến trường" : "Sẵn sàng, chỉ huy!"}
                  </h2>
                  <p>
                    {spectator
                      ? "Chọn một căn cứ hoặc đơn vị để xem thông tin."
                      : "Tập hợp quân đội. Xây dựng phòng tuyến."}
                  </p>
                </div>
              </div>
            )}
          </div>
          </> : <div className="army-dock-content">
            <ArmyCommandPanel troops={friendlyTroops} selected={selectedArmy} enemies={enemies}
              onAttack={targetId => {
                setArmyMenu(null); setCommandTargetId(targetId);
                void issueArmyCommand("RETARGET", selectedArmy.map(unit => unit.id), targetId);
              }}
              onSelectGroup={ids => {
                setSelected(null); setInspected(null); setCommandTargetId("");
                setSelectedArmyIds(ids); setArmySelectionMode(false); setMultipleSelection(false);
              }}
              onClear={() => {setSelectedArmyIds([]); setInspected(null); setCommandTargetId(""); setArmySelectionMode(false); setMultipleSelection(false);}}
              multiple={multipleSelection} onMultiple={() => {setMultipleSelection(value => !value); setArmySelectionMode(false);}}
              selectionMode={armySelectionMode} onSelectionMode={() => {setArmySelectionMode(value => !value); setMultipleSelection(false);}}
              onDefend={() => {setArmyMenu(null); void issueArmyCommand("DEFEND_BASE");}}
              canRetarget={armyBattle || armyGathering || armyRetreatPrep} canRetreat={!armyGathering}
              disabled={pending || !!visibleModal || upgradeOpen || !!targetPicker || store.connectionStatus !== "connected"}
              onSelectedRetreat={() => {
                setArmyMenu(null);
                if (selectedArmy.length > 1 && selectedArmy.length === friendlyTroops.length) {
                  setRetreatSnapshot(selectedArmy.map(unit => unit.id)); setRetreatOpen(true);
                } else void issueArmyCommand("RETREAT_ALL");
              }}
              onRetreat={() => void issueArmyCommand("RETREAT_ALL", retreatSnapshot)}
              retreatOpen={retreatOpen} retreatCount={retreatSnapshot.length}
              onRetreatOpen={open => {if (open) setRetreatSnapshot(friendlyTroops.map(e => e.id)); setRetreatOpen(open);}}
              onUpgrade={selectedEntity && selectedUpgradeType ? () => setUpgradeSelection({entityType: selectedUpgradeType, sourceEntityId: selectedEntity.id}) : undefined}
              upgradeDisabled={blocked || !!selectedEntity && selectedEntity.level >= MAX_UPGRADE_LEVEL} />
          </div>}
          <div className="command-meta">
            <div>
              <span title="Bộ binh không giới hạn. Giới hạn xe và pháo nằm trong bảng triển khai.">
                <Swords size={14} />
                {troopCount}
                <em>/∞</em>
              </span>
              <span>
                <Shield size={14} />
                {occupied.length}
                <em>/∞</em>
              </span>
            </div>
            <button
              aria-label="Xem các đội"
              onClick={() => setDrawer(drawer === "TEAMS" ? null : "TEAMS")}
            >
              <Flag size={16} />
              <span>Các đội</span>
            </button>
            <button
              aria-label="Xem nhật ký chiến trường"
              onClick={() => setDrawer(drawer === "LOG" ? null : "LOG")}
            >
              <ScrollText size={16} />
              <span>Nhật ký</span>
            </button>
          </div>
        </div>
        <div className="bottom-inscription">
          <span>THỦ THÀNH · CHIẾN THUẬT & TRI THỨC</span>
          {/* <span>
            {match?.status === "FINISHED" ? (
              <Link to={`/results/${matchId}`}>Xem kết quả trận đấu →</Link>
            ) : (
              "Đồng đội cùng nhau. Căn cứ vững vàng."
            )}
          </span> */}
        </div>
      </footer>
      {selected?.category === "UNIT" && commandView === "DEPLOY" && (
        <div className="deployment-modal-backdrop" onMouseDown={event => {
          if (event.target === event.currentTarget) setSelected(null);
        }}>
          <section className="deployment-modal fantasy-frame" ref={deploymentDialog} role="dialog" aria-modal="true" aria-labelledby="deployment-modal-title" tabIndex={-1}>
            <header className="deployment-modal-header">
              <EntityIllustration code={selected.code} name={NAMES[selected.code] || selected.name} category={selected.category} level={selectedStats?.level ?? 1} teamIndex={myIndex} />
              <div>
                <small>SẴN SÀNG TRIỂN KHAI</small>
                <h2 id="deployment-modal-title">{NAMES[selected.code] || selected.name}</h2>
                <div className="deployment-modal-stats">
                  <span><Heart size={14} /> {selectedStats?.hp ?? "—"} HP</span>
                  <span><Swords size={14} /> {selectedStats?.damage ?? "—"} sát thương</span>
                  <span><Crosshair size={14} /> {selectedStats?.range ?? "—"} tầm</span>
                  <span>Tốc độ {selectedStats?.movement_speed ?? "—"}</span>
                </div>
              </div>
              <button className="deployment-modal-close" aria-label="Đóng cửa sổ xuất lính" onClick={() => setSelected(null)}><X size={18} /></button>
            </header>
            <div className="deployment-modal-body">
              <DeploymentQuantity value={quantityInput} maximum={maximumQuantity} cost={selected.cost}
                coins={coins} disabled={pending} onChange={setQuantityInput}
                reason={!deploymentAvailability.allowed ? deploymentAvailability.reason : undefined} />
              <div className="deployment-modal-target">
                <label htmlFor="deployment-order">Nhiệm vụ của lính/xe mới</label>
                <select id="deployment-order" className="target-picker" value={deploymentOrder}
                  disabled={pending} onChange={event => setDeploymentOrder(event.target.value as "ATTACK" | "DEFEND_BASE")}>
                  <option value="ATTACK">Tấn công đối thủ</option>
                  <option value="DEFEND_BASE">Bảo vệ căn cứ</option>
                </select>
                {deploymentOrder === "DEFEND_BASE" ? <span>Quân mới sẽ bảo vệ căn cứ và đánh chặn quân địch ở gần.</span> : <>
                <span>Mục tiêu tấn công của lính mới</span>
                <button className="target-picker" onClick={() => { setDrawer(null); setTargetPicker("DEPLOY"); }} aria-label="Chọn mục tiêu cho lính mới">
                  ◎ {teams.find(team => team.id === deploymentTargetId)?.name || "Chọn đối thủ"} ▾
                </button>
                </>}
                <button className="gold-button" disabled={blocked || !canDeploy || (deploymentOrder === "ATTACK" && !deploymentTargetId) || !deploymentAvailability.allowed}
                  onClick={() => place(`node_spawn_t${myIndex + 1}`)}>
                  Xuất {Number.isSafeInteger(quantity) && quantity > 0 ? quantity : "—"} {NAMES[selected.code] || selected.name} → {deploymentOrder === "DEFEND_BASE" ? "Bảo vệ căn cứ" : teams.find(team => team.id === deploymentTargetId)?.name || "Chọn đối thủ"}
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
      {targetPicker && <AttackTargetPicker enemies={enemies}
        target={targetPicker === "DEPLOY" ? deploymentTargetId : commandTargetId}
        title={targetPicker === "DEPLOY" ? "Mục tiêu cho lính mới" : `Đổi mục tiêu cho ${selectedArmy.length} quân`}
        onClose={() => setTargetPicker(null)} onSelect={id => {
          if (targetPicker === "DEPLOY") setDeploymentTargetId(id); else setCommandTargetId(id);
          setTargetPicker(null);
        }} />}
      {upgradeOpen && <TeamUpgradeModal units={catalog} coins={coins} teamIndex={myIndex}
        selectedType={upgradeSelection?.entityType} onSelectType={entityType => setUpgradeSelection(previous => previous ? {...previous, entityType} : null)}
        disabled={!actionAvailability({...availabilityContext, modal: false}, "UPGRADE_TEAM_TYPE").allowed || teamState?.special_actions_enabled.upgrade === false}
        onClose={() => setUpgradeSelection(null)} onPurchase={async (unit, key) => {
          if (!matchId) return;
          await api.upgradeTeamType(matchId, {entity_type: unit.code, expected_current_level: unit.level ?? 1, idempotency_key: key});
          await refreshRef.current();
          wsClient.requestSync();
        }}/>}
      <EntityInfoCard hidden={!!visibleModal || upgradeOpen || !!targetPicker || retreatOpen || commandView === "ARMY" || mode === "BUILD"}
        onSell={id => sellTower(id)} sellDisabled={!sellAvailability.allowed} catalog={catalog} />
      <QuestionModal
        isOpen={visibleModal === "QUESTION"}
        questionState={question}
        totalQuestions={store.questionProgress?.total}
        onSubmitAnswer={submitAnswer}
        onRewardTrigger={(opts) => {
          setReward(opts);
          setModal("REWARD");
        }}
        onClose={() => void closeQuiz()}
        onNextQuestion={openQuiz}
        matchEnded={match?.status === "FINISHED"}
        isSubmitting={answerPending}
      />
      <RewardSelectionModal
        isOpen={visibleModal === "REWARD"}
        rewardOptions={reward}
        matchEnded={match?.status === "FINISHED"}
        unlockedCodes={store.unlockedUnits}
        onClaimReward={claimReward}
        onClose={() => setModal(null)}
        onSuccess={rewardSuccess}
        onRevealChange={setRewardRevealing}
      />
    </div>
  );
}
