# Browser inspection guard

The frontend installs two layers before importing the game:

1. A capture-phase keyboard handler calls `preventDefault` for F12, F2,
   Ctrl/Command + Shift/Alt + I/J/C (also Firefox's K), and Ctrl/Command + U.
   The native context menu is cancelled without cancelling gameplay pointer events.
2. The pinned npm dependency `disable-devtool@0.3.9` runs console-object probes
   (RegToString, DefineId, DateToString, FuncToString), Performance timing and
   DebugLib detection. `Size` and `Debugger` are explicitly excluded. Probes run
   every 1000ms and stop after detection. The library does not clear console logs,
   disable copy/paste/selection, touch parent frames, or redirect the page.

Both layers share a one-way lock latch. Detection immediately replaces all body
content with the warning “⚠️ Hành vi gian lận bị phát hiện! Trò chơi đã bị khóa.”
and a reload button. React unmounts the game and Phaser before replacing body
children, preserving cleanup and button behavior instead of assigning raw
`innerHTML` over a live React tree. Window dimensions, focus and resize alone
never trigger reports or locks: sidebars, zoom and embedded views can resemble tools.

On detection, the client also sends an authenticated report to
`POST /api/v1/matches/{id}/security/inspection/`. The accepted reason is
`inspection_shortcut` or `devtool_detected`. Each page runtime has a UUID, carried in
the `X-Browser-Session` API header and `browser_session` WebSocket query parameter.

The server stores a `BrowserSessionBlock` for the match, authenticated credential
hash and runtime UUID, then sends a private `SESSION_BLOCKED` event to sockets
belonging to that same identity/runtime. Teammates and opponents are unaffected.
The event has sequence zero and bypasses match reducers and snapshot buffering.
The HTTP response returns the same event so the page also locks without a working
WebSocket. No global match event or match sequence is created by this control.
The server rejects legacy `docked_tools` reports and ignores existing blocks
created for that reason. Those records are retained for audit, so no data cleanup
or migration is needed to recover from the old false positives. Existing block
screens need a full reload after deploying the updated frontend/backend.

Locking unmounts the application and Phaser and disconnects the shared realtime
client. The server rejects further API calls with HTTP 403 and the same control
event; reconnecting that runtime gets `SESSION_BLOCKED` and close code 4003 before
a snapshot. Commands on existing sockets check the durable block as well, so
removing the overlay does not authorize requests from a blocked runtime. Both
participant and host token sessions are covered. Reports are idempotent and
cannot specify someone else's credentials or member ID.

Closing tools or changing routes does not unlock it. Close tools, reload and
re-enter the room to resume; a full page load creates a new runtime UUID, while
existing participant credentials are preserved. The guard applies in development
and production. Anonymous pages without a match and failed/offline reports use a
local lock; they cannot claim server acknowledgement.

Run `python manage.py migrate` before restarting an existing backend. Container
startup already runs migrations through `backend/entrypoint.sh`.

Client state lives in module closures, with no public disable flag or reset API. Native
event functions are captured during installation to resist simple later
reassignment. These are deterrents, not a security boundary. Console code can
still bypass client JavaScript; users can disable JavaScript, modify responses,
remove listeners or use a separate client. The runtime UUID is a scope for
temporary locking, not an authentication secret: a modified client can forge a
fresh UUID or omit it (legacy clients without a runtime UUID remain compatible).
The server cannot prove that a reload happened or detect tools if reporting was
disabled before detection. Library probes can detect tools opened through browser
menus or already open at page load, depending on browser support. Indirect console
and timing probes can still produce false positives or miss tools; this is not a
guarantee of cheat detection. The library is imported as a module, not exposed as
`window.DisableDevtool`. See the upstream documentation:
https://github.com/theajack/disable-devtool#35-monitoring-mode

Do not use this signal to ban accounts or authorize game actions. Server-side
authentication, permissions, economy/action validation and rate limits remain
responsible for protecting game state. No debugger loops are enabled. The library
does print console probe objects/data; the Performance probe adds measurement work
and should be evaluated on the devices used by players.
