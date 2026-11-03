/** Phaser's scroll is measured from the unscaled viewport, around originX/Y. */
export interface CameraPort {
  x: number; y: number; width: number; height: number;
  originX: number; originY: number; zoom: number; scrollX: number; scrollY: number;
  setZoom: (zoom: number) => unknown;
  clampX: (scroll: number) => number;
  clampY: (scroll: number) => number;
}
type Point = { x: number; y: number };
export const CAMERA_ZOOM_CONFIG = { damping: 18, zoomStep: 0.12, wheelSensitivity: 0.0012 };

/** One target, no tweens or listeners. Called exclusively from the Phaser update loop. */
export class SmoothCameraController {
  targetZoom: number;
  private minZoom = 0.1;
  private maxZoom = 2;
  private anchor?: Point;
  private focus?: Point;
  constructor(private camera: CameraPort, private updateBounds: () => void) {
    this.targetZoom = camera.zoom;
  }
  setLimits(min: number, max: number) {
    this.minZoom = min;
    this.maxZoom = Math.max(min, max);
    this.targetZoom = this.clamp(this.targetZoom);
  }
  private clamp(zoom: number) { return Math.min(this.maxZoom, Math.max(this.minZoom, zoom)); }
  zoomTo(zoom: number, anchor?: Point) {
    if (!Number.isFinite(zoom)) return;
    this.targetZoom = this.clamp(zoom);
    this.anchor = anchor;
    this.focus = undefined;
  }
  wheel(deltaY: number, anchor: Point) {
    if (!Number.isFinite(deltaY) || deltaY === 0) return;
    const magnitude = Math.max(-240, Math.min(240, deltaY));
    this.zoomTo(this.targetZoom * Math.exp(-magnitude * CAMERA_ZOOM_CONFIG.wheelSensitivity), anchor);
  }
  step(direction: number) {
    this.zoomTo(this.targetZoom * Math.exp(direction * CAMERA_ZOOM_CONFIG.zoomStep));
  }
  moveTo(x: number, y: number, zoom = this.targetZoom, immediate = false) {
    this.zoomTo(zoom);
    this.focus = { x, y };
    if (immediate) {
      this.camera.setZoom(this.targetZoom);
      this.updateBounds();
      this.camera.scrollX = this.camera.clampX(x - this.camera.width / 2);
      this.camera.scrollY = this.camera.clampY(y - this.camera.height / 2);
      this.focus = undefined;
    }
  }
  cancelPan() { this.focus = undefined; this.anchor = undefined; }
  update(deltaMs: number) {
    if (!(deltaMs > 0)) return;
    const c = this.camera;
    const alpha = 1 - Math.exp(-CAMERA_ZOOM_CONFIG.damping * deltaMs / 1000);
    const oldZoom = c.zoom;
    let zoom = oldZoom + (this.targetZoom - oldZoom) * alpha;
    if (Math.abs(zoom - this.targetZoom) < 0.00001) zoom = this.targetZoom;
    let centerX = c.scrollX + c.width / 2;
    let centerY = c.scrollY + c.height / 2;
    if (this.focus) {
      centerX += (this.focus.x - centerX) * alpha;
      centerY += (this.focus.y - centerY) * alpha;
      if (Math.hypot(this.focus.x - centerX, this.focus.y - centerY) < 0.01) {
        centerX = this.focus.x; centerY = this.focus.y; this.focus = undefined;
      }
    } else if (this.anchor && oldZoom !== zoom) {
      // Preserve the world point under the anchor without using a stale camera matrix.
      centerX += (this.anchor.x - c.x - c.width * c.originX) * (1 / oldZoom - 1 / zoom);
      centerY += (this.anchor.y - c.y - c.height * c.originY) * (1 / oldZoom - 1 / zoom);
    }
    if (oldZoom !== zoom) { c.setZoom(zoom); this.updateBounds(); }
    c.scrollX = c.clampX(centerX - c.width / 2);
    c.scrollY = c.clampY(centerY - c.height / 2);
  }
  destroy() { this.cancelPan(); this.targetZoom = this.camera.zoom; }
}
