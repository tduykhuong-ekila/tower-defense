import { angleDifference, AimPoint, TANK_TURRET_MOUNT_X, TURRET_ISOMETRIC_Y, turretTargetYaw } from "./turretAim";

export const TANK_REST_YAW = Math.PI * .17;
export const TANK_DRIVE_TURN_SPEED = Math.PI * 2;
export const TANK_DRIVE_DEADBAND = .12;

/** Track actual interpolated displacement, including vertical and diagonal travel. */
export function tankMovementYaw(previous: AimPoint, next: AimPoint): number | null {
  return Math.hypot(next.x - previous.x, next.y - previous.y) > TANK_DRIVE_DEADBAND
    ? turretTargetYaw(previous, next) : null;
}

export function turnTank(current: number, desired: number, deltaMs: number) {
  const step = TANK_DRIVE_TURN_SPEED * Math.max(0, Math.min(deltaMs, 100)) / 1000;
  return current + Math.max(-step, Math.min(step, angleDifference(current, desired)));
}

/** The rearward turret bearing rotates with the chassis, rather than mirroring. */
export function tankMountOffset(yaw: number, scale: number, mountX = TANK_TURRET_MOUNT_X): AimPoint {
  return {x: Math.cos(yaw) * mountX * scale,
    y: Math.sin(yaw) * mountX * TURRET_ISOMETRIC_Y * scale};
}
