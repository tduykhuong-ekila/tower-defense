export interface Point { x: number; y: number }
interface Sample extends Point { at: number }

/** One update of render delay; a finite polyline follows road corners without extrapolation. */
export class MotionTrack {
  private samples: Sample[] = [];
  private lastSignature = "";
  private simulationClockOffset: number | null = null;
  constructor(private delay = 200) {}
  push(point: Point, signature: string, now: number, corners: Point[] = [], simulationAt?: number) {
    if (simulationAt !== undefined && Number.isFinite(simulationAt)) {
      this.simulationClockOffset ??= now - simulationAt;
      now = simulationAt + this.simulationClockOffset;
    }
    if (signature === this.lastSignature) return;
    const previous = this.samples[this.samples.length - 1];
    if (previous && now <= previous.at) return;
    this.lastSignature = signature;
    if (!previous || now - previous.at > 1500) {
      this.samples = [{ ...point, at: now }];
      return;
    }
    const path = [previous, ...corners, point];
    const lengths = path.slice(1).map((p, i) => Math.hypot(p.x - path[i].x, p.y - path[i].y));
    const length = lengths.reduce((a, b) => a + b, 0);
    let traveled = 0;
    for (let i = 1; i < path.length; i++) {
      traveled += lengths[i - 1];
      this.samples.push({ ...path[i], at: previous.at + (now - previous.at) * (length ? traveled / length : 1) });
    }
    if (this.samples.length > 32) this.samples.splice(0, this.samples.length - 32);
  }
  at(now: number): Point | null {
    const time = now - this.delay;
    while (this.samples.length > 2 && this.samples[1].at <= time) this.samples.shift();
    const [a, b] = this.samples;
    if (!a) return null;
    if (!b || time <= a.at) return { x: a.x, y: a.y };
    const ratio = Math.min(1, Math.max(0, (time - a.at) / Math.max(1, b.at - a.at)));
    return { x: a.x + (b.x - a.x) * ratio, y: a.y + (b.y - a.y) * ratio };
  }
}
