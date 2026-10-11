import { useRef, useState } from 'react';
import { scenarios } from './scenarios';
import { Icon } from './ui';

// The project's front page. Everything here is static: numbers are copied from the reports in
// models/ (benchmark-v3-test.json, benchmark-v2-test*.json, manifest.json) and must be updated with them.
const rounds=[
  {name:'Capsule people',scene:'Boxes carried by hand',passed:78,wrong:0},
  {name:'Animated characters',scene:'Boxes carried by hand',passed:71,wrong:0},
  {name:'Carts',scene:'Shopping, flat and lumber carts pushed by the customer',passed:60,wrong:0,current:true},
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
  {id:'scan',name:'Barcode camera',role:'A wide high-resolution strip that reads the store label on each box.'},
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
        onTimeUpdate={c.id==='lane'?sync:undefined} onClick={toggle}/>
      <figcaption><b>{c.name}</b>{c.role}</figcaption></figure>)}</div>
    <p className="angle-note">{scene.note} The boxes and outlines are drawn by the system from pixels alone.</p>
  </div>;
}

export default function Project({onTour,onScenarios,onLab}:{onTour:(id:string)=>void;onScenarios:()=>void;onLab:(tab:string)=>void}){
  return <div className="project">
    <nav className="project-nav"><div className="wordmark">Pro<span>Pass</span><small>VISION CHECKOUT LAB</small></div>
      <div className="project-links"><a href="#how">How it works</a><a href="#cameras">Cameras</a><a href="#results">Results</a><a href="#scenes">Scenes</a><a href="#limits">Limits</a>
        <button className="secondary-button" onClick={onScenarios}>Open the lab</button></div></nav>

    <header className="project-hero">
      <div><div className="eyebrow">COMPUTER VISION · SYNTHETIC CHECKOUT LANE · REAL TRAINED MODELS</div>
        <h1>The cart counts itself.<br/><span>And knows when to ask for help.</span></h1>
        <p>A contractor pushes a cart down the lane. Three cameras watch. Trained models find every box, read its barcode or recognize it by look, and build the cart with a reason for every line. When the system is not sure, it hands the cart to an associate instead of guessing.</p>
        <div className="title-actions"><button className="primary-button" onClick={()=>onTour('single')}><Icon name="play" size={17}/> Watch the 17 scenes</button>
          <a className="secondary-button" href="#results"><Icon name="chart" size={16}/> See the measured results</a></div></div>
      <video className="hero-video" src="/tour/mixed.webm" autoPlay muted loop playsInline onClick={()=>onTour('mixed')} title="Open this scene in the tour"/>
    </header>

    <section className="project-stats">
      {[['0','carts closed with a wrong item','held-out runs, all three rounds'],['60–78','of 85 held-out runs fully automatic','drops as the scene gets harder'],['3','cameras fused','gate, overhead, barcode'],
        ['2,640','synthetic training scenes','rendered and labelled by Unity'],['36 ms','per frame, three cameras','RTX 4070 Super, development seeds'],['150','automated tests','ledger, API, barcodes, ratings']]
        .map(([value,label,note])=><div key={label}><strong>{value}</strong><span>{label}</span><small>{note}</small></div>)}
    </section>

    <section id="how" className="project-section">
      <div className="section-head"><div className="eyebrow">HOW IT WORKS</div><h2>Only pixels cross the line</h2>
        <p>Unity renders the store, but it never tells the vision system what is in the cart. Each frame is sent as a JPEG with a camera name and a timestamp. Everything after that is inferred.</p></div>
      <div className="flow">{[['camera','See','A YOLO26n detector finds merchandise, people and carts in the gate and overhead views. BoT-SORT follows each box from frame to frame.'],
        ['eye','Identify','A barcode camera reads Code 128 store labels. Where no label is visible, an EfficientNet-B0 classifier recognizes the product by look.'],
        ['grid','Fuse','Calibration puts both views on one lane map, so the same physical box seen twice is one object, and a hidden box is not lost.'],
        ['list','Decide','A ledger gives every physical item one identity, adds it when it crosses the checkout line, removes it if it comes back, and rates how sure it is.'],
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

    <section id="results" className="project-section">
      <div className="section-head"><div className="eyebrow">MEASURED, NOT CLAIMED</div><h2>Results on runs the system was never tuned on</h2>
        <p>17 scenarios × 5 seeds = 85 recorded runs per round. Tuning happens on development seeds only. Each round made the scene harder and both camera model pairs were retrained for it.</p></div>
      <div className="rounds">{rounds.map(r=><div key={r.name} className={`round ${r.current?'current':''}`}>
        <div className="round-head"><h3>{r.name}</h3>{r.current&&<span className="pill verified">current scene</span>}</div><small>{r.scene}</small>
        <div className="round-bar"><span style={{width:`${r.passed/85*100}%`}}/></div>
        <div className="round-numbers"><div><strong>{r.passed}<i>/85</i></strong><span>fully automatic and exactly right</span></div><div><strong className="zero">{r.wrong}</strong><span>carts closed with a wrong item</span></div></div></div>)}</div>
      <p className="fine">In the cart round, 25 runs were handed to an associate. Two of those carts held one wrong line each (a second pair of gloves, a third board), which is why they were not closed automatically.</p>
      <div className="by-scene"><h3>Cart round, held-out seeds 10–14: runs passed out of 5</h3>
        <div className="by-scene-grid">{scenarios.map(s=><button key={s.id} onClick={()=>onTour(s.id)} title="Watch a recorded run"><span>{s.name}</span>
          <div className="dots">{[0,1,2,3,4].map(i=><i key={i} style={{background:i<heldOut[s.id]?rate(heldOut[s.id]):'#1c2a3c'}}/>)}</div><b style={{color:rate(heldOut[s.id])}}>{heldOut[s.id]}/5</b></button>)}</div></div>
      <div className="story-grid">
        <article><div className="eyebrow">A BUG THE DEVELOPMENT SET CAUGHT</div><h3>The barcode that landed on the wrong box</h3>
          <p>With carts, nine development runs were charged the wrong product. The cause: a label on a low cart sits below the calibration plane, so it projects toward the barcode camera and lands on the neighboring box. Giving each label to the first box behind it took development runs from 56 to 68 of 85 with nothing wrongly charged. The held-out set was scored once, after the fix.</p></article>
        <article><div className="eyebrow">MODELS</div><h3>Small models, one pair per camera</h3>
          <p>Detector: YOLO26n, mAP50 0.955 on the gate camera and 0.972 overhead. Classifier: EfficientNet-B0, 94% on held-out crops for both. One shared pair for both views scored far worse, so each camera has its own. Hashes and metrics are stored with every benchmark report.</p></article>
      </div>
    </section>

    <section id="scenes" className="project-section">
      <div className="section-head"><div className="eyebrow">17 SCENES</div><h2>Watch any run, with the decisions beside it</h2>
        <p>Each card plays a recorded run from all three cameras: the boxes the system drew, the cart it built, and what it did at each second. They are seed 2 of every scenario, pass or not.</p></div>
      <div className="scene-grid">{scenarios.map((s,i)=><button key={s.id} className="scene" onClick={()=>onTour(s.id)} style={{backgroundImage:`linear-gradient(180deg,transparent 25%,#0b1320f2 78%),url(/scenarios/${s.id}.jpg)`}}>
        <span className="title-card-number">{String(i+1).padStart(2,'0')}</span><strong>{s.name}</strong><small>{s.detail}</small></button>)}</div>
    </section>

    <section id="limits" className="project-section">
      <div className="section-head"><div className="eyebrow">WHAT IT DOES NOT DO YET</div><h2>Honest limits</h2></div>
      <div className="limits">{[['Synthetic only','Every number here comes from Unity renders. Nothing has been tested on a real camera.'],
        ['Stacked boxes fail','Two boxes pressed together on a cart read as one from both cameras: 0 of 5 held-out runs.'],
        ['Carts hide labels','A box behind another box is not scanned. Barcodes settle 65% of charged items with carts, down from 82% without.'],
        ['Automation fell with realism','78, then 71, then 60 of 85 as people and carts were added. The safety number held; the convenience number is the open work.']]
        .map(([name,text])=><div key={name}><h3>{name}</h3><p>{text}</p></div>)}</div>
    </section>

    <section className="project-section">
      <div className="section-head"><div className="eyebrow">BUILT WITH</div><h2>Stack and how to run it</h2></div>
      <div className="stack">{['Unity 6 · URP','PyTorch','YOLO26n','EfficientNet-B0','BoT-SORT','zxing-cpp','FastAPI','React + Vite','pytest'].map(t=><span key={t}>{t}</span>)}</div>
      <pre className="code">{`git clone https://github.com/dangermos/ProPass && cd ProPass/web
npm ci && npm run dev        # this site and the recorded tour: no GPU, no Unity

bash scripts/get_weights.sh  # trained weights, to run the models yourself
bash scripts/start.sh        # API + dashboard; press Play in Unity for a live lane`}</pre>
      <div className="title-actions"><button className="primary-button" onClick={()=>onTour('single')}><Icon name="play" size={17}/> Start the tour</button>
        <button className="secondary-button" onClick={onScenarios}><Icon name="camera" size={16}/> Live lab</button>
        <button className="secondary-button" onClick={()=>onLab('benchmark')}><Icon name="chart" size={16}/> Full benchmark</button></div>
    </section>
    <footer className="title-foot">Independent portfolio project by Danny (github.com/dangermos), inspired by contractor checkout. Not connected to The Home Depot. Fictional prices, no payment, synthetic data only.</footer>
  </div>;
}
