import type Phaser from "phaser";
import { upgradeLevel } from "../upgradeLevel";
import {
  AimPoint, angleDifference, TURRET_ISOMETRIC_Y, TURRET_REST_YAW,
  turnTurret, turretFrame, turretMuzzle, turretTargetYaw,
  cannonProfile, cannonMuzzle, CANNON_BARREL_PITCH, TurretKind,
  tankProfile, tankMuzzle,
  artilleryProfile, artilleryMuzzle, ARTILLERY_MOUNT_X, ARTILLERY_BARREL_PITCH,
} from "../systems/turretAim";
import { tankMountOffset, TANK_REST_YAW } from "../systems/tankDrive";
import { buildArtillery } from "./artilleryModel";

const FRAMES = 32, TOWER_SIZE = 94;
// Keep the original artwork's 512px sampling density. Crop the empty lower
// foundation area out of each frame so the directional atlas stays compact.
const HEAD_TOP = 0, HEAD_HEIGHT = 3 / 4;
type AssemblyPart = "turret" | "hull";
const textureKey = (level: number, kind: TurretKind = "machineGun", part: AssemblyPart = "turret") => `${kind === "machineGun" ? "mg" : kind}-${part}-${upgradeLevel(level)}`;
export const tankHullTexture = (level: number) => textureKey(level, "tank", "hull");
export const vehicleHullTexture = (level: number, kind: "tank" | "artillery") => textureKey(level, kind, "hull");
// Elevated artillery needs transparent room above the gun at rearward headings.
// The artillery atlas uses 384px sampling (over 5x gameplay size) so its padded
// frames retain crisp edges without a 4096x4096 texture for every upgrade.
function assemblyLayout(kind: TurretKind, part: AssemblyPart = "turret") {
  if (kind === "artillery") return part === "turret"
    ? {width: 1.25, height: 1, top: -.25, columns: 8}
    : {width: 1, height: .875, top: .25, columns: 8};
  return {width: 1, height: HEAD_HEIGHT, top: part === "hull" ? .25 : HEAD_TOP, columns: 8};
}
type Vec3 = [number, number, number];
type Face = { points: Vec3[]; color: string; edge?: string; metal?: boolean };

/** A small orthographic model lets only the gun yaw, with upright armor in every
 * direction. Its shaded frames are baked once, never rebuilt during combat. */
