import { useEffect, useRef, useState } from 'react';
import { scenarios } from './scenarios';
import { Icon } from './ui';
import { asset } from './assets';
import { endingOf } from './tourRun';
import { precaution, type Split } from './results';

// The project's front page. Measured numbers come from /results.json, which scripts/publish_results.py writes
// from the reports in models/, so the page cannot drift from the data. The earlier rounds below are history.
// auto: closed with no person and exactly right. held: unknown-product and locked-tool runs, right only when handed off.
// extra: handed to an associate as a precaution although it was not one of the by-design cases. wrong: closed automatically with a wrong or missing item.
type Net={map50:number;map50_95:number;accuracy:number;crops:number;train_scenes:number|null};
type Results={dev:Split;test:Split;models:{lane:Net;overhead:Net};tests:number|null;products:number};
const earlier=[
  {name:'Capsule people, hand-carried boxes',passed:78,auto:68,extra:6,wrong:1},
  {name:'Animated characters, hand-carried boxes',passed:71,auto:61,extra:14,wrong:0},
  {name:'Carts, plain store',passed:60,auto:50,extra:25,wrong:0},
];
const angleScenes=[
  {id:'mixed',name:'Mixed cart',note:'Three products on a flat cart. Two are settled by barcode, the middle one by look.'},
  {id:'lumber',name:'Lumber',note:'Boards carry no barcode, so they are recognized by look alone.'},
  {id:'parked',name:'Parked flatbed',note:'A flatbed hides the cart from the gate camera for seconds. The overhead camera keeps it.'},
  {id:'locked',name:'Locked-cage tool',note:'A restricted item is identified, then held for an associate by design.'},
];
const cameras=[
  {id:'show',name:'Follow camera',role:'For viewers only: a close look at the cart and the customer. The system never sees this view.'},
  {id:'lane',name:'Gate camera',role:'Detects, tracks and identifies every box as the cart rolls toward it.'},
  {id:'overhead',name:'Overhead camera',role:'A second angle that keeps an item alive when something blocks the gate view.'},
  {id:'scan',name:'Barcode camera',role:'High resolution, facing the oncoming cart, to read the label on each box. Shown here: the middle of its view.'},
];
const rate=(v:number)=>v>=4?'#2ea043':v>=3?'#d29922':'#f85149';

function Angles(){
  const [scene,setScene]=useState(angleScenes[0]);
  const [playing,setPlaying]=useState(false);
  const videos=useRef<Record<string,HTMLVideoElement|null>>({});
  const all=()=>Object.values(videos.current).filter((v):v is HTMLVideoElement=>!!v);
  const toggle=()=>{const next=!playing;setPlaying(next);all().forEach(v=>{if(next)void v.play();else v.pause();});};
  // The gate camera leads; the others are pulled back in step if they drift.
  const sync=()=>{const lead=videos.current.lane;if(!lead)return;all().forEach(v=>{if(v!==lead&&Math.abs(v.currentTime-lead.currentTime)>.25)v.currentTime=lead.currentTime;});};
  const restart=()=>{all().forEach(v=>{v.currentTime=0;});if(!playing)toggle();};
  return <div className="angles">
    <div className="angle-tabs">{angleScenes.map(s=><button key={s.id} className={s.id===scene.id?'on':''} onClick={()=>{setScene(s);setPlaying(false);}}>{s.name}</button>)}
      <span className="angle-spacer"/><button className="angle-play" onClick={toggle}><Icon name={playing?'pause':'play'} size={14}/> {playing?'Pause':'Play all four'}</button>
      <button onClick={restart}><Icon name="reset" size={14}/> Restart</button></div>
    <div className="angle-grid">{cameras.map(c=><figure key={c.id+scene.id} className={`angle ${c.id}`}>
      <video ref={el=>{videos.current[c.id]=el;}} src={asset(`angles/${scene.id}-${c.id}.webm`)} muted playsInline loop preload="metadata" 
        onTimeUpdate={c.id==='lane'?sync:undefined} onClick={toggle} aria-label={`${c.name}: ${c.role}`}/>
      <figcaption><b>{c.name}</b>{c.role}</figcaption></figure>)}</div>
    <p className="angle-note">{scene.note} The boxes and outlines are drawn by the system from pixels alone.</p>
  </div>;
}

