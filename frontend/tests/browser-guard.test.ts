import test from 'node:test';
import assert from 'node:assert/strict';
import { installBrowserGuard, isInspectionShortcut } from '../src/security/browserGuard';

test('inspection shortcuts cover Windows/Linux and macOS without blocking normal keys', () => {
  const key = (key: string, modifiers = {}) => ({ key, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, ...modifiers });
  assert.equal(isInspectionShortcut(key('F12')), true);
  assert.equal(isInspectionShortcut(key('F2')), true);
  for (const modifier of ['ctrlKey', 'metaKey']) {
    assert.equal(isInspectionShortcut(key('U', { [modifier]: true })), true);
    for (const secondary of ['shiftKey', 'altKey']) {
      for (const letter of ['I', 'j', 'c', 'k']) {
        assert.equal(isInspectionShortcut(key(letter, { [modifier]: true, [secondary]: true })), true);
      }
    }
  }
  for (const event of [key('i'), key('c', { ctrlKey: true }), key('r', { metaKey: true }), key('F5')]) {
    assert.equal(isInspectionShortcut(event), false);
  }
});

function setupPage() {
  const reports: string[] = [];
  const ticks: (() => void)[] = [];
  const view = Object.assign(new EventTarget(), {
    outerWidth: 1440, innerWidth: 1440, outerHeight: 900, innerHeight: 780,
    visualViewport: { scale: 1 },
    matchMedia: () => ({ matches: false }),
    setInterval: (tick: () => void) => { ticks.push(tick); return ticks.length; },
  });
  globalThis.window = view as unknown as Window & typeof globalThis;
  installBrowserGuard(reason => reports.push(reason), () => {});
  return { view, reports, ticks };
}

test('sidebars, embedded browsers, zoom and resizing never report inspection or lock on reload', () => {
  const originalWindow = globalThis.window;
  const originalNow = Date.now;
  let timestamp = 0;
  Date.now = () => timestamp;
  try {
    const layouts = [
      { innerWidth: 1000, innerHeight: 780 }, // Browser sidebar.
      { innerWidth: 1440, innerHeight: 500 }, // Embedded browser toolbar.
      { innerWidth: 720, innerHeight: 390 }, // Browser zoom / split view.
      { innerWidth: 0, innerHeight: 0 }, // Minimized window.
    ];
    for (let reload = 0; reload < 2; reload++) {
      const page = setupPage();
      for (const layout of layouts) {
        Object.assign(page.view, layout);
        page.view.dispatchEvent(new Event('resize'));
        page.view.dispatchEvent(new Event('focus'));
        for (let i = 0; i < 10; i++) {
          timestamp += 400;
          page.ticks.forEach(tick => tick());
        }
        assert.deepEqual(page.reports, []);
      }
    }
  } finally {
    globalThis.window = originalWindow;
    Date.now = originalNow;
  }
});

test('library detection reports once and shares the shortcut lock latch', () => {
  const originalWindow = globalThis.window;
  try {
    const view = new EventTarget();
    globalThis.window = view as unknown as Window & typeof globalThis;
    const reports: string[] = [];
    let detect = () => {};
    installBrowserGuard(reason => reports.push(reason), onOpen => { detect = onOpen; });
    detect();
    detect();
    const shortcut = Object.assign(new Event('keydown', { cancelable: true }), { key: 'F2' });
    view.dispatchEvent(shortcut);
    assert.equal(shortcut.defaultPrevented, true);
    assert.deepEqual(reports, ['devtool_detected']);
  } finally {
    globalThis.window = originalWindow;
  }
});

test('guard preserves pointer gameplay and normal keys but reports an inspection shortcut once per page', () => {
  const originalWindow = globalThis.window;
  try {
    const page = setupPage();
    const menu = new Event('contextmenu', { cancelable: true });
    page.view.dispatchEvent(menu);
    assert.equal(menu.defaultPrevented, true);
    const pointer = new Event('pointerdown', { cancelable: true });
    page.view.dispatchEvent(pointer);
    assert.equal(pointer.defaultPrevented, false);
    const copy = Object.assign(new Event('keydown', { cancelable: true }), { key: 'c', ctrlKey: true });
    page.view.dispatchEvent(copy);
    assert.equal(copy.defaultPrevented, false);
    assert.deepEqual(page.reports, []);

    for (let i = 0; i < 2; i++) {
      const shortcut = Object.assign(new Event('keydown', { cancelable: true }), { key: 'F12' });
      page.view.dispatchEvent(shortcut);
      assert.equal(shortcut.defaultPrevented, true);
    }
    assert.deepEqual(page.reports, ['inspection_shortcut']);
    const reloaded = setupPage();
    assert.deepEqual(reloaded.reports, []);
  } finally {
    globalThis.window = originalWindow;
  }
});
