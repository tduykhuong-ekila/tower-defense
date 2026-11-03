import test from "node:test";
import assert from "node:assert/strict";
import {
  angleDifference, TURRET_ISOMETRIC_Y, TURRET_TURN_SPEED,
  turretFrame, turretMuzzle, turretTargetYaw, turnTurret,
  cannonMuzzle, cannonProfile, CANNON_BARREL_PITCH,
  tankMuzzle, tankProfile,
  artilleryMuzzle, artilleryProfile, ARTILLERY_BARREL_PITCH,
} from "../src/game/systems/turretAim";

test("target bearings undo isometric compression in every quadrant", () => {
  const source = {x: 310, y: 580};
  for (let i = 0; i < 32; i++) {
    const angle = i * Math.PI / 16;
    const target = {x: source.x + 100 * Math.cos(angle), y: source.y + 100 * Math.sin(angle) * TURRET_ISOMETRIC_Y};
    assert.ok(Math.abs(angleDifference(angle, turretTargetYaw(source, target)!)) < 1e-10);
  }
});

test("turrets take the short path through the angle wrap without overshooting", () => {
  const degrees = Math.PI / 180;
  const result = turnTurret(179 * degrees, -179 * degrees, 16);
  assert.ok(Math.abs(angleDifference(result, -179 * degrees)) < 1e-10);
  assert.equal(turnTurret(.2, .21, 16), .21);
  assert.equal(turnTurret(.2, 2, 0), .2);
  assert.equal(turnTurret(.2, 2, -100), .2);
});

test("rotation speed is independent of frame rate and bounded after tab suspension", () => {
  let fast = 0, slow = 0;
  for (let i = 0; i < 10; i++) fast = turnTurret(fast, Math.PI, 10);
  for (let i = 0; i < 2; i++) slow = turnTurret(slow, Math.PI, 50);
  assert.ok(Math.abs(fast - slow) < 1e-10);
  assert.ok(turnTurret(0, Math.PI, 60000) <= TURRET_TURN_SPEED * .1);
});

test("missing coordinates and overlapping targets cannot corrupt the turret heading", () => {
  assert.equal(turretTargetYaw({x: 1, y: 2}, {x: 1, y: 2}), null);
  assert.equal(turretTargetYaw({x: 0, y: 0}, {x: NaN, y: 2}), null);
  assert.equal(turretTargetYaw({x: 0, y: 0}, {x: 1, y: Infinity}), null);
});

test("directional frame indices wrap continuously in both directions", () => {
  for (let i = -64; i <= 64; i++) {
    const yaw = i / 32 * Math.PI * 2;
    assert.equal(turretFrame(yaw), (i % 32 + 32) % 32);
  }
});

test("all upgrade muzzles follow the barrel and recoil, never the fixed foundation", () => {
  for (const level of [1, 2, 3]) for (let i = 0; i < 32; i++) {
    const yaw = i / 16 * Math.PI;
    const point = turretMuzzle(level, yaw), recoiled = turretMuzzle(level, yaw, 2);
    assert.ok((point.x - recoiled.x) * Math.cos(yaw) +
      (point.y - recoiled.y) / TURRET_ISOMETRIC_Y * Math.sin(yaw) > 1.99);
    assert.ok(Number.isFinite(point.x) && Number.isFinite(point.y));
  }
});

test("twin and Gatling shots leave distinct barrels rather than the central hub", () => {
  for (const [level, count] of [[1, 1], [2, 2], [3, 6]]) {
    const points = Array.from({length: count}, (_, barrel) => turretMuzzle(level, .8, 0, barrel));
    assert.equal(new Set(points.map(p => `${p.x.toFixed(3)}:${p.y.toFixed(3)}`)).size, count);
  }
});

test("cannon upgrades retain one forward muzzle with increasing barrel length and recoil", () => {
  let previousLength = 0, previousRecoil = 0;
  for (const level of [1, 2, 3]) {
    const profile = cannonProfile(level);
    assert.ok(profile.length > previousLength && profile.recoil > previousRecoil);
    previousLength = profile.length; previousRecoil = profile.recoil;
    for (let direction = 0; direction < 32; direction++) {
      const yaw = direction / 16 * Math.PI;
      const point = cannonMuzzle(level, yaw), recoil = cannonMuzzle(level, yaw, profile.recoil);
      assert.ok(Math.abs(point.x - Math.cos(yaw) * profile.length) < 1e-10);
      assert.ok(Math.abs(point.y - (Math.sin(yaw) * profile.length * TURRET_ISOMETRIC_Y - profile.height - profile.length * CANNON_BARREL_PITCH)) < 1e-10);
      const back = (point.x - recoil.x) * Math.cos(yaw) + (point.y - recoil.y) / TURRET_ISOMETRIC_Y * Math.sin(yaw);
      assert.ok(Math.abs(back - profile.recoil) < 1e-10);
    }
  }
});

test("tank muzzles preserve a single independent aiming axis at all levels and headings", () => {
  for (const level of [1, 2, 3]) for (let direction = 0; direction < 32; direction++) {
    const yaw = direction / 16 * Math.PI, profile = tankProfile(level);
    const muzzle = tankMuzzle(level, yaw), recoiled = tankMuzzle(level, yaw, profile.recoil);
    assert.ok(Math.abs(muzzle.x - Math.cos(yaw) * profile.length) < 1e-10);
    assert.ok(Math.abs(muzzle.y + profile.height - Math.sin(yaw) * profile.length * TURRET_ISOMETRIC_Y) < 1e-10);
    assert.ok(Math.abs((muzzle.x - recoiled.x) * Math.cos(yaw) + (muzzle.y - recoiled.y) / TURRET_ISOMETRIC_Y * Math.sin(yaw) - profile.recoil) < 1e-10);
  }
  assert.ok(tankProfile(1).length < tankProfile(2).length && tankProfile(2).length < tankProfile(3).length);
});

test("elevated artillery recoil follows the pitched barrel at every heading", () => {
  for(const level of [1,2,3])for(let direction=0;direction<32;direction++) {
    const yaw=direction*Math.PI/16,p=artilleryProfile(level);
    const muzzle=artilleryMuzzle(level,yaw),back=artilleryMuzzle(level,yaw,p.recoil);
    assert.ok(muzzle.y < Math.sin(yaw)*p.length*TURRET_ISOMETRIC_Y-p.height);
    assert.ok(Math.abs(muzzle.x-back.x-Math.cos(yaw)*p.recoil)<1e-10);
    assert.ok(Math.abs(muzzle.y-back.y-(Math.sin(yaw)*TURRET_ISOMETRIC_Y-ARTILLERY_BARREL_PITCH)*p.recoil)<1e-10);
  }
});
