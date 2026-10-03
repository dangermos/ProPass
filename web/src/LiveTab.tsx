import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import type { Snapshot, Detection, Event } from './types';
import { Icon, colors, money, shortId } from './ui';

export type LiveProps = {config?:any;snapshot:Snapshot|null;busy:string|null;action:(path:string,body?:unknown)=>Promise<void>;confirm:()=>void;live:boolean;statusText:string};

function VideoCanvas({snapshot,config}:{snapshot:Snapshot|null;config?:any}){
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
      const ledger=config?.ledger||{},W=frame.width,H=frame.height;
      const lane:number[][]|undefined=ledger.lane_polygon;
      if(lane){ctx.save();ctx.beginPath();lane.forEach(([x,y],i)=>i?ctx.lineTo(x*W,y*H):ctx.moveTo(x*W,y*H));ctx.closePath();ctx.fillStyle='rgba(56,214,191,0.07)';ctx.fill();ctx.setLineDash([4,6]);ctx.lineWidth=1.5;ctx.strokeStyle='rgba(220,235,255,0.45)';ctx.stroke();ctx.restore();ctx.font='bold 12px monospace';ctx.fillStyle='rgba(220,235,255,0.7)';ctx.fillText('LANE',lane[3][0]*W+8,24);}
      const zones=[{y:ledger.commit_y??.4,name:'COMMITTED',color:'#38d6bf'},{y:ledger.approach_y??.65,name:'APPROACH',color:'#ffbb71'}];
      zones.forEach(z=>{ctx.strokeStyle=z.color+'99';ctx.lineWidth=2;ctx.setLineDash([9,8]);ctx.beginPath();ctx.moveTo(0,frame.height*z.y);ctx.lineTo(frame.width,frame.height*z.y);ctx.stroke();ctx.setLineDash([]);ctx.font='bold 13px monospace';ctx.fillStyle=z.color;ctx.fillText(z.name,16,frame.height*z.y-10);});
      snapshot.detections.forEach((d:Detection,i:number)=>{
        const [x1,y1,x2,y2]=d.bbox;if(d.bbox.length!==4)return;
        const outside=d.state==='OUTSIDE';
        const color=outside?'#8fa3bf':d.sku?colors[i%colors.length]:'#ff8293';
        ctx.strokeStyle=color;ctx.lineWidth=2.5;ctx.strokeRect(x1,y1,x2-x1,y2-y1);
        const label=`T${d.track_id} · ${d.sku||'UNRESOLVED'} · ${outside?'OUTSIDE LANE':Math.round(d.confidence*100)+'%'}`;
        ctx.font='bold 13px monospace';const w=ctx.measureText(label).width+16;
        ctx.fillStyle=color;ctx.fillRect(x1,Math.max(0,y1-25),w,25);ctx.fillStyle='#07121a';ctx.fillText(label,x1+8,Math.max(17,y1-8));
      });
    };
    image.src=frame.url;
    return()=>{cancelled=true;image.onload=null;};
  },[snapshot?.frame?.url,snapshot?.session.run_id,snapshot?.detections,config]); // overlays belong to this exact processed frame
  return <div className="camera-stage"><canvas ref={ref} className={hasImage?'':'hidden'}/>{!hasImage&&<div className="empty-camera"><div className="camera-grid"/><div className="camera-orbit"><Icon name="camera" size={36}/></div><h3>Waiting for the checkout camera</h3><p>Start the Unity simulation to stream rendered RGB frames.</p><span className="connection-code">UNITY → VISION → CHECKOUT</span></div>}<div className="feed-corner top-left"><span className="dot"/> CAM 01 <span className="muted">/ CHECKOUT LANE</span></div><div className="feed-corner bottom-left">{snapshot?.frame?`FRAME ${snapshot.frame.frame_id.toString().padStart(5,'0')} · ${snapshot.frame.width} × ${snapshot.frame.height}`:'NO FRAMES RECEIVED'}</div><div className="feed-corner bottom-right">RGB INPUT ONLY</div></div>;
}

