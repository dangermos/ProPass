import { useEffect, useState } from 'react';
import { Icon, percent } from './ui';

type Stage={camera:string;model:string;state:string;epoch:number|null;epochs:number|null};
type Progress={
  export:{completed:number;total:number;running:boolean;error:string|null;age_seconds:number|null};
  training:{log:string|null;age_seconds?:number|null;stages:Stage[];active:boolean;finished?:boolean};
  recordings:{folder:string;recorded:number;expected:number;latest:string|null;age_seconds:number|null}[];
  scores:{file:string;available:boolean;label?:string;passed?:number;runs?:number;age_seconds?:number|null;stale?:boolean}[];
  models:{camera:string;age_seconds:number|null;detector_map:number|null;classifier_accuracy:number|null}[];
};

const ago=(s?:number|null)=>s==null?'never':s<90?`${s}s ago`:s<5400?`${Math.round(s/60)} min ago`:s<172800?`${Math.round(s/3600)} h ago`:`${Math.round(s/86400)} days ago`;
const recent=(s?:number|null)=>s!=null&&s<90;

function Bar({value,total,tone}:{value:number;total:number;tone:string}){
  return <span className="bar-track progress-bar"><span className={`bar-fill tone-${tone}`} style={{width:`${total?Math.min(100,value/total*100):0}%`}}/></span>;
}

function Step({icon,title,state,children}:{icon:string;title:string;state:'done'|'running'|'waiting'|'stopped';children:React.ReactNode}){
  const label={done:'Done',running:'Running',waiting:'Waiting',stopped:'Stopped'}[state];
  return <article className={`panel progress-step state-${state}`}><div className="progress-head"><span className="metric-icon teal"><Icon name={icon}/></span><h3>{title}</h3><span className={`progress-state state-${state}`}>{state==='running'&&<span className="dot live"/>}{label}</span></div>{children}</article>;
}

// A read-only view of the offline pipeline. The work is started from a terminal or by an
// assistant. This page only shows where it is, from the files each step writes.
export default function TrainingTab(){
  const [data,setData]=useState<Progress|null>(null);
  const [failed,setFailed]=useState(false);
  useEffect(()=>{
    let stop=false;
    const load=()=>fetch('/api/progress').then(r=>r.ok?r.json():Promise.reject()).then(d=>{if(!stop){setData(d);setFailed(false);}}).catch(()=>{if(!stop)setFailed(true);});
    load();const timer=setInterval(load,3000);
    return()=>{stop=true;clearInterval(timer);};
  },[]);
  if(!data) return <div className="tab-page"><div className="tab-empty"><Icon name="pulse" size={28}/><p>{failed?'The API is not answering. Start it with scripts/start.sh.':'Loading pipeline progress…'}</p></div></div>;
  const e=data.export,t=data.training;
  const exportState=e.running?'running':e.total&&e.completed>=e.total?'done':'waiting';
  const trainState=t.active?'running':t.finished?'done':t.stages.some(s=>s.state==='stopped')?'stopped':'waiting';
  const busy=e.running||t.active||data.recordings.some(r=>r.recorded<r.expected&&recent(r.age_seconds));
  return <div className="tab-page">
    <div className="tab-intro"><div><h2>Training pipeline</h2><p>When products or people change, the models are rebuilt in five steps: export labelled scenes from Unity, train a detector and a classifier for each camera, record the benchmark runs, then score them. This page updates every 3 seconds.</p></div>
      <div className={`pipeline-badge ${busy?'busy':''}`}>{busy&&<span className="dot live"/>}{busy?'Pipeline running':'Idle'}</div></div>
    <div className="progress-grid">
      <Step icon="camera" title="1 · Export training scenes" state={exportState}>
        <Bar value={e.completed} total={e.total} tone="teal"/>
        <p>{e.total?`${e.completed.toLocaleString()} of ${e.total.toLocaleString()} scenes`:'No export yet'} · updated {ago(e.age_seconds)}{e.error?` · error: ${e.error}`:''}</p>
      </Step>
      <Step icon="chip" title="2 · Train models" state={trainState}>
        <div className="stage-list">{t.stages.map(s=><div className={`stage state-${s.state}`} key={s.camera+s.model}>
          <span>{s.camera} camera · {s.model}</span>
          <Bar value={s.state==='done'?1:s.epoch??0} total={s.state==='done'?1:s.epochs??1} tone={s.model==='detector'?'blue':'purple'}/>
          <em>{s.state==='done'?'done':s.epoch!=null?`epoch ${s.epoch} of ${s.epochs}`:s.state}</em></div>)}</div>
        <p>{t.log?`Log: artifacts/logs/${t.log} · updated ${ago(t.age_seconds)}`:'No training log yet'}</p>
      </Step>
      {data.recordings.map((r,i)=><Step key={r.folder} icon="lane" title={`${3+i} · Record ${i?'held-out':'development'} runs`} state={r.recorded>=r.expected?'done':recent(r.age_seconds)?'running':'waiting'}>
        <Bar value={r.recorded} total={r.expected} tone="orange"/>
        <p>{r.recorded} of {r.expected} runs{r.latest?` · latest: ${r.latest}`:''} · updated {ago(r.age_seconds)}</p>
      </Step>)}
      <Step icon="chart" title="5 · Scores" state={data.scores.every(s=>s.available&&!s.stale)?'done':'waiting'}>
        <div className="stage-list">{data.scores.map((s,i)=><div className="stage" key={s.file}><span>{i?'Held-out seeds':'Development seeds'}</span>
          <Bar value={s.passed??0} total={s.runs??1} tone={s.stale?'orange':'good'}/><em>{s.available?`${s.passed} of ${s.runs} · ${s.stale?'previous models':ago(s.age_seconds)}`:'not scored yet'}</em></div>)}</div>
        <p>Scores marked “previous models” were measured before the current weights were trained and are waiting to be re-scored.</p>
      </Step>
      <Step icon="eye" title="Current models" state="done">
        <div className="stage-list">{data.models.map(m=><div className="stage" key={m.camera}><span>{m.camera} camera</span><em>detector mAP50–95 {m.detector_map?.toFixed(3)??'—'} · classifier {percent(m.classifier_accuracy,1)} · trained {ago(m.age_seconds)}</em></div>)}</div>
      </Step>
    </div>
    <p className="tab-footnote">Read-only. Recording and exporting need Unity out of Play mode. Steps are started from a terminal: see docs/training.md.</p>
  </div>;
}
