"""Exercise a running Unity -> RGB inference -> checkout system.

This changes only local, disposable simulation runs. Expected quantities are
test assertions; they are never sent to the vision pipeline.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]


def request(path, body=None):
    req = urllib.request.Request(BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "evaluation-live.json")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    reports = request("/api/reports")
    report = {"domain": "live Unity simulation, RGB-only learned inference",
              "scenarios": [], "runtime_ground_truth": False,
              "cameras": reports.get("cameras", ["lane"]),
              "weights_sha256": {name: reports.get("manifest", {}).get(name, {}).get("sha256")
                                 for name in ("detector", "classifier")}}
    cases = [("single", {"PEX-001": 1}, 15, False),
             ("duplicate", {"PEX-001": 2}, 15, False),
             ("mixed", {"PEX-001": 1, "PEX-003": 1, "PEX-005": 1}, 15, False),
             ("occlusion", {"PEX-001": 1}, 15, False),
             ("remove", {}, 29, False), ("unknown", {}, 15, True)]
    for scenario, expected, end_time, expected_review in cases:
        request("/api/scenario", {"scenario": scenario})
        run_id = request("/api/snapshot")["session"]["run_id"]
        print(f"Recording {scenario} run {run_id}", flush=True)
        deadline = time.monotonic() + 55
        interim = None
        while True:
            snapshot = request("/api/snapshot")
            frame = snapshot.get("frame")
            if frame and frame["run_id"] == run_id:
                if scenario == "remove" and 14 <= frame["timestamp"] <= 16:
                    interim = {item["sku"]: item["quantity"] for item in snapshot["cart"]["items"]}
                if frame["timestamp"] >= end_time:
                    break
            if time.monotonic() > deadline:
                raise RuntimeError(f"Unity did not finish {scenario}; check Play mode and API connection")
            time.sleep(.4)
        actual = {item["sku"]: item["quantity"] for item in snapshot["cart"]["items"]}
        passed = actual == expected and snapshot["review_required"] == expected_review and not snapshot["error"]
        configured = snapshot.get("cameras", ["lane"])
        frames = snapshot.get("frames", {"lane": frame})
        synchronized = (set(frames) == set(configured) and
                        all(f["run_id"] == run_id and f["frame_id"] == frame["frame_id"]
                            for f in frames.values()))
        calibrated = (len(configured) == 1 or
                      bool(snapshot.get("geometry") and snapshot["vision"].get("world_mode")))
        passed = passed and synchronized and calibrated
        if scenario == "remove":
            passed = passed and interim == {"PEX-002": 1}
        record = dict(scenario=scenario, run_id=run_id, expected_cart=expected,
                      actual_cart=actual, expected_review=expected_review,
                      review_required=snapshot["review_required"], passed=passed,
                      synchronized_cameras=synchronized, calibrated_mode=calibrated,
                      frames=frames,
                      frame=frame, interim_cart=interim, events=snapshot["events"],
                      objects=snapshot["objects"], metrics=snapshot["metrics"], error=snapshot["error"])
        report["scenarios"].append(record)
        args.output.write_text(json.dumps(report, indent=2))
        print(json.dumps({"scenario": scenario, "passed": passed, "cart": actual,
                          "review": snapshot["review_required"], "pipeline_ms": snapshot["metrics"].get("pipeline_ms")}), flush=True)
    report["passed"] = sum(case["passed"] for case in report["scenarios"])
    report["total"] = len(cases)
    args.output.write_text(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] == len(cases) else 1)


if __name__ == "__main__":
    main()