export function eventText(e:Event){
  const id=e.object_id?`Object ${e.object_id}`:'Checkout';
  const texts:Record<string,string>={TRACK_CREATED:`${id} acquired`,SKU_RESOLVED:`${id} → ${e.sku}`,ITEM_ADDED:`${e.sku||id} added to cart`,ITEM_REMOVED:`${e.sku||id} removed from cart`,REVIEW_REQUIRED:e.reason||`${id} needs review`};
  return texts[e.type]||e.type.replaceAll('_',' ').toLowerCase();
}

export default function LiveTab({config,snapshot,busy,action,confirm,live,statusText}:LiveProps){
  const [showTracks,setShowTracks]=useState(true);
  const cart=snapshot?.cart,qty=cart?.items.reduce((n,i)=>n+i.quantity,0)||0;
  const reviewing=cart?.status==='REVIEWING',confirmed=cart?.status==='CONFIRMED';
  return <>
      <section className="metric-row"><div className="metric-card"><span className="metric-icon teal"><Icon name="eye"/></span><div><span className="metric-label">VISION ENGINE</span><strong className="engine-value">{snapshot?.vision.ready?'Model ready':snapshot?.vision.mode==='loading'?'Loading model':'Awaiting model'}</strong><small>{snapshot?.vision.mode?.replaceAll('_',' ')||'No checkpoint status yet'}</small></div></div><div className="metric-card"><span className="metric-icon blue"><Icon name="box"/></span><div><span className="metric-label">PHYSICAL UNITS IN CART</span><strong>{qty.toString().padStart(2,'0')}<em>units</em></strong><small>Canonical object membership</small></div></div><div className="metric-card"><span className="metric-icon orange"><Icon name="pulse"/></span><div><span className="metric-label">PIPELINE LATENCY</span><strong>{snapshot?.metrics.pipeline_ms??'—'}<em>ms</em></strong><small>Measured per processed frame</small></div></div><div className="metric-card"><span className="metric-icon purple"><Icon name="check"/></span><div><span className="metric-label">CHECKOUT STATE</span><strong className="state-value">{statusText}</strong><small>Cart version {cart?.version??0}</small></div></div></section>
      <div className="main-grid"><section className="left-column"><article className="panel camera-panel"><div className="panel-heading"><div><span className={`dot ${live?'live':'idle'}`}/><h2>Checkout camera</h2><span className="subtle-tag">UNITY RGB STREAM</span></div><div className="camera-controls"><button className={`toggle ${showTracks?'on':''}`} onClick={()=>setShowTracks(v=>!v)}>Overlays <span/></button><span className="frame-status">{snapshot?.simulator.paused?'PAUSED':live?'LIVE':'IDLE'}</span></div></div><VideoCanvas config={config} snapshot={showTracks?snapshot:snapshot?{...snapshot,detections:[]}:null}/><div className="feed-footer"><div><Icon name="shield" size={15}/><span>Predictions from pixels. Simulator labels never enter inference.</span></div><span>{snapshot?.metrics.processed_frames??0} frames processed</span></div></article>
        <article className="panel events-panel"><div className="panel-heading"><div><h2>Evidence timeline</h2><span className="subtle-tag">PERSISTED EVENTS</span></div><span className="event-count">{snapshot?.events.length??0} events</span></div><div className="event-stream">{snapshot?.events.length?snapshot.events.map(e=><div className={`event-row ${e.type==='REVIEW_REQUIRED'?'review-event':''}`} key={e.sequence}><span className={`event-node ${e.type==='ITEM_ADDED'?'added':e.type==='ITEM_REMOVED'?'removed':''}`}/><span className="event-time">{Number(e.timestamp).toFixed(2)}s</span><span className="event-text">{eventText(e)}</span><span className="event-kind">{e.type.replaceAll('_',' ')}</span></div>):<div className="empty-events"><Icon name="pulse"/><span>The event timeline will appear as merchandise is observed.</span></div>}</div></article>
      </section><aside className="right-column"><article className="panel customer-panel"><div className="panel-heading"><div><h2>Demo customer</h2></div><span className="subtle-tag">SIMULATED</span></div><div className="customer-content"><div className="avatar"><Icon name="user" size={24}/></div><div><strong>{snapshot?.session.customer_name||'Avery Morgan'}</strong><span>Independent portfolio account</span></div></div><select aria-label="Select simulated customer" value={snapshot?.session.customer_name||'Avery Morgan'} disabled={!!busy||confirmed} onChange={e=>void action('session',{customer_name:e.target.value})}><option>Avery Morgan</option><option>Jordan Ellis</option><option>Sam Rivera</option></select><p className="account-note">Demo account picker. No external authentication is connected.</p></article>
        <article className={`panel cart-panel ${confirmed?'confirmed-cart':''}`}><div className="panel-heading"><div><h2>Live cart</h2><span className="quantity-pill">{qty}</span></div><span className="cart-version">v{cart?.version??0}</span></div><div className="cart-lines">{cart?.items.length?cart.items.map((i,index)=><div className="cart-line" key={i.sku}><div className="product-mini" style={{'--product-color':colors[index%colors.length]} as React.CSSProperties}><Icon name="box" size={22}/></div><div className="product-text"><strong>{i.name}</strong><span>{i.sku} · {money(i.unit_price)} each</span><small>Qty <b>{i.quantity}</b></small></div><strong className="line-total">{money(i.line_total)}</strong></div>):<div className="empty-cart"><div><Icon name="box" size={30}/></div><strong>Your cart starts with a crossing</strong><p>Recognized physical products appear here after an observed checkout event.</p></div>}</div>
          {snapshot?.review_required&&<div className="review-message"><Icon name="alert" size={18}/><div><strong>Review required</strong><p>Some product or identity evidence is unresolved. Confirmation stays blocked.</p></div></div>}
          <div className="cart-summary"><div><span>Recognized products</span><span>{qty} {qty===1?'unit':'units'}</span></div><div className="total-row"><span>Demo total</span><strong>{money(cart?.total||0)}</strong></div><p>Fictional catalog prices · no payment collected</p></div>
          {confirmed?<div className="confirmation-state"><span><Icon name="check" size={22}/></span><strong>Checkout recorded</strong><p>An immutable simulated receipt has been saved.</p><button onClick={()=>void action('cart/reset')} disabled={!!busy}>Start another run <Icon name="arrow" size={16}/></button></div>:reviewing?<div className="cart-actions"><div className="prepared-note"><Icon name="pause" size={14}/> Capture paused at frame {cart?.prepared_frame_id}</div><button className="primary-button" disabled={!!busy} onClick={confirm}>{busy?'Recording…':'Confirm demo checkout'}<Icon name="check" size={17}/></button><button className="secondary-button" disabled={!!busy} onClick={()=>void action('cart/resume')}>Resume observation</button></div>:<div className="cart-actions"><button className="primary-button" disabled={!!busy||qty===0||snapshot?.review_required||!snapshot?.vision.ready} onClick={()=>void action('cart/prepare')}>{busy==='cart/prepare'?'Draining camera frames…':'Review checkout'}<Icon name="arrow" size={17}/></button>{snapshot?.simulator.paused&&<button className="secondary-button" disabled={!!busy} onClick={()=>void action('cart/resume')}>Resume observation</button>}<p>Pauses capture and drains accepted frames before review.</p></div>}</article>
        {snapshot?.receipt&&<article className="panel receipt-panel"><Icon name="receipt" size={22}/><div><span>SIMULATED RECEIPT</span><strong>PP-{shortId(snapshot.receipt.id)}</strong><p>{snapshot.receipt.customer_name} · {money(snapshot.receipt.total)}</p></div></article>}
        <div className="architecture-note"><div className="architecture-label">THE IDENTITY CONTRACT</div><div className="identity-chain"><span>Track ID</span><Icon name="arrow" size={14}/><span>Physical unit</span><Icon name="arrow" size={14}/><span>SKU</span></div><p>One product in 100 frames is one unit. Two identical products are two units.</p></div>
      </aside></div>
  </>;
}
