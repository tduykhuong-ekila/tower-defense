import { apiRequest, getAuthToken } from "./api";
import { ConnectionStatus, ServerEnvelope } from "../types/realtime";
import { EnvelopeChunks } from "./envelopeChunks";
import { useMatchStore } from "../stores/matchStore";
import { acceptBrowserSessionEvent, getBrowserSessionId } from "../security/browserSession";

export type MessageHandler = (data: any, envelope: ServerEnvelope) => void;
export type SnapshotLoader = (matchId: string, signal: AbortSignal) => Promise<ServerEnvelope>;
interface QueuedAction { type: string; payload: any; timestamp: number }
export interface SocketHealthOptions {
  heartbeatMs: number;
  staleMs: number;
  snapshotTimeoutMs: number;
  repairMs: number;
  httpFallbackMs: number;
  httpTimeoutMs: number;
  httpRetryMs: number;
}
const DEFAULT_HEALTH: SocketHealthOptions = {
  heartbeatMs: 5000, staleMs: 20000, snapshotTimeoutMs: 8000, repairMs: 30000,
  httpFallbackMs: 2500, httpTimeoutMs: 5000, httpRetryMs: 5000,
};

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private chunks = new EnvelopeChunks();
  private matchId = "";
  private reconnectAttempts = 0;
  private listeners = new Map<string, Set<MessageHandler>>();
  private lastSequenceNumber = 0;
  private syncPending = false;
  private snapshotRequested = false;
  private stateHandler: ((envelope: ServerEnvelope) => void) | null = null;
  private httpTimer: ReturnType<typeof setTimeout> | null = null;
  private httpController: AbortController | null = null;
  private session = 0;
  private httpRetryAt = 0;
  private nextRepairAt = 0;
  private lastAppliedAt = 0;
  private applicationErrors = 0;
  private pendingEvents = new Map<number, ServerEnvelope>();
  private repairTimer: ReturnType<typeof setInterval> | null = null;
  private snapshotTimer: ReturnType<typeof setTimeout> | null = null;
  private seenEventIds = new Set<string>();
  private connectionStatus: ConnectionStatus = "disconnected";
  private actionQueue: QueuedAction[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private lastReceivedAt = 0;
  private lastSnapshotAt = 0;
  private watchingNetwork = false;
  private health: SocketHealthOptions;

  constructor(options: Partial<SocketHealthOptions> = {}, private snapshotLoader: SnapshotLoader =
    (matchId, signal) => apiRequest(`/matches/${encodeURIComponent(matchId)}/snapshot/`, {signal, cache: "no-store"})) {
    this.health = { ...DEFAULT_HEALTH, ...options };
  }

  private wake = () => {
    if (!this.matchId || (typeof document !== "undefined" && document.visibilityState === "hidden")) return;
    if (this.ws?.readyState === WebSocket.OPEN) {
      if (Date.now() - this.lastReceivedAt >= this.health.staleMs) this.restartSocket();
      else this.requestSync();
    } else if (this.ws?.readyState !== WebSocket.CONNECTING) this.connect(this.matchId);
  };

  connect(matchId: string) {
    if (!matchId) return;
    if (this.matchId && this.matchId !== matchId) this.disconnect();
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
    this.matchId = matchId;
    if (!this.watchingNetwork) {
      window.addEventListener?.("online", this.wake);
      if (typeof document !== "undefined") document.addEventListener("visibilitychange", this.wake);
      this.watchingNetwork = true;
    }
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.setStatus(this.reconnectAttempts ? "reconnecting" : "disconnected");
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws/matches/${matchId}/?token=${encodeURIComponent(getAuthToken() || "")}&browser_session=${getBrowserSessionId()}`;
    let socket: WebSocket;
    try { socket = new WebSocket(url); this.ws = socket; this.waitForSnapshot(); }
    catch (err) { console.error("[WebSocket] Failed to instantiate:", err); this.attemptReconnect(); return; }
    socket.onopen = () => {
      if (this.ws !== socket) return;
      this.reconnectAttempts = 0;
      this.lastReceivedAt = Date.now();
      // The consumer sends a snapshot after subscribing, including on first connect.
      // Buffer live events until it arrives so deltas never start from a partial board.
      this.waitForSnapshot();
      this.setStatus(this.syncPending ? "syncing" : "connected");
      if (this.repairTimer) clearInterval(this.repairTimer);
      this.repairTimer = setInterval(() => {
        if (Date.now() - this.lastReceivedAt >= this.health.staleMs) { this.restartSocket(); return; }
        this.send("PING");
        if (Date.now() >= this.nextRepairAt) this.requestSync(false);
      }, this.health.heartbeatMs);
      const valid = this.actionQueue.filter(a => Date.now() - a.timestamp <= 15000);
      this.actionQueue = [];
      valid.forEach(a => this.send(a.type, a.payload));
    };
    socket.onmessage = event => {
      if (this.ws !== socket) return;
      try {
        let envelope: ServerEnvelope = JSON.parse(event.data);
        if (envelope.match_id && envelope.match_id !== this.matchId) return;
        // A security control message must bypass snapshot waits, stale sequence
        // filtering and the match reducer. No queued actions may survive it.
        if (acceptBrowserSessionEvent(envelope)) { this.disconnect(); return; }
        this.lastReceivedAt = Date.now();
        if (envelope.event_type === "JSON_CHUNK") {
          const assembled = this.chunks.push(envelope.payload);
          if (assembled === null) return;
          envelope = JSON.parse(assembled);
          if (envelope.match_id && envelope.match_id !== this.matchId) return;
        }
        if (envelope.event_type === "PONG") {
          if (envelope.payload.state_version > this.lastSequenceNumber) this.requestSync();
          return;
        }
        this.acceptEnvelope(envelope);
      } catch (err) { this.recoverApplication(err); }
    };
    socket.onclose = evt => {
      if (this.ws !== socket) return;
      this.ws = null;
      this.stopHealthChecks();
      this.setStatus("disconnected");
      if (evt.code !== 4001 && evt.code !== 4003) this.attemptReconnect();
      else { this.cancelHttp(); this.session++; this.stopWatchingNetwork(); }
    };
    socket.onerror = err => console.warn("[WebSocket] Error encountered:", err);
  }

  private acceptEnvelope(envelope: ServerEnvelope) {
    if (envelope.match_id && envelope.match_id !== this.matchId) return;
    const sequence = envelope.sequence_number ?? 0;
    if (!Number.isSafeInteger(sequence) || sequence < 0) throw new Error("Invalid event sequence");
    if (envelope.event_type === "MATCH_STATE_SNAPSHOT") {
      if (sequence < this.lastSequenceNumber) {
        // A routine snapshot may be overtaken by live deltas. Never roll back.
        this.clearSnapshotWait();
        this.cancelHttp();
        if (this.syncPending || this.pendingEvents.size) this.requestSync();
        else if (this.ws?.readyState === WebSocket.OPEN) this.setStatus("connected");
        return;
      }
      this.dispatch(envelope);
      this.lastSnapshotAt = Date.now();
      this.syncPending = false;
      this.clearSnapshotWait();
      this.cancelHttp();
      for (const n of this.pendingEvents.keys()) if (n <= sequence) this.pendingEvents.delete(n);
      this.drainPending();
      if (this.pendingEvents.size || this.syncPending) this.requestSync();
      else if (this.ws?.readyState === WebSocket.OPEN) this.setStatus("connected");
      return;
    }
    if (sequence > 0 && sequence <= this.lastSequenceNumber) return;
    if (sequence > 0 && (this.syncPending || sequence > this.lastSequenceNumber + 1)) {
      this.pendingEvents.set(sequence, envelope);
      if (this.pendingEvents.size > 500) this.pendingEvents.clear();
      this.emit("sequence_gap", { expected: this.lastSequenceNumber + 1, received: sequence }, envelope);
      this.requestSync();
      return;
    }
    this.dispatch(envelope);
    this.drainPending();
  }

  private recoverApplication(error: unknown) {
    this.applicationErrors++;
    this.chunks.clear();
    console.error("[WebSocket] State recovery required", {
      matchId: this.matchId, appliedSequence: this.lastSequenceNumber, error,
    });
    this.requestSync();
    void this.recoverOverHttp();
  }

  private drainPending() {
    if (this.syncPending) return;
    while (!this.syncPending && this.pendingEvents.has(this.lastSequenceNumber + 1)) {
      const next = this.pendingEvents.get(this.lastSequenceNumber + 1)!;
      this.dispatch(next);
      this.pendingEvents.delete(next.sequence_number);
    }
  }
  private dispatch(envelope: ServerEnvelope) {
    const snapshot = envelope.event_type === "MATCH_STATE_SNAPSHOT";
    if (!snapshot && envelope.event_id && this.seenEventIds.has(envelope.event_id)) return;
    // State application is critical. UI/animation observers cannot acknowledge it.
    this.stateHandler?.(envelope);
    this.lastSequenceNumber = Math.max(this.lastSequenceNumber, envelope.sequence_number || 0);
    this.lastAppliedAt = Date.now();
    if (!snapshot && envelope.event_id) {
      this.seenEventIds.add(envelope.event_id);
      if (this.seenEventIds.size > 1000) this.seenEventIds.delete(this.seenEventIds.values().next().value!);
    }
    this.emit(envelope.event_type, envelope.payload, envelope);
    this.emit("any", envelope.payload, envelope);
  }

  setStateHandler(handler: (envelope: ServerEnvelope) => void) { this.stateHandler = handler; }

  private cancelHttp() {
    this.httpController?.abort();
    this.httpController = null;
  }

  private async recoverOverHttp() {
    if (!this.matchId || this.httpController || Date.now() < this.httpRetryAt) return;
    const matchId = this.matchId, session = this.session, controller = new AbortController();
    this.httpController = controller;
    this.httpRetryAt = Date.now() + this.health.httpRetryMs;
    const timeout = setTimeout(() => controller.abort(), this.health.httpTimeoutMs);
    let abortListener: () => void = () => {};
    try {
      const aborted = new Promise<never>((_resolve, reject) => {
        abortListener = () => reject(new Error("Recovery cancelled or timed out"));
        controller.signal.addEventListener("abort", abortListener, {once: true});
      });
      const envelope = await Promise.race([this.snapshotLoader(matchId, controller.signal), aborted]);
      if (controller.signal.aborted || session !== this.session || matchId !== this.matchId) return;
      if (envelope.match_id !== matchId || envelope.event_type !== "MATCH_STATE_SNAPSHOT" ||
          !Number.isSafeInteger(envelope.sequence_number) || envelope.sequence_number < 0 ||
          envelope.payload?.match?.id !== matchId || !Array.isArray(envelope.payload.entities) || !Array.isArray(envelope.payload.teams))
        throw new Error("Invalid HTTP recovery snapshot");
      // A delayed HTTP response must not cancel a newer in-flight WebSocket repair.
      if (envelope.sequence_number < this.lastSequenceNumber && (this.syncPending || this.pendingEvents.size)) return;
      try { this.acceptEnvelope(envelope); }
      catch (error) { this.recoverApplication(error); }
    } catch (error) {
      if (!controller.signal.aborted && session === this.session) {
        console.warn("[WebSocket] HTTP recovery failed", {matchId, appliedSequence: this.lastSequenceNumber, error});
      }
    } finally {
      clearTimeout(timeout);
      controller.signal.removeEventListener("abort", abortListener);
      if (this.httpController === controller) this.httpController = null;
    }
  }
  private setStatus(status: ConnectionStatus) {
    if (this.connectionStatus === status) return;
    this.connectionStatus = status;
    this.emit("connection_change", { status }, {} as ServerEnvelope);
  }
  private attemptReconnect() {
    if (!this.matchId || this.reconnectTimer) return;
    this.reconnectAttempts++;
    this.setStatus("reconnecting");
    const delay = Math.min(1000 * Math.pow(2, Math.min(this.reconnectAttempts - 1, 4)), 10000) + Math.random() * 500;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.matchId) this.connect(this.matchId);
    }, delay);
  }
  private restartSocket() {
    const socket = this.ws;
    if (!socket) return;
    // Do not wait indefinitely for a half-open TCP close handshake.
    this.ws = null;
    socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null;
    socket.close(4000, "State recovery timeout");
    this.stopHealthChecks();
    this.attemptReconnect();
  }
  private waitForSnapshot(blocking = true) {
    this.clearSnapshotWait();
    this.snapshotRequested = true;
    this.syncPending ||= blocking;
    this.nextRepairAt = Date.now() + this.health.repairMs * (0.9 + Math.random() * 0.2);
    if (this.syncPending && this.ws?.readyState === WebSocket.OPEN) this.setStatus("syncing");
    this.httpTimer = setTimeout(() => { void this.recoverOverHttp(); }, this.health.httpFallbackMs);
    this.snapshotTimer = setTimeout(() => {
      void this.recoverOverHttp();
      this.restartSocket();
    }, this.health.snapshotTimeoutMs);
  }
  private clearSnapshotWait() {
    if (this.snapshotTimer) clearTimeout(this.snapshotTimer);
    this.snapshotTimer = null;
    if (this.httpTimer) clearTimeout(this.httpTimer);
    this.httpTimer = null;
    this.snapshotRequested = false;
  }
  private stopHealthChecks() {
    this.chunks.clear();
    if (this.repairTimer) clearInterval(this.repairTimer);
    this.repairTimer = null;
    this.clearSnapshotWait();
  }
  private stopWatchingNetwork() {
    window.removeEventListener?.("online", this.wake);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", this.wake);
    this.watchingNetwork = false;
  }
  send(type: string, payload: any = {}) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ event_type: type, payload }));
    else if (type !== "STATE_SYNC_REQUEST" && type !== "PING") this.actionQueue.push({ type, payload, timestamp: Date.now() });
  }
  on(event: string, handler: MessageHandler) {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set());
    this.listeners.get(event)!.add(handler);
  }
  off(event: string, handler: MessageHandler) { this.listeners.get(event)?.delete(handler); }
  onStatusChange(handler: (status: ConnectionStatus) => void): () => void {
    const wrapped: MessageHandler = data => handler(data.status);
    this.on("connection_change", wrapped);
    return () => this.off("connection_change", wrapped);
  }
  onEvent(handler: (envelope: ServerEnvelope) => void): () => void {
    const wrapped: MessageHandler = (_data, envelope) => handler(envelope);
    this.on("any", wrapped);
    return () => this.off("any", wrapped);
  }
  private emit(event: string, data: any, envelope: ServerEnvelope) {
    this.listeners.get(event)?.forEach(handler => {
      try { handler(data, envelope); }
      catch (err) { console.error(`[WebSocket] Listener error on event '${event}':`, err); }
    });
  }
  getStatus(): ConnectionStatus { return this.connectionStatus; }
  getDiagnostics() {
    return {matchId: this.matchId, appliedSequence: this.lastSequenceNumber, lastAppliedAt: this.lastAppliedAt,
      lastSnapshotAt: this.lastSnapshotAt, syncPending: this.syncPending, snapshotRequested: this.snapshotRequested,
      bufferedEvents: this.pendingEvents.size, httpRecoveryPending: !!this.httpController, applicationErrors: this.applicationErrors};
  }
  disconnect() {
    this.stopHealthChecks();
    this.stopWatchingNetwork();
    this.pendingEvents.clear();
    this.cancelHttp();
    this.session++;
    this.syncPending = false;
    this.httpRetryAt = 0;
    this.lastAppliedAt = 0;
    this.applicationErrors = 0;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.reconnectAttempts = 0;
    this.lastSequenceNumber = 0;
    this.lastSnapshotAt = 0;
    this.seenEventIds.clear();
    this.matchId = "";
    this.actionQueue = [];
    if (this.ws) {
      this.ws.onopen = this.ws.onmessage = this.ws.onclose = this.ws.onerror = null;
      this.ws.close();
      this.ws = null;
    }
    this.setStatus("disconnected");
  }

  // Convenience dispatch methods
  deployUnit(
    unitCode: string,
    targetTeamId: string,
    spawnNode?: string,
    idempotencyKey?: string,
    quantity = 1,
  ) {
    this.send("DEPLOY_REQUEST", {
      unit_code: unitCode,
      quantity,
      target_team_id: targetTeamId,
      spawn_node: spawnNode,
      idempotency_key: idempotencyKey || crypto.randomUUID(),
    });
  }

  buildTower(towerCode: string, nodeId: string, idempotencyKey?: string) {
    this.send("BUILD_REQUEST", {
      tower_code: towerCode,
      node_id: nodeId,
      idempotency_key: idempotencyKey || crypto.randomUUID(),
    });
  }

  upgradeTower(entityId: string, idempotencyKey?: string) {
    this.send("UPGRADE_REQUEST", {
      entity_id: entityId,
      idempotency_key: idempotencyKey || crypto.randomUUID(),
    });
  }

  repairBase(idempotencyKey?: string) {
    this.send("REPAIR_REQUEST", {
      idempotency_key: idempotencyKey || crypto.randomUUID(),
    });
  }

  submitAnswer(questionId: string, answer: string) {
    this.send("ANSWER_SUBMITTED", {
      question_id: questionId,
      answer,
    });
  }

  selectReward(
    teamQuestionId: string,
    rewardType: string,
    unitTypeId?: string,
    idempotencyKey?: string,
  ) {
    this.send("REWARD_SELECTED", {
      team_question_id: teamQuestionId,
      reward_type: rewardType,
      unit_type_id: unitTypeId,
      idempotency_key: idempotencyKey || crypto.randomUUID(),
    });
  }

  setTarget(targetTeamId: string) {
    this.send("TARGET_SELECTED", {
      target_team_id: targetTeamId,
    });
  }

  setReady(isReady: boolean) {
    this.send("READY_CHANGED", {
      is_ready: isReady,
    });
  }

  requestSync(blocking = true) {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    if (blocking) { this.syncPending = true; this.setStatus("syncing"); }
    if (this.snapshotRequested) return;
    this.waitForSnapshot(blocking);
    this.send("STATE_SYNC_REQUEST", { last_sequence: this.lastSequenceNumber });
  }
}

export const wsClient = new WebSocketClient();
// Keep the authoritative reducer alive across lobby/battle page transitions.
wsClient.setStateHandler(envelope => {
  useMatchStore.getState().applyEvent(envelope);
  if (envelope.sequence_number > 0 && useMatchStore.getState().lastSequenceNumber < envelope.sequence_number)
    throw new Error("Match store did not accept the event version");
});
