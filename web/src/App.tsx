import { useEffect, useRef, useState } from 'react';
import type { Reports, Snapshot } from './types';
import { scenarioName } from './scenarios';
import { Icon, shortId } from './ui';
import TitleScreen from './TitleScreen';
import LiveTab from './LiveTab';
import DecisionsTab from './DecisionsTab';
import ModelsTab from './ModelsTab';
import BenchmarkTab from './BenchmarkTab';
import TrainingTab from './TrainingTab';
import Tour from './Tour';
import Project from './Project';

// The GitHub Pages build (npm run build:static) has no API: only the project page and the recorded tour work there.
const STATIC=import.meta.env.VITE_STATIC==='1';

const tabs=[
  {id:'live',name:'Live lane',icon:'camera',hint:'Camera, overlays, cart and checkout'},
  {id:'decisions',name:'Decisions',icon:'list',hint:'Why each object is (or isn’t) in the cart'},
  {id:'models',name:'Models',icon:'chip',hint:'Detector, classifier and tracker results'},
  {id:'benchmark',name:'Benchmark',icon:'chart',hint:'Held-out scenario pass rates'},
  {id:'training',name:'Training',icon:'pulse',hint:'Progress of data export, training, recording and scoring'},
];

// The hash keeps the current view on refresh: #/ is the project page, #/scenarios the scenario picker,
// #/lab/<tab> the lab, #/tour/<scenario> a recorded run. Any other hash (#results) is an anchor on the project page.
function readRoute(){const [,view,tab]=location.hash.replace(/^#/,'').split('/');
  if(view==='tour')return {view:'tour',tab:tab||'single'};
  if(view==='lab')return {view:'lab',tab:tabs.some(t=>t.id===tab)?tab:'live'};
  return {view:view==='scenarios'?'title':'project',tab:'live'};}

export default function App(){
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
  const [reports,setReports]=useState<Reports|null>(null);
  const [connected,setConnected]=useState(false);
  const [busy,setBusy]=useState<string|null>(null);
  const [error,setError]=useState<string|null>(null);
  const [route,setRoute]=useState(readRoute);
  const [now,setNow]=useState(Date.now());
  const lastUpdate=useRef(Date.now());
  const confirmationKey=useRef<{cart:string;version:number;key:string}|null>(null);
  const update=(s:Snapshot)=>{setSnapshot(s);lastUpdate.current=Date.now();};
  const go=(view:string,tab='live')=>{location.hash=view==='lab'?`/lab/${tab}`:view==='tour'?`/tour/${tab}`:view==='title'?'/scenarios':'/';window.scrollTo(0,0);};
  useEffect(()=>{const onHash=()=>setRoute(readRoute());window.addEventListener('hashchange',onHash);return()=>window.removeEventListener('hashchange',onHash);},[]);
  useEffect(()=>{if(STATIC)return;fetch('/api/reports').then(r=>r.ok?r.json():Promise.reject()).then(setReports).catch(()=>{});},[connected]);
  useEffect(()=>{
    if(STATIC)return;
    let disposed=false,socket:WebSocket|undefined,retry:ReturnType<typeof setTimeout>|undefined;
    const connect=()=>{if(disposed)return;socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/ws`);socket.onopen=()=>setConnected(true);socket.onmessage=e=>{try{update(JSON.parse(e.data));}catch{/* bad snapshots stay out of rendered state */}};socket.onclose=()=>{setConnected(false);if(!disposed)retry=setTimeout(connect,1500);};socket.onerror=()=>socket?.close();};
    connect();
    const poll=setInterval(()=>{setNow(Date.now());if(!socket||socket.readyState!==WebSocket.OPEN)fetch('/api/snapshot').then(r=>r.ok?r.json():Promise.reject()).then(update).catch(()=>{});},1500);
    return()=>{disposed=true;clearInterval(poll);if(retry)clearTimeout(retry);socket?.close();};
  },[]);
  async function action(path:string,body?:unknown){
    setBusy(path);setError(null);
    try{const response=await fetch(`/api/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const data=await response.json();if(!response.ok)throw new Error(data.detail||'The request could not be completed');if(data.session)update(data);else if(data.pending)setError(data.message);else {const r=await fetch('/api/snapshot');update(await r.json());}}
    catch(e){setError(e instanceof Error?e.message:'Could not connect to the checkout API');}
    finally{setBusy(null);}
  }
  const start=(id:string)=>{void action('scenario',{scenario:id});go('lab','live');};
  // No live scene: play the frames Unity already rendered through the real pipeline. Without the API or the recordings, show the recorded tour.
  const replay=async(id:string)=>{
    try{const response=await fetch('/api/replay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario:id})});
      if(!response.ok)throw new Error();update(await response.json());go('lab','live');}
    catch{go('tour',id);}
  };
  const cart=snapshot?.cart;
  const age=(snapshot?.frame?.age_ms||0)+(now-lastUpdate.current);
  const live=!!snapshot?.frame&&age<4000&&!snapshot.simulator.paused;
  const reviewing=cart?.status==='REVIEWING',confirmed=cart?.status==='CONFIRMED';
  const statusText=confirmed?'Confirmed':reviewing?'Ready to confirm':snapshot?.simulator.paused?'Capture paused':live?(snapshot?.simulator.replay?'Playing recorded frames':'Observing lane'):'Awaiting camera';
  function confirm(){if(!cart)return;if(!confirmationKey.current||confirmationKey.current.cart!==cart.id||confirmationKey.current.version!==cart.version)confirmationKey.current={cart:cart.id,version:cart.version,key:crypto.randomUUID()};void action('cart/confirm',{version:cart.version,idempotency_key:confirmationKey.current.key});}

  if(route.view==='project') return <Project onTour={id=>go('tour',id)} onScenarios={()=>go('title')} onLab={tab=>go('lab',tab)}/>;
  if(route.view==='tour') return <Tour id={route.tab} onPick={id=>go('tour',id)} onBack={()=>go('title')}/>;
  if(route.view==='title') return <TitleScreen snapshot={snapshot} connected={connected} live={live} reports={reports} busy={busy}
    onStart={start} onReplay={id=>void replay(id)} onWatch={id=>go('tour',id)} onResume={()=>go('lab','live')} onOpen={tab=>go('lab',tab)} onHome={()=>go('project')}/>;

  // The lab needs the local API. On the static site, say so instead of showing empty tabs.
  if(STATIC) return <div className="project"><section className="project-hero static-lab"><div>
    <div className="eyebrow">LIVE LAB · RUNS ON YOUR MACHINE</div>
    <h1>The lab needs the <span>local API</span>.</h1>
    <p>This page is a static copy: the project page and the 17 recorded scenes. The live lab plays recorded frames through the trained models, which needs Python, the weights and ideally a GPU. To run it, clone the repository and follow the README quickstart.</p>
    <div className="title-actions"><button className="primary-button" onClick={()=>go('tour','single')}><Icon name="play" size={17}/> Watch the 17 scenes</button>
      <button className="secondary-button" onClick={()=>go('project')}><Icon name="back" size={16}/> Project page</button>
      <a className="secondary-button" href="https://github.com/dangermos/ProPass#2-run-the-models-live-without-unity">How to run it</a></div></div></section></div>;

  const tab=route.tab;
  return <div className="app-shell">
    <aside className="rail"><button className="brand-mark" aria-label="Back to scenarios" title="Scenarios" onClick={()=>go('title')}>P<span/></button><div className="rail-divider"/>
      {tabs.map(t=><button key={t.id} className={`rail-button ${tab===t.id?'selected':''}`} title={`${t.name}: ${t.hint}`} aria-label={t.name} onClick={()=>go('lab',t.id)}><Icon name={t.icon}/></button>)}
      <div className="rail-spacer"/><div className="rail-bottom" title="Local simulation"><Icon name="shield"/></div></aside>
    <main className="workspace">
      <header className="header lab-header">
        <div className="lab-title"><button className="back-button" onClick={()=>go('title')}><Icon name="back" size={16}/> Scenarios</button>
          <div><span className="eyebrow">LANE 01 · SESSION {snapshot?shortId(snapshot.session.id):'—'}</span><h1>{scenarioName(snapshot?.simulator.scenario)}</h1></div></div>
        <div className="header-right">
          <button className="text-button" disabled={!!busy} onClick={()=>void action('cart/reset')}><Icon name="reset" size={15}/> Restart run</button>
          <span className={`api-status ${live?'online':''}`}><span className="dot"/>{statusText}</span>
          <span className={`api-status ${connected?'online':''}`}><span className="dot"/>{connected?'API connected':'Connecting API'}</span>
        </div>
      </header>
      <nav className="tab-bar" role="tablist">{tabs.map(t=><button key={t.id} role="tab" aria-selected={tab===t.id} className={tab===t.id?'active':''} onClick={()=>go('lab',t.id)}><Icon name={t.icon} size={16}/>{t.name}{t.id==='decisions'&&snapshot?.review_required&&<span className="tab-alert" title="Something needs review"/>}</button>)}</nav>
      {(error||snapshot?.error)&&<div role="alert" className="error-banner"><Icon name="alert"/><span>{error||snapshot?.error}</span><button onClick={()=>setError(null)} aria-label="Dismiss error">×</button></div>}
      {tab==='live'&&<LiveTab config={reports?.config} geometry={snapshot?.geometry??reports?.geometry} snapshot={snapshot} busy={busy} action={action} confirm={confirm} live={live} statusText={statusText}/>}
      {tab==='decisions'&&<DecisionsTab snapshot={snapshot}/>}
      {tab==='models'&&<ModelsTab reports={reports}/>}
      {tab==='benchmark'&&<BenchmarkTab reports={reports} busy={busy} onRun={start}/>}
      {tab==='training'&&<TrainingTab/>}
      <footer className="footer"><span><span className="dot"/> PROPASS / LOCAL RESEARCH PROTOTYPE</span><span>Learned perception · canonical identity · reversible events</span><span>SIMULATION ONLY</span></footer>
    </main>
  </div>;
}
