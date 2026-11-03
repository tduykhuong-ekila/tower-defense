import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { useMatchStore } from '../src/stores/matchStore';
import { generateVegetation, vegetationClear } from '../src/game/rendering/vegetation';
import { projectMap, ServerMap, arenaWorld } from '../src/game/map';
import { entityArtwork } from '../src/game/entityArtwork';

const maps: ServerMap[] = JSON.parse(fs.readFileSync(new URL('./fixtures/vegetation-maps.json', import.meta.url), 'utf8'));
for (const map of maps) test(`${map.num_teams} teams: organic vegetation is deterministic, bounded, and reserves all gameplay areas`, () => {
  const nodes = projectMap(map), plants = generateVegetation(map, nodes);
  assert.deepEqual(plants, generateVegetation(map, nodes));
  assert.ok(plants.length >= 10 && plants.length <= 700, `density ${plants.length}`);
  assert.equal(new Set(plants.map(p=>`${p.x}:${p.y}`)).size, plants.length);
  const world = arenaWorld(map);
  assert.ok(plants.some(p=>p.x<0 || p.y<0 || p.x>world.width || p.y>world.height));
  assert.ok(plants.some(p=>p.key.startsWith('tree')));
  assert.ok(plants.every(p=>vegetationClear(map,nodes,p.x,p.y)));
  for (const node of nodes.values()) if (node.node_type === 'tower_slot' || node.node_type === 'base' || node.node_type === 'spawn')
    assert.ok(plants.every(p=>Math.hypot(p.x-node.worldX,p.y-node.worldY)>95));
  assert.equal(new Set(plants.map(p=>p.x)).size, plants.length); // no vertical border rows
  assert.equal(new Set(plants.map(p=>p.y)).size, plants.length);
});

test('one upgrade event updates all matching teammates in place and preserves movement, enemies, and dead units', () => {
  useMatchStore.getState().reset();
  const entity:any={id:'a1',team_id:'a',unit_code:'infantry',entity_kind:'UNIT',level:1,status:'ACTIVE',max_hp:80,current_hp:40,simulation_state:{world_position:{x:12,y:34}}};
  useMatchStore.setState({currentTeamId:'a',entities:[entity,{...entity,id:'a2'},{...entity,id:'b1',team_id:'b'},{...entity,id:'wreck',status:'DESTROYED',current_hp:0}]});
  const event:any={match_id:'match',event_type:'TEAM_UNIT_UPGRADED',sequence_number:1,payload:{team_id:'a',entity_type:'infantry',level:2,stats:{hp:92,damage:5.5,attack_interval_seconds:1.27}}};
  useMatchStore.getState().applyEvent(event);
  const state=useMatchStore.getState();
  assert.deepEqual(state.entities.slice(0,2).map(e=>[e.level,e.max_hp,e.current_hp]),[[2,92,46],[2,92,46]]);
  assert.equal(state.entities[0].simulation_state,entity.simulation_state);
  assert.equal(state.entities[2].level,1);assert.equal(state.entities[3].current_hp,0);
  useMatchStore.getState().applyEvent(event);
  assert.deepEqual(useMatchStore.getState().entities,state.entities);
});

test('all teams, frames, types and levels have equipment artwork with stable dimensions', () => {
  for (const code of ['infantry','tank','artillery','mg_tower','cannon_tower','shield_generator'])
    for (let level=1;level<=3;level++) for (const team of (code==='infantry'?[0,19]:[0])) {
      const path=entityArtwork(code,team,level)!;
      if (['mg_tower', 'cannon_tower', 'tank', 'artillery', 'infantry'].includes(code)) {
        const png = fs.readFileSync(new URL(`../public${path}`,import.meta.url));
        assert.equal(png.subarray(0,8).toString('hex'),'89504e470d0a1a0a');
        assert.equal(png.readUInt32BE(16),512);
        assert.equal(png.readUInt32BE(20),512);
        assert.equal(png[25],6); // RGBA keeps the background transparent.
        continue;
      }
      const svg=fs.readFileSync(new URL(`../public${path}`,import.meta.url),'utf8');
      if(level>1) assert.ok(svg.includes(`data-equipment-level="${level}"`));
      assert.ok(svg.includes(code==='infantry'?'viewBox="0 0 64 64"':'viewBox="0 0 128 128"'));
    }
});
