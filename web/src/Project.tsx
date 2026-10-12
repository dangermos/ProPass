import { useEffect, useRef, useState } from 'react';
import { scenarios } from './scenarios';
import { Icon } from './ui';

// The project's front page. Everything here is static: numbers are copied from the reports in
// models/ (benchmark-v3-test.json, benchmark-v2-test*.json, manifest.json) and must be updated with them.
// auto: closed with no person and exactly right. held: unknown-product and locked-tool runs, which are right only when handed off.
// extra: handed to an associate although the cart could have closed. short: closed automatically with an item missing.
const rounds=[
  {name:'Round 1: capsule people',scene:'Boxes carried by hand · seeds 5–9',auto:68,held:10,extra:6,short:1},
  {name:'Round 2: animated characters',scene:'Boxes carried by hand · seeds 5–9, scored a second time',auto:61,held:10,extra:14,short:0},
  {name:'Round 3: carts',scene:'Shopping, flat and lumber carts · fresh seeds 10–14, scored once',auto:50,held:10,extra:25,short:0,current:true},
];
const heldOut:Record<string,number>={single:4,duplicate:5,mixed:5,occlusion:5,remove:5,unknown:5,hands:2,shopper:2,flatbed:3,edge:4,stacked:0,distractors:3,bystander:5,hesitate:2,parked:3,locked:5,lumber:2};
const angleScenes=[
  {id:'mixed',name:'Mixed cart',note:'Three products on a flat cart. Two are settled by barcode, the middle one by look.'},
  {id:'lumber',name:'Lumber',note:'Boards carry no barcode, so they are recognized by look alone.'},
  {id:'parked',name:'Parked flatbed',note:'A flatbed hides the cart from the gate camera for seconds. The overhead camera keeps it.'},
  {id:'locked',name:'Locked-cage tool',note:'A restricted item is identified, then held for an associate by design.'},
];
const cameras=[
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
  // The gate camera leads; the other two are pulled back in step if they drift.
  const sync=()=>{const lead=videos.current.lane;if(!lead)return;all().forEach(v=>{if(v!==lead&&Math.abs(v.currentTime-lead.currentTime)>.25)v.currentTime=lead.currentTime;});};
  const restart=()=>{all().forEach(v=>{v.currentTime=0;});if(!playing)toggle();};
  return <div className="angles">
    <div className="angle-tabs">{angleScenes.map(s=><button key={s.id} className={s.id===scene.id?'on':''} onClick={()=>{setScene(s);setPlaying(false);}}>{s.name}</button>)}
      <span className="angle-spacer"/><button className="angle-play" onClick={toggle}><Icon name={playing?'pause':'play'} size={14}/> {playing?'Pause':'Play all three'}</button>
      <button onClick={restart}><Icon name="reset" size={14}/> Restart</button></div>
    <div className="angle-grid">{cameras.map(c=><figure key={c.id+scene.id} className={`angle ${c.id}`}>
      <video ref={el=>{videos.current[c.id]=el;}} src={`/angles/${scene.id}-${c.id}.webm`} muted playsInline loop preload="metadata" poster={c.id==='lane'?`/scenarios/${scene.id}.jpg`:undefined}
        onTimeUpdate={c.id==='lane'?sync:undefined} onClick={toggle} aria-label={`${c.name}: ${c.role}`}/>
      <figcaption><b>{c.name}</b>{c.role}</figcaption></figure>)}</div>
    <p className="angle-note">{scene.note} The boxes and outlines are drawn by the system from pixels alone.</p>
  </div>;
}

