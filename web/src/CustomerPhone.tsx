import type { Snapshot } from './types';
import { Icon, money } from './ui';

// What the shopper would see on their own phone while walking the lane. It only ever
// shows what the system has decided: no camera views and no internals.
export const ratingInfo:Record<string,{label:string;tone:string;hint:string}>={
  verified:{label:'Verified',tone:'good',hint:'Barcode read'},
  high:{label:'High',tone:'blue',hint:'Recognized'},
  medium:{label:'Medium',tone:'warn',hint:'Recognized, less certain'},
  associate:{label:'Associate',tone:'purple',hint:'Added by an associate'},
  needs_associate:{label:'Needs associate',tone:'bad',hint:'Could not be scanned'},
};

export function RatingBadge({rating}:{rating?:string|null}){
  const info=rating?ratingInfo[rating]:null;
  return info?<span className={`rating-badge tone-${info.tone}`} title={info.hint}>{info.label}</span>:null;
}

type Props={snapshot:Snapshot|null;busy:string|null;live:boolean;onReview:()=>void;onConfirm:()=>void};

export default function CustomerPhone({snapshot,busy,live,onReview,onConfirm}:Props){
  const cart=snapshot?.cart,items=cart?.items??[],assist=snapshot?.assist??[],moving=snapshot?.in_progress??0;
  const qty=items.reduce((n,i)=>n+i.quantity,0);
  const status=cart?.status??'OPEN';
  const stage=status==='CONFIRMED'?'done':status==='ASSIST'?'assist':status==='REVIEWING'?'confirm':qty||moving||assist.length?'scanning':'welcome';
  const title={welcome:'Welcome to Pro Express',scanning:moving?'Scanning your items…':'Items scanned',assist:'Please see an associate',confirm:'Ready to check out',done:'You’re all set'}[stage];
  const subtitle={welcome:live?'Walk through the lane with your items.':'The lane camera is offline.',
    scanning:moving?`${moving} item${moving>1?'s':''} still passing the scanner.`:assist.length?`We couldn’t scan ${assist.length} item${assist.length>1?'s':''}.`:'Everything was scanned.',
    assist:`We couldn’t scan everything. Your ${qty} scanned item${qty===1?'':'s'} ${qty===1?'is':'are'} saved, and an associate will finish up.`,
    confirm:'Check your items, then confirm.',done:'Thanks for shopping. Your receipt is saved.'}[stage];
  return <div className={`phone stage-${stage}`} aria-label="Customer phone preview">
    <div className="phone-notch"/>
    <div className="phone-screen">
      <div className="phone-brand">Pro<span>Express</span><small>{snapshot?.session.customer_name??'Guest'}</small></div>
      <div className={`phone-status tone-${stage==='assist'?'warn':stage==='done'||stage==='confirm'?'good':'blue'}`}>
        <Icon name={stage==='assist'?'alert':stage==='done'?'check':stage==='confirm'?'receipt':'pulse'} size={22}/>
        <div><strong>{title}</strong><p>{subtitle}</p></div>
      </div>
      <div className="phone-list">
        {items.map(i=><div className="phone-line" key={i.sku}><div><strong>{i.name}</strong><small>Qty {i.quantity} · {money(i.unit_price)}</small></div><RatingBadge rating={i.rating}/></div>)}
        {assist.map(a=><div className="phone-line unscanned" key={a.object_id}><div><strong>{a.restricted?'Locked item':'Unscanned item'}</strong><small>{a.restricted?'An associate has to release it':'An associate will add it'}</small></div><RatingBadge rating="needs_associate"/></div>)}
        {!items.length&&!assist.length&&<div className="phone-empty"><Icon name="box" size={26}/><span>Your items appear here as they’re scanned.</span></div>}
      </div>
      <div className="phone-total"><span>Total</span><strong>{money(cart?.total??0)}</strong></div>
      {stage==='scanning'&&<button className="phone-button" disabled={!!busy||!!moving||(!qty&&!assist.length)} onClick={onReview}>{moving?'Keep walking…':'I’m done, check out'}</button>}
      {stage==='confirm'&&<button className="phone-button" disabled={!!busy} onClick={onConfirm}>Confirm and pay <small>(demo)</small></button>}
      {stage==='assist'&&<div className="phone-wait"><span className="dot live"/>Waiting for an associate</div>}
      {stage==='done'&&snapshot?.receipt&&<div className="phone-wait">Receipt PP-{snapshot.receipt.id.slice(0,8).toUpperCase()}</div>}
    </div>
  </div>;
}
