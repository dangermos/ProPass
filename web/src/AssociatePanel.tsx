import { useEffect, useState } from 'react';
import type { Snapshot } from './types';
import { Icon } from './ui';

type Product={sku:string;name:string;price:number};

// The associate's side of a hand-off: settle each flagged item, and the cart moves on.
export default function AssociatePanel({snapshot,busy,action}:{snapshot:Snapshot|null;busy:string|null;action:(path:string,body?:unknown)=>Promise<void>}){
  const [catalog,setCatalog]=useState<Product[]>([]);
  const [choice,setChoice]=useState<Record<string,string>>({});
  useEffect(()=>{fetch('/api/catalog').then(r=>r.json()).then(d=>setCatalog(d.products??[])).catch(()=>{});},[]);
  const assist=snapshot?.assist??[],active=snapshot?.cart.status==='ASSIST';
  if(!assist.length&&!active) return null;
  const name=(sku?:string|null)=>catalog.find(p=>p.sku===sku)?.name??sku??'Unrecognized item';
  return <article className={`panel associate-panel ${active?'active':''}`}>
    <div className="panel-heading"><div><Icon name="user" size={18}/><h2>Associate</h2><span className="subtle-tag">{active?'HAND-OFF IN PROGRESS':'WOULD BE CALLED'}</span></div><span className="quantity-pill warn">{assist.length}</span></div>
    {!active&&<p className="associate-note">These items can’t finish on their own. When the customer checks out, an associate settles them and the scanned items stay in the cart.</p>}
    <div className="associate-list">{assist.map(a=>{const sku=choice[a.object_id]??a.sku??catalog[0]?.sku??'';return <div className="associate-item" key={a.object_id}>
      <div className="associate-item-head"><Icon name={a.restricted?'shield':'alert'} size={16}/><div><strong>{a.restricted?`Locked: ${name(a.sku)}`:a.sku?name(a.sku):'Unscanned item'}</strong><small>{a.reason}</small></div></div>
      {active&&<div className="associate-actions">
        {!a.restricted&&<select aria-label="Product to add" value={sku} onChange={e=>setChoice(c=>({...c,[a.object_id]:e.target.value}))}>{catalog.map(p=><option key={p.sku} value={p.sku}>{p.name}</option>)}</select>}
        <button className="primary-button" disabled={!!busy||!sku} onClick={()=>void action('assist/add',{sku:a.restricted?a.sku:sku,object_id:a.object_id})}>{a.restricted?'Release and add':'Add to cart'}</button>
        <button className="secondary-button" disabled={!!busy} onClick={()=>void action('assist/dismiss',{object_id:a.object_id})}>{a.restricted?'Customer left it':'Not an item'}</button>
      </div>}
    </div>;})}</div>
  </article>;
}
