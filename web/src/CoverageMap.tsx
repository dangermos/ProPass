import { useEffect, useId, useState } from 'react';
import type { CSSProperties } from 'react';
import type { Detection, Geometry, Snapshot } from './types';
import { cameraColor, cameraName, objectColor } from './camera';
import { Icon } from './ui';

type Point=[number,number];
type Trail={id:string;points:Point[]};
const keyFor=(object:Detection)=>object.object_id??String(object.track_id);
const validPoint=(world?:Point):world is Point=>!!world&&world.length===2&&world.every(Number.isFinite);

export default function CoverageMap({geometry,snapshot,camera,onCamera}:{geometry?:Geometry|null;snapshot:Snapshot|null;camera:string;onCamera:(id:string)=>void}){
  const id=useId().replaceAll(':','');
  const [history,setHistory]=useState<{run:string;trails:Trail[]}>({run:'',trails:[]});
  useEffect(()=>{
    if(!snapshot)return;
    setHistory(previous=>{
      const trails=new Map((previous.run===snapshot.session.run_id?previous.trails:[]).map(t=>[t.id,t.points]));
      for(const object of snapshot.objects){
        if(!validPoint(object.world)||object.visible===false)continue;
        const points=trails.get(keyFor(object))??[],last=points.at(-1);
        if(!last||Math.hypot(object.world[0]-last[0],object.world[1]-last[1])>.06)trails.set(keyFor(object),[...points,object.world].slice(-32));
      }
      const ids=new Set(snapshot.objects.map(keyFor));
      return {run:snapshot.session.run_id,trails:[...trails].filter(([key])=>ids.has(key)).map(([key,points])=>({id:key,points}))};
    });
  // Keyed to the processed frame on purpose: trails grow once per frame, not on every snapshot.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[snapshot?.session.run_id,snapshot?.frame?.frame_id,snapshot?.objects]);

  if(!geometry)return <article className="panel coverage-panel"><div className="panel-heading"><div><Icon name="lane" size={17}/><h2>Lane coverage</h2><span className="subtle-tag">IMAGE MODE</span></div></div><div className="coverage-empty"><strong>Single-view tracking</strong><p>No calibrated lane map is available. The camera overlay shows the image-space checkout zones.</p></div></article>;

  const {bounds,lane,cameras}=geometry;
  // One meter has the same scale on both axes. Travel runs left → right (+z).
  const scale=Math.min(600/(bounds.z[1]-bounds.z[0]),350/(bounds.x[1]-bounds.x[0]));
  const width=(bounds.z[1]-bounds.z[0])*scale,height=(bounds.x[1]-bounds.x[0])*scale;
  const left=(740-width)/2,top=(418-height)/2;
  const project=([x,z]:number[]):Point=>[left+(z-bounds.z[0])*scale,top+(x-bounds.x[0])*scale];
  const polygon=(points:number[][])=>points.map(point=>project(point).join(',')).join(' ');
  const objects=(snapshot?.objects??[]).filter(object=>validPoint(object.world));
  const visible=objects.filter(o=>o.visible!==false).length;
  const trails=history.run===snapshot?.session.run_id?history.trails:[];
  const latestCameras=snapshot?.frames?Object.keys(snapshot.frames):snapshot?.frame?[snapshot.frame.camera_id??'lane']:[];
  const lines=[{z:lane.approach_z,name:'APPROACH',color:'#ffbb71'},{z:lane.commit_z,name:'COMMIT',color:'#38d6bf'}];
  const gridX=Array.from({length:Math.floor(bounds.x[1]-bounds.x[0])+1},(_,i)=>bounds.x[0]+i);
  const gridZ=Array.from({length:Math.floor(bounds.z[1]-bounds.z[0])+1},(_,i)=>bounds.z[0]+i);

  return <article className="panel coverage-panel">
    <div className="panel-heading"><div><Icon name="lane" size={17}/><h2>Lane coverage</h2><span className="subtle-tag">CALIBRATED METERS</span></div><span className="coverage-count">{visible} visible · {objects.length-visible} last seen</span></div>
    <div className="coverage-legend">{cameras.map(cam=><button key={cam.id} aria-pressed={camera===cam.id} className={camera===cam.id?'active':''} onClick={()=>onCamera(cam.id)} style={{'--camera-color':cameraColor(cam.id)} as CSSProperties}><span className="coverage-swatch"/>{cameraName(cam.id)}<small>{latestCameras.includes(cam.id)?'received':'missing'}</small></button>)}<span className="overlap-key"><i/>Overlap</span><span className="blind-key"><i/>No geometric coverage</span></div>
    <svg className="coverage-map" viewBox="0 0 740 450" role="img" aria-label={`Calibrated top-down lane map. ${visible} visible physical products. Travel direction is left to right.`}>
      <defs>
        <clipPath id={`${id}-bounds`}><rect x={left} y={top} width={width} height={height} rx="6"/></clipPath>
        <pattern id={`${id}-blind`} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><line x1="0" y1="0" x2="0" y2="8" stroke="#66748a" strokeOpacity=".3" strokeWidth="2"/></pattern>
        <mask id={`${id}-uncovered`}><rect width="740" height="450" fill="white"/>{cameras.map(cam=><polygon key={cam.id} points={polygon(cam.footprint)} fill="black"/>)}</mask>
        {cameras.map(cam=><clipPath key={cam.id} id={`${id}-${cam.id}`}><polygon points={polygon(cam.footprint)}/></clipPath>)}
      </defs>
      <g clipPath={`url(#${id}-bounds)`}>
        <rect x={left} y={top} width={width} height={height} fill="#091321"/>
        <rect x={left} y={project([-lane.half_width,bounds.z[0]])[1]} width={width} height={lane.half_width*2*scale} fill="#38d6bf" fillOpacity=".06"/>
        {gridX.map(x=>{const [,y]=project([x,0]);return <line key={`x${x}`} x1={left} y1={y} x2={left+width} y2={y} stroke="#283d52" strokeOpacity=".45"/>;})}
        {gridZ.map(z=>{const [x]=project([0,z]);return <line key={`z${z}`} x1={x} y1={top} x2={x} y2={top+height} stroke="#283d52" strokeOpacity=".45"/>;})}
        <rect x={left} y={top} width={width} height={height} fill={`url(#${id}-blind)`} mask={`url(#${id}-uncovered)`}/>
        {cameras.map(cam=><polygon key={cam.id} points={polygon(cam.footprint)} fill={cameraColor(cam.id)} fillOpacity={camera===cam.id ? .13 : .045} stroke={cameraColor(cam.id)} strokeOpacity={camera===cam.id ? .8 : .4} strokeWidth={camera===cam.id?2:1} strokeDasharray={camera===cam.id?undefined:'5 5'}/>)}
        {cameras.map((a,i)=>cameras.slice(i+1).map(b=><g key={`${a.id}-${b.id}`} clipPath={`url(#${id}-${a.id})`}><polygon points={polygon(b.footprint)} fill="#38d6bf" fillOpacity=".08"/></g>))}
        {[-lane.half_width,lane.half_width].map(x=>{const [,y]=project([x,0]);return <line key={x} x1={left} y1={y} x2={left+width} y2={y} stroke="#b3c8d9" strokeOpacity=".55" strokeWidth="1.5"/>;})}
        {lines.map(line=>{const [x,y]=project([-lane.half_width,line.z]);return <g key={line.name}><line x1={x} y1={y} x2={x} y2={y+2*lane.half_width*scale} stroke={line.color} strokeWidth="2" strokeDasharray="6 5"/><text x={x+7} y={y-9} fill={line.color} className="map-zone-label">{line.name}</text><text x={x+7} y={y+2*lane.half_width*scale+16} fill={line.color} className="map-meter-label">z {line.z.toFixed(1)} m</text></g>;})}
        {objects.map(object=>{
          const trail=trails.find(t=>t.id===keyFor(object));
          return trail&&trail.points.length>1?<polyline key={keyFor(object)} points={polygon(trail.points)} stroke={objectColor(object)} strokeOpacity={object.visible===false ? .25 : .6} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>:null;
        })}
        {objects.map(object=>{
          const [x,y]=project(object.world!),color=objectColor(object),lastSeen=object.visible===false;
          return <g key={keyFor(object)} className="map-object" opacity={lastSeen ? .55 : 1}>
            <title>{`${keyFor(object)} · ${object.sku??'unresolved'} · ${object.state??'tracked'} · ${lastSeen?'last seen position':'visible'} · x ${object.world![0].toFixed(2)}, z ${object.world![1].toFixed(2)} m`}</title>
            {object.review_reason&&<circle cx={x} cy={y} r="12" fill="none" stroke="#ff8293" strokeWidth="1.5" strokeDasharray="3 2"/>}
            <circle cx={x} cy={y} r={object.membership?7:6} fill={lastSeen?'#0b1524':color} stroke={color} strokeWidth="2"/>
            {object.membership&&<path d={`M${x-3} ${y}l2 2 4-4`} stroke={lastSeen?color:'#07121a'} strokeWidth="1.7" fill="none"/>}
            <text x={x+11} y={y-9} fill={color} className="map-object-label">{keyFor(object)}</text>
          </g>;
        })}
      </g>
      <rect x={left} y={top} width={width} height={height} rx="6" fill="none" stroke="#314459"/>
      {cameras.map(cam=>{
        const [x,y]=project([cam.position[0],cam.position[2]]),clampedX=Math.min(left+width-10,Math.max(left+10,x)),clampedY=Math.min(top+height-10,Math.max(top+10,y));
        return <g key={cam.id} onClick={()=>onCamera(cam.id)} className="map-camera"><title>{`${cameraName(cam.id)} at (${cam.position.map(v=>v.toFixed(2)).join(', ')}) meters`}</title><rect x={clampedX-9} y={clampedY-8} width="18" height="16" rx="4" fill="#102031" stroke={cameraColor(cam.id)} strokeWidth="1.5"/><circle cx={clampedX} cy={clampedY} r="3" fill={cameraColor(cam.id)}/><text x={clampedX+14} y={clampedY+4} className="map-camera-label" fill={cameraColor(cam.id)}>{cam.id}</text></g>;
      })}
      <text x={left} y={top+height+22} className="map-axis-label" fill="#8194a9">ENTRY</text>
      <path d={`M${left+width/2-44} ${top+height+18}h88m-6-4 6 4-6 4`} stroke="#8194a9" fill="none"/>
      <text x={left+width/2} y={top+height+36} textAnchor="middle" className="map-axis-label" fill="#8194a9">TRAVEL +z · 1 m GRID</text>
      <text x={left+width} y={top+height+22} textAnchor="end" className="map-axis-label" fill="#8194a9">EXIT</text>
    </svg>
    <div className="coverage-footer"><span><i className="object-key"/> Visible <i className="object-key lost"/> Last seen</span><span>Footprints at {geometry.plane_height??.9} m carry height · obstacles can hide products.</span></div>
  </article>;
}
