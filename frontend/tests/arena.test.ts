import test from 'node:test';
import assert from 'node:assert/strict';
import { PALETTE, TEAM_SYMBOLS, WORLD, overviewCamera, projectMap, routeToTeam, ServerMap, teamIndex } from '../src/game/map';
import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';
import { TeamDirectory } from '../src/components/arena/ArenaNavigation';

test('all twenty visual identities have real textures, distinct symbols and colors', () => {
  assert.equal(new Set(PALETTE).size, 20);
  assert.equal(new Set(TEAM_SYMBOLS).size, 20);
  for(let i=0;i<20;i++) for(const name of [`base-${i}`,`banner-${i}`,`infantry-${i}-0`,`infantry-${i}-3`])
    assert.match(readFileSync(new URL(`../public/assets/woodland/${name}.svg`, import.meta.url),'utf8'),/<svg/);
});
for (const count of [2,3,4,5,8,12,13,16,19,20]) test(`${count} teams: server projection preserves identities within dynamic world and route preview avoids impassable slots`, () => {
  const scale=Math.max(1,count/5), width=1200*scale+400, height=Math.max(1040,688*scale+400);
  const data: ServerMap={num_teams:count,team_ids:Array.from({length:count},(_,i)=>`t${i+1}`),arena:{version:2,key:`radial-v2-${count}`,profile:'LARGE',width,height,centerX:width/2,centerY:height/2,layout_scale:scale,regions:5},nodes:[],edges:[]};
  for(let i=1;i<=count;i++) {
    const a=2*Math.PI*(i-1)/count;
    for(const [prefix,type,r] of [['base','base',400],['spawn','spawn',240],['lane','lane',320]] as const) {
      const id=prefix === 'lane' ? `node_lane_t${i}_1` : `node_${prefix}_t${i}`;
      data.nodes.push({node_id:id,node_type:type,team_index:i,is_passable:true,x:r*scale*Math.cos(a),y:r*scale*Math.sin(a)});
    }
    data.edges.push({from:`node_spawn_t${i}`,to:`node_lane_t${i}_1`},{from:`node_lane_t${i}_1`,to:`node_lane_t${i%count+1}_1`});
  }
  const projected=projectMap(data);
  assert.equal(projected.size,count*3);
  for(const n of projected.values()) assert.ok(n.worldX>=0 && n.worldX<=width && n.worldY>=0 && n.worldY<=height);
  assert.equal(teamIndex(data,`t${count}`),count-1);
  const route=routeToTeam(data,`t${count}`,'t1');
  assert.equal(route[0],`node_spawn_t${count}`);
  assert.equal(route.at(-1),'node_lane_t1_1');
});
test('scoreboard renders every team including team 20, score, status and search controls', () => {
  const teams=Array.from({length:20},(_,i)=>({id:`t${i}`,name:`Team ${i+1}`,base_hp:500,initial_base_hp:500,base_shield:0,score:i,status:i===19?'ELIMINATED':'ACTIVE'}));
  const html=renderToStaticMarkup(React.createElement(TeamDirectory,{teams,ownId:'t0',targetId:'t18',onSelect:()=>{}}));
  assert.equal((html.match(/class="drawer-team/g)||[]).length,20);
  assert.match(html,/Team 20/); assert.match(html,/Đã bị loại/); assert.match(html,/Tìm đội hoặc số đội/); assert.match(html,/Sắp xếp đội/);
});


test('expanded arena overview keeps the whole world clear of command HUD and desktop minimap', () => {
  const world = {width:5200,height:3152,centerX:2600,centerY:1576};
  for (const [width,height] of [[390,844],[757,928],[1366,900],[1024,600]]) {
    const fit = overviewCamera(width,height,world);
    const screen = (x:number,y:number) => ({x:width/2+(x-fit.centerX)*fit.zoom,y:height/2+(y-fit.centerY)*fit.zoom});
    const a=screen(0,0),b=screen(world.width,world.height);
    assert.ok(fit.centerX-width/fit.zoom/2 >= fit.bounds.x-0.01);
    assert.ok(fit.centerY-height/fit.zoom/2 >= fit.bounds.y-0.01);
    assert.ok(fit.centerX+width/fit.zoom/2 <= fit.bounds.x+fit.bounds.width+0.01);
    assert.ok(fit.centerY+height/fit.zoom/2 <= fit.bounds.y+fit.bounds.height+0.01);
    assert.ok(a.x >= fit.area.x-0.01 && a.y >= fit.area.y-0.01);
    assert.ok(b.x <= fit.area.x+fit.area.width+0.01 && b.y <= fit.area.y+fit.area.height+0.01);
    assert.ok(b.y <= height-190);
    if(width>=700) assert.ok(b.x <= width-260);
  }
});

test('legacy four-team overview retains its original zoom and center', () => {
  const fit=overviewCamera(1280,800,WORLD);
  assert.equal(fit.zoom,Math.min(1280/WORLD.width,800/WORLD.height));
  assert.equal(fit.centerX,WORLD.centerX);assert.equal(fit.centerY,WORLD.centerY);
});
