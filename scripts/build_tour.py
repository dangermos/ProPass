"""Build the browser scene tour: one short video and one decision timeline per scenario.

Each recorded development run (seed 2 of every scenario, pass or fail) goes through the
trained models exactly as the benchmark does. The three camera views are drawn into one
video with the boxes the system tracked, and what it decided is written beside it as JSON.
The dashboard plays these from web/public/tour with no API, GPU or Unity.

    .venv/bin/python scripts/build_tour.py            # all scenarios
    .venv/bin/python scripts/build_tour.py mixed      # one
"""
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RECORDINGS, OUT, SEED = ROOT / "artifacts/benchmark", ROOT / "web/public/tour", 2
# These scenes also get one full video per camera in web/public/angles, for the project page.
ANGLES = ("mixed", "lumber", "parked", "locked")
STATE_COLOR = {"ADDED": (94, 197, 34), "REVIEW": (2, 99, 249), "REMOVED": (140, 140, 140)}   # BGR
FONT = cv2.FONT_HERSHEY_SIMPLEX


class Video:
    """VP8 WebM at a fixed bitrate through ffmpeg when one is found (about 0.8 MB a scene);
    otherwise OpenCV's own VP9 writer, which works everywhere but makes files 3-5x larger."""
    def __init__(self, path, rate, size, bitrate="350k"):
        bundled = glob.glob(os.path.expanduser("~/.cache/ms-playwright/ffmpeg-*/ffmpeg-linux"))
        ffmpeg, codec = (shutil.which("ffmpeg"), "libvpx") if shutil.which("ffmpeg") else (bundled[0], "vp8") if bundled else (None, None)
        self.process = self.writer = None
        if ffmpeg:
            self.process = subprocess.Popen(
                [ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(rate), "-i", "/dev/stdin",
                 "-c:v", codec, "-b:v", bitrate, "-qmin", "4", "-qmax", "48", "-deadline", "good", "-cpu-used", "2", "-g", "80", str(path)],
                stdin=subprocess.PIPE)
        else:
            self.writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"VP90"), rate, size)

    def write(self, frame):
        if self.process:
            self.process.stdin.write(cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes())
        else:
            self.writer.write(frame)

    def release(self):
        if self.process:
            self.process.stdin.close()
            self.process.wait()
        else:
            self.writer.release()


