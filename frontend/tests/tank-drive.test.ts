import test from "node:test";
import assert from "node:assert/strict";
import { angleDifference, TANK_TURRET_MOUNT_X, TURRET_ISOMETRIC_Y } from "../src/game/systems/turretAim";
import { tankMovementYaw, tankMountOffset, turnTank, TANK_DRIVE_DEADBAND, TANK_DRIVE_TURN_SPEED } from "../src/game/systems/tankDrive";

test("tracks align with full projected movement, including vertical and all diagonals", () => {
  for (let direction = 0; direction < 32; direction++) {
    const yaw = direction * Math.PI / 16;
    const from = {x: 147, y: 583};
    const next = {x: from.x + Math.cos(yaw) * 20, y: from.y + Math.sin(yaw) * 20 * TURRET_ISOMETRIC_Y};
    const actual = tankMovementYaw(from, next)!;
    assert.ok(Math.abs(angleDifference(actual, yaw)) < 1e-10);
  }
});

test("stopped, jittering and invalid positions do not invent new chassis headings", () => {
  assert.equal(tankMovementYaw({x: 0,y: 0},{x: 0,y: 0}), null);
  assert.equal(tankMovementYaw({x: 0,y: 0},{x: TANK_DRIVE_DEADBAND / 2,y: 0}), null);
  assert.equal(tankMovementYaw({x: 0,y: 0},{x: NaN,y: 1}), null);
  assert.equal(tankMovementYaw({x: 0,y: 0},{x: Infinity,y: 1}), null);
});

test("chassis turns take the shortest arc, stop at the target and limit tab-resume jumps", () => {
  const radians = Math.PI / 180;
  assert.ok(Math.abs(angleDifference(turnTank(179*radians,-179*radians,16),-179*radians)) < 1e-10);
  assert.equal(turnTank(.2,.21,16),.21);
  assert.equal(turnTank(.2,2,0),.2);
  assert.ok(turnTank(0,Math.PI,60000) <= TANK_DRIVE_TURN_SPEED*.1);
  let fast=0,slow=0;
  for(let i=0;i<10;i++)fast=turnTank(fast,Math.PI,10);
  for(let i=0;i<2;i++)slow=turnTank(slow,Math.PI,50);
  assert.ok(Math.abs(fast-slow)<1e-10);
});

test("the turret mounting point rotates with the hull without mirroring its world aim", () => {
  for(const scale of [68/94,1])for(let direction=0;direction<32;direction++) {
    const yaw=direction*Math.PI/16,offset=tankMountOffset(yaw,scale);
    assert.ok(Math.abs(Math.hypot(offset.x,offset.y/TURRET_ISOMETRIC_Y)-Math.abs(TANK_TURRET_MOUNT_X)*scale)<1e-10);
    const forward=offset.x*Math.cos(yaw)+offset.y/TURRET_ISOMETRIC_Y*Math.sin(yaw);
    assert.ok(forward<0); // The bearing stays behind the chassis center at every heading.
  }
});
