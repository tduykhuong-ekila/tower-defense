import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ServerMap} from '../src/game/map';
import {placementCell,gridCell,gridAnchor,gridRect,placementReason} from '../src/game/placement';
import {useMatchStore} from '../src/stores/matchStore';
const fixtures=JSON.parse(readFileSync(new URL('./fixtures/grid-maps.json',import.meta.url),'utf8'));
for(const {map,valid} of fixtures as {map:ServerMap;valid:{row:number;col:number}[]}[]) {
 test(`server grid parity and footprints for ${map.num_teams} teams`,()=>{
  const grid=map.placement_grid!,f=grid.footprints.cannon_tower;
  for(const cell of valid) {
    assert.equal(placementReason(map,cell,'cannon_tower','team-1',[]),'');
    const rect=gridRect(grid,cell,f),anchor=gridAnchor(grid,cell,f);
    assert.deepEqual(gridCell(grid,rect.x+.1,rect.y+.1),cell);
    assert.equal(anchor.x,rect.x+rect.width/2);assert.equal(anchor.y,rect.y+rect.height/2+f.anchorOffsetY);
    assert.deepEqual(placementCell(grid,anchor.x,anchor.y,f),cell);
    assert.deepEqual(placementCell(grid,anchor.x+15,anchor.y-15,f),cell);
    assert.notEqual(placementReason(map,cell,'cannon_tower','team-2',[]),'');
    const tower={entity_kind:'TOWER',status:'ACTIVE',current_node_id:'node_lane_t1_2',simulation_state:{grid_placement:{...cell,...f}}};
    assert.notEqual(placementReason(map,cell,'cannon_tower','team-1',[tower]),'');
    assert.equal(placementReason(map,cell,'cannon_tower','team-1',[{...tower,status:'DESTROYED'}]),'');
  }
  assert.notEqual(placementReason(map,{row:-1,col:2},'cannon_tower','team-1',[]),'');
  assert.notEqual(placementReason(map,{row:2,col:grid.cols},'cannon_tower','team-1',[]),'');
  assert.notEqual(placementReason(map,{row:2,col:2},'unknown','team-1',[]),'');
 });
}
test('negative origin coordinate conversion uses floor',()=>{
 const grid={...fixtures[0].map.placement_grid,originX:-320,originY:-160};
 assert.deepEqual(gridCell(grid,-320.1,-160.1),{row:-1,col:-1});
 assert.deepEqual(gridCell(grid,-319,-159),{row:0,col:0});
});
test('TOWER_BUILT preserves authoritative occupancy and deduplicates existing entity',()=>{
 useMatchStore.getState().reset();
 const payload={entity_id:'grid-tower',team_id:'team-1',tower_code:'cannon_tower',node_id:'node_lane_t1_2',damage:20,current_hp:150,max_hp:150,
  simulation_state:{world_position:{x:10,y:20},grid_placement:{row:3,col:4,widthCells:4,heightCells:4,anchorOffsetY:32}}};
 for(let seq=1;seq<=2;seq++)useMatchStore.getState().applyEvent({event_type:'TOWER_BUILT',payload,sequence_number:seq,match_id:'m',server_time:new Date().toISOString()} as any);
 assert.equal(useMatchStore.getState().entities.length,1);
 assert.deepEqual(useMatchStore.getState().entities[0].simulation_state,payload.simulation_state);
});

test('saved vehicle offsets protect their full route with the server body metadata',async()=>{
 const {projectMap}=await import('../src/game/map');
 const map=fixtures[0].map as ServerMap,cell=fixtures[0].valid[0],g=map.placement_grid!,f=g.footprints.cannon_tower;
 const nodes=projectMap(map),edge=map.edges.find(e=>nodes.get(e.from)?.is_passable&&nodes.get(e.to)?.is_passable)!;
 const a=nodes.get(edge.from)!,b=nodes.get(edge.to)!,rect=gridRect(g,cell,f);
 const x=rect.x+rect.width/2-(a.worldX+b.worldX)/2,y=rect.y+rect.height/2-(a.worldY+b.worldY)/2+27;
 const angle=-Math.PI*3/4,offset={x:x/1.5*Math.cos(angle)+y/.86*Math.sin(angle),y:-x/1.5*Math.sin(angle)+y/.86*Math.cos(angle)};
 const unit={entity_kind:'UNIT',unit_code:'tank',status:'ACTIVE',current_node_id:a.id,simulation_state:{crowd_offset:offset}};
 assert.notEqual(placementReason(map,cell,'cannon_tower','team-1',[unit]),'');
 assert.equal(placementReason(map,cell,'cannon_tower','team-1',[{...unit,status:'DESTROYED'}]),'');
});

test('saved staging approach blocks its current physical position',()=>{
 const map=fixtures[0].map as ServerMap,cell=fixtures[0].valid[0],g=map.placement_grid!,f=g.footprints.cannon_tower;
 const rect=gridRect(g,cell,f),world=map.arena!,angle=-Math.PI*3/4;
 const px=rect.x+rect.width/2-world.centerX,py=rect.y+rect.height/2-world.centerY-60;
 const position={x:px/1.5*Math.cos(angle)+py/.86*Math.sin(angle),
  y:-px/1.5*Math.sin(angle)+py/.86*Math.cos(angle)};
 const unit={entity_kind:'UNIT',unit_code:'infantry',status:'ACTIVE',current_node_id:'node_spawn_t1',
  simulation_state:{movement_zone:'STAGING' as const,world_position:position,
   route_nodes:['node_spawn_t1','node_lane_t1_2'],staging_entry_distance:80,crowd_offset:{x:0,y:0}}};
 assert.notEqual(placementReason(map,cell,'cannon_tower','team-1',[unit]),'');
 assert.equal(placementReason(map,cell,'cannon_tower','team-1',[{...unit,status:'DESTROYED'}]),'');
});

test('shield placement follows the displayed base ellipse',()=>{
 const map=structuredClone(fixtures[0].map) as ServerMap,cell=fixtures[0].valid[0],grid=map.placement_grid!;
 const anchor=gridAnchor(grid,cell,grid.footprints.shield_generator),world=map.arena!;
 const base=map.nodes.find(n=>n.node_id==='node_base_t1')!,a=-Math.PI*3/4;
 const setBase=(dx:number)=>{
  const x=(anchor.x-world.centerX-dx)/1.5,y=(anchor.y-world.centerY-60+17)/.86;
  base.x=x*Math.cos(a)+y*Math.sin(a);base.y=-x*Math.sin(a)+y*Math.cos(a);
 };
 setBase(219);
 assert.equal(placementReason(map,cell,'shield_generator','team-1',[]),'');
 setBase(221);
 assert.match(placementReason(map,cell,'shield_generator','team-1',[]),/vòng khiên/);
 assert.equal(placementReason(map,cell,'cannon_tower','team-1',[]),'');
});
