import type { Reports } from './types';
import { scenarioName } from './scenarios';
import { Icon, percent, rateColor } from './ui';

export default function BenchmarkTab({reports,busy,onRun}:{reports:Reports|null;busy:string|null;onRun:(id:string)=>void}){
  const report=reports?.benchmark,reference=reports?.benchmark_reference;
  if(!report) return <div className="tab-page"><div className="tab-empty"><Icon name="chart" size={28}/><p>No benchmark yet. Record runs in Unity and score them with <code>training/benchmark.py</code> (see docs/training.md).</p></div></div>;
  const before=(id:string)=>reference?.scenarios.find(r=>r.scenario===id);
  const s=report.summary;
  return <div className="tab-page">
    <div className="tab-intro">
      <div><h2>Scenario benchmark</h2><p>Every scenario was rendered offline from fixed seeds that were never used for tuning, then scored automatically. A run passes when the cart is exactly right <em>and</em> checkout is blocked only when it should be.</p></div>
      <div className="bench-hero"><strong>{s.passed}<span>/{s.runs}</span></strong><small>runs pass{reference?` · was ${reference.summary.passed}`:''}</small></div>
    </div>
    <article className="panel wide-panel bench-panel">
      <div className="bench-row bench-head"><span>Scenario</span><span>Pass rate</span><span>ID switches / run</span><span>False adds</span><span>Missed</span><span/></div>
      {report.scenarios.map(r=>{const b=before(r.scenario);return <div className={`bench-row ${r.group}`} key={r.scenario}>
        <span className="bench-name"><span className={`group-dot ${r.group}`}/><strong>{scenarioName(r.scenario)}</strong><small>{r.description}</small></span>
        <span className="bench-bar"><span className="bar-track"><span className="bar-fill" style={{width:`${Math.max(2,r.pass_rate*100)}%`,background:rateColor(r.pass_rate)}}/>{b&&<span className="bar-ref" style={{width:`${Math.max(1,b.pass_rate*100)}%`}}/>}</span><b>{percent(r.pass_rate)}</b><em>{b&&b.pass_rate!==r.pass_rate?`was ${percent(b.pass_rate)}`:''}</em></span>
        <span>{r.id_switches_per_run}</span><span>{r.false_adds}</span><span>{r.missed_items}</span>
        <span><button className="text-button" disabled={!!busy} onClick={()=>onRun(r.scenario)}>Run live <Icon name="play" size={12}/></button></span>
      </div>;})}
    </article>
    <p className="tab-footnote">{s.label}{reference?` · reference: ${reference.summary.label}`:''} · median {s.latency_ms_median} ms per frame · full report in docs/benchmark.md</p>
  </div>;
}
