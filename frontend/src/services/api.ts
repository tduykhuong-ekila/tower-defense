import {
  CreateMatchResponse,
  JoinMatchResponse,
  Match,
  MatchConfig,
  RoomConstraints,
  Team,
  TeamMember,
} from "../types/match";
import { TeamQuestion } from "../types/question";
import { QuestionBankPreview } from "../types/questionBank";
import { RewardClaim, RewardOptions } from "../types/reward";
import { acceptBrowserSessionEvent, getBrowserSessionId } from "../security/browserSession";
import { GameAction, GameEntity, TeamState, UnitType } from "../types/unit";
import {
  BalancePreview,
  HostTelemetry,
  MatchPreset,
  MatchResultsApiResponse,
} from "../types/combat";

const API_BASE = "/api/v1";

const PARTICIPANT_TOKEN_KEY = "tower_participant_token";
const HOST_TOKEN_KEY = "tower_host_token";
const HOST_SESSIONS_KEY = "tower_host_sessions";
const ACTIVE_MEMBER_KEY = "tower_active_member";
let lastMatchId: string | undefined;
export const getActiveApiMatchId = () => lastMatchId;

type SavedHostSession = Pick<Match, "id" | "name" | "room_code"> & { token: string };

export function getSavedHostSessions(): SavedHostSession[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(HOST_SESSIONS_KEY) || "[]");
    return Array.isArray(value) ? value.filter((entry): entry is SavedHostSession =>
      entry && typeof entry.id === "string" && typeof entry.name === "string" &&
      typeof entry.room_code === "string" && typeof entry.token === "string",
    ) : [];
  } catch {
    return [];
  }
}

export function getParticipantToken(): string | null {
  return sessionStorage.getItem(PARTICIPANT_TOKEN_KEY);
}

export function setParticipantToken(token: string): void {
  sessionStorage.setItem(PARTICIPANT_TOKEN_KEY, token);
}

// Host credentials are used only in an explicitly opened Host session.
export function isHostMode(): boolean {
  return (
    typeof window !== "undefined" && (
      new URLSearchParams(window.location.search || "").get("host") === "1" ||
      (window.location.pathname || "").startsWith("/host"))
  );
}

// WebSocket identity follows the same explicit Host mode as API requests.
export const getAuthToken = () =>
  isHostMode() ? getHostToken() : getParticipantToken();
export const setAuthToken = setParticipantToken;

export function clearParticipantToken(): void {
  sessionStorage.removeItem(PARTICIPANT_TOKEN_KEY);
  sessionStorage.removeItem(ACTIVE_MEMBER_KEY);
}

export function getHostToken(matchId?: string): string | null {
  const targetId = matchId || (typeof window !== "undefined"
    ? window.location.pathname?.match(/^\/(?:battle|lobby|results)\/([^/]+)/)?.[1]
    : undefined);
  if (targetId) {
    const saved = getSavedHostSessions().find((entry) => entry.id === targetId);
    if (saved) return saved.token;
  }
  const token = sessionStorage.getItem(HOST_TOKEN_KEY);
  try {
    // Migrate existing open host tabs, and recover after a tab/browser closes.
    if (token) localStorage.setItem(HOST_TOKEN_KEY, token);
    return token || localStorage.getItem(HOST_TOKEN_KEY);
  } catch {
    return token;
  }
}

export function setHostToken(token: string, match?: Pick<Match, "id" | "name" | "room_code">): void {
  sessionStorage.setItem(HOST_TOKEN_KEY, token);
  try {
    localStorage.setItem(HOST_TOKEN_KEY, token);
    if (match) {
      const sessions = getSavedHostSessions().filter((entry) => entry.id !== match.id);
      localStorage.setItem(HOST_SESSIONS_KEY, JSON.stringify([
        { id: match.id, name: match.name, room_code: match.room_code, token }, ...sessions,
      ]));
    }
  } catch {
    // The current tab still works if browser storage is unavailable.
  }
}

export function clearHostToken(): void {
  sessionStorage.removeItem(HOST_TOKEN_KEY);
  try {
    localStorage.removeItem(HOST_TOKEN_KEY);
    localStorage.removeItem(HOST_SESSIONS_KEY);
  } catch { /* Storage may be disabled. */ }
}

