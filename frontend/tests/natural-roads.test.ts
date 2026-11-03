import test from "node:test";
import assert from "node:assert/strict";
import { naturalRoad, roadWidthScale } from "../src/game/rendering/roadShape";

for (const width of [43, 70]) {
  test(`${width}px sand bends naturally while containing the shortest troop corridor`, () => {
    const a = {x: -300, y: 240}, b = {x: 1100, y: -520};
    const key = "node_center_ring_t1:node_lane_t1_3";
    const points = naturalRoad(a, b, key, width);
    assert.deepEqual(points[0], a);
    assert.ok(Math.hypot(points.at(-1)!.x-b.x, points.at(-1)!.y-b.y) < 1e-9);
    assert.deepEqual(naturalRoad(a,b,key,width),points);
    assert.notDeepEqual(naturalRoad(a,b,key+"2",width),points);
    const dx = b.x-a.x, dy = b.y-a.y, length = Math.hypot(dx,dy);
    const deviations = points.map((p,i) => Math.hypot(p.x-(a.x+dx*i/32),p.y-(a.y+dy*i/32)));
    assert.ok(Math.max(...deviations)>2);
    for (let i=0; i<32; i++) {
      const start = points[i], end = points[i+1];
      const vx = end.x-start.x, vy = end.y-start.y;
      for (let step=0; step<=10; step++) {
        const t = (i+step/10)/32;
        for (const offset of [-12,0,12]) {
          const x=a.x+dx*t-dy/length*offset, y=a.y+dy*t+dx/length*offset;
          const u=Math.max(0,Math.min(1,((x-start.x)*vx+(y-start.y)*vy)/(vx*vx+vy*vy)));
          const distance=Math.hypot(x-start.x-u*vx,y-start.y-u*vy);
          assert.ok(distance<=width/2-2, `ground anchor leaves sand at ${t}`);
        }
      }
      assert.ok(roadWidthScale(i,key)>=1 && roadWidthScale(i,key)<=1.08);
    }
  });
}

test("short and degenerate roads stay finite", () => {
  for (const b of [{x:0,y:0},{x:1,y:1}])
    for (const point of naturalRoad({x:0,y:0},b,"edge",43))
      assert.ok(Number.isFinite(point.x)&&Number.isFinite(point.y));
});
