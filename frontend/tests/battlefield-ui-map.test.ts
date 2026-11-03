import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { battlefieldWorld, arenaWorld, minimapPoint, minimapViewport, overviewCamera, projectMap, ServerMap } from '../src/game/map';
import { ENTITY_NAMES, entityArtwork } from '../src/game/entityArtwork';
import { EntityIllustration } from '../src/components/game/EntityIllustration';

for (const count of [2,4,8,20]) test(`${count} teams: visual padding preserves all graph coordinates and fits with negative bounds`, () => {
  const scale=Math.max(1,count/5), width=1200*scale+400, height=Math.max(1040,688*scale+400);
  const map:ServerMap={num_teams:count,team_ids:[],arena:{version:4,key:'test',profile:'STANDARD',width,height,centerX:width/2,centerY:height/2,layout_scale:scale,regions:5},
    nodes:[{node_id:'base',node_type:'base',team_index:1,is_passable:true,x:-300,y:190}],edges:[]};
  const before=JSON.stringify(map), node=projectMap(map).get('base')!;
  const world=battlefieldWorld(map);
  assert.ok(world.x < 0 && world.y < 0);
  assert.ok(world.x+world.width > width && world.y+world.height > height);
  assert.equal(world.centerX,arenaWorld(map).centerX);
  assert.deepEqual(projectMap(map).get('base'),node);
  assert.equal(JSON.stringify(map),before);
  for(const [w,h] of [[390,844],[1440,900],[1024,600]]) {
    const fit=overviewCamera(w,h,world);
    const screen=(x:number,y:number)=>({x:w/2+(x-fit.centerX)*fit.zoom,y:h/2+(y-fit.centerY)*fit.zoom});
    const a=screen(world.x,world.y),b=screen(world.x+world.width,world.y+world.height);
    assert.ok(a.x>=fit.area.x-1e-6&&a.y>=fit.area.y-1e-6);
    assert.ok(b.x<=fit.area.x+fit.area.width+1e-6&&b.y<=fit.area.y+fit.area.height+1e-6);
    assert.ok(fit.bounds.x<=world.x&&fit.bounds.y<=world.y);
  }
});

test('minimap projects all padded corners and clips a viewport against every edge', () => {
  const world=battlefieldWorld(null), right=world.x+world.width, bottom=world.y+world.height;
  assert.deepEqual(minimapPoint(world,0,0),{x:world.x,y:world.y});
  assert.deepEqual(minimapPoint(world,1,1),{x:right,y:bottom});
  assert.deepEqual(minimapPoint(world,.5,.5),{x:world.centerX,y:world.centerY});
  assert.deepEqual(minimapViewport(world,{x:world.x-100,y:world.y-100,width:200,height:200}),{x:world.x,y:world.y,width:100,height:100});
  assert.deepEqual(minimapViewport(world,{x:right-100,y:bottom-100,width:500,height:500}),{x:right-100,y:bottom-100,width:100,height:100});
  assert.equal(minimapViewport(world,{x:right+10,y:0,width:10,height:10}).width,0);
});

test('every supported entity maps to real Phaser artwork, with team frame clamping and graceful unknown fallback', () => {
  for(const code of Object.keys(ENTITY_NAMES)) {
    const path=entityArtwork(code)!;
    assert.ok(existsSync(new URL(`../public${path}`,import.meta.url)),code);
    const html=renderToStaticMarkup(React.createElement(EntityIllustration,{code,name:ENTITY_NAMES[code],category:code.includes('tower')?'TOWER':'UNIT'}));
    assert.ok(html.includes(path));assert.match(html,/width="160" height="112"/);
  }
  assert.match(entityArtwork('infantry',99)!,/infantry\.png/);
  assert.equal(entityArtwork('unavailable'),undefined);
  const html=renderToStaticMarkup(React.createElement(EntityIllustration,{code:'unavailable',name:'Công sự mới',category:'TOWER'}));
  assert.match(html,/data-state="fallback"/);assert.doesNotMatch(html,/<img/);
});
