import type { Detection, Event, Snapshot } from './types';
import { eventText } from './LiveTab';
import { Icon, percent } from './ui';

// Plain-language reason for each ledger state, so every cart line can be explained.
const explain:Record<string,{tone:string;title:string;why:(o:Detection)=>string}>={
  ADDED:{tone:'good',title:'In the cart',why:o=>`Seen in APPROACH, then crossed into COMMIT with ${o.sku} accepted at ${percent(o.confidence)} average confidence.`},
  REMOVED:{tone:'bad',title:'Removed',why:()=>'It was in the cart, then was seen carried back to APPROACH, so it was taken out.'},
  OUTSIDE:{tone:'muted',title:'Outside the lane',why:()=>'Tracked outside the lane polygon (for example, the next aisle). It is never charged and never blocks checkout.'},
  LEFT:{tone:'muted',title:'Left the lane',why:()=>'Carried back out through the entry edge of the frame before checkout.'},
  FRAGMENT:{tone:'muted',title:'Edge fragment',why:()=>'Only ever seen cut off by the frame border, then replaced by a clearer track of the same item.'},
  ENTERING:{tone:'warn',title:'Entering',why:()=>'Seen in APPROACH and not across the checkout line yet. Checkout waits for it.'},
  TRACKED:{tone:'warn',title:'In the lane',why:o=>o.sku?`Recognized as ${o.sku}, still mid-lane. Checkout waits until it crosses or leaves.`:'Still collecting views to recognize the SKU. Checkout waits.'},
};

function ObjectCard({o,events}:{o:Detection;events:Event[]}){
  const state=o.state||'TRACKED',info=explain[state]||explain.TRACKED;
  const tone=o.review_reason?'bad':info.tone;
  return <article className={`decision-card tone-${tone}`}>
    <header>
      <div><span className="decision-id">{o.object_id?.split('-').pop()?.toUpperCase()}</span><strong>{o.sku||'Unrecognized'}</strong></div>
      <span className={`decision-state tone-${tone}`}>{o.review_reason?'Needs review':info.title}</span>
    </header>
    <p className="decision-why">{info.why(o)}</p>
    {o.review_reason&&<p className="decision-review"><Icon name="alert" size={14}/> {o.review_reason}</p>}
    <div className="decision-chips">
      <span>Zone <b>{o.zone||'—'}</b></span><span>Track <b>T{o.track_id}</b></span>
      <span>{o.visible?'Visible now':'Not visible'}</span><span>SKU confidence <b>{percent(o.confidence)}</b></span>
    </div>
    {events.length>0&&<ol className="decision-events">{events.slice().reverse().map(e=><li key={e.sequence} className={e.type.toLowerCase()}>
      <span>{Number(e.timestamp).toFixed(2)}s</span>{eventText(e)}</li>)}</ol>}
  </article>;
}

export default function DecisionsTab({snapshot}:{snapshot:Snapshot|null}){
  const objects=snapshot?.objects??[];
  const byObject=(id?:string)=>(snapshot?.events??[]).filter(e=>e.object_id===id);
  const blockers=objects.filter(o=>o.review_reason||(!o.membership&&['ENTERING','TRACKED'].includes(o.state||'')&&(o.visible||o.zone==='APPROACH')));
  const counts=objects.reduce<Record<string,number>>((c,o)=>{const k=o.review_reason?'REVIEW':o.state||'TRACKED';c[k]=(c[k]||0)+1;return c;},{});
  const order=['ADDED','REVIEW','ENTERING','TRACKED','REMOVED','OUTSIDE','LEFT','FRAGMENT'];
  return <div className="tab-page">
    <div className="tab-intro">
      <div><h2>Why the cart looks the way it does</h2><p>Every physical object the ledger has tracked in this run, with the evidence behind its state. Tracker IDs come and go. These canonical objects are what the cart counts.</p></div>
      <div className="state-tally">{order.filter(k=>counts[k]).map(k=><span key={k} className={`tally tally-${k.toLowerCase()}`}>{counts[k]} {k.toLowerCase()}</span>)}</div>
    </div>
    <div className={`blocker-banner ${blockers.length?'blocked':'clear'}`}>
      <Icon name={blockers.length?'alert':'check'} size={18}/>
      {blockers.length?<span><b>Checkout is blocked</b> by {blockers.length} object{blockers.length>1?'s':''}: {blockers.map(o=>o.review_reason||`${o.sku||'an unrecognized item'} is still in the lane`).join(' · ')}</span>
        :<span><b>Nothing is blocking checkout.</b> {snapshot?.cart.items.length?'The cart can be reviewed.':'No products have crossed yet.'}</span>}
    </div>
    {objects.length?<div className="decision-grid">{objects.slice().sort((a,b)=>order.indexOf(a.review_reason?'REVIEW':a.state||'')-order.indexOf(b.review_reason?'REVIEW':b.state||'')).map(o=><ObjectCard key={o.object_id} o={o} events={byObject(o.object_id)}/>)}</div>
      :<div className="tab-empty"><Icon name="box" size={28}/><p>No objects yet. Start a scenario and they'll appear here as the camera sees them.</p></div>}
  </div>;
}
