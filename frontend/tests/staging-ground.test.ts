import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {stagingOutline, GroundPoint} from '../src/game/rendering/stagingGround';

const cases: {key:string; points:GroundPoint[]; gate:GroundPoint; bounds:GroundPoint[]}[] =
  JSON.parse(fs.readFileSync(new URL('./fixtures/staging-ground.json',import.meta.url),'utf8'));
function inside(point:GroundPoint, polygon:GroundPoint[]) {
  let result=false;
  for(let i=0,j=polygon.length-1;i<polygon.length;j=i++) {
    const a=polygon[i],b=polygon[j];
    if((a.y>point.y)!==(b.y>point.y) && point.x<(b.x-a.x)*(point.y-a.y)/(b.y-a.y)+a.x)result=!result;
  }
  return result;
}
for(const [index,area] of cases.entries()) {
  test(`organic staging ground ${index}: covers real parking and approaches within the reserved rectangle`,()=>{
    const outline=stagingOutline([...area.points,area.gate],area.key);
    assert.ok(outline.length>8);
    const left=Math.min(...area.bounds.map(p=>p.x)),right=Math.max(...area.bounds.map(p=>p.x));
    const top=Math.min(...area.bounds.map(p=>p.y)),bottom=Math.max(...area.bounds.map(p=>p.y));
    for(const p of outline) assert.ok(p.x>=left-1e-6&&p.x<=right+1e-6&&p.y>=top-1e-6&&p.y<=bottom+1e-6);
    for(const p of area.points) {
      for(let step=0;step<=10;step++) {
        const t=step/10;
        const center={x:p.x*(1-t)+area.gate.x*t,y:p.y*(1-t)+area.gate.y*t};
        for(let i=0;i<16;i++) {
          const angle=i*Math.PI/8;
          assert.ok(inside({x:center.x+12*Math.cos(angle),y:center.y+12*Math.sin(angle)},outline));
        }
      }
    }
  });
}
