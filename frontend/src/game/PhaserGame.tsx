import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import Phaser from "phaser";
import { BootScene } from "./scenes/BootScene";
import { BattleScene } from "./scenes/BattleScene";
import { CombatEvent } from "../types/combat";
import { SceneCallbacks, SceneState } from "./bridge";

export interface PhaserGameRef {
  playCombatEvents: (events: CombatEvent[]) => void;
  playLiveEvents: (events: CombatEvent[]) => void;
  fit: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  focusBase: (teamId?: string) => void;
  navigate: (x: number, y: number, minimumZoom?: number) => void;
  focusCombat: () => void;
  skipCombat: () => void;
}
export const PhaserGame = forwardRef<
  PhaserGameRef,
  { state: SceneState; callbacks: SceneCallbacks }
>(({ state, callbacks }, ref) => {
  const container = useRef<HTMLDivElement>(null);
  const scene = useRef<BattleScene | null>(null);
  const latest = useRef({ state, callbacks });
  latest.current = { state, callbacks };
  const queued = useRef<CombatEvent[][]>([]);
  const queuedLive = useRef<CombatEvent[]>([]);
  useImperativeHandle(
    ref,
    () => ({
      playCombatEvents(events) {
        if (scene.current) scene.current.playCombatEvents(events);
        else queued.current.push(events);
      },
      playLiveEvents(events) {
        if (scene.current) scene.current.playLiveEvents(events);
        else queuedLive.current = [...queuedLive.current, ...events].slice(-500);
      },
      zoomIn() { scene.current?.zoomIn(); },
      zoomOut() { scene.current?.zoomOut(); },
      fit() {
        scene.current?.fit();
      },
      focusBase(teamId) {
        scene.current?.focusBase(teamId);
      },
      navigate(x, y, minimumZoom) { scene.current?.navigate(x, y, minimumZoom); },
      focusCombat() { scene.current?.focusCombat(); },
      skipCombat() {
        queuedLive.current = [];
        queued.current = [];
        scene.current?.skipCombat();
      },
    }),
    [],
  );
  useEffect(() => {
    if (!container.current) return;
    const game = new Phaser.Game({
      type: Phaser.AUTO,
      parent: container.current,
      width: container.current.clientWidth,
      height: container.current.clientHeight,
      backgroundColor: "#78934b",
      scene: [BootScene, BattleScene],
      scale: {
        mode: Phaser.Scale.RESIZE,
        autoCenter: Phaser.Scale.CENTER_BOTH,
      },
      render: { antialias: true, roundPixels: false },
      input: { activePointers: 3 },
      audio: { noAudio: true },
    });
    game.events.on("battle-ready", (ready: BattleScene) => {
      scene.current = ready;
      ready.callbacks = latest.current.callbacks;
      ready.updateState(latest.current.state);
      queued.current
        .splice(0)
        .forEach((events) => ready.playCombatEvents(events));
      ready.playLiveEvents(queuedLive.current.splice(0));
    });
    game.events.on("art-error", () => latest.current.callbacks.onLoadError?.());
    const restoreVisibility = () => {
      if (document.visibilityState === "visible") {
        queued.current = [];
        scene.current?.skipCombat();
      }
    };
    document.addEventListener("visibilitychange", restoreVisibility);
    const resize = new ResizeObserver(() => {
      if (container.current)
        game.scale.resize(
          container.current.clientWidth,
          container.current.clientHeight,
        );
    });
    resize.observe(container.current);
    return () => {
      resize.disconnect();
      document.removeEventListener("visibilitychange", restoreVisibility);
      scene.current = null;
      queuedLive.current = [];
      queued.current = [];
      game.destroy(true);
    };
  }, []);
  useEffect(() => {
    if (scene.current) {
      scene.current.callbacks = callbacks;
      scene.current.updateState(state);
    }
  }, [state, callbacks]);
  return (
    <div
      className="battle-canvas"
      ref={container}
      role="application"
      aria-label="Chiến trường: kéo để di chuyển map, Shift + kéo để chọn quân, Shift + click để thêm hoặc bỏ quân, click hai ngón để mở lệnh. Cuộn hoặc chụm hai ngón để thu phóng."
    />
  );
});
