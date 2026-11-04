import { installDevtoolDetector } from './devtoolDetector';

// Deterrence only: a browser controlled by the player cannot be trusted as an
// anti-cheat boundary. Keep game authorization and validation on the server.
export function isInspectionShortcut(event: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'altKey'>): boolean {
  const key = event.key.toLowerCase();
  return key === 'f12' || key === 'f2'
    || ((event.ctrlKey || event.metaKey) && (
      key === 'u' || ((event.shiftKey || event.altKey) && ['i', 'j', 'c', 'k'].includes(key))
    ));
}

export type InspectionReason = 'inspection_shortcut' | 'devtool_detected';

export function installBrowserGuard(
  onBlock: (reason: InspectionReason) => void,
  startDetector: (onOpen: () => void) => void = installDevtoolDetector,
): void {
  // No window flags, exposed reset method, or storage value can unlock a page.
  // Capture these before app code runs so later reassignment does not replace
  // the functions used by this guard. This cannot stop arbitrary console code.
  const listen = window.addEventListener.bind(window);
  const prevent = Event.prototype.preventDefault;
  const stop = Event.prototype.stopImmediatePropagation;
  let blocked = false;
  const block = (reason: InspectionReason) => {
    if (blocked) return;
    blocked = true;
    onBlock(reason);
  };

  listen('contextmenu', event => {
    // Do not swallow pointer events: right-click orders still work in Phaser.
    prevent.call(event);
  }, { capture: true, passive: false });
  listen('keydown', event => {
    if (!isInspectionShortcut(event)) return;
    prevent.call(event);
    stop.call(event);
    block('inspection_shortcut');
  }, { capture: true, passive: false });

  // Viewport size, focus and resize are not evidence of inspection: sidebars,
  // zoom and embedded browsers can produce the same outer/inner size gaps.
  startDetector(() => block('devtool_detected'));
}
