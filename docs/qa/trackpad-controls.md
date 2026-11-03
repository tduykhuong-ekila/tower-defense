# Trackpad controls

Default primary-button drag pans the map in both tabs. Shift-drag selects friendly mobile units and adds them to the existing selection. Shift-click toggles an individual unit. Space-drag remains a pan override. A secondary click (normally two-finger click on a trackpad) opens the selected army's command popup. The visible Khoanh vùng button is a one-shot alternative to holding Shift.

Army control is enabled by game phase and player eligibility rather than the dock tab. Selection can take priority over deployment/building with Shift or the explicit box tool, without placing or deploying a unit. Modals, pending commands and spectator restrictions continue to block selection. Multitouch pinch cancels box selection.

Verification, 2026-11-01:
- Unit tests cover drag intent across IDLE, INSPECT, COMBAT, DEPLOY, BUILD, MODAL and WAITING, as well as touch, button, Space and permission guards. 8/8 army-control tests passed.
- Production build passed.
- Real browser: plain drag panned a zoomed map in the deployment tab.
- Clicking a visible infantry unit selected it and automatically opened the army tab.
- Plain drag panned the map and retained the selected unit in the army tab.
- Explicit box tool selected all four units and reset itself after release.
- Secondary-click opened the command popup; Escape closed it and retained four selected units.
- The existing army-command UX browser regression script now uses Shift-drag, tests it from the deployment tab, and checks ordinary-drag pan. The automated browser script was updated but not executed in this environment.
