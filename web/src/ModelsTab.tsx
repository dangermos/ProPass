import type { Reports } from './types';
import { scenarioName } from './scenarios';
import { Icon, Stat, percent } from './ui';

const ms=(v?:number)=>v==null?'—':`${v.toFixed(1)} ms`;
const trackerName=(file?:string)=>({'botsort.yaml':'BoT-SORT','bytetrack.yaml':'ByteTrack'} as Record<string,string>)[file||'botsort.yaml']||file;
const count=(value?:number)=>value==null?'—':value.toLocaleString();
const fraction=(value?:number,total?:number)=>`${count(value)} / ${count(total)}`;

export default function ModelsTab({reports}:{reports:Reports|null}){
  if(!reports) return <div className="tab-page"><div className="tab-empty"><Icon name="chip" size={28}/><p>Loading model reports from the API…</p></div></div>;
  const det=reports.manifest?.detector,cls=reports.manifest?.classifier,t=reports.static?.totals;
  const world=!!reports.geometry&&reports.config?.world_mode!==false;
  const L={...reports.config?.ledger,...(world?reports.config?.world_ledger:{})};
  const lane=reports.geometry?.lane;
  const boundary=world&&lane?`${Number(lane.approach_z.toFixed(1))} / ${Number(lane.commit_z.toFixed(1))}`:`${L.approach_y??'—'} / ${L.commit_y??'—'}`;
  const skuCount=cls?.class_labels?.filter((label:string)=>label!=='ZZZ-UNKNOWN').length??5;
  const prototypes=cls?.prototype_bank_shape?.[1]??cls?.rejection_calibration?.clusters_per_class;
  const accepted=t?.known_detected_accepted,correct=t?.known_detected_accepted_correct;
  const acceptedPrecision=accepted>0&&correct!=null?correct/accepted:null;
  const abstained=t?.known_detected_crops!=null&&accepted!=null?t.known_detected_crops-accepted:undefined;
  const precisionNote=acceptedPrecision==null?'No accepted-SKU precision is available.':`Measured accepted-SKU precision: ${percent(acceptedPrecision,1)} (${fraction(correct,accepted)} correct).`;
  return <div className="tab-page">
    <div className="tab-intro"><div><h2>The models behind the lane</h2><p>Two fine-tuned networks read every frame. Camera trackers and a physical ledger turn their outputs into a cart. The reports separate held-out synthetic tests from validation calibration.</p></div></div>
    <div className="model-grid">
      <article className="panel model-card"><div className="model-head"><span className="metric-icon blue"><Icon name="eye"/></span><div><span className="metric-label">DETECTOR</span><h3>YOLO26n · {det?.classes?.join(' · ')??'merchandise'}</h3></div></div>
        <div className="stat-row"><Stat label="mAP50" value={det?.test?.map50?.toFixed(3)??'—'}/><Stat label="mAP50–95" value={det?.test?.map50_95?.toFixed(3)??'—'}/><Stat label="Recall" value={percent(det?.test?.recall,1)}/></div>
        <p>Metrics are from the held-out detector test. Fine-tuned from COCO on {count(det?.train_images)} cluttered Unity scenes in {det?.seconds!=null?Math.round(det.seconds):'—'} s. Training includes separate person and cart classes. Only merchandise boxes enter product tracking.</p></article>
      <article className="panel model-card"><div className="model-head"><span className="metric-icon purple"><Icon name="box"/></span><div><span className="metric-label">SKU CLASSIFIER</span><h3>EfficientNet-B0 · {skuCount} SKUs + reject</h3></div></div>
        <div className="stat-row"><Stat label="Crop accuracy" value={percent(cls?.test?.accuracy,1)} tone="purple"/><Stat label="Temperature" value={cls?.temperature?.toFixed(2)??'—'} tone="purple"/><Stat label="Reject distance" value={cls?.maximum_prototype_distance?.toFixed(2)??'—'} tone="purple"/></div>
        <p>Crop accuracy uses the held-out test; temperature and distance gate use validation. Fine-tuned from ImageNet on {count(cls?.dataset_sizes?.train)} crops, including partly hidden ones. {prototypes?`${prototypes} training-only appearance centers per class cover different views.`:'Training-only feature means summarize each class.'} The explicit reject class learns a gray-package outlier family; arbitrary unseen products remain unverified.</p></article>
      <article className="panel model-card"><div className="model-head"><span className="metric-icon teal"><Icon name="lane"/></span><div><span className="metric-label">TRACKING + LEDGER</span><h3>{world?`Camera-local ${trackerName(reports.config?.tracker)} + fusion`:`${trackerName(reports.config?.tracker)} · physical ledger`}</h3></div></div>
        <div className="stat-row"><Stat label={world?'Zones: z (m)':'Zones: image y'} value={boundary} tone="orange"/><Stat label="Occlusion gap" value={`${L.occlusion_seconds??6} s`} tone="orange"/><Stat label="SKU vote" value={percent(L.sku_threshold)} tone="orange"/></div>
        <p>{world?'Each camera keeps its own tracker. Calibrated carry-height projections fuse observations into one physical ledger; approach and commit are shared world-z lines. ':'Zones use normalized image rows inside the lane polygon. '}Physical identity uses motion, a clear-view appearance gallery and SKU compatibility. Settings: <code>vision/config.json</code>{world&&<>; calibration: <code>vision/cameras.json</code></>}.</p></article>
    </div>
    {t&&<article className="panel wide-panel"><div className="panel-heading"><div><h2>Static held-out test</h2><span className="subtle-tag">{count(t.images??reports.static.images)} CLUTTERED SCENES</span></div><span className="event-count">{ms(reports.static.latency_ms?.median)} median per frame</span></div>
      <div className="stat-row wide"><Stat label="Packages found (IoU ≥ .5)" value={fraction(t.matched_iou50,t.gt_merchandise)}/><Stat label="Accepted SKUs correct" value={fraction(correct,accepted)} tone="purple"/><Stat label="Known crops abstained" value={fraction(abstained,t.known_detected_crops)} tone="orange"/><Stat label="Gray outlier rejected" value={fraction(t.unknown_detected_rejected,t.unknown_detected_crops)} tone="blue"/></div>
      <p className="panel-note">{precisionNote} Abstained crops supply no accepted SKU evidence; the ledger can wait for another view. Unknown rejection covers the synthetic gray-package family only. Static crops do not establish exact-cart accuracy.</p></article>}
    {reports.live&&<article className="panel wide-panel"><div className="panel-heading"><div><h2>Live end-to-end check</h2><span className="subtle-tag">UNITY → API → CART</span></div></div>
      <div className="live-checks">{reports.live.scenarios.map((r:any)=><div key={r.scenario} className={`live-check ${r.passed?'pass':'fail'}`}><Icon name={r.passed?'check':'alert'} size={16}/><strong>{scenarioName(r.scenario)}</strong><span>{Object.entries(r.actual_cart||{}).map(([k,v])=>`${v}× ${k}`).join(', ')||'empty cart'}{r.review_required?' · review':''}</span></div>)}</div></article>}
    <p className="tab-footnote">Synthetic Unity data only. No real-camera transfer has been measured yet.</p>
  </div>;
}
