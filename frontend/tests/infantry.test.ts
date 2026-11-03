import test from 'node:test';
import assert from 'node:assert/strict';
import {purchaseAvailability, AvailabilityContext} from '../src/game/actionAvailability';
import {UnitType} from '../src/types/unit';
import {EnvelopeChunks} from '../src/services/envelopeChunks';

test('100 Infantry do not disable purchases or consume vehicle capacity; coins still apply', () => {
  const c = {match:{status:'ACTIVE',phase:'WAR',configuration:{gameplay_mode:'CONTINUOUS',max_active_units_per_team:1,timer_state:{round_phase:'BATTLE'}}},team:{id:'a',status:'ACTIVE'},connection:'connected',coins:100,entities:Array.from({length:100},(_,i)=>({id:String(i),team_id:'a',entity_kind:'UNIT',unit_code:'infantry',status:'ACTIVE'})),unlocked:[],slots:[]} as unknown as AvailabilityContext;
  const infantry = {code:'infantry',category:'UNIT',cost:15,is_starter:true} as UnitType;
  assert.equal(purchaseAvailability(c,infantry).allowed,true);
  assert.equal(purchaseAvailability(c,{...infantry,code:'tank'}).allowed,true);
  c.entities.push({...c.entities[0],id:'tank',unit_code:'tank'});
  assert.equal(purchaseAvailability(c,{...infantry,code:'tank'}).reason_code,'UNIT_LIMIT_REACHED');
  assert.equal(purchaseAvailability(c,infantry).allowed,true);
  c.coins=14;
  assert.equal(purchaseAvailability(c,infantry).reason_code,'INSUFFICIENT_COINS');
});

test('large snapshots reassemble once, preserving Unicode and ignoring duplicate chunks',()=>{
  const chunks=new EnvelopeChunks(),raw=JSON.stringify({event_id:'e',payload:'Bộ binh 🚀'.repeat(10000)});
  const size=60000,total=Math.ceil(raw.length/size);let result:string|null=null;
  for(let index=0;index<total;index++){
    const packet={id:'one',index,total,data:raw.slice(index*size,(index+1)*size)};
    result=chunks.push(packet);
    if(index<total-1){assert.equal(result,null);assert.equal(chunks.push(packet),null);}
  }
  assert.equal(result,raw);
  assert.deepEqual(JSON.parse(result!),JSON.parse(raw));
});

test('missing, stale, malformed and abandoned chunks cannot expose partial state',()=>{
  const chunks=new EnvelopeChunks();
  assert.equal(chunks.push({id:'one',index:0,total:3,data:'{'},0),null);
  assert.throws(()=>chunks.push({id:'one',index:2,total:3,data:'}'}));
  chunks.clear();
  assert.throws(()=>chunks.push({id:'one',index:1,total:2,data:'}'}));
  assert.equal(chunks.push({id:'two',index:0,total:2,data:'{'},0),null);
  assert.throws(()=>chunks.push({id:'two',index:1,total:2,data:'}'},30001));
  assert.throws(()=>chunks.push({id:'huge',index:0,total:2049,data:'x'}));
  assert.equal(chunks.push({id:'new',index:0,total:1,data:'{}'}),'{}');
});

test('large-army occlusion preserves representatives through motion and never merges distinct positions', async () => {
  const {coincidentKey,coincidentRepresentatives}=await import('../src/game/systems/crowd');
  const make=(id:string,x=0,team='a')=>({data:{id,team_id:team,unit_code:'infantry',target_team_id:'b',level:1,current_hp:80,current_shield:0,simulation_state:{world_position:{x,y:0},movement_state:'MOVING'}} as any,root:{visible:true}});
  const a=make('a'),b=make('b'),differentPosition=make('near',.0001),enemy=make('enemy',0,'other');
  for(let tick=0;tick<500;tick++){
    a.data.simulation_state.world_position.x=tick*.37;
    b.data.simulation_state.world_position.x=tick*.37;
    const reps=coincidentRepresentatives([a,b,differentPosition,enemy]);
    assert.ok(reps.has('a'));assert.ok(!reps.has('b'));
    assert.ok(reps.has('near'));assert.ok(reps.has('enemy'));
    a.root.visible=true;b.root.visible=false;
  }
  const arrival=make('earlier-id');arrival.data.simulation_state.world_position.x=a.data.simulation_state.world_position.x;
  assert.ok(coincidentRepresentatives([arrival,b,a],new Set(['a'])).has('a'));
  assert.notEqual(coincidentKey(a.data),coincidentKey({...a.data,current_hp:75}));
  assert.equal(coincidentKey({...a.data,unit_code:'tank'}),null);
});
