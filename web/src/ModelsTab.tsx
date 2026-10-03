import type { Reports } from './types';
import { scenarioName } from './scenarios';
import { Icon, Stat, percent } from './ui';

const ms=(v?:number)=>v==null?'—':`${v.toFixed(1)} ms`;
const trackerName=(file?:string)=>({'botsort.yaml':'BoT-SORT','bytetrack.yaml':'ByteTrack'} as Record<string,string>)[file||'botsort.yaml']||file;

export default function ModelsTab({reports}:{reports:Reports|null}){
  if(!reports) return <div className="tab-page"><div className="tab-empty"><Icon name="chip" size={28}/><p>Loading model reports from the API…</p></div></div>;
  const det=reports.manifest?.detector,cls=reports.manifest?.classifier,t=reports.static?.totals,L=reports.config?.ledger||{};
  return <div className="tab-page">
    <div className="tab-intro"><div><h2>The models behind the lane</h2><p>Two fine-tuned networks read every frame, and a tracker plus the physical ledger turn their outputs into a cart. All numbers come from files the training scripts write, measured on held-out synthetic data.</p></div></div>
    <div className="model-grid">
      <article className="panel model-card"><div className="model-head"><span className="metric-icon blue"><Icon name="eye"/></span><div><span className="metric-label">DETECTOR</span><h3>YOLO26n · {det?.classes?.join(' · ')??'merchandise'}</h3></div></div>
        <div className="stat-row"><Stat label="mAP50" value={det?det.test.map50.toFixed(3):'—'}/><Stat label="mAP50–95" value={det?det.test.map50_95.toFixed(3):'—'}/><Stat label="Recall" value={percent(det?.test.recall,1)}/></div>
        <p>Fine-tuned from COCO on {det?.train_images??'—'} cluttered Unity scenes in {det?Math.round(det.seconds):'—'} s. People and carts are their own classes, so they stop being mistaken for products. Only merchandise boxes are tracked.</p></article>
      <article className="panel model-card"><div className="model-head"><span className="metric-icon purple"><Icon name="box"/></span><div><span className="metric-label">SKU CLASSIFIER</span><h3>EfficientNet-B0 · 5 SKUs + reject</h3></div></div>
        <div className="stat-row"><Stat label="Crop accuracy" value={percent(cls?.test?.accuracy,1)} tone="purple"/><Stat label="Temperature" value={cls?.temperature?.toFixed(2)??'—'} tone="purple"/><Stat label="Reject distance" value={cls?.maximum_prototype_distance?.toFixed(2)??'—'} tone="purple"/></div>
        <p>Fine-tuned from ImageNet on {cls?.dataset_sizes?.train??'—'} crops, including partly hidden ones. An outlier class and a feature-prototype distance gate reject packages it was never taught.</p></article>
      <article className="panel model-card"><div className="model-head"><span className="metric-icon teal"><Icon name="lane"/></span><div><span className="metric-label">TRACKING + LEDGER</span><h3>{trackerName(reports.config?.tracker)} · physical ledger</h3></div></div>
        <div className="stat-row"><Stat label="Approach / commit" value={`${L.approach_y??'—'} / ${L.commit_y??'—'}`} tone="orange"/><Stat label="Occlusion window" value={`${L.occlusion_seconds??6} s`} tone="orange"/><Stat label="SKU threshold" value={percent(L.sku_threshold)} tone="orange"/></div>
        <p>Tracker IDs are re-attached to physical objects using the motion path, a clear-view appearance gallery and SKU compatibility. Zones only exist inside the lane polygon. All settings live in <code>vision/config.json</code>.</p></article>
    </div>
    {t&&<article className="panel wide-panel"><div className="panel-heading"><div><h2>Static held-out test</h2><span className="subtle-tag">{reports.static.images} CLUTTERED SCENES</span></div><span className="event-count">{ms(reports.static.latency_ms?.median)} median per frame</span></div>
      <div className="stat-row wide"><Stat label="Packages found" value={`${t.matched_iou50} / ${t.gt_merchandise}`}/><Stat label="Accepted SKUs correct" value={`${t.known_detected_accepted_correct} / ${t.known_detected_accepted}`} tone="purple"/><Stat label="Abstained (sent to review)" value={`${t.known_detected_crops-t.known_detected_accepted} / ${t.known_detected_crops}`} tone="orange"/><Stat label="Unknown package rejected" value={`${t.unknown_detected_rejected} / ${t.unknown_detected_crops}`} tone="blue"/></div>
      <p className="panel-note">When a crop is unclear the classifier abstains rather than guess, and the tracker waits for a better view. Every accepted SKU in the test set was correct.</p></article>}
    {reports.live&&<article className="panel wide-panel"><div className="panel-heading"><div><h2>Live end-to-end check</h2><span className="subtle-tag">UNITY → API → CART</span></div></div>
      <div className="live-checks">{reports.live.scenarios.map((r:any)=><div key={r.scenario} className={`live-check ${r.passed?'pass':'fail'}`}><Icon name={r.passed?'check':'alert'} size={16}/><strong>{scenarioName(r.scenario)}</strong><span>{Object.entries(r.actual_cart||{}).map(([k,v])=>`${v}× ${k}`).join(', ')||'empty cart'}{r.review_required?' · review':''}</span></div>)}</div></article>}
    <p className="tab-footnote">Synthetic Unity data only. No real-camera transfer has been measured yet.</p>
  </div>;
}
