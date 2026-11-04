import type { ServerEnvelope } from '../types/realtime';

// One ID per page runtime; a full reload starts a fresh session. Keep it out of
// localStorage/window so a storage toggle cannot unlock the current session.
let sessionId: string | undefined;
let blocked = false;
const listeners = new Set<() => void>();

export function getBrowserSessionId(): string {
  return sessionId ??= crypto.randomUUID();
}

export function onBrowserSessionBlocked(listener: () => void): void {
  listeners.add(listener);
  if (blocked) listener();
}

export function acceptBrowserSessionEvent(event: Pick<ServerEnvelope, 'event_type'> | undefined): boolean {
  if (event?.event_type !== 'SESSION_BLOCKED') return false;
  if (!blocked) {
    blocked = true;
    listeners.forEach(listener => listener());
  }
  return true;
}
