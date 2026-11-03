import { upgradeLevel } from "../upgradeLevel";

export const TURRET_ISOMETRIC_Y = 0.55;
export const TURRET_REST_YAW = Math.PI * 0.84;
export const TURRET_TURN_SPEED = Math.PI * 3;
export interface AimPoint { x: number; y: number; }
export type TurretKind = "machineGun" | "cannon" | "tank" | "artillery";
export const TANK_TURRET_MOUNT_X = -2.2;
export const ARTILLERY_MOUNT_X = -4.5;
export const ARTILLERY_BARREL_PITCH = .7;
const ARTILLERY_PROFILES = [
  {length: 37, height: 43, radius: 3.4, muzzleRadius: 4.3, recoil: 2.7},
  {length: 40, height: 44, radius: 3.9, muzzleRadius: 5.1, recoil: 3.3},
  {length: 43, height: 45, radius: 4.4, muzzleRadius: 5.9, recoil: 4},
] as const;
export function artilleryProfile(level: number) { return ARTILLERY_PROFILES[upgradeLevel(level) - 1]; }
export function artilleryMuzzle(level: number, yaw: number, recoil = 0): AimPoint {
  const profile = artilleryProfile(level), length = profile.length - recoil;
  return {x: Math.cos(yaw) * length,
    y: Math.sin(yaw) * length * TURRET_ISOMETRIC_Y - profile.height - length * ARTILLERY_BARREL_PITCH};
}
const TANK_PROFILES = [
  {length: 37, height: 44, radius: 3.2, muzzleRadius: 4.1, recoil: 2},
  {length: 41, height: 45, radius: 3.7, muzzleRadius: 5.3, recoil: 2.7},
  {length: 44, height: 47, radius: 4.2, muzzleRadius: 6.2, recoil: 3.2},
] as const;
export function tankProfile(level: number) { return TANK_PROFILES[upgradeLevel(level) - 1]; }
export function tankMuzzle(level: number, yaw: number, recoil = 0): AimPoint {
  const profile = tankProfile(level), length = profile.length - recoil;
  return {x: Math.cos(yaw) * length,
    y: Math.sin(yaw) * length * TURRET_ISOMETRIC_Y - profile.height};
}

const CANNON_PROFILES = [
  {length: 27, height: 42, radius: 8.5, muzzleRadius: 10, recoil: 3.5},
  {length: 32, height: 43, radius: 10, muzzleRadius: 11.5, recoil: 4.2},
  {length: 37, height: 45, radius: 11.5, muzzleRadius: 12.5, recoil: 5},
] as const;
export const CANNON_BARREL_PITCH = .065;
export function cannonProfile(level: number) { return CANNON_PROFILES[upgradeLevel(level) - 1]; }

export function cannonMuzzle(level: number, yaw: number, recoil = 0): AimPoint {
  const profile = cannonProfile(level), length = profile.length - recoil;
  return {x: Math.cos(yaw) * length,
    y: Math.sin(yaw) * length * TURRET_ISOMETRIC_Y - profile.height - profile.length * CANNON_BARREL_PITCH};
}

export function angleDifference(from: number, to: number) {
  return Math.atan2(Math.sin(to - from), Math.cos(to - from));
}

/** Undo the vertical isometric compression before finding the horizontal yaw. */
export function turretTargetYaw(source: AimPoint, target: AimPoint): number | null {
  const dx = target.x - source.x, dy = (target.y - source.y) / TURRET_ISOMETRIC_Y;
  return Number.isFinite(dx) && Number.isFinite(dy) && Math.hypot(dx, dy) > .001
    ? Math.atan2(dy, dx) : null;
}

export function turnTurret(current: number, desired: number, deltaMs: number) {
  const difference = angleDifference(current, desired);
  const step = TURRET_TURN_SPEED * Math.max(0, Math.min(deltaMs, 100)) / 1000;
  return current + Math.max(-step, Math.min(step, difference));
}

export function turretFrame(yaw: number, frames = 32) {
  return ((Math.round(yaw / (Math.PI * 2) * frames) % frames) + frames) % frames;
}

/** Same model coordinates used by the gun renderer, in battlefield pixels. */
export function turretMuzzle(level: number, yaw: number, recoil = 0, barrel = 0): AimPoint {
  const current = upgradeLevel(level);
  const length = (current === 1 ? 37 : current === 2 ? 40 : 42) - recoil;
  const phase = (barrel % 6) / 6 * Math.PI * 2;
  const side = current === 1 ? 0 : current === 2 ? (barrel % 2 ? 5 : -5) : Math.cos(phase) * 7.1;
  const height = current === 3 ? 49 + Math.sin(phase) * 7.1 : 43;
  return {x: Math.cos(yaw) * length - Math.sin(yaw) * side,
    y: (Math.sin(yaw) * length + Math.cos(yaw) * side) * TURRET_ISOMETRIC_Y - height};
}
