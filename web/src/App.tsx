import { useEffect, useRef, useState } from 'react';
import type { Snapshot, Detection, Event } from './types';

const money=(n:number)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n);
const shortId=(id:string)=>id.slice(0,8).toUpperCase();
const scenarioOptions=[
  {id:'single',name:'Single item',detail:'The first clean crossing',icon:'01'},
  {id:'duplicate',name:'Identical products',detail:'Same SKU, two physical units',icon:'02'},
  {id:'mixed',name:'Mixed cart',detail:'Different products in one trip',icon:'03'},
  {id:'occlusion',name:'Temporary occlusion',detail:'Recover identity after hiding',icon:'04'},
  {id:'remove',name:'Change of mind',detail:'Forward add, reverse removal',icon:'05'},
  {id:'unknown',name:'Unknown product',detail:'Uncertain evidence needs review',icon:'06'},
];
const colors=['#38d6bf','#6aa8ff','#ffbb71','#bd9aff','#ff8293'];

function Icon({name,size=20}:{name:string;size?:number}){
  const paths:Record<string,string>={grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',camera:'M3 7h4l2-3h6l2 3h4v14H3z M16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0',arrow:'M4 12h16M14 6l6 6-6 6',check:'M5 12l4 4L19 6',box:'M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 5 9-5M12 12v9',pulse:'M2 12h5l3-8 4 16 3-8h5',reset:'M3 10a9 9 0 1 1 1 9M3 4v6h6',pause:'M8 5v14M16 5v14',play:'M7 4l14 8-14 8z',user:'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-3a8 8 0 0 1 16 0v3',shield:'M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6',eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',alert:'M12 3l10 18H2zM12 9v5M12 17v1',receipt:'M5 3h14v18l-3-2-4 2-4-2-3 2zM8 7h8M8 11h8M8 15h5'};
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]||paths.box}/></svg>;
}

function VideoCanvas({snapshot}:{snapshot:Snapshot|null}){
  const ref=useRef<HTMLCanvasElement>(null);
  const [hasImage,setHasImage]=useState(false);
  useEffect(()=>{
    if(!snapshot?.frame){setHasImage(false);return;}
    const frame=snapshot.frame;
    const image=new Image();
    let cancelled=false;
    image.onload=()=>{
      if(cancelled||!ref.current)return;
      const canvas=ref.current,ctx=canvas.getContext('2d');if(!ctx)return;
      canvas.width=frame.width;canvas.height=frame.height;
      ctx.drawImage(image,0,0);setHasImage(true);
      const zones=[{y:.4,name:'COMMITTED',color:'#38d6bf'},{y:.65,name:'APPROACH',color:'#ffbb71'}];
      zones.forEach(z=>{ctx.strokeStyle=z.color+'99';ctx.lineWidth=2;ctx.setLineDash([9,8]);ctx.beginPath();ctx.moveTo(0,frame.height*z.y);ctx.lineTo(frame.width,frame.height*z.y);ctx.stroke();ctx.setLineDash([]);ctx.font='bold 13px monospace';ctx.fillStyle=z.color;ctx.fillText(z.name,16,frame.height*z.y-10);});
      snapshot.detections.forEach((d:Detection,i:number)=>{
        const [x1,y1,x2,y2]=d.bbox;if(d.bbox.length!==4)return;
        const color=d.sku?colors[i%colors.length]:'#ff8293';
        ctx.strokeStyle=color;ctx.lineWidth=2.5;ctx.strokeRect(x1,y1,x2-x1,y2-y1);
        const label=`T${d.track_id} · ${d.sku||'UNRESOLVED'} · ${Math.round(d.confidence*100)}%`;
        ctx.font='bold 13px monospace';const w=ctx.measureText(label).width+16;
        ctx.fillStyle=color;ctx.fillRect(x1,Math.max(0,y1-25),w,25);ctx.fillStyle='#07121a';ctx.fillText(label,x1+8,Math.max(17,y1-8));
      });
    };
    image.src=frame.url;
    return()=>{cancelled=true;image.onload=null;};
  },[snapshot?.frame?.url,snapshot?.session.run_id,snapshot?.detections]); // overlays belong to this exact processed frame
  return <div className="camera-stage"><canvas ref={ref} className={hasImage?'':'hidden'}/>{!hasImage&&<div className="empty-camera"><div className="camera-grid"/><div className="camera-orbit"><Icon name="camera" size={36}/></div><h3>Waiting for the checkout camera</h3><p>Start the Unity simulation to stream rendered RGB frames.</p><span className="connection-code">UNITY → VISION → CHECKOUT</span></div>}<div className="feed-corner top-left"><span className="dot"/> CAM 01 <span className="muted">/ CHECKOUT LANE</span></div><div className="feed-corner bottom-left">{snapshot?.frame?`FRAME ${snapshot.frame.frame_id.toString().padStart(5,'0')} · ${snapshot.frame.width} × ${snapshot.frame.height}`:'NO FRAMES RECEIVED'}</div><div className="feed-corner bottom-right">RGB INPUT ONLY</div></div>;
}

