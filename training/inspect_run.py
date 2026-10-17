"""Write a development-only RGB inference trace for diagnosis.

Ground truth is not passed into the engine. This tool refuses held-out benchmark
roots so diagnostic tuning stays separate from final scoring.
"""
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .benchmark import ROOT


def main():
    import cv2
    import torch

    from vision.engine import VisionEngine
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--config", type=Path, default=ROOT / "vision/config.json")
    args = parser.parse_args()
    if "benchmark-test" in str(args.run.resolve()):
        raise SystemExit("Use development recordings for diagnostic tuning")
    torch.set_num_threads(4)
    engine = VisionEngine(ROOT / "catalog.json", ROOT / "models", args.config)
    if args.device == "cpu":
        engine.device = "cpu"
        engine.classifier.to("cpu")
        if engine.prototypes is not None:
            engine.prototypes = engine.prototypes.to("cpu")
        if engine.prototype_bank is not None:
            engine.prototype_bank = engine.prototype_bank.to("cpu")
    info = json.loads((args.run / "run.json").read_text())
    engine.reset(info["run_id"])
    original_observe = engine._observe
    seen = []

    def observe(camera, image):
        observations = original_observe(camera, image)
        for obs in observations:
            data = asdict(obs)
            data.pop("embedding")
            seen.append(data)
        return observations

    engine._observe = observe
    trace = []
    for path in sorted(p for p in args.run.glob("*.jpg") if "." not in p.stem):
        record = json.loads(path.with_suffix(".json").read_text())
        images = {camera: cv2.imread(str(path if camera == "lane" else path.with_suffix(f".{camera}.jpg")))
                  for camera in engine.camera_ids}
        seen.clear()
        output = engine.process_frames(images, record["frame_id"], record["timestamp"], info["run_id"])
        trace.append({"frame_id": record["frame_id"], "timestamp": record["timestamp"],
                      "observations": list(seen), "objects": output["objects"],
                      "events": output["events"], "review_required": output["review_required"]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"run_id": info["run_id"], "trace": trace}, indent=2))
    print(f"Wrote {len(trace)} development frames to {args.output}")


if __name__ == "__main__":
    main()
