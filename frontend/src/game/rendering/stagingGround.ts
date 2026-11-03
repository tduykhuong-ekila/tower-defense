export interface GroundPoint { x: number; y: number }

/** A soft clearing around actual parking spots contains every straight
 * approach to the rally gate. Its uneven border stays within the old reserved
 * rectangle, so changing the artwork cannot cover nearby building plots.
 */
export function stagingOutline(points: GroundPoint[], key: string): GroundPoint[] {
  if (!points.length) return [];
  const left = Math.min(...points.map(p => p.x)) - 35;
  const right = Math.max(...points.map(p => p.x)) + 35;
  const top = Math.min(...points.map(p => p.y)) - 35;
  const bottom = Math.max(...points.map(p => p.y)) + 35;
  let polygon = [{x:left,y:top},{x:right,y:top},{x:right,y:bottom},{x:left,y:bottom}];
  const phase = [...key].reduce((sum,ch,i) => sum+ch.charCodeAt(0)*(i+1),0) % 628 / 100;
  // Clip by support lines instead of warping parking positions or walking paths.
  for (let i=0; i<48; i++) {
    const angle = i*Math.PI*2/48, nx = Math.cos(angle), ny = Math.sin(angle);
    const margin = 30 + 2*Math.sin(3*angle+phase) + Math.sin(5*angle-phase);
    const support = Math.max(...points.map(p => p.x*nx+p.y*ny)) + margin;
    const clipped: GroundPoint[] = [];
    for (let j=0; j<polygon.length; j++) {
      const a = polygon[j], b = polygon[(j+1)%polygon.length];
      const da = a.x*nx+a.y*ny-support, db = b.x*nx+b.y*ny-support;
      if (da<=0) clipped.push(a);
      if ((da<0 && db>0)||(da>0 && db<0)) {
        const t = da/(da-db);
        clipped.push({x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t});
      }
    }
    polygon = clipped;
  }
  // Gentle inward scallops break up long grid-aligned sides. The 27px minimum
  // support margin leaves the 12px walking allowance clear of this worn fringe.
  const worn: GroundPoint[] = [];
  polygon.forEach((a,i) => {
    const b=polygon[(i+1)%polygon.length], dx=b.x-a.x,dy=b.y-a.y;
    const length=Math.hypot(dx,dy), steps=Math.max(1,Math.ceil(length/22));
    for(let j=0;j<steps;j++) {
      const t=j/steps;
      const wear=-(Math.sin(Math.PI*t)**2)*(5+4*Math.sin(t*Math.PI*3+phase+i));
      worn.push({x:a.x+dx*t+dy/(length||1)*wear,y:a.y+dy*t-dx/(length||1)*wear});
    }
  });
  // Smooth by physical perimeter distance, avoiding the clipped hull's angular
  // shoulders while keeping the clearing inside its reserved ground.
  const samples: GroundPoint[]=[];
  const lengths=worn.map((p,i)=>Math.hypot(p.x-worn[(i+1)%worn.length].x,p.y-worn[(i+1)%worn.length].y));
  const perimeter=lengths.reduce((sum,n)=>sum+n,0), count=Math.max(24,Math.ceil(perimeter/10));
  let segment=0,passed=0;
  for(let i=0;i<count;i++) {
    const distance=i*perimeter/count;
    while(segment<lengths.length-1 && passed+lengths[segment]<distance){passed+=lengths[segment++];}
    const a=worn[segment],b=worn[(segment+1)%worn.length],t=(distance-passed)/(lengths[segment]||1);
    samples.push({x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t});
  }
  return samples.map((_,i)=>{
    let x=0,y=0,total=0;
    for(let offset=-10;offset<=10;offset++) {
      const weight=Math.exp(-.5*(offset/3.5)**2),p=samples[(i+offset+count)%count];
      x+=p.x*weight;y+=p.y*weight;total+=weight;
    }
    return {x:x/total,y:y/total};
  });
}