export default function Project({onTour,onScenarios,onLab}:{onTour:(id:string)=>void;onScenarios:()=>void;onLab:(tab:string)=>void}){
  // How each recorded tour run ended, shown on its card so the result is visible before pressing play.
  const [res,setRes]=useState<Results|null>(null);
  useEffect(()=>{fetch(asset('results.json')).then(r=>r.ok?r.json():Promise.reject()).then(setRes).catch(()=>{});},[]);
  const t=res?.test,d=res?.dev;
  const [ends,setEnds]=useState<Record<string,string>>({});
  useEffect(()=>{scenarios.forEach(s=>{fetch(asset(`tour/${s.id}.json`)).then(r=>r.ok?r.json():Promise.reject()).then(run=>setEnds(e=>({...e,[s.id]:endingOf(run)}))).catch(()=>{});});},[]);
  const endText:Record<string,string>={pass:'Closed correctly',held:'Correctly held',assist:'Sent to associate',fail:'Wrong cart'};
  return <div className="project">
    <nav className="project-nav"><div className="wordmark">Pro<span>Pass</span><small>VISION CHECKOUT LAB</small></div>
      <div className="project-links"><a href="#results">Results</a><a href="#how">How it works</a><a href="#cameras">Cameras</a><a href="#scenes">Scenes</a><a href="#limits">Limits</a>
        <button className="secondary-button" onClick={onScenarios}>Open the lab</button></div></nav>

    <header className="project-hero">
      <div><div className="eyebrow">COMPUTER VISION PROJECT · SIMULATED STORE LANE · TRAINED MODELS</div>
        <h1>The lane rings up the cart.<br/><span>When it isn't sure, it calls an associate.</span></h1>
        <p>I built a simulated store lane where a contractor pushes a cart past three cameras. Models I trained find each box, read its barcode or recognize it by look, and add it to the cart with a reason for every line. When the lane isn't sure about an item, it hands the cart to an associate instead of guessing.</p>
        <div className="title-actions"><button className="primary-button" onClick={()=>onTour('single')}><Icon name="play" size={17}/> Watch the 17 scenes</button>
          <a className="secondary-button" href="#results"><Icon name="chart" size={16}/> See the measured results</a></div></div>
      <video className="hero-video" src={asset('angles/mixed-show.webm')} autoPlay muted loop playsInline onClick={()=>onTour('mixed')} title="Open this scene in the tour" aria-label="A customer pushes a flat cart with three boxes down a store checkout lane" tabIndex={0} onKeyDown={e=>{if(e.key==='Enter')onTour('mixed');}}/>
    </header>

    <p className="byline">Built by <b>Danny Germosen</b>, SUNY Oswego (<a href="https://github.com/dangermos">github.com/dangermos</a>), as an independent student project. Not affiliated with or endorsed by The Home Depot. Everything shown is a simulation: fictional prices, no payment, no real store or camera.</p>

    <section className="why">
      {[['The problem','A contractor with a loaded cart waits in line while every box is found, turned and scanned by hand.'],
        ['The idea','Cameras over the lane ring up the cart as it rolls through, so the customer doesn\'t have to stop.'],
        ['The safeguard','If the lane isn\'t sure about an item, it doesn\'t guess. It keeps what it scanned and calls an associate for the rest.']]
        .map(([name,text])=><div key={name}><h3>{name}</h3><p>{text}</p></div>)}
    </section>

    <section className="project-stats">
      {(t?[[`${t.auto} of ${t.runs}`,'carts closed with no one stepping in, exactly right','current scene, runs never tuned on'],
        [`${t.held} of ${t.held}`,'carts that needed a person were sent to one','unknown product and locked-cage tool'],
        [`${t.wrong} of ${t.runs}`,'carts closed with a wrong or missing item',`with ${t.runs} runs the true rate could still be up to about 3.5%`],
        [`${t.extra} of ${t.runs}`,'carts sent to an associate as a precaution, in scenes the lane could have closed',`${t.extra-t.extra_incomplete} were already right; the other ${t.extra_incomplete} would have closed short or over`],
        ['36 ms','to process one moment from all cameras','median, models only, recorded frames, RTX 4070 Super; measured on the previous 8-product round']]:[])
        .map(([value,label,note])=><div key={label}><strong>{value}</strong><span>{label}</span><small>{note}</small></div>)}
    </section>

    <section id="results" className="project-section">
      <div className="section-head"><div className="eyebrow">RESULTS</div><h2>Results on runs set aside for testing</h2>
        <p>17 scenarios × 5 random variations (seeds) = 85 recorded runs. Settings are tuned on development runs only. The held-out runs were recorded after tuning was finished and scored once.</p></div>
      {t&&d&&<><div className="rounds">{([['Held-out runs',`Seeds ${t.seeds[0]}–${t.seeds[t.seeds.length-1]} · never tuned on · scored once`,t,true],['Development runs',`Seeds ${d.seeds[0]}–${d.seeds[d.seeds.length-1]} · the runs settings were tuned on`,d,false]] as [string,string,Split,boolean][]).map(([name,note,r,current])=><div key={name} className={`round ${current?'current':''}`}>
        <div className="round-head"><h3>{name}</h3>{current&&<span className="pill verified">the number that counts</span>}</div><small>{note}</small>
        <div className="round-bar" role="img" aria-label={`${r.auto} closed automatically, ${r.held} correctly handed off, ${r.extra} sent to an associate as a precaution, ${r.wrong} closed wrong`}>
          <span className="auto" style={{width:`${r.auto/r.runs*100}%`}}/><span className="held" style={{width:`${r.held/r.runs*100}%`}}/><span className="extra" style={{width:`${r.extra/r.runs*100}%`}}/><span className="short" style={{width:`${r.wrong/r.runs*100}%`}}/></div>
        <div className="round-numbers"><div><strong>{r.auto}</strong><span>closed automatically, exactly right</span></div><div><strong className="held">{r.held}</strong><span>correctly sent to an associate</span></div>
          <div><strong className="extra">{r.extra}</strong><span>sent to an associate as a precaution</span></div><div><strong className={r.wrong?'short':'zero'}>{r.wrong}</strong><span>closed with a wrong or missing item</span></div></div></div>)}</div>
      <p className="fine"><b>How to read this.</b> A run passes when the cart is exactly right and an associate is called only when one should be: {t.passed} of {t.runs} held-out runs passed. The {t.by_design??t.held} carts built to need a person (unknown product, locked tool) all went to one. In the other {t.runs-(t.by_design??t.held)}, the lane closed {t.auto} on its own and sent {t.extra} to an associate rather than guess. {precaution(t)} The most common reason was: {(t.top_reasons[0]?.[0]??'').toLowerCase()}. With 5 runs per scenario, read the per-scene scores below as signals, not rates.</p>
      <div className="by-scene"><h3>By scene, held-out runs handled correctly out of 5</h3>
        <div className="by-scene-grid">{scenarios.map(s=><button key={s.id} onClick={()=>onTour(s.id)} title="Watch a recorded run"><span>{s.name}</span>
          <div className="dots">{[0,1,2,3,4].map(i=><i key={i} style={{background:i<(t.scenes[s.id]??0)?rate(t.scenes[s.id]??0):'#1c2a3c'}}/>)}</div><b style={{color:rate(t.scenes[s.id]??0)}}>{t.scenes[s.id]??0}/5</b></button>)}</div></div></>}
      <p className="fine"><b>Earlier rounds</b> used 8 products and simpler scenes, each on its own 85 test runs: {earlier.map(e=>`${e.name}: ${e.passed} passed, ${e.auto} automatic, ${e.extra} precautionary hand-offs, ${e.wrong} closed wrong`).join('. ')}. The one wrong close was a lumber cart that closed a board short.</p>
      <div className="story-grid">
        <article><div className="eyebrow">A BUG THE DEVELOPMENT SET CAUGHT</div><h3>The barcode that landed on the wrong box</h3>
          <p>In an earlier round, nine development runs were charged the wrong product. The cause: a label on a low cart sits below the calibration plane, so it projects toward the barcode camera and lands on the neighboring box. Giving each label to the first box behind it took development runs from 56 to 68 of 85 with nothing wrongly charged. The held-out set was scored once, after the fix.</p></article>
        <article><div className="eyebrow">MODELS</div><h3>Small models, one pair per camera</h3>
          <p>{res?`Detector: YOLO26n, ${res.models.lane.train_scenes??''} training scenes per camera. Test mAP50-95 ${res.models.lane.map50_95} on the gate camera and ${res.models.overhead.map50_95} overhead. Classifier: EfficientNet-B0 over ${res.products} products plus an unknown class, ${(res.models.lane.accuracy*100).toFixed(1)}% and ${(res.models.overhead.accuracy*100).toFixed(1)}% on test crops. `:''}I first tried one shared pair for both views. It scored far worse, so each camera has its own. Model hashes are stored with every benchmark report.</p></article>
      </div>
    </section>

    <section id="how" className="project-section">
      <div className="section-head"><div className="eyebrow">HOW IT WORKS</div><h2>The system only gets pictures</h2>
        <p>A game engine (Unity) renders the store, but it never tells the vision system what is in the cart. Each camera sends a plain image with a timestamp. Everything after that is worked out from the pixels, the way it would have to be in a real store.</p></div>
      <div className="flow">{[['camera','See','A small object detector (YOLO26n, three classes: merchandise, person, cart) finds every box in the gate and overhead views. A tracker (BoT-SORT) follows each one from frame to frame.'],
        ['eye','Identify','A third camera reads the barcode label on each box. Where no label is visible, an image classifier (EfficientNet-B0) recognizes which of the 15 catalog products it is, or says it does not know.'],
        ['grid','Fuse','Each camera is calibrated to the lane floor plan (a homography on a plane at cart-load height), so the same box seen by two cameras is one object, and a box hidden from one camera is not lost.'],
        ['list','Decide','Every physical item gets one identity. It is added to the cart when it crosses the checkout line, removed if it comes back, and given a rating for how sure the system is.'],
        ['user','Hand off','Unknown products, restricted tools and anything unsettled go to an associate. The part of the cart that was scanned is kept.']]
        .map(([icon,name,text],i)=><div className="flow-step" key={name}><span className="flow-number">{i+1}</span><Icon name={icon} size={22}/><h3>{name}</h3><p>{text}</p></div>)}</div>
      <div className="ratings"><h3>Every cart line carries a rating</h3>
        <div><span className="pill verified">Verified</span>barcode read twice or more</div><div><span className="pill high">High</span>one barcode read</div>
        <div><span className="pill look">Recognized by look</span>classifier only, above its threshold</div><div><span className="pill ask">Associate</span>not settled, restricted or unknown</div></div>
    </section>

    <section id="cameras" className="project-section">
      <div className="section-head"><div className="eyebrow">ONE MOMENT, EVERY ANGLE</div><h2>What each camera sees</h2>
        <p>The same run from every camera, played in step. Pick a scene and press play. Three cameras feed the system. The fourth is only for viewers.</p></div>
      <Angles/>
    </section>

    <section id="scenes" className="project-section">
      <div className="section-head"><div className="eyebrow">17 SCENES</div><h2>Watch any run, with the decisions beside it</h2>
        <p>Each card plays a recorded run from all three cameras: the boxes the system drew, the cart it built, and what it did at each second. They are development seed 2 of every scenario, pass or not, so they are examples and not the test runs scored above.</p></div>
      <div className="scene-grid">{scenarios.map((s,i)=><button key={s.id} className="scene" onClick={()=>onTour(s.id)} style={{backgroundImage:`linear-gradient(180deg,transparent 25%,#0b1320f2 78%),url(${asset(`scenarios/${s.id}.jpg`)})`}}>
        <span className="title-card-number">{String(i+1).padStart(2,'0')}</span>{ends[s.id]&&<span className={`end-chip ${ends[s.id]}`}>{endText[ends[s.id]]}</span>}<strong>{s.name}</strong><small>{s.detail}</small></button>)}</div>
    </section>

    <section id="limits" className="project-section">
      <div className="section-head"><div className="eyebrow">WHAT IT DOES NOT DO YET</div><h2>Limits</h2></div>
      <div className="limits">{[['Synthetic only','Every number here comes from Unity renders. Nothing has been tested on a real camera.'],
        ['Touching packages are hard',t?`Two packages stacked or pressed together can read as one: ${t.scenes.stacked??0} of 5 held-out runs handled correctly. The cart goes to an associate rather than being charged short.`:'Two packages stacked or pressed together can read as one.'],
        ['Carts hide labels',t?`A package behind another package is not scanned. Barcodes settled ${t.barcode} of ${t.charged} charged items; the rest were recognized by look.`:'A package behind another package is not scanned and falls back to recognition by look.'],
        ['Cautious hand-offs',t?`${t.extra} of ${t.runs} held-out carts went to an associate as a precaution, in scenes the lane could have closed, and ${t.extra-t.extra_incomplete} of those were already right. A store would want fewer. Cutting that number without risking wrong charges is the main open problem.`:'Carts go to an associate as a precaution more often than a store would want. Cutting that without risking wrong charges is the main open problem.'],
        ['Small test','85 runs and 15 products. Enough to find failures, not enough to promise a rate.'],
        ['Next step to make it real','Point one real camera at one real cart with real packages, and measure what breaks first: detection, barcode reading under motion blur, or calibration.']]
        .map(([name,text])=><div key={name}><h3>{name}</h3><p>{text}</p></div>)}</div>
    </section>

    <section className="project-section">
      <div className="section-head"><div className="eyebrow">BUILT WITH</div><h2>Stack and how to run it</h2></div>
      <div className="stack">{['Unity 6.6 · URP','PyTorch','YOLO26n','EfficientNet-B0','BoT-SORT','zxing-cpp','FastAPI','React + Vite','pytest'].map(t=><span key={t}>{t}</span>)}</div>
      <pre className="code">{`git clone https://github.com/dangermos/ProPass && cd ProPass/web
npm ci && npm run dev        # this site and the recorded tour: no GPU, no Unity

bash scripts/get_weights.sh     # trained weights
bash scripts/get_recordings.sh  # frames Unity already rendered, one run per scene
bash scripts/start.sh           # API + dashboard: any scene runs live through the models, no Unity`}</pre>
      <div className="title-actions"><button className="primary-button" onClick={()=>onTour('single')}><Icon name="play" size={17}/> Start the tour</button>
        <button className="secondary-button" onClick={onScenarios}><Icon name="camera" size={16}/> Live lab</button>
        <button className="secondary-button" onClick={()=>onLab('benchmark')}><Icon name="chart" size={16}/> Full benchmark</button></div>
    </section>
    <footer className="title-foot">Independent student project by Danny Germosen, SUNY Oswego (github.com/dangermos), inspired by contractor checkout. Not affiliated with or endorsed by The Home Depot. Fictional prices, no payment, simulated data only.</footer>
  </div>;
}