function drawGun(ctx: CanvasRenderingContext2D, level: number, yaw: number, resolution: number, kind: TurretKind, part: AssemblyPart) {
  const faces: Face[] = [];
  const steel = "#9a9fa6", olive = "#969958", gold = "#e5b956";
  const edge = "#3c4035";
  const add = (points: Vec3[], color: string, outline = edge, metal = false) => faces.push({points, color, edge: outline, metal});
  function box(x: number, y: number, z: number, length: number, width: number, height: number, color: string, bevel = 1.4) {
    const a = length / 2, b = width / 2, c = height / 2;
    const ring = (h: number, inset: number): Vec3[] => [
      [-a + bevel, -b + inset, h], [a - bevel, -b + inset, h],
      [a - inset, -b + bevel, h], [a - inset, b - bevel, h],
      [a - bevel, b - inset, h], [-a + bevel, b - inset, h],
      [-a + inset, b - bevel, h], [-a + inset, -b + bevel, h],
    ].map(p => [p[0] + x, p[1] + y, p[2] + z] as Vec3);
    const lower = ring(-c + bevel, 0), upper = ring(c - bevel, 0), top = ring(c, bevel * .6);
    const bottom = ring(-c, bevel * .6);
    add([...top].reverse(), color);
    for (let i = 0; i < 8; i++) {
      const next = (i + 1) % 8;
      add([lower[i], lower[next], upper[next], upper[i]], color);
      add([upper[i], upper[next], top[next], top[i]], color, "#b4b185");
      add([bottom[i], bottom[next], lower[next], lower[i]], color);
    }
  }
  function cylinder(start: number, end: number, side: number, height: number, radius: number, color: string, hollow = false) {
    const count = 16;
    const circle = (x: number, r: number): Vec3[] => Array.from({length: count}, (_, i) => {
      const a = i / count * Math.PI * 2;
      return [x, side + Math.cos(a) * r, height + Math.sin(a) * r];
    });
    const back = circle(start, radius), front = circle(end, radius);
    add([...back].reverse(), color);
    for (let i = 0; i < count; i++) add([back[i], front[i], front[(i + 1) % count], back[(i + 1) % count]], color, "", true);
    if (!hollow) { add(front, color, edge, true); return; }
    const inner = circle(end + .08, radius * .64);
    for (let i = 0; i < count; i++) add([front[i], inner[i], inner[(i + 1) % count], front[(i + 1) % count]], "#d8dcd6", "#46515a", true);
    add(inner, "#0d151c", "#27333c");
  }
  function verticalCylinder(z: number, height: number, radius: number, color: string, cx = 0, cy = 0) {
    const top: Vec3[] = [];
    for (let i = 0; i < 16; i++) {
      const a = i / 16 * Math.PI * 2, b = (i + 1) / 16 * Math.PI * 2;
      const p: Vec3 = [cx + Math.cos(a) * radius, cy + Math.sin(a) * radius, z];
      const q: Vec3 = [cx + Math.cos(b) * radius, cy + Math.sin(b) * radius, z];
      add([p, q, [q[0], q[1], z + height], [p[0], p[1], z + height]], color, "");
      top.push([p[0], p[1], z + height]);
    }
    add(top.reverse(), color);
  }
  function rod(from: Vec3, to: Vec3, radius: number, color: string) {
    const axis = to.map((n, i) => n - from[i]);
    const length = Math.hypot(...axis);
    if (!length) return;
    const n = axis.map(x => x / length);
    const helper = Math.abs(n[2]) < .9 ? [0, 0, 1] : [0, 1, 0];
    const u = [n[1] * helper[2] - n[2] * helper[1], n[2] * helper[0] - n[0] * helper[2], n[0] * helper[1] - n[1] * helper[0]];
    const magnitude = Math.hypot(...u);
    u.forEach((_, i) => u[i] /= magnitude);
    const v = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]];
    const ring = (center: Vec3): Vec3[] => Array.from({length: 16}, (_, i) => {
      const a = i / 16 * Math.PI * 2;
      return center.map((value, j) => value + radius * (u[j] * Math.cos(a) + v[j] * Math.sin(a))) as Vec3;
    });
    const back = ring(from), front = ring(to);
    add([...back].reverse(), color, edge, true); add(front, color, edge, true);
    for (let i = 0; i < 16; i++) add([back[i], front[i], front[(i + 1) % 16], back[(i + 1) % 16]], color, "", true);
  }
  if (kind === "artillery") {
    buildArtillery(level, part, {add, box, rod, verticalCylinder});
  } else if (kind === "tank" && part === "hull") {
    const dark = "#39424a", tread = "#64666c", hull = "#87924e";
    // A real 3D track loop and roadwheels give a readable fore/aft axis at all
    // headings. Track centers, chassis dimensions and collision size are shared.
    const outline = [[-21,10],[21,10],[27,14],[27,19],[21,23],[-21,23],[-27,19],[-27,14]];
    for (const side of [-1, 1]) {
      const y = side * 17.5, near = y + side * 3.5, far = y - side * 3.5;
      add(outline.map(([x,z]) => [x, near, z] as Vec3), dark);
      add(outline.map(([x,z]) => [x, far, z] as Vec3), dark);
      for (let i = 0; i < outline.length; i++) {
        const [x,z] = outline[i], [nx,nz] = outline[(i+1)%outline.length];
        add([[x,near,z],[nx,near,nz],[nx,far,nz],[x,far,z]], tread, "#303940", true);
        const length = Math.hypot(nx-x,nz-z), steps = Math.ceil(length/4);
        const tx=(nx-x)/length, tz=(nz-z)/length;
        for(let j=0;j<steps;j++) {
          const cx=x+(nx-x)*(j+.5)/steps, cz=z+(nz-z)*(j+.5)/steps;
          const a: Vec3=[cx-tx*1.5+tz*.4,near,cz-tz*1.5-tx*.4];
          const b: Vec3=[cx+tx*1.5+tz*.4,near,cz+tz*1.5-tx*.4];
          add([a,b,[b[0],far,b[2]],[a[0],far,a[2]]], tread, "#353c43", true);
        }
      }
      for(const x of [-20,-7,6,19]) {
        rod([x,y,16.5],[x,side*21.1,16.5],5.2,dark);
        rod([x,side*21.1,16.5],[x,side*21.35,16.5],4.3,hull);
        rod([x,side*21.36,16.5],[x,side*21.5,16.5],2.7,dark);
        rod([x,side*21.51,16.5],[x,side*21.9,16.5],1.5,gold);
      }
      if(level>1) for(const x of [-15,0,15]) {
        box(x,side*22,23.5,14,2.1,10.5,steel,1.1);
        box(x,side*22.15,23.5,12,2.4,8.7,hull,1);
        if(level===3) box(x,side*23.4,21.8,13,1,5,dark,.6);
        for(const offset of [-5,5]) rod([x+offset,side*23.5,27],[x+offset,side*24,27],.65,level===3?gold:steel);
      }
    }
    box(-4,0,20,44,28,6,dark,2);
    box(-5,0,26,32,28,12,hull,2.8);
    add([[11,-14,32],[26,-14,23],[26,14,23],[11,14,32]],hull);
    add([[11,-14,17.5],[26,-14,17.5],[26,-14,23],[11,-14,32]],hull);
    add([[11,14,17.5],[26,14,17.5],[26,14,23],[11,14,32]],hull);
    add([[26,-14,17.5],[26,14,17.5],[26,14,23],[26,-14,23]],hull);
    // Frontal armor and warm yellow headlights identify the forward direction.
    if(level>1) {
      add([[10.5,-12,33.3],[25,-12,25],[25,12,25],[10.5,12,33.3]],hull,"#aeb4a0");
      for(const y of [-12,0,12]) rod([11,y,33.6],[25,y,25.6],.7,level===3?steel:dark);
    } else box(16,0,29.5,9,13,1.5,hull,.6);
    for(const side of [-1,1]) {
      box(24,side*14.5,24.5,5,6,3.5,level===3?steel:dark,.7);
      box(26.6,side*14.5,24.5,.4,4.5,2.6,"#ffcf46",.1);
      box(26.85,side*14.5,24.5,.2,2.1,2,"#fff2a0",.05);
      box(-17,side*10.5,32.5,7,7,5.5,level===3?dark:"#79664b",.7);
      box(-17,side*10.5,35.4,1.5,7.4,.8,level===3?gold:steel,.25);
      if(level>1) {
        rod([27,side*9,19],[28,side*9,19],1.5,steel);
        rod([28,side*9,19],[28.7,side*9,19],.8,dark);
      }
    }
    verticalCylinder(31.2,1,15.5,dark,-2.2);
  } else if (kind === "tank") {
    const profile = tankProfile(level), z = profile.height;
    const dark = "#62636b", hull = "#929953", paint = "#a2a65d";
    // Model the approved tank's sloped octagonal shell, rather than a square
    // gun box. The roof, mantlet and barrel all rotate as one assembly.
    const turretRing = (height: number, length: number, width: number): Vec3[] => [
      [-length + 4,-width,height],[length - 4,-width,height],
      [length,-width + 4,height],[length,width - 4,height],
      [length - 4,width,height],[-length + 4,width,height],
      [-length,width - 4,height],[-length,-width + 4,height],
    ].map(([x,y,h]) => [x - 3,y,h]);
    verticalCylinder(31.5, 3, 15.5, dark);
    verticalCylinder(34.5, 1.8, 15, hull);
    const roofHeight=49+level-1;
    const bottom = turretRing(36.3,17,14.3), shoulder = turretRing(roofHeight-4,16.5,13.6), roof = turretRing(roofHeight,13.8,11.5);
    add([...roof].reverse(), paint, "#c5c68e");
    for(let i=0;i<8;i++) {
      const n=(i+1)%8;
      add([bottom[i],bottom[n],shoulder[n],shoulder[i]],hull);
      add([shoulder[i],shoulder[n],roof[n],roof[i]],hull,"#b6b981");
    }
    // Large fasteners and separate cheek panels are visible in the source art
    // even at sprite size; avoid adding thin antennas or unreadable decoration.
    for(const side of [-1,1])for(const x of [-12,-3,6]) {
      rod([x,side*14.1,43.5],[x,side*14.5,43.5],.6,level===3?gold:"#c4c5b5");
      rod([x,side*14.1,38],[x,side*14.5,38],.6,level===3?gold:"#c4c5b5");
    }
    box(12, 0, z, 3.5, 14.5, 12.5, hull, 1);
    for(const y of [-5.5,5.5])for(const h of [-4,4])
      rod([13.7,y,z+h],[14.3,y,z+h],.7,"#b2b3ae");

    // Painted, turned barrel: olive collar and tube, with no generic silver
    // bore rim. Brake ports are recessed patches on the curved surface itself.
    const ring = (x: number, radius: number): Vec3[] => Array.from({length:32},(_,i)=> {
      const a=i/32*Math.PI*2;return [x,Math.cos(a)*radius,z+Math.sin(a)*radius];
    });
    type Section = {x:number;radius:number;color:string;ports?:boolean};
    const end=profile.length, brakeStart=end-(level===1?2.5:7.5);
    const sections:Section[]=[
      {x:13.5,radius:5.7,color:hull},{x:14.4,radius:6,color:paint},
      {x:16.8,radius:6,color:hull},{x:17.5,radius:4.7,color:hull},
      {x:20,radius:profile.radius+.45,color:paint},
      {x:21,radius:profile.radius,color:paint},
      {x:brakeStart,radius:profile.radius*.93,color:paint},
      {x:brakeStart+.6,radius:profile.muzzleRadius*.93,color:level===1?paint:dark},
      {x:brakeStart+1.2,radius:profile.muzzleRadius,color:level===1?paint:dark},
    ];
    if(level>1)for(let i=0;i<(level===3?3:2);i++) {
      const x=brakeStart+1.4+i*(level===3?1.65:2.25);
      sections.push({x,radius:profile.muzzleRadius,color:dark},
        {x:x+1,radius:profile.muzzleRadius,color:dark,ports:true});
    }
    sections.push({x:end-.5,radius:profile.muzzleRadius,color:level===1?paint:dark},
      {x:end,radius:profile.muzzleRadius*.9,color:level===1?paint:"#9b9ba1"});
    const rings=sections.map(s=>ring(s.x,s.radius));
    for(let j=1;j<rings.length;j++)for(let i=0;i<32;i++) {
      const n=(i+1)%32, port=sections[j].ports&&([0,1,7,8,9,15,16,17,23,24,25,31].includes(i));
      add([rings[j-1][i],rings[j][i],rings[j][n],rings[j-1][n]],port?"#1c2026":sections[j].color,"",!port&&level>1&&j>=8);
    }
    const lip=rings[rings.length-1], bore=ring(end+.03,profile.muzzleRadius*.66);
    const deep=ring(end-2.5,profile.muzzleRadius*.61);
    for(let i=0;i<32;i++) {
      const n=(i+1)%32;
      add([lip[i],bore[i],bore[n],lip[n]],level===1?"#a9aa6a":"#aaabb0","",level>1);
      add([bore[i],deep[i],deep[n],bore[n]],"#252a29","");
    }
    add(deep,"#0b1013","");
    // Fine olive seams on the tube are rings, not exposed silver pipe joints.
    if(level>1)for(const x of [24,level===3?30:27]) {
      const a=ring(x,profile.radius+.06),b=ring(x+.18,profile.radius+.06);
      for(let i=0;i<32;i++) {
        const n=(i+1)%32;add([a[i],b[i],b[n],a[n]],"#626b3e","");
      }
    }
    // Same cheek panels, hatch and rear boxes, reinforced at higher levels.
    for (const side of [-1, 1]) {
      const y = side * 14;
      if (level > 1) {
        box(-4, y, 42, 21, 3, 12, steel, 1);
        box(-4, y + side * .2, 42, 18, 3.4, 10, hull, 1);
        box(-17, side * 10, 43, 7, 8, 9, dark);
      }
      if (level === 3) {
        for (const x of [-10, -3, 4]) {
          box(x, side * 16.5, 42.5, 5.8, 3, 12, dark, .9);
          rod([x, side * 18, 46.5], [x, side * 18.6, 46.5], .8, gold);
          rod([x, side * 18, 38.5], [x, side * 18.6, 38.5], .8, gold);
        }
        box(-15, side * 11, roofHeight, 5, 5, 3, gold, .6);
      }
    }
    verticalCylinder(roofHeight, 1, 5.8, dark,-5,-2);
    verticalCylinder(roofHeight+1, 1.5, 5.3, paint,-5,-2);
    box(-5,-2,roofHeight+2.7,4.5,1.1,.9,hull,.3);
    box(5, -6, roofHeight+1.5, 5, 3.5, 2, dark, .5);
    box(-12, 8, roofHeight+1.5, 3.5, 3.5, 2.5, hull, .6);
    if (level > 1) {
      box(-4, 0, roofHeight+4, 3.5, 4, 3, dark, .5);
      const opticWidth = level === 3 ? 10 : 6, opticZ=roofHeight+7.5;
      box(-4, 0, opticZ, 8, opticWidth, 5.5, hull, 1);
      box(.2, 0, opticZ, .6, opticWidth - 1, 5, dark, .1);
      box(.6, level === 3 ? -1.8 : 0, opticZ, .3, level === 3 ? 4.5 : 3.8, 3.5, "#168fd0", .08);
      box(.8, level === 3 ? -2.5 : -.8, opticZ+1, .15, 1.2, 1, "#91ebff", .03);
      if (level === 3) box(.6, 3, opticZ, .3, 2.2, 3, "#68d7f4", .08);
    }
  } else if (kind === "cannon") {
    const profile = cannonProfile(level), z = profile.height;
    const iron = "#505361", red = "#b64a3e", wood = "#ab7137";
    const ring = (x: number, radius: number): Vec3[] => Array.from({length: 24}, (_, i) => {
      const a = i / 24 * Math.PI * 2;
      return [x, Math.cos(a) * radius, z + x * CANNON_BARREL_PITCH + Math.sin(a) * radius];
    });
    // A single turned barrel, including its rounded breech and one hollow bore.
    const sections = [
      {x: -25, radius: 2.5, color: iron}, {x: -23, radius: profile.radius * .7, color: iron},
      {x: -18, radius: profile.radius + 1, color: iron},
      {x: 1, radius: profile.radius + 1, color: level > 1 ? olive : iron},
      {x: 6, radius: profile.radius, color: iron},
      {x: profile.length - 7, radius: profile.radius * .85, color: iron},
      {x: profile.length - 5.5, radius: profile.muzzleRadius, color: level === 3 ? gold : level === 2 ? steel : iron},
      {x: profile.length - 1, radius: profile.muzzleRadius, color: level === 3 ? gold : level === 2 ? steel : iron},
      {x: profile.length, radius: profile.muzzleRadius * .96, color: level === 3 ? gold : steel},
    ];
    const rings = sections.map(section => ring(section.x, section.radius));
    add([...rings[0]].reverse(), iron);
    for (let j = 1; j < rings.length; j++) for (let i = 0; i < 24; i++)
      add([rings[j - 1][i], rings[j][i], rings[j][(i + 1) % 24], rings[j - 1][(i + 1) % 24]], sections[j].color, "", true);
    const lip = rings[rings.length - 1], bore = ring(profile.length + .1, profile.muzzleRadius * .73);
    for (let i = 0; i < 24; i++)
      add([lip[i], bore[i], bore[(i + 1) % 24], lip[(i + 1) % 24]], level === 3 ? "#f3ce78" : "#b7bdc5", "#424653", true);
    add(bore, "#0c1016", "#292d36");
    // Bearing and U-shaped cradle stay recognizable across all three upgrades.
    verticalCylinder(27, 3, 19.5, olive);
    verticalCylinder(30, 2.5, 17, level === 3 ? gold : steel);
    box(-5, 0, 33, 26, 30, 3, level === 1 ? wood : olive);
    for (const side of [-1, 1]) {
      const y = side * (level === 3 ? 17 : 14);
      if (level === 3) box(-6, y, 42, 28, 4.5, 27, gold, 2);
      box(-6, y + side * (level === 3 ? .2 : 0), level === 3 ? 42 : 38,
        level === 3 ? 24 : 19, level === 3 ? 4.8 : 4, level === 3 ? 23 : 15, level === 1 ? wood : olive, 1.8);
      rod([-5, y, z], [-5, y + side * 4, z], level === 3 ? 7.2 : 6, level === 1 ? red : steel);
      rod([-5, y + side * 4, z], [-5, y + side * 4.8, z], 3.8, gold);
      if (level === 2) {
        box(5, side * 16, 36, 16, 3, 13, steel);
        box(5, side * 16.2, 36, 13, 3.3, 10, olive);
        for (let i = 0; i < 10; i++) {
          const a = i / 10 * Math.PI * 2;
          box(-5 + Math.cos(a) * 7, y + side * 3, z + Math.sin(a) * 7, 2.8, 3, 2.8, steel, .4);
        }
      }
      if (level === 3) {
        rod([-1, side * 21, 32], [-14, side * 20, 45], 1.9, steel);
        rod([-1, side * 21, 32], [-6, side * 20.6, 37], 3, gold);
        rod([-13, side * 20, 44], [-15, side * 20, 46], 2.8, gold);
        rod([-6, side * 20, 42], [-6, side * 21, 42], 2.7, "#35bce9");
      }
    }
    // Distinct broad color bands: brick red, olive/silver, then brass/olive.
    if (level < 3) cylinder(-18, -14, 0, z - 16 * CANNON_BARREL_PITCH, profile.radius + 1.8, red);
    if (level > 1) {
      cylinder(-14, 0, 0, z - 7 * CANNON_BARREL_PITCH, profile.radius + 2, level === 3 ? "#687244" : olive);
      for (const x of [-15, 1]) cylinder(x, x + 2.5, 0, z + x * CANNON_BARREL_PITCH, profile.radius + 2.8, level === 3 ? gold : steel);
    }
    if (level === 3) {
      box(-9, 0, z + 16, 12, 6, 3, gold);
      cylinder(-17, -3, 0, z + 21, 4.2, olive);
      cylinder(-5, -2.5, 0, z + 21, 4.8, gold);
      cylinder(-2.5, -2.3, 0, z + 21, 3.4, "#28bdec");
    }
  } else {
    const elite = level === 3, z = elite ? 49 : 43;
    verticalCylinder(32, 4, 10, olive);
    verticalCylinder(36, 3, 7.5, steel);
    box(-5, 0, z, elite ? 35 : 30, elite ? 29 : 22, elite ? 25 : 19, olive, 2.4);
    box(-5, 0, z + (elite ? 13 : 10), elite ? 25 : 23, elite ? 24 : 18, 2.5, olive);
    // Reinforcing straps, rear cap, ammunition crates and side armor.
    for (const x of [-17, 7]) box(x, 0, z, 3, elite ? 31 : 24, elite ? 26 : 20, elite ? gold : steel, .9);
    box(-23, 0, z - 1, 5, elite ? 25 : 18, elite ? 20 : 15, steel);
    for (const side of (level === 1 ? [1] : [-1, 1])) {
      const y = side * (elite ? 20 : level === 2 ? 17 : 15);
      box(-10, y, z - 3, level === 1 ? 13 : 18, 9, level === 1 ? 13 : 16, level === 1 ? "#9e6d38" : olive);
      box(-10, y, z + (level === 1 ? 4 : 5), level === 1 ? 14 : 19, 10, 2, steel, .6);
      box(-10, y, z - 3, 2, 10, level === 1 ? 15 : 18, elite ? gold : steel, .5);
      if (level > 1) box(3, side * (elite ? 18 : 15), z, 17, 3, elite ? 25 : 23, olive);
      if (elite) for (const x of [-15, -10, -5]) box(x, side * 25, z - 2, 1.6, 1, 10, gold, .3);
    }
    if (elite) {
      cylinder(10, 17, 0, z, 11, steel);
      for (let i = 0; i < 6; i++) {
        const a = i / 6 * Math.PI * 2;
        const y = Math.cos(a) * 7.1, h = z + Math.sin(a) * 7.1;
        cylinder(15, 42, y, h, 2.65, "#626c78", true);
      }
      cylinder(29, 32, 0, z, 10.2, gold);
      // The hoop is behind the muzzle tips, leaving all six openings readable.
      for (let i = 0; i < 6; i++) {
        const a = i / 6 * Math.PI * 2;
        cylinder(32, 42, Math.cos(a) * 7.1, z + Math.sin(a) * 7.1, 2.65, "#626c78", true);
        cylinder(39.5, 42, Math.cos(a) * 7.1, z + Math.sin(a) * 7.1, 2.85, steel, true);
      }
      box(6, 0, z + 17, 7, 9, 7, steel);
      cylinder(9.6, 10.6, 0, z + 17, 2.6, "#41c9f0");
    } else {
      for (const side of (level === 1 ? [0] : [-5, 5])) {
        cylinder(9, 15, side, z, 5, steel);
        cylinder(15, level === 1 ? 37 : 40, side, z, 3.1, "#626c78", true);
        cylinder(18.5, 19.5, side, z, 3.35, "#424d59");
        cylinder(level === 1 ? 31 : 34, level === 1 ? 37 : 40, side, z, 4.2, steel, true);
      }
      // Handle and large panel fasteners read at normal gameplay size.
      box(-7, 0, z + 14, 2.4, 15, 2.4, steel, .5);
      for (const side of [-6, 6]) box(-7, side, z + 11, 2.4, 2.4, 6, steel, .5);
    }
  }
  const rotate = ([x, y, z]: Vec3): Vec3 => [x * Math.cos(yaw) - y * Math.sin(yaw), x * Math.sin(yaw) + y * Math.cos(yaw), z];
  const transformed = faces.map(face => ({...face, points: face.points.map(rotate)}));
  const depth = (face: Face) => face.points.reduce((sum, p) => sum + p[1] * .84 + p[2] * .55, 0) / face.points.length;
  transformed.sort((a, b) => depth(a) - depth(b));
  ctx.save();
  ctx.scale(resolution / TOWER_SIZE, resolution / TOWER_SIZE);
  const layout = assemblyLayout(kind, part);
  ctx.translate(TOWER_SIZE * layout.width / 2, TOWER_SIZE * (.89 - layout.top));
  ctx.lineJoin = "round";
  for (const face of transformed) {
    const [a, b, c] = face.points;
    const u = b.map((n, i) => n - a[i]), v = c.map((n, i) => n - a[i]);
    let normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
    const magnitude = Math.hypot(...normal) || 1;
    normal = normal.map(n => n / magnitude);
    // Two-sided polygons also cover the barrel bores; shade against a fixed light.
    if (normal[1] * .84 + normal[2] * .55 < 0) normal = normal.map(n => -n);
    const diffuse = Math.max(0, normal[0] * -.4 + normal[1] * -.45 + normal[2] * .8);
    const light = face.metal ? .48 + .65 * diffuse : .65 + .4 * diffuse;
    const shine = face.metal ? 64 * Math.pow(Math.max(0, normal[0] * -.25 + normal[1] * .22 + normal[2] * .94), 18) : 0;
    const rgb = [1, 3, 5].map(i => Math.min(255, Math.round(parseInt(face.color.slice(i, i + 2), 16) * light + shine)));
    ctx.beginPath();
    face.points.forEach((p, i) => {
      const x = p[0], y = p[1] * TURRET_ISOMETRIC_Y - p[2];
      if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = `rgb(${rgb.join(",")})`;
    ctx.fill();
    if (face.edge) {
      ctx.strokeStyle = face.edge;
      ctx.lineWidth = .22;
      ctx.stroke();
    }
  }
  ctx.restore();
}

export function bakeTurretTextures(scene: Phaser.Scene, kind: TurretKind, onlyLevel?: number, part: AssemblyPart = "turret") {
  const renderer = scene.game.renderer;
  const gl = renderer && "gl" in renderer ? renderer.gl : undefined;
  const largeTexture = !gl || gl.getParameter(gl.MAX_TEXTURE_SIZE) >= 4096;
  const resolution = kind === "artillery" && part === "turret" ? (largeTexture ? 384 : 192) : (largeTexture ? 512 : 256);
  const layout = assemblyLayout(kind, part);
  const frameWidth = resolution * layout.width, frameHeight = resolution * layout.height;
  for (let level = 1; level <= 3; level++) {
    if (onlyLevel !== undefined && level !== upgradeLevel(onlyLevel)) continue;
    if (scene.textures.exists(textureKey(level, kind, part))) continue;
    const canvas = document.createElement("canvas");
    canvas.width = frameWidth * layout.columns; canvas.height = frameHeight * FRAMES / layout.columns;
    const ctx = canvas.getContext("2d")!;
    for (let frame = 0; frame < FRAMES; frame++) {
      ctx.save(); ctx.translate((frame % layout.columns) * frameWidth, Math.floor(frame / layout.columns) * frameHeight);
      // Clip each cell so an antialiased edge cannot bleed into its neighbor.
      ctx.beginPath(); ctx.rect(0, 0, frameWidth, frameHeight); ctx.clip();
      drawGun(ctx, level, frame / FRAMES * Math.PI * 2, resolution, kind, part); ctx.restore();
    }
    const texture = scene.textures.addCanvas(textureKey(level, kind, part), canvas)!;
    for (let frame = 0; frame < FRAMES; frame++)
      texture.add(frame, 0, (frame % layout.columns) * frameWidth, Math.floor(frame / layout.columns) * frameHeight, frameWidth, frameHeight);
  }
  if (!scene.textures.exists("mg-muzzle-flash")) {
    const canvas = document.createElement("canvas"); canvas.width = 32; canvas.height = 24;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#f9bf43"; ctx.beginPath();
    ctx.moveTo(0, 12); ctx.lineTo(9, 3); ctx.lineTo(12, 9); ctx.lineTo(31, 12);
    ctx.lineTo(12, 15); ctx.lineTo(9, 21); ctx.closePath(); ctx.fill();
    ctx.fillStyle = "#fff1bc"; ctx.beginPath();ctx.ellipse(8,12,9,3,0,0,Math.PI*2);ctx.fill();
    scene.textures.addCanvas("mg-muzzle-flash", canvas);
  }
}

type PendingShot = { targetId: string; expires: number; launch: (point: AimPoint) => void };

export class AimedTurret {
  readonly head: Phaser.GameObjects.Image;
  readonly flash: Phaser.GameObjects.Image;
  yaw = TURRET_REST_YAW;
  desiredYaw = TURRET_REST_YAW;
  private level: number;
  private recoil = 0;
  private barrel = 0;
  private flashUntil = 0;
  private eventTarget?: {id: string; expires: number};
  private pending: PendingShot[] = [];
  private hullYaw = TANK_REST_YAW;
  private scale: number;

  constructor(private root: Phaser.GameObjects.Container, level: number, private kind: TurretKind = "machineGun", size = TOWER_SIZE) {
    this.level = upgradeLevel(level);
    this.scale = size / TOWER_SIZE;
    bakeTurretTextures(root.scene, kind, this.level);
    if (kind !== "machineGun") this.yaw = this.desiredYaw = Math.PI * .17;
    const layout = assemblyLayout(kind);
    this.head = root.scene.add.image(0, 0, textureKey(level, kind), turretFrame(this.yaw))
      .setOrigin(.5, (.89 - layout.top) / layout.height).setDisplaySize(size * layout.width, size * layout.height);
    this.flash = root.scene.add.image(0, 0, "mg-muzzle-flash").setOrigin(0, .5).setDisplaySize(12, 9).setVisible(false);
    if (kind === "cannon") this.flash.setDisplaySize(21, 15);
    if (kind === "tank") this.flash.setDisplaySize(15 * this.scale, 10 * this.scale);
    if (kind === "artillery") this.flash.setDisplaySize(20 * this.scale, 12 * this.scale);
    const offset = this.mountOffset(); this.head.setPosition(offset.x, offset.y);
    root.add([this.head, this.flash]);
  }

  setLevel(level: number) {
    this.level = upgradeLevel(level);
    bakeTurretTextures(this.root.scene, this.kind, this.level);
    this.head.setTexture(textureKey(level, this.kind), turretFrame(this.yaw));
  }

  fire(targetId: string, now: number, launch: PendingShot["launch"]) {
    this.trackTarget(targetId, now);
    // A large tick can contain several attacks. Bound visual work independently
    // of authoritative damage, which the server has already resolved.
    if (this.pending.length < 4) this.pending.push({targetId, expires: now + 800, launch});
  }

  trackTarget(id: string, now: number) {
    this.eventTarget = {id, expires: now + 1800};
  }

  setHullYaw(yaw: number) { if (Number.isFinite(yaw)) this.hullYaw = yaw; }

  private mountOffset() {
    return this.kind === "tank" || this.kind === "artillery"
      ? tankMountOffset(this.hullYaw, this.scale, this.kind === "artillery" ? ARTILLERY_MOUNT_X : undefined) : {x: 0, y: 0};
  }

  mountPoint(): AimPoint {
    const offset = this.mountOffset();
    const point = this.root.getWorldTransformMatrix().transformPoint(offset.x, offset.y);
    return {x: point.x, y: point.y};
  }

  update(delta: number, now: number, targetId: string | null | undefined, active: boolean,
    locate: (id: string) => AimPoint | undefined) {
    if (!active) {
      this.pending = []; this.eventTarget = undefined;
      this.recoil = 0; this.flashUntil = 0;
      const offset = this.mountOffset(); this.head.setPosition(offset.x, offset.y);
      this.flash.setVisible(false); this.head.setAlpha(.4); return;
    }
    this.head.setAlpha(1);
    const id = targetId === undefined
      ? (this.eventTarget && this.eventTarget.expires > now ? this.eventTarget.id : undefined)
      : targetId;
    const target = id ? locate(id) : undefined;
    if (target) {
      const yaw = turretTargetYaw(this.mountPoint(), target);
      if (yaw !== null) this.desiredYaw = yaw;
    } else if (this.kind === "tank" || this.kind === "artillery") this.desiredYaw = this.hullYaw;
    this.yaw = turnTurret(this.yaw, this.desiredYaw, delta);
    this.recoil *= Math.exp(-Math.max(0, delta) / (this.kind === "machineGun" ? 65 : 125));
    const offset = this.mountOffset();
    this.head.setFrame(turretFrame(this.yaw)).setPosition(offset.x - Math.cos(this.yaw) * this.recoil * this.scale,
      offset.y + ((this.kind === "artillery" ? ARTILLERY_BARREL_PITCH : 0) - Math.sin(this.yaw) * TURRET_ISOMETRIC_Y) * this.recoil * this.scale);
    const aligned = target && Math.abs(angleDifference(this.yaw, this.desiredYaw)) < .1;
    this.pending = this.pending.filter(shot => {
      if (shot.expires < now || !locate(shot.targetId) || (targetId !== undefined && shot.targetId !== targetId)) return false;
      if (!aligned || shot.targetId !== id) return true;
      this.barrel = (this.barrel + 1) % (this.kind !== "machineGun" ? 1 : this.level === 3 ? 6 : this.level === 2 ? 2 : 1);
      const muzzle = this.muzzle();
      const world = this.root.getWorldTransformMatrix().transformPoint(muzzle.x, muzzle.y);
      shot.launch({x: world.x, y: world.y});
      this.recoil = this.kind === "cannon" ? cannonProfile(this.level).recoil
        : this.kind === "tank" ? tankProfile(this.level).recoil : this.kind === "artillery" ? artilleryProfile(this.level).recoil : this.level === 3 ? 1.5 : 2.2;
      this.flashUntil = now + (this.kind === "machineGun" ? 65 : 100);
      return false;
    });
    const muzzle = this.muzzle();
    this.flash.setVisible(this.root.visible && now < this.flashUntil)
      .setPosition(muzzle.x, muzzle.y).setRotation(Math.atan2(Math.sin(this.yaw) * TURRET_ISOMETRIC_Y - (this.kind === "artillery" ? ARTILLERY_BARREL_PITCH : 0), Math.cos(this.yaw)));
  }

  private muzzle() {
    const point = this.kind === "artillery" ? artilleryMuzzle(this.level, this.yaw, this.recoil)
      : this.kind === "tank" ? tankMuzzle(this.level, this.yaw, this.recoil)
      : this.kind === "cannon" ? cannonMuzzle(this.level, this.yaw, this.recoil)
      : turretMuzzle(this.level, this.yaw, this.recoil, this.barrel);
    const offset = this.mountOffset();
    return {x: offset.x + point.x * this.scale, y: offset.y + point.y * this.scale};
  }

  destroy() { this.pending = []; this.eventTarget = undefined; }
}