function traceClearing(c: CanvasRenderingContext2D, outline: GroundPoint[]) {
  const last = outline[outline.length-1], first = outline[0];
  c.beginPath(); c.moveTo((last.x+first.x)/2,(last.y+first.y)/2);
  outline.forEach((point,i) => {
    const next = outline[(i+1)%outline.length];
    c.quadraticCurveTo(point.x,point.y,(point.x+next.x)/2,(point.y+next.y)/2);
  });
  c.closePath();
}

/** Packed earth, a worn grass transition and faint wheel scuffs, baked once. */
export function paintStagingGround(c: CanvasRenderingContext2D, points: GroundPoint[], gate: GroundPoint, key: string, teamColor: string) {
  // Shrink only the painted sand toward the gate; parking and routes stay fixed.
  const sandScale = .75;
  const outline = stagingOutline([...points,gate],key).map(p => ({
    x: gate.x + (p.x-gate.x)*sandScale,
    y: gate.y + (p.y-gate.y)*sandScale,
  }));
  if (!outline.length) return;
  c.save();
  c.lineJoin = 'round';
  // Transparent shoulders soften the boundary instead of framing it with a line.
  for (const [width,color] of [[12,'#9e995c25'],[6,'#b5a56855']] as const) {
    traceClearing(c,outline); c.lineWidth=width; c.strokeStyle=color; c.stroke();
  }
  const cx=outline.reduce((sum,p)=>sum+p.x,0)/outline.length;
  const cy=outline.reduce((sum,p)=>sum+p.y,0)/outline.length;
  const radius=Math.max(60,...outline.map(p=>Math.hypot(p.x-cx,p.y-cy)));
  const dirt=c.createRadialGradient(cx,cy,18,cx,cy,radius);
  dirt.addColorStop(0,'#d0b985'); dirt.addColorStop(.7,'#c4ad77'); dirt.addColorStop(1,'#b5a16e');
  traceClearing(c,outline); c.fillStyle=dirt; c.fill(); c.clip();
  // A restrained team-color wash keeps the ground earthy while marking ownership.
  c.globalAlpha=.18; c.fillStyle=teamColor;
  c.fillRect(cx-radius,cy-radius,radius*2,radius*2); c.globalAlpha=1;
  let seed=[...key].reduce((sum,ch)=>sum+ch.charCodeAt(0),917);
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)|0;return(seed>>>0)/4294967296;};
  // Broad wear patches vary the soil before fine dust and pebbles are added.
  for(let i=0;i<28;i++) {
    const a=random()*Math.PI*2,r=Math.sqrt(random())*radius;
    const x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r;
    const patch=c.createRadialGradient(x,y,0,x,y,25+random()*45);
    patch.addColorStop(0,i%2?'#f0d79b18':'#92784814');patch.addColorStop(1,'#b6a06e00');
    c.fillStyle=patch;c.fillRect(x-75,y-75,150,150);
  }
  // Uneven pale dust, compacted patches and small stones, without a parking grid.
  for(let i=0;i<340;i++) {
    const a=random()*Math.PI*2,r=Math.sqrt(random())*radius;
    const x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r;
    c.fillStyle=i%4===0?'#826f4a20':i%3===0?'#ecd7a125':'#ac915c1a';
    c.beginPath();c.ellipse(x,y,1+random()*5,.5+random()*2,random(),0,Math.PI*2);c.fill();
  }
  // Short, broken tire marks point toward the exit rather than outlining stalls.
  for(let i=1;i<points.length;i+=5) {
    const p=points[i],dx=gate.x-p.x,dy=gate.y-p.y,len=Math.hypot(dx,dy)||1;
    for(const side of [-7,7]) {
      const x=p.x-dy/len*side,y=p.y+dx/len*side;
      c.strokeStyle='#8c79512b';c.lineWidth=2;c.setLineDash([3,5]);
      c.beginPath();c.moveTo(x,y);c.quadraticCurveTo(x+dx*.04+3,y+dy*.04,x+dx/len*24,y+dy/len*24);c.stroke();
    }
  }
  c.restore();
}
