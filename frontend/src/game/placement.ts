import { ServerMap, arenaWorld, projectMap } from './map';
import { UnitSimulationState } from '../types/unit';
export interface Footprint { widthCells: number; heightCells: number; anchorOffsetY: number; }
export interface PlacementGrid {
  version: number; cellSize: number; originX: number; originY: number; cols: number; rows: number;
  shieldPlacement?: {width:number; height:number; offsetY:number};
  geometryRevision?: number;
  riverOffsetX?: number;
  riverPath?: [number, number][];
  roadClearance?: {movementEnvelope: number[]; placementEnvelope?: number[]; bodies?:Record<string,number[]>; paintedHalfWidth: number; paintedWidths?: number[]; safetyMargin: number; stagingSafetyMargin?: number; curveTolerance: number; movementFollowsPaintedCurves?: boolean};
  footprints: Record<string, Footprint>; buildableRuns: [number, number, number, number][];
}
export interface GridCell { row: number; col: number; }
type Occupant = {entity_kind:string; status:string; current_node_id:string; unit_code?:string; unit_type_code?:string; simulation_state?:UnitSimulationState};
const masks = new WeakMap<PlacementGrid, Uint8Array>();
function mask(grid:PlacementGrid) {
  let data = masks.get(grid);
  if (!data) {
    data = new Uint8Array(grid.rows*grid.cols);
    for (const [row,start,end,owner] of grid.buildableRuns) data.fill(owner,row*grid.cols+start,row*grid.cols+end);
    masks.set(grid,data);
  }
  return data;
}
export function gridCell(grid:PlacementGrid,x:number,y:number):GridCell {
  return {col:Math.floor((x-grid.originX)/grid.cellSize),row:Math.floor((y-grid.originY)/grid.cellSize)};
}
export function gridRect(grid:PlacementGrid,cell:GridCell,footprint:Footprint) {
  return {x:grid.originX+cell.col*grid.cellSize,y:grid.originY+cell.row*grid.cellSize,
    width:footprint.widthCells*grid.cellSize,height:footprint.heightCells*grid.cellSize};
}
export function gridAnchor(grid:PlacementGrid,cell:GridCell,footprint:Footprint) {
  const rect=gridRect(grid,cell,footprint);
  return {x:rect.x+rect.width/2,y:rect.y+rect.height/2+footprint.anchorOffsetY};
}
/** Nearest tower anchor, in world pixels after camera unprojection. */
export function placementCell(grid:PlacementGrid,x:number,y:number,footprint:Footprint):GridCell {
  const anchor = gridAnchor(grid,{row:0,col:0},footprint);
  return {col:Math.round((x-anchor.x)/grid.cellSize),row:Math.round((y-anchor.y)/grid.cellSize)};
}
// Rebuild once per authoritative entity array, rather than scan the army at each
// pointer event. Saved reservations keep their original dimensions and anchor.
type StagingApproach = {road:[number,number,number,number]; envelope:number[]};
const occupancy = new WeakMap<ServerMap, {entities:Occupant[]; cells:Uint8Array; legacy:ReturnType<typeof gridRect>[]; corridors:number[][]; roads:[number,number,number,number][]; approaches:StagingApproach[]}>();
function occupiedCells(map:ServerMap,entities:Occupant[]) {
  let cached = occupancy.get(map);
  if(cached?.entities===entities) return cached;
  const grid=map.placement_grid!,cells=new Uint8Array(grid.cols*grid.rows),legacy:ReturnType<typeof gridRect>[]=[];
  const corridors:number[][]=[],approaches:StagingApproach[]=[],envelopes=new Set<string>(),clearance=grid.roadClearance;
  let nodes:ReturnType<typeof projectMap>|undefined;
  for(const e of entities) {
    if(e.entity_kind==='UNIT' && e.status!=='DESTROYED' && clearance?.bodies) {
      const offset=e.simulation_state?.crowd_offset;
      const a=-Math.PI*3/4;
      if(offset) {
        const x=(offset.x*Math.cos(a)-offset.y*Math.sin(a))*1.5,y=(offset.x*Math.sin(a)+offset.y*Math.cos(a))*.86;
        const [w,h,oy]=clearance.bodies[e.unit_code || e.unit_type_code || ''] || [54,50,-27];
        const envelope=[x-w/2,y+oy-h/2,x+w/2,y+oy+h/2],standard=clearance.movementEnvelope;
        const contained=envelope[0]>=standard[0]-1e-8&&envelope[1]>=standard[1]-1e-8&&envelope[2]<=standard[2]+1e-8&&envelope[3]<=standard[3]+1e-8;
        const key=envelope.join(',');if(!contained&&!envelopes.has(key)){envelopes.add(key);corridors.push(envelope);}
      }
      if(e.simulation_state?.movement_zone==='STAGING' && e.simulation_state.world_position) {
        nodes ||= projectMap(map);
        const node=nodes.get(e.current_node_id),p=e.simulation_state.world_position;
        if(node) {
          const [w,h,oy]=clearance.bodies[e.unit_code || e.unit_type_code || ''] || [54,50,-27];
          const x=(p.x*Math.cos(a)-p.y*Math.sin(a))*1.5,y=(p.x*Math.sin(a)+p.y*Math.cos(a))*.86;
          const dx=offset ? (offset.x*Math.cos(a)-offset.y*Math.sin(a))*1.5 : 0;
          const dy=offset ? (offset.x*Math.sin(a)+offset.y*Math.cos(a))*.86 : 0;
          const route=e.simulation_state.route_nodes||[];
          let goal=node,remaining=Math.max(0,e.simulation_state.staging_entry_distance||0);
          for(let i=0;i<route.length-1;i++) {
            const from=nodes.get(route[i]),to=nodes.get(route[i+1]);
            if(!from||!to)break;
            const length=Math.hypot(to.x-from.x,to.y-from.y);
            if(remaining<=length) {
              const fraction=remaining/Math.max(length,1e-9);
              goal={...from,worldX:from.worldX+(to.worldX-from.worldX)*fraction,
                worldY:from.worldY+(to.worldY-from.worldY)*fraction};
              remaining=0;break;
            }
            remaining-=length;goal=to;
          }
          const world=arenaWorld(map);
          approaches.push({road:[x+world.centerX,y+world.centerY+60,goal.worldX+dx,goal.worldY+dy],envelope:[-w/2,oy-h/2,w/2,oy+h/2]});
        }
      }
      continue;
    }
    if(!['TOWER','SPECIAL'].includes(e.entity_kind) || e.status==='DESTROYED') continue;
    const occupied=e.simulation_state?.grid_placement;
    if(occupied) {
      for(let r=Math.max(0,occupied.row);r<Math.min(grid.rows,occupied.row+occupied.heightCells);r++)
        cells.fill(1,r*grid.cols+Math.max(0,occupied.col),r*grid.cols+Math.min(grid.cols,occupied.col+occupied.widthCells));
    } else {
      nodes ||= projectMap(map);
      const node=nodes.get(e.current_node_id); if(!node) continue;
      const p=e.simulation_state?.world_position;
      const a=-Math.PI*3/4,dx=(p?.x??node.x)-node.x,dy=(p?.y??node.y)-node.y;
      legacy.push({x:node.worldX+(dx*Math.cos(a)-dy*Math.sin(a))*1.5-54,
        y:node.worldY+(dx*Math.sin(a)+dy*Math.cos(a))*.86-90,width:108,height:115});
    }
  }
  const roads:[number,number,number,number][]=[];
  if(corridors.length) {
    nodes ||= projectMap(map);
    for(const edge of map.edges) {
      const a=nodes.get(edge.from),b=nodes.get(edge.to);
      if(a?.is_passable&&b?.is_passable)roads.push([a.worldX,a.worldY,b.worldX,b.worldY]);
    }
  }
  cached={entities,cells,legacy,corridors,roads,approaches};occupancy.set(map,cached);return cached;
}
function intersectsSegment(a:number[],rect:number[]) {
  let low=0,high=1;
  for(let i=0;i<2;i++) {
    const start=a[i],delta=a[i+2]-start;
    if(Math.abs(delta)<1e-12){if(start<rect[i]||start>rect[i+2])return false;}
    else {const t1=(rect[i]-start)/delta,t2=(rect[i+2]-start)/delta;low=Math.max(low,Math.min(t1,t2));high=Math.min(high,Math.max(t1,t2));if(low>high)return false;}
  }
  return true;
}
export function placementReason(map:ServerMap,cell:GridCell,code:string,teamId:string,entities:Occupant[]) {
  const grid=map.placement_grid,footprint=grid?.footprints[code],owner=map.team_ids.indexOf(teamId)+1;
  if (!grid || !footprint || !owner) return 'Không có bản đồ xây dựng';
  if(!Number.isInteger(cell.row) || !Number.isInteger(cell.col)) return 'Tọa độ không hợp lệ';
  if (cell.row<0 || cell.col<0 || cell.row+footprint.heightCells>grid.rows || cell.col+footprint.widthCells>grid.cols) return 'Ngoài bản đồ';
  if(code==='shield_generator') {
    const base=projectMap(map).get(`node_base_t${owner}`),anchor=gridAnchor(grid,cell,footprint);
    const zone=grid.shieldPlacement || {width:440,height:340,offsetY:-17};
    if(!base || ((anchor.x-base.worldX)/(zone.width/2))**2+((anchor.y-base.worldY-zone.offsetY)/(zone.height/2))**2>1+1e-9)
      return 'Máy tạo khiên phải nằm trong vòng khiên quanh căn cứ';
  }
  const data=mask(grid);
  for (let r=cell.row;r<cell.row+footprint.heightCells;r++) for(let c=cell.col;c<cell.col+footprint.widthCells;c++)
    if (data[r*grid.cols+c]!==owner) return 'Ngoài lãnh thổ hoặc chạm đường, nước, căn cứ, khu tập kết';
  const rect=gridRect(grid,cell,footprint),occupied=occupiedCells(map,entities);
  for(const [left,top,right,bottom] of occupied.corridors) {
    const gap=grid.roadClearance!.safetyMargin,expanded=[rect.x-right-gap,rect.y-bottom-gap,rect.x+rect.width-left+gap,rect.y+rect.height-top+gap];
    if(occupied.roads.some(road=>intersectsSegment(road,expanded)))return 'Chạm hành lang di chuyển của quân hiện có';
  }
  for(const {road:[ax,ay,bx,by],envelope:[left,top,right,bottom]} of occupied.approaches) {
    const gap=grid.roadClearance?.stagingSafetyMargin ?? grid.roadClearance?.safetyMargin ?? 0;
    if(intersectsSegment([ax,ay,bx,by],[rect.x-right-gap,rect.y-bottom-gap,rect.x+rect.width-left+gap,rect.y+rect.height-top+gap]))
      return 'Chạm khu tập kết của quân hiện có';
  }
  for(let r=cell.row;r<cell.row+footprint.heightCells;r++) for(let c=cell.col;c<cell.col+footprint.widthCells;c++)
    if(occupied.cells[r*grid.cols+c]) return 'Vị trí đã có công sự';
  for(const other of occupied.legacy) {
    if(rect.x<other.x+other.width && rect.x+rect.width>other.x && rect.y<other.y+other.height && rect.y+rect.height>other.y) return 'Vị trí đã có công sự';
  }
  return '';
}
