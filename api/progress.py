"""Read-only progress of the offline pipeline: data export, training, benchmark recording, scoring.

Nothing here starts or controls work. It only reads the files those steps already write, so the
dashboard's Training tab can show where a run is.
"""
import json
from pathlib import Path
import re
import time

STAGES = [("lane", "detector"), ("lane", "classifier"), ("overhead", "detector"), ("overhead", "classifier")]
DETECTOR_DONE, CLASSIFIER_DONE = '"architecture"', "Unity synthetic crop splits"


def _json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _age(path):
    return round(time.time() - path.stat().st_mtime) if path.exists() else None


def _training(root):
    logs = sorted((root / "artifacts" / "logs").glob("train-*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        return {"log": None, "stages": [], "active": False}
    log = logs[-1]
    text = log.read_text(errors="replace")
    detectors, classifiers = text.count(DETECTOR_DONE), text.count(CLASSIFIER_DONE)
    done = min(detectors, classifiers) * 2 + (1 if detectors > classifiers else 0)
    tail = text[-6000:].replace("\r", "\n")
    stages = []
    for index, (camera, kind) in enumerate(STAGES):
        stage = {"camera": camera, "model": kind, "state": "done" if index < done else "waiting", "epoch": None, "epochs": None}
        if index == done:
            if kind == "detector":
                epochs = re.findall(r"^\s*(\d+)/(\d+)\s+[\d.]+G", tail, re.M)
                if epochs:
                    stage.update(state="running", epoch=int(epochs[-1][0]), epochs=int(epochs[-1][1]))
            else:
                epochs = re.findall(r'^\{"epoch": (\d+)', tail, re.M)
                if epochs:
                    stage.update(state="running", epoch=int(epochs[-1]), epochs=12)
        stages.append(stage)
    age = _age(log)
    # A log that stopped changing is a finished or interrupted run, not a live one.
    active = done < len(STAGES) and age is not None and age < 120
    if not active:
        for stage in stages:
            if stage["state"] == "running":
                stage["state"] = "stopped"
    return {"log": log.name, "age_seconds": age, "stages": stages, "active": active, "finished": done >= len(STAGES)}


def _recordings(root, folder, expected):
    directory = root / "artifacts" / folder
    runs = sorted(directory.glob("*/*/run.json"), key=lambda p: p.stat().st_mtime) if directory.exists() else []
    latest = runs[-1] if runs else None
    return {"folder": folder, "recorded": len(runs), "expected": expected,
            "latest": f"{latest.parent.parent.name} · {latest.parent.name}" if latest else None,
            "age_seconds": _age(latest) if latest else None}


def _score(root, name):
    path = root / "models" / name
    report = _json(path)
    if not report:
        return {"file": name, "available": False}
    summary = report["summary"]
    return {"file": name, "available": True, "label": summary.get("label"), "passed": summary.get("passed"),
            "runs": summary.get("runs"), "age_seconds": _age(path)}


def _models(root):
    result = []
    for camera, folder in (("lane", root / "models"), ("overhead", root / "models" / "overhead")):
        manifest = _json(folder / "manifest.json") or {}
        result.append({"camera": camera, "age_seconds": _age(folder / "classifier.pt"),
                       "detector_map": (manifest.get("detector", {}).get("test") or {}).get("map50_95"),
                       "classifier_accuracy": (manifest.get("classifier", {}).get("test") or {}).get("accuracy")})
    return result


def progress(root: Path, scenarios: int):
    export = _json(root / "training" / "data" / "export-progress.json") or {}
    expected = scenarios * 5
    models = _models(root)
    # The newest round that has a report: v3 is carts, v2 is characters.
    scores = [next((s for s in (_score(root, f"benchmark-{v}-{split}.json") for v in ("v3", "v2")) if s["available"]),
                   _score(root, f"benchmark-v2-{split}.json")) for split in ("dev", "test")]
    trained = min((m["age_seconds"] for m in models if m["age_seconds"] is not None), default=None)
    for score in scores:
        # A score written before the newest weights describes the previous models.
        score["stale"] = bool(score["available"] and trained is not None and score["age_seconds"] > trained)
    return {
        "export": {"completed": export.get("completed", 0), "total": export.get("total", 0),
                   "running": bool(export.get("running")), "error": export.get("error") or None,
                   "age_seconds": _age(root / "training" / "data" / "export-progress.json")},
        "training": _training(root),
        "recordings": [_recordings(root, "benchmark", expected), _recordings(root, "benchmark-test", expected)],
        "scores": scores,
        "models": models,
    }
