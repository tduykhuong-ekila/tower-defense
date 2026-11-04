import React from 'react';
import ReactDOM from 'react-dom/client';
import { flushSync } from 'react-dom';
import { installBrowserGuard, type InspectionReason } from './security/browserGuard';
import { acceptBrowserSessionEvent, onBrowserSessionBlocked } from './security/browserSession';
import { BrowserBlocked } from './security/BrowserBlocked';
import './index.css';

const container = document.getElementById('root')!;
const root = ReactDOM.createRoot(container);
let blocked = false;
let disconnect: (() => void) | undefined;
let detected: InspectionReason | undefined;
let report: ((reason: InspectionReason) => Promise<void>) | undefined;

const blockApp = () => {
  if (blocked) return;
  blocked = true;
  container.inert = false;
  // Synchronously unmount Phaser, page effects, controls and routing before
  // disconnecting the shared socket. Closing tools cannot resume this runtime.
  flushSync(() => root.render(<BrowserBlocked />));
  // Replace all body content while retaining React's managed root and reload
  // button. Replacing innerHTML directly would skip Phaser/effect cleanup.
  document.body.replaceChildren(container);
  disconnect?.();
};
onBrowserSessionBlocked(blockApp);

installBrowserGuard(reason => {
  detected = reason;
  // Start the authenticated report before unmounting pages disconnects sockets.
  if (report) void report(reason);
  blockApp();
});

// Install the guard before loading game modules. Never mount a late import if
// the player has already triggered the lock screen during startup.
void Promise.all([import('./App'), import('./services/websocket'), import('./services/api')]).then(([{ default: App }, { wsClient }, apiModule]) => {
  disconnect = () => wsClient.disconnect();
  report = async reason => {
    const matchId = window.location.pathname.match(/^\/(?:battle|lobby|results)\/([0-9a-f-]{36})/i)?.[1]
      || wsClient.getDiagnostics().matchId || apiModule.getActiveApiMatchId();
    try {
      if (!matchId) { blockApp(); return; }
      const event = await apiModule.apiRequest<import('./types/realtime').ServerEnvelope>(
        `/matches/${matchId}/security/inspection/`,
        { method: 'POST', body: JSON.stringify({ reason }), keepalive: true },
      );
      if (!acceptBrowserSessionEvent(event)) blockApp();
    } catch {
      // Offline/anonymous pages still lock locally. Never claim a server
      // acknowledgement if the report could not reach the authenticated API.
      blockApp();
    }
  };
  if (detected) { void report(detected); return; }
  if (blocked) { disconnect(); return; }
  root.render(<React.StrictMode><App /></React.StrictMode>);
});
