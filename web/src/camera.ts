import type { CameraFrame, Detection, Snapshot } from './types';
import { colors } from './ui';

export const cameraName=(id:string)=>id==='lane'?'Lane camera':id==='overhead'?'Overhead camera':id==='scan'?'Barcode scan camera':id.replaceAll('_',' ');
export const cameraColor=(id:string)=>id==='overhead'?'#bd9aff':'#6aa8ff';

export function frameForCamera(snapshot:Snapshot|null,camera:string):CameraFrame|null{
  if(!snapshot)return null;
  // A missing camera in a grouped snapshot is missing evidence, never the previous view.
  if(snapshot.frames)return snapshot.frames[camera]??null;
  const legacy=snapshot.frame;
  return legacy&&(legacy.camera_id??'lane')===camera?legacy:null;
}

export function detectionsForCamera(snapshot:Snapshot|null,camera:string):Detection[]{
  return snapshot?.detections.filter(d=>(d.camera??'lane')===camera)??[];
}

export function objectColor(object:Detection){
  if(object.state==='OUTSIDE')return '#8fa3bf';
  if(!object.sku)return '#ff8293';
  const id=object.object_id??String(object.track_id);
  let hash=0;for(const char of id)hash=(hash*31+char.charCodeAt(0))>>>0;
  return colors[hash%colors.length];
}