export function getActiveMember(): TeamMember | null {
  const data = sessionStorage.getItem(ACTIVE_MEMBER_KEY);
  if (!data) return null;
  try {
    return JSON.parse(data) as TeamMember;
  } catch {
    return null;
  }
}

export function setActiveMember(member: TeamMember): void {
  sessionStorage.setItem(ACTIVE_MEMBER_KEY, JSON.stringify(member));
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const matchId = endpoint.match(/^\/matches\/([^/]+)\//)?.[1];
  if (matchId && /^[0-9a-f-]{36}$/i.test(matchId)) lastMatchId = matchId;
  const hostToken = isHostMode() ? getHostToken(matchId) : null;
  const participantToken = getParticipantToken();

  const headers: Record<string, string> = {
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers as Record<string, string>),
  };
  headers["X-Browser-Session"] = getBrowserSessionId();

  if (hostToken) {
    headers["X-Host-Token"] = hostToken;
  }
  if (participantToken) {
    headers["X-Participant-Token"] = participantToken;
    if (!headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${participantToken}`;
    }
  }

  try {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
    signal: options.signal || AbortSignal.timeout(15000),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    acceptBrowserSessionEvent(errorData.event);
    const message =
      errorData.error ||
      errorData.detail ||
      (typeof errorData === "object" && Object.values(errorData)[0]) ||
      `HTTP Error ${response.status}`;
    throw new Error(String(message));
  }

  return response.status === 204 ? undefined as T : await response.json();
  } catch (error) {
    if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) {
      throw new Error("Máy chủ chưa phản hồi. Đồng bộ lại trạng thái trước khi thử lại thao tác.");
    }
    throw error;
  }
}

export const api = {
  getHealth: () =>
    apiRequest<{ status: string; components: Record<string, string> }>(
      "/health/",
    ),

  getRoomConstraints: () => apiRequest<RoomConstraints>("/matches/constraints/"),

  // Matches
  createMatch: (data: { name: string; configuration?: Partial<Omit<MatchConfig, "min_teams" | "min_players_per_team">>; question_bank_id?: string; question_bank_token?: string; creation_token?: string }) =>
    apiRequest<CreateMatchResponse>("/matches/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listMatches: () => apiRequest<Match[]>("/matches/"),

  uploadQuestionBank: (file: File, token: string, onProgress: (progress: number) => void, signal?: AbortSignal) =>
    new Promise<QuestionBankPreview>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const abort = () => xhr.abort();
      xhr.open('POST', `${API_BASE}/question-banks/upload/`);
      xhr.setRequestHeader('X-Question-Bank-Token', token);
      xhr.timeout = 60000;
      xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100)); };
      const cleanup = () => signal?.removeEventListener('abort', abort);
      xhr.onload = () => {
        cleanup();
        if (xhr.status === 413) { reject(new Error('Tệp vượt quá giới hạn dung lượng máy chủ.')); return; }
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) resolve(data);
          else reject(new Error(String(data.error || data.detail || `HTTP ${xhr.status}`)));
        } catch { reject(new Error('Máy chủ trả về dữ liệu không hợp lệ.')); }
      };
      xhr.onerror = () => { cleanup(); reject(new Error('Không thể tải lên. Kiểm tra kết nối và thử lại.')); };
      xhr.ontimeout = () => { cleanup(); reject(new Error('Tải lên quá thời gian. Hãy thử lại.')); };
      xhr.onabort = () => { cleanup(); reject(new DOMException('Upload canceled', 'AbortError')); };
      signal?.addEventListener('abort', abort, { once: true });
      if (signal?.aborted) { cleanup(); reject(new DOMException('Upload canceled', 'AbortError')); return; }
      const form = new FormData(); form.append('file', file); xhr.send(form);
    }),

  previewQuestionBank: (id: string, token: string, page = 1) =>
    apiRequest<QuestionBankPreview>(`/question-banks/${id}/preview/?page=${page}`, { headers: { 'X-Question-Bank-Token': token } }),

  deleteQuestionBank: (id: string, token: string) =>
    apiRequest<void>(`/question-banks/${id}/preview/`, { method: 'DELETE', headers: { 'X-Question-Bank-Token': token } }),

  getQuestionProgress: (matchId: string) =>
    apiRequest<import('../types/question').QuestionProgress>(`/matches/${matchId}/questions/progress/`),

  getMatch: (matchId: string) => apiRequest<Match>(`/matches/${matchId}/`),

  getMatchByCode: (roomCode: string) =>
    apiRequest<Match>(`/matches/code/${roomCode.toUpperCase().trim()}/`),

  joinMatch: (
    matchId: string,
    data: {
      room_code?: string;
      display_name: string;
      team_id?: string | null;
      new_team_name?: string;
      role: string;
    },
  ) =>
    apiRequest<JoinMatchResponse>(`/matches/${matchId}/join/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  startMatch: (matchId: string) =>
    apiRequest<Match>(`/matches/${matchId}/start/`, {
      method: "POST",
    }),

  pauseMatch: (matchId: string) =>
    apiRequest<Match>(`/matches/${matchId}/pause/`, {
      method: "POST",
    }),

  resumeMatch: (matchId: string) =>
    apiRequest<Match>(`/matches/${matchId}/resume/`, {
      method: "POST",
    }),

  endMatch: (matchId: string) =>
    apiRequest<Match>(`/matches/${matchId}/end/`, {
      method: "POST",
    }),

  advancePhase: (matchId: string, targetPhase?: string) =>
    apiRequest<Match>(`/matches/${matchId}/advance-phase/`, {
      method: "POST",
      body: JSON.stringify({ target_phase: targetPhase }),
    }),

  toggleMatchLock: (matchId: string, isLocked?: boolean) =>
    apiRequest<Match>(`/matches/${matchId}/lock/`, {
      method: "POST",
      body: JSON.stringify(
        isLocked !== undefined ? { is_locked: isLocked } : {},
      ),
    }),

  updateMatchConfig: (matchId: string, config: Partial<MatchConfig>) =>
    apiRequest<Match>(`/matches/${matchId}/config/`, {
      method: "PATCH",
      body: JSON.stringify(config),
    }),

  // Lobby management
  createTeam: (matchId: string, name: string) =>
    apiRequest<Team>(`/matches/${matchId}/teams/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  updateTeam: (matchId: string, teamId: string, name: string) =>
    apiRequest<Team>(`/matches/${matchId}/teams/${teamId}/`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),

  deleteTeam: (matchId: string, teamId: string) =>
    apiRequest<{ message: string }>(`/matches/${matchId}/teams/${teamId}/`, {
      method: "DELETE",
    }),

  setTeamReady: (matchId: string, teamId: string, isReady?: boolean) =>
    apiRequest<Team>(`/matches/${matchId}/teams/${teamId}/ready/`, {
      method: "POST",
      body: JSON.stringify(isReady !== undefined ? { is_ready: isReady } : {}),
    }),

  assignMember: (
    matchId: string,
    memberId: string,
    data: { team_id?: string | null; role?: string },
  ) =>
    apiRequest<TeamMember>(`/matches/${matchId}/members/${memberId}/assign/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  removeMember: (matchId: string, memberId: string) =>
    apiRequest<{ message: string }>(
      `/matches/${matchId}/members/${memberId}/`,
      {
        method: "DELETE",
      },
    ),

  // Phase 2: Questions & Rewards (§20)
  armyCommand: (matchId: string, data: {command_type: "RETARGET" | "RETREAT_ALL" | "DEFEND_BASE"; unit_ids?: string[]; target_team_id?: string; idempotency_key: string}) =>
    apiRequest<{affected_count: number; command_version: number}>(`/matches/${matchId}/actions/army/`, {
      method: "POST", body: JSON.stringify(data),
    }),
  getCurrentQuestion: (matchId: string, teamId?: string) => {
    const query = teamId ? `?team_id=${encodeURIComponent(teamId)}` : "";
    return apiRequest<TeamQuestion | { question: null; message: string }>(
      `/matches/${matchId}/questions/current/${query}`,
    );
  },

  questionAction: (matchId: string, questionId: string | null, action: "OPEN_SESSION" | "OPEN" | "CLOSE" | "HEARTBEAT" | "NEXT", viewerId: string) =>
    apiRequest<(TeamQuestion | {question: null}) & {previous_question_expired?: boolean}>(`/matches/${matchId}/questions/current/`, {
      method: "POST", body: JSON.stringify({question_id: questionId, action, viewer_id: viewerId}),
      ...(action === "CLOSE" ? {keepalive: true} : {}),
    }),
  submitAnswer: (matchId: string, questionId: string, answer: string) =>
    apiRequest<TeamQuestion>(
      `/matches/${matchId}/questions/${questionId}/answer/`,
      {
        method: "POST",
        body: JSON.stringify({ answer }),
      },
    ),

  claimReward: (
    matchId: string,
    data: {
      team_question_id: string;
      reward_type: "COIN" | "UNLOCK";
      unit_type_id?: string;
      idempotency_key?: string;
    },
  ) =>
    apiRequest<RewardClaim>(`/matches/${matchId}/rewards/claim/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getRewardOptions: (matchId: string, teamQuestionId: string) =>
    apiRequest<RewardOptions>(
      `/matches/${matchId}/rewards/options/${teamQuestionId}/`,
    ),

  getQuestionHistory: (matchId: string) =>
    apiRequest<TeamQuestion[]>(`/matches/${matchId}/questions/history/`),

  resolveCombat: (matchId: string, expectedRound?: number) =>
    apiRequest<import("../types/combat").RoundResult>(
      `/matches/${matchId}/combat/resolve/`,
      { method: "POST", body: JSON.stringify({ expected_round: expectedRound }) },
    ),

  getMap: (matchId: string) =>
    apiRequest<import("../game/map").ServerMap>(`/matches/${matchId}/map/`),

  getMatchUnits: (matchId: string) =>
    apiRequest<UnitType[]>(`/matches/${matchId}/units/`),

  // Phase 3: Action commands & Authoritative Team State (§20, §2.5)
  deployUnit: (
    matchId: string,
    data: {
      unit_type_code_or_id: string;
      target_team_id?: string;
      order?: "ATTACK" | "DEFEND_BASE";
      quantity?: number;
      spawn_node_id?: string;
      idempotency_key?: string;
    },
  ) =>
    apiRequest<{
      action: GameAction;
      entity: GameEntity;
      entities: GameEntity[];
      quantity: number;
      team_coins: number;
    }>(`/matches/${matchId}/actions/deploy/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  buildTower: (
    matchId: string,
    data: {
      unit_type_code_or_id: string;
      node_id?: string;
      grid_row?: number; grid_col?: number;
      idempotency_key?: string;
    },
  ) =>
    apiRequest<{
      action: GameAction;
      entity: GameEntity;
      team_coins: number;
    }>(`/matches/${matchId}/actions/build/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  upgradeTeamType: (matchId: string, data: {entity_type: string; expected_current_level: number; idempotency_key: string}) =>
    apiRequest<{level: number; coins_after: number}>(`/matches/${matchId}/upgrades/`, {method: "POST", body: JSON.stringify(data)}),

  sellTower: (matchId: string, data: {entity_id: string; idempotency_key: string}) =>
    apiRequest<{action: GameAction; entity: GameEntity; refund: number; team_coins: number}>(
      `/matches/${matchId}/actions/sell/`, {method: "POST", body: JSON.stringify(data)}),

  upgradeTower: (
    matchId: string,
    data: {
      entity_id: string;
      idempotency_key?: string;
    },
  ) =>
    apiRequest<{
      action: GameAction;
      entity: GameEntity;
      team_coins: number;
    }>(`/matches/${matchId}/actions/upgrade/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  repairBase: (
    matchId: string,
    data?: {
      idempotency_key?: string;
    },
  ) =>
    apiRequest<{
      action: GameAction;
      team_base_hp: number;
      team_coins: number;
    }>(`/matches/${matchId}/actions/repair/`, {
      method: "POST",
      body: JSON.stringify(data || {}),
    }),

  scout: (
    matchId: string,
    data: {
      target_team_id: string;
      idempotency_key?: string;
    },
  ) =>
    apiRequest<{
      action: GameAction;
      scout_data: any;
      team_coins: number;
    }>(`/matches/${matchId}/actions/scout/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  emp: (
    matchId: string,
    data: {
      target_entity_id: string;
      idempotency_key?: string;
    },
  ) =>
    apiRequest<{
      action: GameAction;
      entity: GameEntity;
      team_coins: number;
    }>(`/matches/${matchId}/actions/emp/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getTeamState: (matchId: string, teamId: string) =>
    apiRequest<TeamState>(`/matches/${matchId}/teams/${teamId}/state/`),

  // Phase 6: Host Console, Results, Presets & Overrides (§14.8, §14.9, FR-09, FR-10)
  getHostTelemetry: (matchId: string) =>
    apiRequest<HostTelemetry>(`/matches/${matchId}/host-telemetry/`),

  listPresets: () => apiRequest<MatchPreset[]>(`/matches/presets/`),

  applyPreset: (matchId: string, presetId: string) =>
    apiRequest<Match>(`/matches/${matchId}/apply-preset/`, {
      method: "POST",
      body: JSON.stringify({ preset_id: presetId }),
    }),

  previewConfig: (matchId: string, configuration: any) =>
    apiRequest<BalancePreview>(`/matches/${matchId}/config/preview/`, {
      method: "POST",
      body: JSON.stringify({ configuration }),
    }),

  rematch: (matchId: string) =>
    apiRequest<{
      new_match_id: string;
      new_room_code: string;
      host_token: string;
      match: Match;
    }>(`/matches/${matchId}/rematch/`, {
      method: "POST",
    }),

  overrideCloseQuestion: (
    matchId: string,
    teamQuestionId: string,
    reason?: string,
  ) =>
    apiRequest<{ message: string }>(
      `/matches/${matchId}/override/close-question/`,
      {
        method: "POST",
        body: JSON.stringify({
          team_question_id: teamQuestionId,
          reason: reason || "Host override: Stuck question closed",
        }),
      },
    ),

  overrideAdjustCoins: (
    matchId: string,
    teamId: string,
    amount: number,
    reason?: string,
  ) =>
    apiRequest<{
      message: string;
      team_id: string;
      amount: number;
      balance_after: number;
    }>(`/matches/${matchId}/override/adjust-coins/`, {
      method: "POST",
      body: JSON.stringify({
        team_id: teamId,
        amount,
        reason: reason || "Host override: Coin adjustment",
      }),
    }),

  advancePhaseOverride: (
    matchId: string,
    targetPhase: string,
    reason?: string,
  ) =>
    apiRequest<Match>(`/matches/${matchId}/advance-phase/`, {
      method: "POST",
      body: JSON.stringify({
        target_phase: targetPhase,
        is_override: true,
        reason: reason || "Host override: Skip phase",
      }),
    }),

  removeMemberOverride: (matchId: string, memberId: string, reason?: string) =>
    apiRequest<{ message: string }>(
      `/matches/${matchId}/members/${memberId}/?is_override=true&reason=${encodeURIComponent(
        reason || "Host override: Member removed",
      )}`,
      {
        method: "DELETE",
      },
    ),

  getEvents: (
    matchId: string,
    params?: {
      event_type?: string;
      after_sequence?: number;
      until_sequence?: number;
      limit?: number;
      offset?: number;
      order?: string;
    },
  ) => {
    const q = new URLSearchParams();
    if (params?.event_type) q.append("event_type", params.event_type);
    if (params?.after_sequence !== undefined)
      q.append("after_sequence", String(params.after_sequence));
    if (params?.until_sequence !== undefined)
      q.append("until_sequence", String(params.until_sequence));
    if (params?.limit !== undefined) q.append("limit", String(params.limit));
    if (params?.offset !== undefined) q.append("offset", String(params.offset));
    if (params?.order) q.append("order", params.order);
    return apiRequest<{
      events: any[];
      count: number;
      total: number;
      limit: number;
      offset: number;
    }>(`/matches/${matchId}/events/?${q.toString()}`);
  },

  getResults: (matchId: string) =>
    apiRequest<MatchResultsApiResponse>(`/matches/${matchId}/results/`),

  listUnitTypes: () => apiRequest<UnitType[]>(`/unit-types/`),

  updateUnitType: (id: string, data: Partial<UnitType>) =>
    apiRequest<UnitType>(`/unit-types/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};
