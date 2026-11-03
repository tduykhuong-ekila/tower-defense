import { ARTILLERY_BARREL_PITCH, artilleryProfile } from "../systems/turretAim";

type Vec3 = [number, number, number];
type ModelTools = {
  add: (points: Vec3[], color: string, edge?: string, metal?: boolean) => unknown;
  box: (x:number,y:number,z:number,length:number,width:number,height:number,color:string,bevel?:number) => void;
  rod: (from:Vec3,to:Vec3,radius:number,color:string) => void;
  verticalCylinder: (z:number,height:number,radius:number,color:string,cx?:number,cy?:number) => void;
};

/** The approved artillery family's large forms, in the same coordinates as its
 * muzzle math. Hull equipment follows travel; the elevated gun follows targets. */
export function buildArtillery(level: number, part: "turret" | "hull", tools: ModelTools) {
  const {add,box,rod,verticalCylinder}=tools;
  const olive=level===3?"#64703c":level===2?"#879352":"#a2a45b";
  const steel="#92969d", dark="#42484e", gold="#dfad49", wood="#b67b3c", rubber="#303238";
  const trim=level===3?gold:steel;
  if(part==="hull") {
    box(0,0,20,51,29,7,dark,1.4);
    box(0,0,25,53,33,6,olive,1.3);
    box(0,0,29,49,31,2,olive,.7);
    for(const side of [-1,1]) {
      // Exactly three axles, with tires/rims oriented around the vehicle's Y axis.
      for(const x of [-18,0,18]) {
        const near=side*21,far=side*15.3,r=7.5,centerZ=13;
        const ring=(y:number,radius:number):Vec3[]=>Array.from({length:24},(_,i)=>{
          const a=i/24*Math.PI*2;return [x+Math.cos(a)*radius,y,centerZ+Math.sin(a)*radius];
        });
        const a=ring(far,r),b=ring(near,r);
        add(a,rubber);add([...b].reverse(),rubber);
        for(let i=0;i<24;i++) {
          const n=(i+1)%24;
          add([a[i],b[i],b[n],a[n]],i%2?"#45464b":rubber,"#20252a");
        }
        rod([x,near,centerZ],[x,near+side*.4,centerZ],5.1,dark);
        rod([x,near+side*.5,centerZ],[x,near+side*.8,centerZ],4.1,olive);
        rod([x,near+side*.9,centerZ],[x,near+side*1.2,centerZ],2.1,level===3?gold:olive);
        box(x,side*17,22.5,14.5,10,2.5,olive,.8);
      }
      // Same storage rail layout, progressively enclosed by steel armor.
      box(-1,side*16.4,32,40,2.5,7,level===1?wood:olive,.5);
      for(const x of [-15,0,15]) {
        if(level>1) {
          box(x,side*17.6,31.5,13,2.5,7.5,trim,.7);
          box(x,side*18.1,31.5,11.5,2.7,6,level===3?dark:steel,.5);
        }
        for(const z of [29.5,34])rod([x-4,side*19.5,z],[x-4,side*19.9,z],.55,trim);
      }
      for(const x of [-24,24]) {
        // Compact stabilizers stay within the shared footprint in every frame.
        rod([x,side*15.5,22],[x+Math.sign(x)*1.5,side*20.5,8],level===3?2.2:1.6,steel);
        rod([x,side*15.5,22],[x+Math.sign(x)*.6,side*17.5,17],level===3?3:2.5,olive);
        box(x+Math.sign(x)*1.5,side*21,5.4,10,8,2.5,dark,.7);
        box(x+Math.sign(x)*1.5,side*21,7,7.5,6,1,level===3?gold:olive,.3);
        if(level===3)box(x,side*17,18,5,6,3,gold,.5);
      }
      // Tail lamps and tow eyes make fore/aft travel legible.
      box(-26.9,side*11,23,1.4,4.5,4,dark,.35);
      rod([-27.6,side*11,23],[-28,side*11,23],1.4,"#e14b31");
      box(26.8,side*11,23,1.4,4.5,3.5,dark,.35);
      box(27.6,side*11,23,.3,3,2,"#f6d45c",.07);
      box(-17,side*8.5,33.5,10,10,7,level===1?wood:olive,.8);
      box(-17,side*8.5,37.2,11,10.5,1,level===3?gold:steel,.3);
      box(-17,side*8.5,34,1.6,10.5,7.7,dark,.3);
      box(-2,side*11,32.5,11,8,6,level===1?wood:level===3?dark:olive,.6);
      box(-2,side*11,35.7,11.5,8.5,.9,level===3?gold:steel,.25);
    }
    if(level>1) {
      box(17,0,33,11,23,8,level===3?dark:olive,1);
      box(17,0,37,11.5,24,1.5,trim,.4);
      for(const y of [-7,0,7]) {
        verticalCylinder(37.8,6,1.9,olive,17,y);
        verticalCylinder(43.8,1,2,gold,17,y);
        const ring:Vec3[]=Array.from({length:12},(_,i)=>[17+Math.cos(i/12*Math.PI*2)*1.9,y+Math.sin(i/12*Math.PI*2)*1.9,44.8]);
        for(let i=0;i<12;i++)add([ring[i],ring[(i+1)%12],[17,y,49.5]],gold,"",true);
      }
      if(level===3) {
        box(8,-9,36,8,8,9,dark,.8);
        box(8,-13.2,36,6,.7,7,gold,.2);
        for(const z of [34,36,38])box(8,-13.7,z,4,.4,.7,dark,.1);
        box(21,0,33,2,20,2,steel,.4);
      }
    }
    verticalCylinder(29.5,2.5,12.8,dark,-4.5);
    verticalCylinder(32,1.5,11.7,olive,-4.5);
    return;
  }

  const p=artilleryProfile(level),pitch=ARTILLERY_BARREL_PITCH;
  const axis=(x:number):Vec3=>[x,0,p.height+x*pitch];
  verticalCylinder(32,2,11.5,olive);
  box(-5,0,35,19,18,3,level===3?gold:steel,.8);
  for(const side of [-1,1]) {
    const y=side*7;
    if(level===1) {
      rod([-9,y,34],[-9,y,42],2.2,olive);
      rod([4,y,34],[-4,y,46],1.7,dark);
    } else {
      const profile:[[number,number],[number,number],[number,number],[number,number],[number,number]]=[[-15,34],[-18,48],[-10,53],[3,45],[5,35]];
      const shape=(cy:number,inset=0):Vec3[]=>profile.map(([x,z])=>[x*(1-inset)-3*inset,cy,z*(1-inset)+43*inset]);
      const front=shape(y+side*2),back=shape(y-side*1.2);
      add(front,level===3?gold:steel);add(back,dark);
      for(let i=0;i<5;i++)add([front[i],back[i],back[(i+1)%5],front[(i+1)%5]],dark);
      if(level===3)add(shape(y+side*2.1,.11),dark,"#d5a34a");
      for(const [x,z] of [[-12,46],[-8,49],[0,43],[-11,37]])
        rod([x,y+side*2.2,z],[x,y+side*2.6,z],.65,level===3?gold:"#b9bdc0");
    }
    // Elevation trunnions, hydraulic body and exposed silver piston.
    rod([-5,y,43],[-5,y+side*3,43],3.1,steel);
    rod([-5,y+side*3.1,43],[-5,y+side*3.7,43],1.5,level===1?olive:gold);
    rod([7,y,34],[12,y,artilleryProfile(level).height+12*ARTILLERY_BARREL_PITCH-4.2],1.1,steel);
    rod([7,y,34],[9.5,y,41.5],2,level===3?dark:olive);
    rod([8.8,y,39.5],[9.5,y,41.5],2.15,level===3?gold:steel);
    if(level===3) {
      rod([1,y+side*3,35],[7,y+side*3,45],1.1,steel);
      rod([1,y+side*3,35],[4,y+side*3,40],2,dark);
    }
  }
  // Hand-operated elevation wheel remains part of the family at every level.
  rod([-7,10.5,39],[-7,11.5,39],4.6,dark);
  rod([-7,11.6,39],[-7,12,39],3.6,level===1?olive:gold);
  rod([-7,12.1,39],[-7,12.4,39],2.6,dark);
  for(const a of [0,Math.PI/3,Math.PI*2/3]) {
    const dx=Math.cos(a)*3.7,dz=Math.sin(a)*3.7;
    rod([-7-dx,12.5,39-dz],[-7+dx,12.5,39+dz],.3,steel);
  }
  rod([-7,12.6,39],[-7,13,39],1.2,steel);

  // One continuous elevated barrel, with its painted tube, reinforcement bands,
  // bevelled muzzle and recessed bore all following the same pitched axis.
  const ring=(x:number,r:number):Vec3[]=>Array.from({length:32},(_,i)=>{
    const a=i/32*Math.PI*2;return [x,Math.cos(a)*r,p.height+x*pitch+Math.sin(a)*r];
  });
  type Section={x:number;r:number;color:string;port?:boolean;metal?:boolean};
  const sections:Section[]=[
    {x:-19,r:2.4,color:dark},{x:-17,r:5.3,color:olive},
    {x:-3,r:5.3,color:olive},{x:0,r:5.9,color:level===3?gold:steel,metal:true},
    {x:2,r:5.9,color:level===3?gold:steel,metal:true},
    {x:3,r:p.radius+.3,color:olive},{x:p.length-7,r:p.radius,color:olive},
    {x:p.length-6.5,r:p.muzzleRadius,color:level===3?gold:steel,metal:true},
    {x:p.length-5.5,r:p.muzzleRadius,color:level===3?gold:steel,metal:true},
    {x:p.length-5,r:p.muzzleRadius,color:dark,metal:true},
  ];
  if(level===3)for(const x of [p.length-4.5,p.length-2.7]) {
    sections.push({x,r:p.muzzleRadius,color:dark,metal:true},{x:x+1.1,r:p.muzzleRadius,color:dark,port:true,metal:true});
  }
  sections.push({x:p.length-.4,r:p.muzzleRadius,color:dark,metal:true},{x:p.length,r:p.muzzleRadius*.93,color:steel,metal:true});
  const rings=sections.map(s=>ring(s.x,s.r));
  add([...rings[0]].reverse(),dark);
  for(let j=1;j<rings.length;j++)for(let i=0;i<32;i++) {
    const n=(i+1)%32,port=sections[j].port&&[0,1,7,8,9,15,16,17,23,24,25,31].includes(i);
    add([rings[j-1][i],rings[j][i],rings[j][n],rings[j-1][n]],port?"#131920":sections[j].color,"",sections[j].metal&&!port);
  }
  const lip=rings[rings.length-1],inner=ring(p.length+.03,p.muzzleRadius*.69),deep=ring(p.length-3,p.muzzleRadius*.62);
  for(let i=0;i<32;i++) {
    const n=(i+1)%32;
    add([lip[i],inner[i],inner[n],lip[n]],"#b7b8b9","",true);
    add([inner[i],deep[i],deep[n],inner[n]],"#20262a","");
  }
  add(deep,"#0b1116","");
  if(level>1)for(const x of [10,24]) {
    const a=ring(x,p.radius+.55),b=ring(x+1,p.radius+.55);
    for(let i=0;i<32;i++)add([a[i],b[i],b[(i+1)%32],a[(i+1)%32]],level===3?gold:steel,"",true);
  }
  // Rectangular breech and a compact sight, rather than a tank turret roof.
  rod(axis(-17),axis(-3),4.8,olive);
  box(-12,0,p.height-5,15,8,7,olive,1);
  if(level>1) {
    box(-7,0,p.height+10,7,6,5,olive,.7);
    box(-3.3,0,p.height+10,.5,4.5,3.5,dark,.1);
    rod([-3,0,p.height+10],[-2.5,0,p.height+10],1.4,level===3?"#30c5ef":"#e6ab36");
    if(level===3) {
      box(-9,-6,p.height+8,7,3,5,gold,.5);
      rod([-6,-6,p.height+8],[-5.5,-6,p.height+8],1,"#71def7");
    }
  }
}