export default function Project({onTour,onScenarios,onLab}:{onTour:(id:string)=>void;onScenarios:()=>void;onLab:(tab:string)=>void}){
  // How each recorded tour run ended, shown on its card so the result is visible before pressing play.
  const [ends,setEnds]=useState<Record<string,string>>({});
  useEffect(()=>{scenarios.forEach(s=>{fetch(`/tour/${s.id}.json`).then(r=>r.ok?r.json():Promise.reject()).then(run=>setEnds(e=>({...e,[s.id]:run.passed?(run.expected_review?'held':'pass'):run.review_required?'assist':'fail'}))).catch(()=>{});});},[]);
  const endText:Record<string,string>={pass:'Closed correctly',held:'Correctly held',assist:'Sent to associate',fail:'Wrong cart'};
  return <div className="project">
    <nav className="project-nav"><div className="wordmark">Pro<span>Pass</span><small>VISION CHECKOUT LAB</small></div>
      <div className="project-links"><a href="#results">Results</a><a href="#how">How it works</a><a href="#cameras">Cameras</a><a href="#scenes">Scenes</a><a href="#limits">Limits</a>
        <button className="secondary-button" onClick={onScenarios}>Open the lab</button></div></nav>

    <header className="project-hero">
      <div><div className="eyebrow">COMPUTER VISION PROJECT · SIMULATED STORE LANE · TRAINED MODELS</div>
        <h1>The cart counts itself.<br/><span>And knows when to ask for help.</span></h1>
        <p>A contractor pushes a cart down the lane. Three cameras watch. Trained models find every box, read its barcode or recognize it by look, and build the cart with a reason for every line. When the system is not sure, it hands the cart to an associate instead of guessing.</p>
        <div className="title-actions"><button className="primary-button" onClick={()=>onTour('single')}><Icon name="play" size={17}/> Watch the 17 scenes</button>
          <a className="secondary-button" href="#results"><Icon name="chart" size={16}/> See the measured results</a></div></div>
      <video className="hero-video" src="/angles/mixed-lane.webm" autoPlay muted loop playsInline onClick={()=>onTour('mixed')} title="Open this scene in the tour" aria-label="A customer pushes a flat cart with three boxes down the lane; the system outlines and names each box and adds it to the cart" tabIndex={0} onKeyDown={e=>{if(e.key==='Enter')onTour('mixed');}}/>
    </header>

    <p className="byline">Independent student project by <b>Danny</b> (<a href="https://github.com/dangermos">github.com/dangermos</a>). Not affiliated with or endorsed by The Home Depot. Everything shown is a simulation: fictional prices, no payment, no real store or camera.</p>

    <section className="why">
      {[['The problem','A contractor with a loaded cart waits in line while every box is found, turned and scanned by hand.'],
        ['The idea','Cameras over the lane ring the cart up as it rolls through. The customer keeps walking.'],
        ['The safeguard','When the system is not sure, it never guesses. It keeps what it scanned and calls an associate for the rest.']]
        .map(([name,text])=><div key={name}><h3>{name}</h3><p>{text}</p></div>)}
    </section>

    <section className="project-stats">
      {[['50 of 85','carts closed with no one stepping in, exactly right','hardest scene (carts), runs never tuned on'],
        ['10 of 10','carts that needed a person were sent to one','unknown product and locked-cage tool'],
        ['0 of 85','carts closed with a wrong or missing item','cart round; with 85 runs the true rate could be up to about 3.5%'],
        ['25','carts sent to an associate that did not need to be','the open work: 15 of them had an item the cameras lost'],
        ['36 ms','to process one moment from all cameras','median, models only, recorded frames, RTX 4070 Super']]
        .map(([value,label,note])=><div key={label}><strong>{value}</strong><span>{label}</span><small>{note}</small></div>)}
    </section>

    <section id="results" className="project-section">
      <div className="section-head"><div className="eyebrow">MEASURED, NOT CLAIMED</div><h2>Results on runs set aside for testing</h2>
        <p>17 scenarios × 5 random variations (seeds) = 85 recorded runs per round. Settings are tuned on separate development runs only. Each round made the scene harder, and the models were retrained for it. Only round 3 used test runs that had never been scored before; rounds 1 and 2 shared theirs.</p></div>
      <div className="rounds">{rounds.map(r=><div key={r.name} className={`round ${r.current?'current':''}`}>
        <div className="round-head"><h3>{r.name}</h3>{r.current&&<span className="pill verified">current scene</span>}</div><small>{r.scene}</small>
        <div className="round-bar" role="img" aria-label={`${r.auto} closed automatically, ${r.held} correctly handed off, ${r.extra} handed off unnecessarily, ${r.short} closed with an item missing`}>
          <span className="auto" style={{width:`${r.auto/85*100}%`}}/><span className="held" style={{width:`${r.held/85*100}%`}}/><span className="extra" style={{width:`${r.extra/85*100}%`}}/><span className="short" style={{width:`${r.short/85*100}%`}}/></div>
        <div className="round-numbers"><div><strong>{r.auto}</strong><span>closed automatically, exactly right</span></div><div><strong className="held">{r.held}</strong><span>correctly sent to an associate</span></div>
          <div><strong className="extra">{r.extra}</strong><span>sent to an associate unnecessarily</span></div><div><strong className={r.short?'short':'zero'}>{r.short}</strong><span>closed with a wrong or missing item</span></div></div></div>)}</div>
      <p className="fine"><b>How to read this.</b> A run passes when the cart is exactly right and an associate is called only when one should be, so each round passed 78, 71 and 60 of 85. No cart in any of these rounds was charged for something the customer did not have. One cart in round 1 closed a lumber board short. In round 3, 15 of the 25 unnecessary hand-offs had an incomplete cart (16 items the cameras lost, most often because the item left view before the checkout line), and two held one wrong line. With 5 runs per scenario, read the per-scene scores below as signals, not rates. On development runs the same system scored 68 of 85.</p>
      <div className="by-scene"><h3>Round 3 by scene, test seeds 10–14: runs handled correctly out of 5</h3>
        <div className="by-scene-grid">{scenarios.map(s=><button key={s.id} onClick={()=>onTour(s.id)} title="Watch a recorded run"><span>{s.name}</span>
          <div className="dots">{[0,1,2,3,4].map(i=><i key={i} style={{background:i<heldOut[s.id]?rate(heldOut[s.id]):'#1c2a3c'}}/>)}</div><b style={{color:rate(heldOut[s.id])}}>{heldOut[s.id]}/5</b></button>)}</div></div>
      <div className="story-grid">
        <article><div className="eyebrow">A BUG THE DEVELOPMENT SET CAUGHT</div><h3>The barcode that landed on the wrong box</h3>
          <p>With carts, nine development runs were charged the wrong product. The cause: a label on a low cart sits below the calibration plane, so it projects toward the barcode camera and lands on the neighboring box. Giving each label to the first box behind it took development runs from 56 to 68 of 85 with nothing wrongly charged. The held-out set was scored once, after the fix.</p></article>
        <article><div className="eyebrow">MODELS</div><h3>Small models, one pair per camera</h3>
          <p>Detector: YOLO26n, 2,000 training scenes (2,640 rendered, the rest for validation and test). Test mAP50 0.955 and mAP50-95 0.776 on the gate camera, 0.972 and 0.840 overhead. Classifier: EfficientNet-B0 over 8 products plus an unknown class, 94% on test crops (346 of 367 and 410 of 435). One shared pair for both views scored far worse, so each camera has its own. Model hashes are stored with every benchmark report.</p></article>
      </div>
    </section>

    <section id="how" className="project-section">
      <div className="section-head"><div className="eyebrow">HOW IT WORKS</div><h2>The system only gets pictures</h2>
        <p>A game engine (Unity) renders the store, but it never tells the vision system what is in the cart. Each camera sends a plain image with a timestamp. Everything after that is worked out from the pixels, the way it would have to be in a real store.</p></div>
      <div className="flow">{[['camera','See','A small object detector (YOLO26n, three classes: merchandise, person, cart) finds every box in the gate and overhead views. A tracker (BoT-SORT) follows each one from frame to frame.'],
        ['eye','Identify','A third camera reads the barcode label on each box. Where no label is visible, an image classifier (EfficientNet-B0) recognizes which of the 8 catalog products it is, or says it does not know.'],
        ['grid','Fuse','Each camera is calibrated to the lane floor plan (a homography on a plane at cart-load height), so the same box seen by two cameras is one object, and a box hidden from one camera is not lost.'],
        ['list','Decide','Every physical item gets one identity. It is added to the cart when it crosses the checkout line, removed if it comes back, and given a rating for how sure the system is.'],
        ['user','Hand off','Unknown products, restricted tools and anything unsettled go to an associate. The part of the cart that was scanned is kept.']]
        .map(([icon,name,text],i)=><div className="flow-step" key={name}><span className="flow-number">{i+1}</span><Icon name={icon} size={22}/><h3>{name}</h3><p>{text}</p></div>)}</div>
      <div className="ratings"><h3>Every cart line carries a rating</h3>
        <div><span className="pill verified">Verified</span>barcode read twice or more</div><div><span className="pill high">High</span>one barcode read</div>
        <div><span className="pill look">Recognized by look</span>classifier only, above its threshold</div><div><span className="pill ask">Associate</span>not settled, restricted or unknown</div></div>
    </section>

    <section id="cameras" className="project-section">
      <div className="section-head"><div className="eyebrow">ONE MOMENT, THREE ANGLES</div><h2>What each camera sees</h2>
        <p>The same run from every camera, played in step. Pick a scene and press play.</p></div>
      <Angles/>
    </section>

    <section id="scenes" className="project-section">
      <div className="section-head"><div className="eyebrow">17 SCENES</div><h2>Watch any run, with the decisions beside it</h2>
        <p>Each card plays a recorded run from all three cameras: the boxes the system drew, the cart it built, and what it did at each second. They are development seed 2 of every scenario, pass or not, so they are examples and not the test runs scored above.</p></div>
      <div className="scene-grid">{scenarios.map((s,i)=><button key={s.id} className="scene" onClick={()=>onTour(s.id)} style={{backgroundImage:`linear-gradient(180deg,transparent 25%,#0b1320f2 78%),url(/scenarios/${s.id}.jpg)`}}>
        <span className="title-card-number">{String(i+1).padStart(2,'0')}</span>{ends[s.id]&&<span className={`end-chip ${ends[s.id]}`}>{endText[ends[s.id]]}</span>}<strong>{s.name}</strong><small>{s.detail}</small></button>)}</div>
    </section>

    <section id="limits" className="project-section">
      <div className="section-head"><div className="eyebrow">WHAT IT DOES NOT DO YET</div><h2>Honest limits</h2></div>
      <div className="limits">{[['Synthetic only','Every number here comes from Unity renders. Nothing has been tested on a real camera.'],
        ['Stacked boxes fail','Two boxes pressed together on a cart read as one from both cameras: 0 of 5 test runs. The second box is not charged; the cart is sent to an associate.'],
        ['Carts hide labels','A box behind another box is not scanned. Barcodes settle 65% of charged items with carts, down from 82% without.'],
        ['Automation fell with realism','68, then 61, then 50 of 85 carts closed on their own as people and carts were added. Sending 4 carts in 10 to an associate would not work in a store; cutting the 25 unnecessary hand-offs is the open work.'],
        ['Small test','85 runs per round and 8 products. Enough to find failures, not enough to promise a rate.'],
        ['Next step to make it real','Point one real camera at one real cart with these 8 boxes, and measure what breaks first: detection, barcode reading under motion blur, or calibration.']]
        .map(([name,text])=><div key={name}><h3>{name}</h3><p>{text}</p></div>)}</div>
    </section>

    <section className="project-section">
      <div className="section-head"><div className="eyebrow">BUILT WITH</div><h2>Stack and how to run it</h2></div>
      <div className="stack">{['Unity 6.6 · URP','PyTorch','YOLO26n','EfficientNet-B0','BoT-SORT','zxing-cpp','FastAPI','React + Vite','pytest'].map(t=><span key={t}>{t}</span>)}</div>
      <pre className="code">{`git clone https://github.com/dangermos/ProPass && cd ProPass/web   # private for now: ask for access
npm ci && npm run dev        # this site and the recorded tour: no GPU, no Unity

bash scripts/get_weights.sh     # trained weights
bash scripts/get_recordings.sh  # frames Unity already rendered, one run per scene
bash scripts/start.sh           # API + dashboard: any scene runs live through the models, no Unity`}</pre>
      <div className="title-actions"><button className="primary-button" onClick={()=>onTour('single')}><Icon name="play" size={17}/> Start the tour</button>
        <button className="secondary-button" onClick={onScenarios}><Icon name="camera" size={16}/> Live lab</button>
        <button className="secondary-button" onClick={()=>onLab('benchmark')}><Icon name="chart" size={16}/> Full benchmark</button></div>
    </section>
    <footer className="title-foot">Independent student project by Danny (github.com/dangermos), inspired by contractor checkout. Not affiliated with or endorsed by The Home Depot. Fictional prices, no payment, simulated data only.</footer>
  </div>;
}
