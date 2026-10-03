import type React from 'react';

export const money=(n:number)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n);
export const shortId=(id:string)=>id.slice(0,8).toUpperCase();
export const percent=(v?:number|null,digits=0)=>v==null?'—':`${(v*100).toFixed(digits)}%`;
export const colors=['#38d6bf','#6aa8ff','#ffbb71','#bd9aff','#ff8293'];
export const rateColor=(v:number)=>v>=.8?'#2ea043':v>=.5?'#d29922':'#f85149';

export function Icon({name,size=20}:{name:string;size?:number}){
  const paths:Record<string,string>={grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',camera:'M3 7h4l2-3h6l2 3h4v14H3z M16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0',arrow:'M4 12h16M14 6l6 6-6 6',check:'M5 12l4 4L19 6',box:'M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 5 9-5M12 12v9',pulse:'M2 12h5l3-8 4 16 3-8h5',reset:'M3 10a9 9 0 1 1 1 9M3 4v6h6',pause:'M8 5v14M16 5v14',play:'M7 4l14 8-14 8z',user:'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-3a8 8 0 0 1 16 0v3',shield:'M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6',eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',alert:'M12 3l10 18H2zM12 9v5M12 17v1',receipt:'M5 3h14v18l-3-2-4 2-4-2-3 2zM8 7h8M8 11h8M8 15h5',list:'M8 6h13M8 12h13M8 18h13M3 6h1M3 12h1M3 18h1',chip:'M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4',chart:'M4 20V10M10 20V4M16 20v-7M22 20H2',back:'M15 18l-6-6 6-6',lane:'M6 21L9 3M18 21L15 3M12 5v2M12 11v2M12 17v2'};
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]||paths.box}/></svg>;
}

export function Stat({label,value,note,tone='teal'}:{label:string;value:React.ReactNode;note?:React.ReactNode;tone?:string}){
  return <div className={`stat-card tone-${tone}`}><span className="metric-label">{label}</span><strong>{value}</strong>{note&&<small>{note}</small>}</div>;
}
