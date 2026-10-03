"""RGB-only temporal replay, with a separate ground-truth checkout oracle.

Only metadata frame_id/timestamp/run_id is passed into VisionEngine. The
ground_truth field is read later by expected_cart(), never by inference.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]


def expected_cart(records, known_skus):
    objects = {}
    for record in records:
        for product in record.get("ground_truth",[]):
            obj = objects.setdefault(product["physical_id"],
                {"sku":product["sku"],"approach":False,"membership":False,"crossed":False})
            y = product["image_y"]
            if y>=0.675:
                obj["approach"] = True
                obj["membership"] = False
            elif y<=0.375 and obj["approach"]:
                obj["crossed"] = True
                obj["membership"] = True
    counts = Counter(obj["sku"] for obj in objects.values()
                     if obj["membership"] and obj["sku"] in known_skus)
    review = any(obj["crossed"] and obj["sku"] not in known_skus for obj in objects.values())
    return dict(sorted(counts.items())),review


def main():
    import cv2
    import numpy as np
    from vision.engine import VisionEngine
    parser = argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT/"artifacts"/"replays")
    parser.add_argument("--scenario",default=None)
    parser.add_argument("--run",default=None)
    parser.add_argument("--output",type=Path,default=ROOT/"models"/"evaluation-temporal.json")
    parser.add_argument("--config",type=Path,default=ROOT/"vision"/"config.json")
    args = parser.parse_args()
    engine = VisionEngine(ROOT/"catalog.json",ROOT/"models",args.config)
    if not engine.status()["ready"]:
        raise RuntimeError(engine.status()["error"])
    engine.torch.set_num_threads(4)
    runs = sorted(path for path in args.root.glob("*/*") if path.is_dir())
    if args.scenario:
        runs = [path for path in runs if path.parent.name==args.scenario]
    if args.run:
        runs = [path for path in runs if path.name==args.run]
    reports = []
    for run in runs:
        records = []
        files = sorted(run.glob("*.jpg"))
        if not files:
            continue
        metadata = json.loads(files[0].with_suffix(".json").read_text())
        run_id = metadata["run_id"]
        engine.reset(run_id)
        events = []
        times = []
        max_membership = 0
        max_objects = 0
        output = None
        trace = []
        for path in files:
            record = json.loads(path.with_suffix(".json").read_text())
            image = cv2.imread(str(path))
            if image is None:
                raise ValueError(f"Unreadable RGB frame: {path}")
            started = time.perf_counter()
            # Deliberately keep this call limited to image + source timing.
            output = engine.process_frame(image,record["frame_id"],record["timestamp"],run_id)
            times.append((time.perf_counter()-started)*1000)
            events.extend(output["events"])
            records.append(record)
            max_membership = max(max_membership,output["metrics"]["cart_units"])
            max_objects = max(max_objects,output["metrics"]["physical_objects"])
            if output["events"] or len(trace)<3:
                trace.append({"frame_id":record["frame_id"],"timestamp":record["timestamp"],
                              "detections":output["detections"],"events":output["events"],
                              "review_required":output["review_required"]})
        expected,expected_review = expected_cart(records,engine.skus)
        actual = dict(sorted(Counter(obj["sku"] for obj in output["objects"]
                                     if obj["membership"] and obj["sku"]).items()))
        report = {"scenario":run.parent.name,"run_id":run_id,"frames":len(files),
                  "source_duration_seconds":records[-1]["timestamp"]-records[0]["timestamp"],
                  "expected_cart":expected,"predicted_cart":actual,
                  "expected_review":expected_review,"review_required":output["review_required"],
                  "exact_cart":actual==expected,
                  "passed":actual==expected and output["review_required"]==expected_review,
                  "maximum_cart_units":max_membership,"maximum_canonical_objects":max_objects,
                  "event_counts":dict(Counter(event["type"] for event in events)),
                  "duplicate_event_ids":len(events)-len({event["event_id"] for event in events}),
                  "latency_ms":{"median":float(np.median(times[1:])),
                                "p95":float(np.percentile(times[1:],95))},
                  "final_objects":output["objects"],"trace":trace}
        reports.append(report)
        print(json.dumps({k:v for k,v in report.items() if k not in ("final_objects","trace")}),flush=True)
    final = {"domain":"Recorded Unity RGB checkout sequences",
             "runtime_ground_truth":False,"runs":len(reports),
             "exact_cart_runs":sum(r["exact_cart"] for r in reports),
             "passed_runs":sum(r["passed"] for r in reports),
             "config":json.loads(args.config.read_text()),
             "limitations":["Scripted single-customer synthetic scene; no real-camera transfer tested",
                            "Results describe these recorded runs, not population-level performance"],
             "results":reports}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(final,indent=2))
    print(json.dumps({k:v for k,v in final.items() if k!="results"},indent=2),flush=True)


if __name__=="__main__":
    main()