def label(image, text, x, y, color):
    (w, h), _ = cv2.getTextSize(text, FONT, 0.5, 1)
    cv2.rectangle(image, (x, y - h - 8), (x + w + 8, y), color, -1)
    cv2.putText(image, text, (x + 4, y - 5), FONT, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


def title(image, text):
    label(image, text, 6, 26, (40, 34, 30))


def cart_lines(objects, names):
    lines = {}
    for o in objects:
        if o["state"] != "ADDED" or not o["sku"]:
            continue
        line = lines.setdefault(o["sku"], {"sku": o["sku"], "name": names.get(o["sku"], o["sku"]), "quantity": 0,
                                           "rating": o.get("rating"), "source": o.get("sku_source")})
        line["quantity"] += 1
    return sorted(lines.values(), key=lambda l: l["sku"])


def build(engine, scenario, names):
    run = RECORDINGS / scenario / f"seed_{SEED:02d}"
    info = json.loads((run / "run.json").read_text())
    engine.reset(info["run_id"])
    writer = Video(OUT / f"{scenario}.webm", info["frame_rate"], (1280, 450))
    angles = {}
    if scenario in ANGLES:
        (OUT.parent / "angles").mkdir(exist_ok=True)
        angles = {c: Video(OUT.parent / "angles" / f"{scenario}-{c}.webm", info["frame_rate"], size, bitrate)
                  for c, size, bitrate in (("lane", (960, 540), "450k"), ("overhead", (960, 540), "450k"), ("scan", (1920, 540), "700k"))}
    steps, notes, last, output = [], [], None, None
    for path in sorted(p for p in run.glob("*.jpg") if "." not in p.stem):
        record = json.loads(path.with_suffix(".json").read_text())
        images = {c: cv2.imread(str(path if c == "lane" else path.with_suffix(f".{c}.jpg")))
                  for c in engine.camera_ids + engine.scan_cameras}
        output = engine.process_frames({c: i for c, i in images.items() if i is not None},
                                       record["frame_id"], record["timestamp"], info["run_id"])
        views = {c: images[c].copy() for c in engine.camera_ids if images.get(c) is not None}
        objects = {o["object_id"]: o for o in output["objects"]}
        for d in output["detections"]:
            o, view = objects.get(d.get("object_id")), views.get(d.get("camera", "lane"))
            if o is None or view is None:
                continue
            color = STATE_COLOR.get(o["state"], (255, 168, 106))
            x1, y1, x2, y2 = (int(v) for v in d["bbox"])
            cv2.rectangle(view, (x1, y1), (x2, y2), color, 2)
            if d.get("camera", "lane") == "lane":
                label(view, names.get(o["sku"], "identifying") if o["sku"] else "identifying", x2 + 6, (y1 + y2)//2 + 10, color)
        lane = views["lane"]
        canvas = np.full((450, 1280, 3), (32, 26, 24), np.uint8)
        canvas[:, :800] = cv2.resize(lane, (800, 450), interpolation=cv2.INTER_AREA)
        title(canvas[:, :800], "Gate camera: detect, track, identify")
        if "overhead" in views:
            canvas[:270, 800:] = cv2.resize(views["overhead"], (480, 270), interpolation=cv2.INTER_AREA)
            title(canvas[:270, 800:], "Overhead camera")
        scan = images.get("scan")
        if scan is not None:
            scan = scan.copy()
            for b in output["barcodes"]:
                cv2.polylines(scan, [np.array(b["corners"], np.int32)], True, (94, 197, 34), 12)
            canvas[270:405, 800:] = cv2.resize(scan, (480, 135), interpolation=cv2.INTER_AREA)
            title(canvas[270:405, 800:], "Barcode camera" + (": label read" if output["barcodes"] else ""))
        writer.write(canvas)
        for c, video in angles.items():
            frame = scan if c == "scan" else views.get(c)
            if frame is not None:
                video.write(cv2.resize(frame, (1920, 540) if c == "scan" else (960, 540), interpolation=cv2.INTER_AREA))
        t = round(record["timestamp"], 2)
        for event in output["events"]:
            text = {"ITEM_ADDED": "Added to the cart", "ITEM_REMOVED": "Taken back out of the cart",
                    "SKU_RESOLVED": "Identified"}.get(event["type"])
            if text:
                notes.append({"t": t, "text": f"{text}: {names.get(event.get('sku'), event.get('sku') or 'item')}"})
        for b in output["barcodes"]:
            note = f"Barcode read: {names.get(b['sku'], 'not in the catalog')}"
            if not any(n["text"] == note for n in notes):
                notes.append({"t": t, "text": note})
        for o in output["objects"]:
            note = o.get("review_reason") and f"Needs an associate: {o['review_reason']}"
            if note and not any(n["text"] == note for n in notes):
                notes.append({"t": t, "text": note})
        state = {"lines": cart_lines(output["objects"], names)}
        if state != last:
            steps.append({"t": t, **state})
            last = state
    writer.release()
    for video in angles.values():
        video.release()
    expected = {l["sku"]: l["quantity"] for l in info.get("expected_cart", [])}
    final = {l["sku"]: l["quantity"] for l in (last or {"lines": []})["lines"]}
    exact = final == expected
    result = {"scenario": scenario, "seed": SEED, "description": info["description"], "duration": info["duration"],
              "expected": [{"sku": s, "name": names.get(s, s), "quantity": q} for s, q in expected.items()],
              "exact_cart": exact, "review_required": output["review_required"],
              "expected_review": info.get("expected_review", False),
              "passed": exact and output["review_required"] == info.get("expected_review", False),
              "steps": steps, "notes": notes}
    (OUT / f"{scenario}.json").write_text(json.dumps(result, separators=(",", ":")))
    print(f"{scenario:<12} {'PASS' if result['passed'] else 'handed off' if output['review_required'] else 'FAIL'}"
          f"  {len(steps)} cart states, {len(notes)} notes", flush=True)


def main():
    from vision.engine import VisionEngine
    catalog = json.loads((ROOT / "catalog.json").read_text())
    names = {p["sku"]: p["name"] for p in catalog["products"]}
    OUT.mkdir(parents=True, exist_ok=True)
    engine = VisionEngine(ROOT / "catalog.json", ROOT / "models", ROOT / "vision/config.json")
    wanted = sys.argv[1:] or sorted(p.name for p in RECORDINGS.iterdir() if (p / f"seed_{SEED:02d}").is_dir())
    for scenario in wanted:
        build(engine, scenario, names)


if __name__ == "__main__":
    main()
