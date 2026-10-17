"""Score the vision pipeline on recorded benchmark runs.

Record runs first (Unity → ProPass → Record benchmark suite, or the Unity CLI; see
docs/training.md). Each run folder holds JPEG frames, per-frame ground-truth JSON and
run.json with the expected cart. Only JPEG pixels and frame timing are passed to
VisionEngine; ground truth is read afterwards, for scoring only.

    .venv/bin/python -m training.benchmark --root artifacts/benchmark --label baseline
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ["single", "duplicate", "mixed", "occlusion", "remove", "unknown"]
MESSY = ["hands", "shopper", "flatbed", "edge", "stacked", "distractors", "bystander", "hesitate", "parked", "locked", "lumber"]


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(truth, detections, threshold=0.3):
    """Greedy one-to-one IoU matching of ground-truth products to tracked detections."""
    pairs = sorted(((iou(t["bbox"], d["bbox"]), ti, di)
                    for ti, t in enumerate(truth) if len(t.get("bbox", [])) == 4
                    for di, d in enumerate(detections) if len(d.get("bbox", [])) == 4), reverse=True)
    used_t, used_d, result = set(), set(), []
    for score, ti, di in pairs:
        if score < threshold or ti in used_t or di in used_d:
            continue
        used_t.add(ti)
        used_d.add(di)
        result.append((truth[ti], detections[di]))
    return result


def score_run(engine, run_dir):
    import cv2
    info = json.loads((run_dir / "run.json").read_text())
    # 000001.jpg is the lane camera; 000001.<camera>.jpg are the other cameras.
    files = sorted(p for p in run_dir.glob("*.jpg") if "." not in p.stem)
    engine.reset(info["run_id"])
    output, times = None, []
    tracks = defaultdict(list)          # physical_id -> canonical object_id per matched frame
    matched_objects, seen_frames, detected_frames = set(), Counter(), Counter()
    for path in files:
        record = json.loads(path.with_suffix(".json").read_text())
        images = {camera: cv2.imread(str(path if camera == "lane" else path.with_suffix(f".{camera}.jpg")))
                  for camera in engine.camera_ids + engine.scan_cameras}
        images = {camera: image for camera, image in images.items() if image is not None}
        started = time.perf_counter()
        output = engine.process_frames(images, record["frame_id"], record["timestamp"], info["run_id"])
        times.append((time.perf_counter() - started) * 1000)
        truth = [t for t in record["ground_truth"] if len(t.get("bbox", [])) == 4]
        for t in truth:
            seen_frames[t["physical_id"]] += 1
        # Ground-truth boxes are in the lane camera's image, so identity is scored there.
        for t, d in match(truth, [d for d in output["detections"] if d.get("camera", "lane") == "lane"]):
            tracks[t["physical_id"]].append(d["object_id"])
            matched_objects.add(d["object_id"])
            detected_frames[t["physical_id"]] += 1
    expected = {line["sku"]: line["quantity"] for line in info.get("expected_cart", [])}
    predicted = dict(Counter(o["sku"] for o in output["objects"] if o["membership"] and o["sku"]))
    skus = set(expected) | set(predicted)
    switches = sum(sum(1 for a, b in zip(ids, ids[1:], strict=False) if a != b) for ids in tracks.values())
    phantoms = [o for o in output["objects"] if o["object_id"] not in matched_objects]
    reasons = sorted({o["review_reason"] for o in output["objects"] if o.get("review_reason")})
    exact = predicted == expected
    return {
        "scenario": info["scenario"], "seed": info["seed"], "run_id": info["run_id"],
        "description": info.get("description", ""), "frames": len(files),
        "expected_cart": expected, "predicted_cart": predicted,
        "expected_review": info.get("expected_review", False), "review_required": output["review_required"],
        "exact_cart": exact, "passed": exact and output["review_required"] == info.get("expected_review", False),
        "false_adds": sum(max(0, predicted.get(s, 0) - expected.get(s, 0)) for s in skus),
        "missed_items": sum(max(0, expected.get(s, 0) - predicted.get(s, 0)) for s in skus),
        # How each charged item's SKU was established: by barcode or by look.
        "sku_sources": dict(Counter(o.get("sku_source") or "none" for o in output["objects"] if o["membership"])),
        "assist_items": len(output.get("assist", [])),
        "id_switches": switches,
        "phantom_objects": len(phantoms),
        "detection_recall": round(sum(detected_frames.values()) / max(1, sum(seen_frames.values())), 3),
        "review_reasons": reasons,
        "latency_ms_median": round(statistics.median(times[1:]), 2) if len(times) > 1 else None,
    }


def summarize(runs):
    by = defaultdict(list)
    for r in runs:
        by[r["scenario"]].append(r)
    order = [s for s in CLASSIC + MESSY if s in by] + sorted(set(by) - set(CLASSIC + MESSY))
    rows = []
    for s in order:
        rs = by[s]
        rows.append({
            "scenario": s, "group": "classic" if s in CLASSIC else "messy", "runs": len(rs),
            "description": rs[0]["description"],
            "pass_rate": round(sum(r["passed"] for r in rs) / len(rs), 3),
            "exact_cart_rate": round(sum(r["exact_cart"] for r in rs) / len(rs), 3),
            "false_adds": sum(r["false_adds"] for r in rs), "missed_items": sum(r["missed_items"] for r in rs),
            "barcode_share": round(sum(r["sku_sources"].get("barcode", 0) for r in rs) /
                                   max(1, sum(sum(r["sku_sources"].values()) for r in rs)), 3),
            "assist_items": sum(r["assist_items"] for r in rs),
            "id_switches_per_run": round(sum(r["id_switches"] for r in rs) / len(rs), 2),
            "phantom_objects_per_run": round(sum(r["phantom_objects"] for r in rs) / len(rs), 2),
            "review_rate": round(sum(r["review_required"] for r in rs) / len(rs), 3),
            "detection_recall": round(statistics.mean(r["detection_recall"] for r in rs), 3),
            "top_review_reasons": [k for k, _ in Counter(x for r in rs for x in r["review_reasons"]).most_common(2)],
        })
    return rows


def chart_svg(rows, title, reference=None):
    """Horizontal pass-rate bars, one per scenario, readable on light and dark GitHub themes.
    With a reference run, a thin gray bar under each scenario shows its earlier score."""
    reference = reference or {}
    bar_w, left, row_h, top = 520, 150, 34 if reference else 30, 64
    height = top + row_h * len(rows) + 40
    def color(v):
        return "#2ea043" if v >= .8 else "#d29922" if v >= .5 else "#f85149"
    total_w = 840 if reference else 760
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {height}" font-family="Segoe UI, Helvetica, Arial, sans-serif">',
           f'<rect width="{total_w}" height="{height}" rx="16" fill="#0d1420"/>',
           f'<text x="24" y="36" fill="#ffffff" font-size="18" font-weight="700">{title}</text>',
           '<text x="24" y="54" fill="#8fa3bf" font-size="12">Share of runs with the exact cart and the correct review decision</text>']
    for i, r in enumerate(rows):
        y = top + i * row_h
        w = max(2, bar_w * r["pass_rate"])
        tag = "#ffbb71" if r["group"] == "classic" else "#bd9aff"
        out += [f'<circle cx="30" cy="{y + 12}" r="4" fill="{tag}"/>',
                f'<text x="42" y="{y + 16}" fill="#c9d4e3" font-size="13">{r["scenario"]}</text>',
                f'<rect x="{left}" y="{y + 3}" width="{bar_w}" height="18" rx="5" fill="#1b2638"/>',
                f'<rect x="{left}" y="{y + 3}" width="{w:.0f}" height="18" rx="5" fill="{color(r["pass_rate"])}"/>',
                f'<text x="{left + bar_w + 12}" y="{y + 16}" fill="#ffffff" font-size="13" font-weight="600">{r["pass_rate"] * 100:.0f}%</text>']
        if r["scenario"] in reference:
            before = reference[r["scenario"]]
            out += [f'<rect x="{left}" y="{y + 24}" width="{max(2, bar_w * before):.0f}" height="5" rx="2" fill="#5b6b82"/>',
                    f'<text x="{left + bar_w + 56}" y="{y + 16}" fill="#8fa3bf" font-size="12">was {before * 100:.0f}%</text>']
    y = top + row_h * len(rows) + 22
    out += [f'<circle cx="30" cy="{y - 4}" r="4" fill="#ffbb71"/><text x="42" y="{y}" fill="#8fa3bf" font-size="12">classic scenario</text>',
            f'<circle cx="170" cy="{y - 4}" r="4" fill="#bd9aff"/><text x="182" y="{y}" fill="#8fa3bf" font-size="12">messy scenario</text>']
    if reference:
        out.append(f'<rect x="300" y="{y - 7}" width="24" height="5" rx="2" fill="#5b6b82"/><text x="332" y="{y}" fill="#8fa3bf" font-size="12">reference run</text>')
    out.append('</svg>')
    return "\n".join(out)


def markdown(summary, rows, chart_path, reference=None, reference_label=None):
    def dot(v):
        return "🟢" if v >= .8 else "🟡" if v >= .5 else "🔴"
    lines = [
        "# 📊 Benchmark", "",
        "<!-- Generated by training/benchmark.py. Edit the script, not this file. -->", "",
        f"**{summary['label']}** · {summary['runs']} recorded runs · {summary['passed']} passed "
        f"({summary['pass_rate'] * 100:.0f}%) · median latency {summary['latency_ms_median']} ms per frame", "",
        f"![Pass rate by scenario]({chart_path})", "",
        "A run **passes** when the final cart is exactly right *and* checkout is blocked only when it should be "
        "(the unknown package). Every run is synthetic and was rendered offline by Unity from a fixed seed, so it can be "
        "reproduced exactly. See [training.md](training.md#-scenario-benchmark) for how to record and score runs.", "",
        f"Cameras: **{', '.join(summary['cameras'])}** · coordinates: **{'calibrated carry-height plane' if summary['world_mode'] else 'lane image'}** "
        f"· seeds: **{', '.join(map(str, summary.get('seeds', [])))}**. "
        "Model and source hashes are recorded in the JSON report. "
        "Identity switches, phantom counts and detection recall are scored against **lane-camera annotations only**; "
        "an overhead-only observation can therefore count as a phantom. Exact-cart and review scores use the complete fused output.", "",
        *([f"Compared with **{reference_label}** on the same recordings: "
           f"{reference['summary']['passed']} → {summary['passed']} runs passed. The gray bars and *was* column show the reference.", ""]
          if reference else []),
        "| | Scenario | Pass | Exact cart | False adds | Missed | ID switches / run | Phantom objects / run | Blocked for review | Detection recall | By barcode | Assist items |",
        "|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|",
    ]
    before = {r["scenario"]: r["pass_rate"] for r in reference["scenarios"]} if reference else {}
    for r in rows:
        was = f" <sub>was {before[r['scenario']] * 100:.0f}%</sub>" if r["scenario"] in before else ""
        lines.append(f"| {dot(r['pass_rate'])} | **{r['scenario']}**<br><sub>{r['description']}</sub> | "
                     f"{r['pass_rate'] * 100:.0f}%{was} | {r['exact_cart_rate'] * 100:.0f}% | {r['false_adds']} | {r['missed_items']} | "
                     f"{r['id_switches_per_run']} | {r['phantom_objects_per_run']} | {r['review_rate'] * 100:.0f}% | {r['detection_recall'] * 100:.0f}% | "
                     f"{r.get('barcode_share', 0) * 100:.0f}% | {r.get('assist_items', 0)} |")
    lines += ["", "## 🔎 Why runs fail", "",
              "The most common review reasons the ledger reported, per scenario:", ""]
    for r in rows:
        if r["top_review_reasons"] and r["pass_rate"] < 1:
            lines.append(f"- **{r['scenario']}**: " + "; ".join(r["top_review_reasons"]))
    lines += ["", "## 📖 Column guide", "",
              "| Column | Meaning |", "|---|---|",
              "| False adds / Missed | Units charged that weren't purchased / purchased units that weren't charged, summed over runs |",
              "| ID switches | Times a real box's matched canonical object ID changed. Lower means steadier identity. |",
              "| Phantom objects | Canonical objects that never matched a real product, usually distractors or occluders detected as merchandise |",
              "| Blocked for review | Share of runs that ended needing an associate or still waiting on an item |",
              "| By barcode | Share of charged items whose SKU came from a decoded barcode. The rest were recognized by look. |",
              "| Assist items | Items handed to an associate (unscanned, unknown barcode, conflicting evidence), summed over runs |",
              "| Detection recall | Share of frames where an in-frame product was matched to a tracked detection (amodal boxes, IoU ≥ 0.3), so heavy occlusion lowers it |",
              ""]
    return "\n".join(lines)


_worker_engine = None


def _worker_start(models, config, cameras, image_mode):
    """Each scoring process loads its own copy of the models once."""
    global _worker_engine
    from vision.engine import VisionEngine
    _worker_engine = VisionEngine(ROOT / "catalog.json", models, config, cameras, world_mode=False if image_mode else None)


def _worker_score(run_dir):
    return score_run(_worker_engine, run_dir)


def main():
    from vision.engine import VisionEngine
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts" / "benchmark")
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--scenario", action="append", help="limit to these scenarios (repeatable)")
    parser.add_argument("--config", type=Path, default=ROOT / "vision" / "config.json")
    parser.add_argument("--output", type=Path, default=None, help="default: models/benchmark-<label>.json")
    parser.add_argument("--docs", action="store_true", help="also write docs/benchmark.md and its chart")
    parser.add_argument("--models", type=Path, default=ROOT / "models", help="directory holding detector.pt and classifier.pt")
    parser.add_argument("--cameras", help="comma-separated camera ids (default: from the config)")
    parser.add_argument("--image-mode", action="store_true", help="ignore calibration: lane camera, image-space zones")
    parser.add_argument("--compare", type=Path, help="earlier benchmark JSON to show alongside (docs only)")
    parser.add_argument("--workers", type=int, default=1,
                        help="score this many runs at once, each in its own process (about 0.5 GB of GPU memory each); "
                             "results are identical, but per-frame latency is only meaningful with 1")
    args = parser.parse_args()
    provenance = {"recording_root": str(args.root.resolve()),
                  "weights_sha256": {name: hashlib.sha256((ROOT / "models" / name).read_bytes()).hexdigest()
                                     for name in ("detector.pt", "classifier.pt")},
                  "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                    for name in ("vision/engine.py", "vision/ledger.py", "vision/geometry.py", "vision/rejection.py",
                                                 "vision/config.json", "vision/cameras.json")
                                    if (ROOT / name).exists()},
                  "config_path": str(args.config.resolve()),
                  "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest()}
    cameras = ["lane"] if args.image_mode else args.cameras.split(",") if args.cameras else None
    engine = VisionEngine(ROOT / "catalog.json", args.models, args.config, cameras,
                          world_mode=False if args.image_mode else None)
    if not engine.status()["ready"]:
        raise SystemExit(engine.status()["error"])
    run_dirs = sorted(p.parent for p in args.root.glob("*/*/run.json"))
    if args.scenario:
        run_dirs = [p for p in run_dirs if p.parent.name in args.scenario]
    if not run_dirs:
        raise SystemExit(f"No recorded runs under {args.root}. Record them in Unity first (docs/training.md).")
    def report(result):
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"{mark}  {result['run_id']:<24} expected {result['expected_cart']}  got {result['predicted_cart']}  "
              f"review {result['review_required']}  switches {result['id_switches']}", flush=True)
        return result

    if args.workers > 1:
        import multiprocessing
        del engine
        with multiprocessing.get_context("spawn").Pool(args.workers, _worker_start, (args.models, args.config, cameras, args.image_mode)) as pool:
            runs = [report(r) for r in pool.imap(_worker_score, run_dirs)]
        engine = VisionEngine(ROOT / "catalog.json", args.models, args.config, cameras, world_mode=False if args.image_mode else None)
    else:
        runs = [report(score_run(engine, run_dir)) for run_dir in run_dirs]
    rows = summarize(runs)
    latencies = [r["latency_ms_median"] for r in runs if r["latency_ms_median"] is not None]
    summary = {"label": args.label, "runs": len(runs), "passed": sum(r["passed"] for r in runs),
               "pass_rate": round(sum(r["passed"] for r in runs) / len(runs), 3),
               "latency_ms_median": round(statistics.median(latencies), 1) if latencies else None,
               "domain": "Unity synthetic, offline-rendered seeded scenarios; RGB-only inference",
               "runtime_ground_truth": False, "cameras": engine.camera_ids,
               "world_mode": engine.calibration is not None, "config": json.loads(args.config.read_text()),
               "seeds": sorted({r["seed"] for r in runs}), "provenance": provenance}
    output = args.output or ROOT / "models" / f"benchmark-{args.label}.json"
    output.write_text(json.dumps({"summary": summary, "scenarios": rows, "runs": runs}, indent=2))
    print(json.dumps(summary, indent=2))
    if args.docs:
        reference = json.loads(args.compare.read_text()) if args.compare else None
        if reference and {(r["run_id"], r["seed"]) for r in reference["runs"]} != {(r["run_id"], r["seed"]) for r in runs}:
            raise SystemExit("Comparison requires the same recorded runs and seeds; report saved, docs not changed")
        ref_rates = {r["scenario"]: r["pass_rate"] for r in reference["scenarios"]} if reference else None
        ref_label = reference["summary"]["label"] if reference else None
        (ROOT / "docs" / "images" / "benchmark.svg").write_text(chart_svg(rows, f"Benchmark · {args.label}", ref_rates))
        (ROOT / "docs" / "benchmark.md").write_text(markdown(summary, rows, "images/benchmark.svg", reference, ref_label))
        print("Wrote docs/benchmark.md and docs/images/benchmark.svg")


if __name__ == "__main__":
    main()