function eventText(e:Event){
  const id=e.object_id?`Object ${e.object_id}`:'Checkout';
  const texts:Record<string,string>={TRACK_CREATED:`${id} acquired`,SKU_RESOLVED:`${id} → ${e.sku}`,ITEM_ADDED:`${e.sku||id} added to cart`,ITEM_REMOVED:`${e.sku||id} removed from cart`,REVIEW_REQUIRED:e.reason||`${id} needs review`};
  return texts[e.type]||e.type.replaceAll('_',' ').toLowerCase();
}

export default function App(){
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
  const [connected,setConnected]=useState(false);
  const [busy,setBusy]=useState<string|null>(null);
  const [error,setError]=useState<string|null>(null);
  const [showTracks,setShowTracks]=useState(true);
  const [now,setNow]=useState(Date.now());
  const lastUpdate=useRef(Date.now());
  const confirmationKey=useRef<{cart:string;version:number;key:string}|null>(null);
  const update=(s:Snapshot)=>{setSnapshot(s);lastUpdate.current=Date.now();};
  useEffect(()=>{
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
  const cart=snapshot?.cart,qty=cart?.items.reduce((n,i)=>n+i.quantity,0)||0;
  const age=(snapshot?.frame?.age_ms||0)+(now-lastUpdate.current);
  const live=!!snapshot?.frame&&age<4000&&!snapshot.simulator.paused;
  const reviewing=cart?.status==='REVIEWING',confirmed=cart?.status==='CONFIRMED';
  const statusText=confirmed?'Confirmed':reviewing?'Ready to confirm':snapshot?.simulator.paused?'Capture paused':live?'Observing lane':'Awaiting camera';
  function confirm(){if(!cart)return;if(!confirmationKey.current||confirmationKey.current.cart!==cart.id||confirmationKey.current.version!==cart.version)confirmationKey.current={cart:cart.id,version:cart.version,key:crypto.randomUUID()};void action('cart/confirm',{version:cart.version,idempotency_key:confirmationKey.current.key});}
  return <div className="app-shell">
    <aside className="rail"><a href="/" className="brand-mark" aria-label="ProPass home">P<span/></a><div className="rail-divider"/><button className="rail-button selected" title="Vision checkout lab"><Icon name="grid"/></button><div className="rail-spacer"/><div className="rail-bottom" title="Local simulation"><Icon name="shield"/></div></aside>
    <main className="workspace">
      <header className="header"><div className="wordmark">Pro<span>Pass</span><small>VISION CHECKOUT LAB</small></div><div className="header-right"><span className="lab-badge">SYNTHETIC ENVIRONMENT</span><span className={`api-status ${connected?'online':''}`}><span className="dot"/>{connected?'API connected':'Connecting API'}</span></div></header>
      <section className="page-heading"><div><div className="eyebrow">RESEARCH CONSOLE / LANE 01</div><h1>Every item. One seamless pass.</h1><p>Physical product identity, exact recognition, and reversible checkout events.</p></div><div className="session-label"><span>SESSION</span><strong>{snapshot?shortId(snapshot.session.id):'—'}</strong><span className="simulation-note">Simulated checkout · no payment</span></div></section>
      <section className="metric-row"><div className="metric-card"><span className="metric-icon teal"><Icon name="eye"/></span><div><span className="metric-label">VISION ENGINE</span><strong className="engine-value">{snapshot?.vision.ready?'Model ready':snapshot?.vision.mode==='loading'?'Loading model':'Awaiting model'}</strong><small>{snapshot?.vision.mode?.replaceAll('_',' ')||'No checkpoint status yet'}</small></div></div><div className="metric-card"><span className="metric-icon blue"><Icon name="box"/></span><div><span className="metric-label">PHYSICAL UNITS IN CART</span><strong>{qty.toString().padStart(2,'0')}<em>units</em></strong><small>Canonical object membership</small></div></div><div className="metric-card"><span className="metric-icon orange"><Icon name="pulse"/></span><div><span className="metric-label">PIPELINE LATENCY</span><strong>{snapshot?.metrics.pipeline_ms??'—'}<em>ms</em></strong><small>Measured per processed frame</small></div></div><div className="metric-card"><span className="metric-icon purple"><Icon name="check"/></span><div><span className="metric-label">CHECKOUT STATE</span><strong className="state-value">{statusText}</strong><small>Cart version {cart?.version??0}</small></div></div></section>
      {(error||snapshot?.error)&&<div role="alert" className="error-banner"><Icon name="alert"/><span>{error||snapshot?.error}</span><button onClick={()=>setError(null)} aria-label="Dismiss error">×</button></div>}
      <div className="main-grid"><section className="left-column"><article className="panel camera-panel"><div className="panel-heading"><div><span className={`dot ${live?'live':'idle'}`}/><h2>Checkout camera</h2><span className="subtle-tag">UNITY RGB STREAM</span></div><div className="camera-controls"><button className={`toggle ${showTracks?'on':''}`} onClick={()=>setShowTracks(v=>!v)}>Overlays <span/></button><span className="frame-status">{snapshot?.simulator.paused?'PAUSED':live?'LIVE':'IDLE'}</span></div></div><VideoCanvas snapshot={showTracks?snapshot:snapshot?{...snapshot,detections:[]}:null}/><div className="feed-footer"><div><Icon name="shield" size={15}/><span>Predictions from pixels. Simulator labels never enter inference.</span></div><span>{snapshot?.metrics.processed_frames??0} frames processed</span></div></article>
        <article className="panel scenarios-panel"><div className="panel-heading"><div><h2>Scenario laboratory</h2><span className="subtle-tag">REPEATABLE TESTS</span></div><button className="text-button" disabled={!!busy} onClick={()=>void action('cart/reset')}><Icon name="reset" size={15}/> Restart run</button></div><div className="scenario-grid">{scenarioOptions.map(s=><button key={s.id} disabled={!!busy} onClick={()=>void action('scenario',{scenario:s.id})} className={`scenario ${snapshot?.simulator.scenario===s.id?'active':''}`}><span className="scenario-number">{s.icon}</span><div><strong>{s.name}</strong><small>{s.detail}</small></div><Icon name="arrow" size={15}/></button>)}</div></article>
        <article className="panel events-panel"><div className="panel-heading"><div><h2>Evidence timeline</h2><span className="subtle-tag">PERSISTED EVENTS</span></div><span className="event-count">{snapshot?.events.length??0} events</span></div><div className="event-stream">{snapshot?.events.length?snapshot.events.map(e=><div className={`event-row ${e.type==='REVIEW_REQUIRED'?'review-event':''}`} key={e.sequence}><span className={`event-node ${e.type==='ITEM_ADDED'?'added':e.type==='ITEM_REMOVED'?'removed':''}`}/><span className="event-time">{Number(e.timestamp).toFixed(2)}s</span><span className="event-text">{eventText(e)}</span><span className="event-kind">{e.type.replaceAll('_',' ')}</span></div>):<div className="empty-events"><Icon name="pulse"/><span>The event timeline will appear as merchandise is observed.</span></div>}</div></article>
      </section><aside className="right-column"><article className="panel customer-panel"><div className="panel-heading"><div><h2>Demo customer</h2></div><span className="subtle-tag">SIMULATED</span></div><div className="customer-content"><div className="avatar"><Icon name="user" size={24}/></div><div><strong>{snapshot?.session.customer_name||'Avery Morgan'}</strong><span>Independent portfolio account</span></div></div><select aria-label="Select simulated customer" value={snapshot?.session.customer_name||'Avery Morgan'} disabled={!!busy||confirmed} onChange={e=>void action('session',{customer_name:e.target.value})}><option>Avery Morgan</option><option>Jordan Ellis</option><option>Sam Rivera</option></select><p className="account-note">Demo account picker. No external authentication is connected.</p></article>
        <article className={`panel cart-panel ${confirmed?'confirmed-cart':''}`}><div className="panel-heading"><div><h2>Live cart</h2><span className="quantity-pill">{qty}</span></div><span className="cart-version">v{cart?.version??0}</span></div><div className="cart-lines">{cart?.items.length?cart.items.map((i,index)=><div className="cart-line" key={i.sku}><div className="product-mini" style={{'--product-color':colors[index%colors.length]} as React.CSSProperties}><Icon name="box" size={22}/></div><div className="product-text"><strong>{i.name}</strong><span>{i.sku} · {money(i.unit_price)} each</span><small>Qty <b>{i.quantity}</b></small></div><strong className="line-total">{money(i.line_total)}</strong></div>):<div className="empty-cart"><div><Icon name="box" size={30}/></div><strong>Your cart starts with a crossing</strong><p>Recognized physical products appear here after an observed checkout event.</p></div>}</div>
          {snapshot?.review_required&&<div className="review-message"><Icon name="alert" size={18}/><div><strong>Review required</strong><p>Some product or identity evidence is unresolved. Confirmation stays blocked.</p></div></div>}
          <div className="cart-summary"><div><span>Recognized products</span><span>{qty} {qty===1?'unit':'units'}</span></div><div className="total-row"><span>Demo total</span><strong>{money(cart?.total||0)}</strong></div><p>Fictional catalog prices · no payment collected</p></div>
          {confirmed?<div className="confirmation-state"><span><Icon name="check" size={22}/></span><strong>Checkout recorded</strong><p>An immutable simulated receipt has been saved.</p><button onClick={()=>void action('cart/reset')} disabled={!!busy}>Start another run <Icon name="arrow" size={16}/></button></div>:reviewing?<div className="cart-actions"><div className="prepared-note"><Icon name="pause" size={14}/> Capture paused at frame {cart?.prepared_frame_id}</div><button className="primary-button" disabled={!!busy} onClick={confirm}>{busy?'Recording…':'Confirm demo checkout'}<Icon name="check" size={17}/></button><button className="secondary-button" disabled={!!busy} onClick={()=>void action('cart/resume')}>Resume observation</button></div>:<div className="cart-actions"><button className="primary-button" disabled={!!busy||qty===0||snapshot?.review_required||!snapshot?.vision.ready} onClick={()=>void action('cart/prepare')}>{busy==='cart/prepare'?'Draining camera frames…':'Review checkout'}<Icon name="arrow" size={17}/></button>{snapshot?.simulator.paused&&<button className="secondary-button" disabled={!!busy} onClick={()=>void action('cart/resume')}>Resume observation</button>}<p>Pauses capture and drains accepted frames before review.</p></div>}</article>
        {snapshot?.receipt&&<article className="panel receipt-panel"><Icon name="receipt" size={22}/><div><span>SIMULATED RECEIPT</span><strong>PP-{shortId(snapshot.receipt.id)}</strong><p>{snapshot.receipt.customer_name} · {money(snapshot.receipt.total)}</p></div></article>}
        <div className="architecture-note"><div className="architecture-label">THE IDENTITY CONTRACT</div><div className="identity-chain"><span>Track ID</span><Icon name="arrow" size={14}/><span>Physical unit</span><Icon name="arrow" size={14}/><span>SKU</span></div><p>One product in 100 frames is one unit. Two identical products are two units.</p></div>
      </aside></div>
      <footer className="footer"><span><span className="dot"/> PROPASS / LOCAL RESEARCH PROTOTYPE</span><span>Learned perception · canonical identity · reversible events</span><span>SIMULATION ONLY</span></footer>
    </main>
  </div>;
}
