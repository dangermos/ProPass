import { useEffect, useRef, useState } from 'react';
import { scenarios } from './scenarios';
import { Icon } from './ui';
import { cue, moving, soundOff, soundOn } from './sound';
import { cartAt, outcomeOf, type Run } from './tourRun';
import { asset } from './assets';

// A recorded run and what the trained models decided, built by scripts/build_tour.py.
// Plays from static files in /tour: no API, GPU or Unity needed. #/tour/<scenario>/<seconds> opens paused at that moment.

const ratingText:Record<string,string>={verified:'Verified by barcode',high:'High: one barcode read',medium:'Recognized by look',low:'Low confidence',needs_associate:'Held for an associate'};

export default function Tour({id,onPick,onBack}:{id:string;onPick:(id:string)=>void;onBack:()=>void}){
  const [run,setRun]=useState<Run|null>(null);
  const [missing,setMissing]=useState(false);
  const [time,setTime]=useState(0);
  const [ended,setEnded]=useState(false);
  const video=useRef<HTMLVideoElement>(null);
  const [sound,setSound]=useState(()=>{try{return localStorage.getItem('propass-sound')==='on';}catch{return false;}});
  const heard=useRef(0);          // scene time up to which cues have been played
  const toggleSound=()=>{const next=!sound;setSound(next);try{localStorage.setItem('propass-sound',next?'on':'off');}catch{/* private mode */}
    if(next){soundOn();moving(!!video.current&&!video.current.paused);}else soundOff();};
  useEffect(()=>()=>{moving(false);},[]);
  // Follow the video closely (timeupdate alone fires only a few times a second) and play each decision's cue as it happens.
  useEffect(()=>{let frame=0;const tick=()=>{const v=video.current;
      if(v&&run){const t=v.currentTime;
        if(t<heard.current||t-heard.current>1)heard.current=t;      // a seek or a restart: do not replay or dump cues
        else{for(const n of run.notes)if(n.t>heard.current&&n.t<=t&&n.kind&&n.kind!=='identify')cue(n.kind);heard.current=t;}
        setTime(t);}
      frame=requestAnimationFrame(tick);};
    frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame);},[run]);
  const toast=run?.notes.filter(n=>n.kind&&n.kind!=='identify'&&n.t<=time&&time-n.t<1.8).pop();
  const index=Math.max(0,scenarios.findIndex(s=>s.id===id)),info=scenarios[index];
  useEffect(()=>{setRun(null);setMissing(false);setTime(0);setEnded(false);
    fetch(asset(`tour/${info.id}.json`)).then(r=>r.ok?r.json():Promise.reject()).then(setRun).catch(()=>setMissing(true));},[info.id]);
  const notes=run?.notes.filter(n=>ended||n.t<=time)??[];
  const lines=cartAt(run,time,ended);
  const outcome=outcomeOf(run);
  const move=(by:number)=>onPick(scenarios[(index+by+scenarios.length)%scenarios.length].id);
  return <div className="tour">
    <header className="tour-top">
      <button className="back-button" onClick={onBack}><Icon name="back" size={16}/> Scenarios</button>
      <div><span className="eyebrow">RECORDED RUN {String(index+1).padStart(2,'0')} OF {scenarios.length} · DEVELOPMENT SEED {run?.seed??2} · DECISIONS BY THE TRAINED MODELS</span><h1>{info.name}</h1></div>
      <div className="tour-nav"><button className={`back-button sound-toggle ${sound?'on':''}`} onClick={toggleSound} aria-pressed={sound} title="Lane ambience and a sound for each decision">{sound?'🔊 Sound on':'🔈 Sound off'}</button><button className="back-button" onClick={()=>move(-1)}>‹ Previous</button><button className="back-button" onClick={()=>move(1)}>Next ›</button></div>
    </header>
    <div className="tour-grid">
      <section className="tour-stage">
        <p className="tour-watch"><b>Watch for:</b> {info.detail.toLowerCase()}. This scene tests {info.tests.toLowerCase()}.</p>
        {missing?<div className="tab-empty">This scene has not been built yet. Run <code>.venv/bin/python scripts/build_tour.py</code>.</div>
          :<video ref={video} key={info.id} src={asset(`tour/${info.id}.webm`)} controls autoPlay muted playsInline
              onLoadedMetadata={e=>{const at=Number(location.hash.split('/')[3]);if(at>0){e.currentTarget.pause();e.currentTarget.currentTime=at;}}}
              onPlay={()=>{setEnded(false);if(sound){soundOn();moving(true);}}} onPause={()=>moving(false)}
              onEnded={()=>{setEnded(true);moving(false);if(run)cue(run.passed&&!run.review_required?'pass':'handoff');}}/>}
        {toast&&!missing&&<div className={`tour-toast ${toast.kind}`} key={toast.t+toast.text}>{toast.text}</div>}
        <p className="tour-caption">{run?.description}. Boxes are drawn by the system: <span className="k add">green</span> is in the cart, <span className="k see">blue</span> is tracked, <span className="k ask">orange</span> needs an associate.</p>
      </section>
      <aside className="tour-side">
        {outcome&&<div className={`tour-panel tour-outcome ${outcome.tone}`}><h2>How this run ends</h2>
          <strong>{outcome.title}</strong><p>{outcome.text}</p></div>}

        <div className="tour-panel"><h2>Cart the system built</h2>
          {lines.length?lines.map(l=><div className="tour-line" key={l.sku}><span className="qty">{l.quantity}×</span><div><strong>{l.name}</strong><small>{ratingText[l.rating??'']??(l.source==='barcode'?'Barcode':'Recognized by look')}</small></div></div>)
            :<p className="tour-empty">Nothing charged yet.</p>}
          {run&&<p className="tour-expected">Should be: {run.expected.length?run.expected.map(l=>`${l.quantity}× ${l.name}`).join(', '):'an empty cart'}</p>}
        </div>
        <div className="tour-panel"><h2>What it did</h2>
          {notes.length?<ol className="tour-notes">{notes.map((n,i)=><li key={i}><time>{n.t.toFixed(1)} s</time>{n.text}</li>)}</ol>:<p className="tour-empty">Watching the lane.</p>}
        </div>
              </aside>
    </div>
    <div className="tour-strip">{scenarios.map(s=><button key={s.id} className={s.id===info.id?'on':''} onClick={()=>onPick(s.id)} title={s.detail}
      style={{backgroundImage:`linear-gradient(180deg,transparent 30%,#0b1320ee),url(${asset(`scenarios/${s.id}.jpg`)})`}}>{s.name}</button>)}</div>
  </div>;
}
