import Phaser from "phaser";
import { naturalRoad, roadShapeKey, roadWidthScale } from "./roadShape";
import { paintStagingGround } from "./stagingGround";
import { movementEdges, PALETTE, ServerMap, VisualNode, arenaWorld, battlefieldWorld } from "../map";

import { generateVegetation, riverX, seeded } from "./vegetation";
export { riverX } from "./vegetation";

/** Painted ground texture, built once per graph. Entities are independent sprites above it. */
export function createTerrain(
  scene: Phaser.Scene,
  data: ServerMap,
  nodes: Map<string, VisualNode>,
) {
  const world = arenaWorld(data);
  const bounds = battlefieldWorld(data);
  const riverOffsetX = data.placement_grid?.riverOffsetX ?? 0;
  const riverPath = data.placement_grid?.riverPath;
  // A tiny repeatable grass texture fills visual padding and camera letterboxing.
  // Roads/water remain a separate transparent canvas in original world coordinates.
  if (!scene.textures.exists("woodland-grass")) {
    const grass = scene.textures.createCanvas("woodland-grass", 256, 256)!;
    const ctx = grass.context, noise = seeded(217);
    ctx.fillStyle = "#85a352"; ctx.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 180; i++) {
      const x = noise() * 256, y = noise() * 256;
      ctx.fillStyle = ["#b9c76a30", "#4e77331c", "#e5d99120"][i % 3];
      // Wrap each mark so the reusable ground has no texture seams.
      for (const dx of [-256, 0, 256]) for (const dy of [-256, 0, 256]) {
        ctx.beginPath(); ctx.ellipse(x + dx, y + dy, 2 + i % 15, 1 + i % 4, 0, 0, Math.PI * 2); ctx.fill();
      }
    }
    grass.refresh();
  }
  const backdrop = scene.add.tileSprite(bounds.x, bounds.y, bounds.width, bounds.height, "woodland-grass")
    .setOrigin(0).setDepth(-1001).setName("battlefield-ground");
  backdrop.tilePositionX = bounds.x; backdrop.tilePositionY = bounds.y;
  const resolution = Math.min(1, 2048 / Math.max(bounds.width, bounds.height));
  if (scene.textures.exists("woodland-ground"))
    scene.textures.remove("woodland-ground");
  const texture = scene.textures.createCanvas(
    "woodland-ground",
    Math.ceil(bounds.width * resolution),
    Math.ceil(bounds.height * resolution),
  )!;
  const c = texture.context;
  c.scale(resolution, resolution);
  c.translate(-bounds.x, -bounds.y);
  const random = seeded(217);
  const edges = movementEdges(data);
  c.lineJoin = "round";
  c.lineCap = "round";
  // Worn roads follow exactly the passable graph, including the center ring.
  const roadWidths = data.placement_grid?.roadClearance?.paintedWidths || [57, 49, 43];
  const roadShapes = edges.map(edge => {
    const a = nodes.get(edge.from)!, b = nodes.get(edge.to)!;
    const key = roadShapeKey(`${edge.from}:${edge.to}`, (data.arena?.version ?? 0) >= 7 && [6, 7].includes(data.num_teams));
    return {key, points: naturalRoad({x:a.worldX, y:a.worldY}, {x:b.worldX, y:b.worldY}, key, roadWidths[2])};
  });
  for (const [color, width] of [
    ["#6e8742", roadWidths[0]],
    ["#bfa261", roadWidths[1]],
    ["#dec486", roadWidths[2]],
  ] as const) {
    c.strokeStyle = color;
    c.lineWidth = width;
    roadShapes.forEach(({key, points}) => {
      // Rounded overlapping strokes create worn, gently uneven shoulders.
      for (let i = 1; i < points.length; i++) {
        c.lineWidth = width * roadWidthScale(i, key);
        c.beginPath();
        c.moveTo(points[i - 1].x, points[i - 1].y);
        c.lineTo(points[i].x, points[i].y);
        c.stroke();
      }
    });
  }
  // Actual parking positions form a worn clearing, rather than a square marker.
  for (const area of data.staging_areas || []) {
    const node = nodes.get(area.spawn_node_id);
    if (!node) continue;
    const angle = -Math.PI * 3 / 4;
    const project = (point: {x:number; y:number}) => {
      const dx = point.x-node.x, dy = point.y-node.y;
      return {x:node.worldX+(dx*Math.cos(angle)-dy*Math.sin(angle))*1.5,
        y:node.worldY+(dx*Math.sin(angle)+dy*Math.cos(angle))*.86};
    };
    let spots = area.parking_points?.map(project);
    if (!spots?.length) {
      // Older snapshots have only the reserved bounds. Inset their safety margin.
      const boundary = area.bounds.map(project);
      const left=Math.min(...boundary.map(p=>p.x))+36, right=Math.max(...boundary.map(p=>p.x))-36;
      const top=Math.min(...boundary.map(p=>p.y))+35, bottom=Math.max(...boundary.map(p=>p.y))-35;
      spots=[{x:left,y:top},{x:right,y:top},{x:right,y:bottom},{x:left,y:bottom}];
    }
    paintStagingGround(c,spots,{x:node.worldX,y:node.worldY},area.spawn_node_id,PALETTE[(node.team_index ?? 1)-1] || PALETTE[0]);
  }
  for (const n of nodes.values()) {
    if (n.node_type === "base" || (!data.placement_grid && n.node_type === "tower_slot")) {
      c.fillStyle = "#b7a866";
      c.beginPath();
      c.ellipse(
        n.worldX,
        n.worldY + 12,
        n.node_type === "base" ? 64 : 34,
        n.node_type === "base" ? 35 : 22,
        0,
        0,
        Math.PI * 2,
      );
      c.fill();
    }
  }
  for (let i = 0; i < 1600; i++) {
    const shape = roadShapes[Math.floor(random() * roadShapes.length)];
    if (!shape) break;
    const index = Math.floor(random() * (shape.points.length - 1));
    const a = shape.points[index], b = shape.points[index + 1], t = random();
    const x = a.x + (b.x - a.x) * t + (random() - 0.5) * 28,
      y = a.y + (b.y - a.y) * t + (random() - 0.5) * 24;
    c.fillStyle = i % 2 ? "#f4db9b4f" : "#ad915c35";
    c.beginPath();
    c.ellipse(x, y, random() * 3 + 0.5, random() + 0.5, 0, 0, 7);
    c.fill();
  }
  const river = () => {
    c.beginPath();
    for (let y = bounds.y - 80; y < bounds.y + bounds.height + 100; y += 8) {
      const x = riverX(y, world, riverOffsetX, riverPath);
      y === bounds.y - 80 ? c.moveTo(x, y) : c.lineTo(x, y);
    }
  };
  for (const [color, width] of [
    ["#6b8050", 96],
    ["#b7ad7b", 83],
    ["#9bc6c6", 72],
    ["#649ead", 63],
    ["#72aeba", 51],
  ] as const) {
    river();
    c.strokeStyle = color;
    c.lineWidth = width;
    c.stroke();
  }
  for (let i = 0; i < 450; i++) {
    const y = bounds.y + random() * bounds.height,
      x = riverX(y, world, riverOffsetX, riverPath) + (random() - 0.5) * 50;
    c.strokeStyle = i % 3 ? "#bee0d96b" : "#dcf0df85";
    c.lineWidth = 1.5;
    c.beginPath();
    c.moveTo(x, y);
    c.quadraticCurveTo(x + 3, y - 2, x + 6, y - 1);
    c.stroke();
  }
  // Each actual road/river intersection gets a timber bridge.
  const connectedBridgePath = data.num_teams === 5 &&
    (data.placement_grid?.geometryRevision ?? 0) >= 15 && riverPath;
  const bridgeCenters: { x: number; y: number }[] = [];
  const drawBridge = (x: number, y: number, angle: number) => {
    if (bridgeCenters.some((p) => Math.hypot(p.x - x, p.y - y) < 95)) return;
    bridgeCenters.push({ x, y });
    c.save();
    c.translate(x, y);
    c.rotate(angle);
    c.fillStyle = "#4c5d3b55";
    c.fillRect(-60, -31, 126, 66);
    c.fillStyle = "#775735";
    c.strokeStyle = "#534a30";
    c.lineWidth = 3;
    c.fillRect(-59, -26, 118, 52);
    c.strokeRect(-59, -26, 118, 52);
    for (let xx = -55; xx < 60; xx += 12) {
      c.fillStyle = xx % 3 ? "#b69761" : "#c4a470";
      c.fillRect(xx, -25, 10, 50);
      c.strokeStyle = "#927345";
      c.lineWidth = 1;
      c.beginPath();
      c.moveTo(xx + 3, -19);
      c.lineTo(xx + 5, 16);
      c.stroke();
    }
    c.strokeStyle = "#655136";
    c.lineWidth = 5;
    [-29, 29].forEach((yy) => {
      c.beginPath();
      c.moveTo(-62, yy);
      c.lineTo(62, yy);
      c.stroke();
      [-55, 0, 55].forEach((xx) => {
        c.fillStyle = "#b39a65";
        c.fillRect(xx - 3, yy - 8, 6, 13);
      });
    });
    c.restore();
  };
  if (!connectedBridgePath) edges.forEach((e) => {
    const a = nodes.get(e.from)!,
      b = nodes.get(e.to)!;
    // Bridges follow the shortest walking axis across the river.
    const pointAt = (t: number) => ({
      x: a.worldX + (b.worldX - a.worldX) * t,
      y: a.worldY + (b.worldY - a.worldY) * t,
    });
    const bankSide = (t: number) => {
      const p = pointAt(t);
      return p.x - riverX(p.y, world, riverOffsetX, riverPath);
    };
    let previousT = 0;
    let previousSide = bankSide(previousT);
    for (let step = 1; step <= 64; step++) {
      const currentT = step / 64;
      const currentSide = bankSide(currentT);
      if (previousSide === 0 || currentSide === 0 || previousSide * currentSide < 0) {
        let low = previousT, high = currentT;
        const lowSide = previousSide;
        for (let i = 0; i < 18; i++) {
          const middle = (low + high) / 2;
          if (bankSide(middle) * lowSide > 0) low = middle;
          else high = middle;
        }
        const t = (low + high) / 2;
        const point = pointAt(t);
        const tangentX = b.worldX - a.worldX;
        const tangentY = b.worldY - a.worldY;
        drawBridge(point.x, point.y, Math.atan2(tangentY, tangentX));
      }
      previousT = currentT;
      previousSide = currentSide;
    }
  });
  if (connectedBridgePath) {
    // A connected timber deck follows the painted roads across both banks,
    // keeping curved and nearby crossings continuous.
    // Clipping to the river corridor keeps the rest of every road as yellow sand.
    const banks = [-1, 1].map(side => connectedBridgePath.map((point, index) => {
      const a = connectedBridgePath[Math.max(0, index - 1)];
      const b = connectedBridgePath[Math.min(connectedBridgePath.length - 1, index + 1)];
      const dx = b[0] - a[0], dy = b[1] - a[1], length = Math.hypot(dx, dy) || 1;
      return {x: point[0] + side * dy / length * 60, y: point[1] - side * dx / length * 60};
    }));
    c.save();
    c.beginPath();
    [...banks[0], ...banks[1].reverse()].forEach((point, index) => {
      if (index === 0) c.moveTo(point.x, point.y); else c.lineTo(point.x, point.y);
    });
    c.closePath();
    c.clip();
    for (const [color, width, planks] of [
      ["#534a30", roadWidths[0] + 4, false],
      ["#b69761", roadWidths[1] + 4, false],
      ["#927345", roadWidths[1], true],
    ] as const) {
      c.strokeStyle = color;
      c.lineWidth = width;
      c.lineCap = planks ? "butt" : "round";
      c.setLineDash(planks ? [2, 12] : []);
      for (const {points} of roadShapes) {
        c.beginPath();
        points.forEach((point, index) => {
          if (index === 0) c.moveTo(point.x, point.y); else c.lineTo(point.x, point.y);
        });
        c.stroke();
      }
    }
    c.restore();
  }
  // Raised stone construction platforms remain dry where the decorative river crosses.
  // Placed after water/bridges and reserved from forest scattering below.
  for (const node of nodes.values()) if (!data.placement_grid && node.node_type === "tower_slot") {
    c.fillStyle = "#827e68";
    c.strokeStyle = "#555d48";
    c.lineWidth = 2;
    c.beginPath(); c.ellipse(node.worldX, node.worldY + 4, 25, 16, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    c.fillStyle = "#c2b992";
    c.beginPath(); c.ellipse(node.worldX, node.worldY, 22, 13, 0, 0, Math.PI * 2);
    c.fill();
  }
  for (const decoration of generateVegetation(data, nodes)) {
    for (let i = 0; i < 5; i++) {
      const x = decoration.x + (random()-.5)*35, y = decoration.y + (random()-.5)*22;
      c.strokeStyle = "#506f38"; c.lineWidth = 2;
      c.beginPath(); c.moveTo(x-3,y); c.lineTo(x,y-5); c.lineTo(x+2,y); c.stroke();
      if (i % 3 === 0) {c.fillStyle = i ? "#f0d783" : "#eac9b1"; c.beginPath(); c.arc(x,y-5,2,0,Math.PI*2); c.fill();}
    }
  }
  texture.refresh();
  scene.add.image(bounds.x, bounds.y, "woodland-ground").setOrigin(0).setDisplaySize(bounds.width, bounds.height).setDepth(-1000);
  const vegetation = generateVegetation(data, nodes);
  for (const decoration of vegetation) {
    scene.add.image(decoration.x, decoration.y, decoration.key)
      .setName("natural-vegetation").setData("vegetation", decoration)
      .setOrigin(.5, .9).setScale(decoration.scale).setFlipX(decoration.flip)
      .setDepth(decoration.y - 10);
  }
  for (const n of nodes.values())
    if (n.node_type === "barrier") {
      scene.add
        .image(n.worldX, n.worldY, "camp")
        .setOrigin(0.5, 0.86)
        .setScale(0.6)
        .setDepth(n.worldY);
      scene.add
        .image(n.worldX + 34, n.worldY + 15, "crate")
        .setOrigin(0.5, 0.9)
        .setScale(0.25)
        .setDepth(n.worldY + 15);
    }
  // Continue the same decorative river through HUD letterboxing and long queues.
  // One Graphics object avoids scaling the detailed arena canvas or adding sprites.
  const riverExtension = scene.add.graphics().setDepth(-1000.5);
  let riverTop = Infinity, riverBottom = -Infinity;
  const cover = (area: { x: number; y: number; width: number; height: number }) => {
    // Phaser rounds worldView to whole coordinates; bleed avoids subpixel edge gaps.
    const x = Math.floor(area.x) - 2, y = Math.floor(area.y) - 2;
    backdrop.setPosition(x, y).setSize(Math.ceil(area.x + area.width) - x + 2, Math.ceil(area.y + area.height) - y + 2);
    backdrop.tilePositionX = x; backdrop.tilePositionY = y;
    const top = Math.floor(area.y / 256) * 256 - 128;
    const bottom = Math.ceil((area.y + area.height) / 256) * 256 + 128;
    if (top >= riverTop && bottom <= riverBottom) return;
    riverTop = Math.min(top, riverTop); riverBottom = Math.max(bottom, riverBottom);
    riverExtension.clear();
    for (const [color, width] of [[0x6b8050,96],[0xb7ad7b,83],[0x9bc6c6,72],[0x649ead,63],[0x72aeba,51]]) {
      riverExtension.lineStyle(width, color, 1).beginPath();
      for (let yy = riverTop; yy <= riverBottom; yy += 8) {
        const xx = riverX(yy, world, riverOffsetX, riverPath);
        if (yy === riverTop) riverExtension.moveTo(xx, yy); else riverExtension.lineTo(xx, yy);
      }
      riverExtension.strokePath();
    }
  };
  cover(bounds);
  return { backdrop, cover };
}
