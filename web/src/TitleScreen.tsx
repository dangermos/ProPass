import type { Reports, Snapshot } from './types';
import { scenarios, scenarioName, type ScenarioInfo } from './scenarios';
import { Icon, percent, rateColor } from './ui';
import { asset } from './assets';

type Props = {snapshot:Snapshot|null;connected:boolean;live:boolean;reports:Reports|null;busy:string|null;
  onStart:(id:string)=>void;onReplay:(id:string)=>void;onWatch:(id:string)=>void;onResume:()=>void;onOpen:(tab:string)=>void;onHome:()=>void};

function Card({s,index,score,active,disabled,live,onStart}:{s:ScenarioInfo;index:number;score?:number;active:boolean;disabled:boolean;live:boolean;onStart:()=>void}){
  return <button className={`title-card ${s.group} ${active?'active':''}`} disabled={disabled} onClick={onStart}>
    <div className="title-card-image" style={{backgroundImage:`url(${asset(`scenarios/${s.id}.jpg`)})`}}>
      <span className="title-card-number">{String(index+1).padStart(2,'0')}</span>
      {score!=null&&<span className="title-card-score" style={{borderColor:rateColor(score),color:rateColor(score)}} title="Share of held-out benchmark runs passed">{percent(score)}</span>}
      {active&&<span className="title-card-live"><span className="dot"/>CURRENT</span>}
    </div>
    <div className="title-card-body">
      <strong>{s.name}</strong>
      <small>{s.detail}</small>
      <div className="title-card-foot"><span className="title-card-tag">{s.tests}</span><span className="title-card-go">{live?'Run live':'Run'} <Icon name="play" size={12}/></span></div>
    </div>
  </button>;
}

export default function TitleScreen({snapshot,connected,live,reports,busy,onStart,onReplay,onWatch,onResume,onOpen,onHome}:Props){
  // A live scene is the Unity Editor streaming now. Recorded frames played by the API do not count.
  const streaming=live&&!snapshot?.simulator.replay;
  const score=(id:string)=>reports?.benchmark?.scenarios.find(r=>r.scenario===id)?.pass_rate;
  const bench=reports?.benchmark?.summary;
  const groups:[string,string,'classic'|'messy'][]=[
    ['Classic demos','Clean runs that show each core idea on its own.','classic'],
    ['Messy lanes','Real-world clutter: occlusion, partial views, distractors, other shoppers.','messy']];
  return <div className="title-screen">
    <div className="title-backdrop" aria-hidden="true"><div className="title-lane"/></div>
    <header className="title-top">
      <button className="wordmark wordmark-link" onClick={onHome} title="About the project">Pro<span>Pass</span><small>VISION CHECKOUT LAB</small></button>
      <div className="title-status">
        <span className={`status-chip ${connected?'ok':''}`}><span className="dot"/>{connected?'API connected':'API offline'}</span>
        <span className={`status-chip ${live?'ok':''}`}><span className="dot"/>{streaming?'Scene streaming':live?'Playing recorded frames':'No scene streaming'}</span>
        <span className={`status-chip ${snapshot?.vision.ready?'ok':''}`}><span className="dot"/>{snapshot?.vision.ready?'Models ready':'Models load on first frame'}</span>
      </div>
    </header>
    <section className="title-hero">
      <div className="eyebrow">SYNTHETIC CHECKOUT LANE · REAL TRAINED MODELS</div>
      <h1>Pick a scenario.<br/><span>Watch every item get counted.</span></h1>
      <p>Unity renders the lane, a YOLO detector and an EfficientNet classifier read the pixels, and a physical-object ledger builds the cart. Every decision can be inspected.</p>
      <div className="title-actions">
        <button className="primary-button" onClick={()=>onWatch('single')}><Icon name="play" size={17}/> Watch the recorded tour <span className="muted">· 17 scenes, no setup</span></button>
        {snapshot&&live&&<button className="secondary-button" onClick={onResume}><Icon name="camera" size={17}/> Resume live lane <span className="muted">· {scenarioName(snapshot.simulator.scenario)}</span></button>}
        <button className="secondary-button" onClick={()=>onOpen('benchmark')}><Icon name="chart" size={16}/> Benchmark{bench?` · ${bench.passed}/${bench.runs} runs pass`:''}</button>
        <button className="secondary-button" onClick={()=>onOpen('models')}><Icon name="chip" size={16}/> Models</button>
        <button className="secondary-button" onClick={()=>onOpen('training')}><Icon name="pulse" size={16}/> Training</button>
      </div>
      {!streaming&&<p className="title-hint"><Icon name="alert" size={14}/> No scene is rendering right now, and none is needed: each card plays the frames Unity <b>already rendered</b> through the trained models at full speed, with the live cart, decisions and checkout. Without the API it plays the recorded tour instead. To render fresh frames, press <b>Play</b> on <code>Checkout.unity</code> in Unity.</p>}
    </section>
    {groups.map(([title,blurb,group])=><section className="title-group" key={group}>
      <div className="title-group-head"><h2>{title}</h2><p>{blurb}</p></div>
      <div className={`title-grid ${group}`}>{scenarios.filter(s=>s.group===group).map(s=><Card key={s.id} s={s} index={scenarios.indexOf(s)} score={score(s.id)}
        active={live&&snapshot?.simulator.scenario===s.id} disabled={!!busy} live={streaming} onStart={()=>streaming?onStart(s.id):connected?onReplay(s.id):onWatch(s.id)}/>)}</div>
    </section>)}
    <footer className="title-foot">Independent portfolio project · fictional products and prices · no payment · synthetic data only</footer>
  </div>;
}
