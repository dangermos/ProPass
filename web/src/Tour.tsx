import { useEffect, useRef, useState } from 'react';
import { scenarios } from './scenarios';
import { Icon } from './ui';

// A recorded run and what the trained models decided, built by scripts/build_tour.py.
// Plays from static files in /tour: no API, GPU or Unity needed. #/tour/<scenario>/<seconds> opens paused at that moment.
type Line={sku:string;name:string;quantity:number;rating?:string|null;source?:string|null};
type Run={scenario:string;seed:number;description:string;duration:number;expected:Line[];exact_cart:boolean;
  review_required:boolean;expected_review:boolean;passed:boolean;steps:{t:number;lines:Line[]}[];notes:{t:number;text:string}[]};

const ratingText:Record<string,string>={verified:'Verified by barcode',high:'High: one barcode read',medium:'Recognized by look',low:'Low confidence',needs_associate:'Held for an associate'};

export default function Tour({id,onPick,onBack}:{id:string;onPick:(id:string)=>void;onBack:()=>void}){
  const [run,setRun]=useState<Run|null>(null);
  const [missing,setMissing]=useState(false);
  const [time,setTime]=useState(0);
  const [ended,setEnded]=useState(false);
  const video=useRef<HTMLVideoElement>(null);
  const index=Math.max(0,scenarios.findIndex(s=>s.id===id)),info=scenarios[index];
  useEffect(()=>{setRun(null);setMissing(false);setTime(0);setEnded(false);
    fetch(`/tour/${info.id}.json`).then(r=>r.ok?r.json():Promise.reject()).then(setRun).catch(()=>setMissing(true));},[info.id]);
  const step=run?.steps.filter(s=>s.t<=time).pop();
  const notes=run?.notes.filter(n=>ended||n.t<=time)??[];
  const lines=ended&&run?run.steps[run.steps.length-1]?.lines??[]:step?.lines??[];
  const outcome=!run?null:run.passed?{tone:'pass',title:run.expected_review?'Correctly held for an associate':'Closed automatically, exactly right',
      text:run.expected_review?'This scene is meant to need a person, and the system asked for one.':'Every item was counted once and identified. No one had to step in.'}
    :run.review_required?{tone:'assist',title:'Handed to an associate',text:run.exact_cart?'The cart was right, but the system was not sure enough to close it on its own.':'The system could not settle every item, so it kept what it had and asked for help instead of guessing.'}
    :{tone:'fail',title:'Closed with a wrong cart',text:'This run is a miss: the cart was closed without the right items.'};
  const move=(by:number)=>onPick(scenarios[(index+by+scenarios.length)%scenarios.length].id);
  return <div className="tour">
    <header className="tour-top">
      <button className="back-button" onClick={onBack}><Icon name="back" size={16}/> Scenarios</button>
      <div><span className="eyebrow">RECORDED RUN {String(index+1).padStart(2,'0')} OF {scenarios.length} · SEED {run?.seed??2} · REAL TRAINED MODELS</span><h1>{info.name}</h1></div>
      <div className="tour-nav"><button className="back-button" onClick={()=>move(-1)}>‹ Previous</button><button className="back-button" onClick={()=>move(1)}>Next ›</button></div>
    </header>
    <div className="tour-grid">
      <section className="tour-stage">
        {missing?<div className="tab-empty">This scene has not been built yet. Run <code>.venv/bin/python scripts/build_tour.py</code>.</div>
          :<video ref={video} key={info.id} src={`/tour/${info.id}.webm`} controls autoPlay muted playsInline
              onLoadedMetadata={e=>{const at=Number(location.hash.split('/')[3]);if(at>0){e.currentTarget.pause();e.currentTarget.currentTime=at;}}}
              onTimeUpdate={e=>{setTime(e.currentTarget.currentTime);setEnded(false);}} onEnded={()=>setEnded(true)}/>}
        <p className="tour-caption"><b>{info.detail}.</b> Tests: {info.tests.toLowerCase()}. {run?.description}. Boxes are drawn by the system: <span className="k add">green</span> is in the cart, <span className="k see">blue</span> is tracked, <span className="k ask">orange</span> needs an associate.</p>
      </section>
      <aside className="tour-side">
        <div className="tour-panel"><h2>Cart the system built</h2>
          {lines.length?lines.map(l=><div className="tour-line" key={l.sku}><span className="qty">{l.quantity}×</span><div><strong>{l.name}</strong><small>{ratingText[l.rating??'']??(l.source==='barcode'?'Barcode':'Recognized by look')}</small></div></div>)
            :<p className="tour-empty">Nothing charged yet.</p>}
          {run&&<p className="tour-expected">Should be: {run.expected.length?run.expected.map(l=>`${l.quantity}× ${l.name}`).join(', '):'an empty cart'}</p>}
        </div>
        <div className="tour-panel"><h2>What it did</h2>
          {notes.length?<ol className="tour-notes">{notes.map((n,i)=><li key={i}><time>{n.t.toFixed(1)} s</time>{n.text}</li>)}</ol>:<p className="tour-empty">Watching the lane.</p>}
        </div>
        {outcome&&<div className={`tour-panel tour-outcome ${ended?outcome.tone:'pending'}`}><h2>Outcome</h2>
          {ended?<><strong>{outcome.title}</strong><p>{outcome.text}</p></>:<p className="tour-empty">Shown when the run ends.</p>}</div>}
      </aside>
    </div>
    <div className="tour-strip">{scenarios.map(s=><button key={s.id} className={s.id===info.id?'on':''} onClick={()=>onPick(s.id)} title={s.detail}
      style={{backgroundImage:`linear-gradient(180deg,transparent 30%,#0b1320ee),url(/scenarios/${s.id}.jpg)`}}>{s.name}</button>)}</div>
  </div>;
}
