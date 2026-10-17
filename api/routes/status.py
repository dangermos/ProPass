"""Read-only endpoints: health, snapshot, catalog, measured reports and pipeline progress."""
import json

from fastapi import APIRouter

from ..progress import progress
from ..runtime import ROOT
from ..store import SCENARIOS


def router(runtime):
    api = APIRouter()

    @api.get("/api/health")
    async def health():
        async with runtime.lock:
            snapshot = runtime.snapshot()
            return {"status": "ok", "simulation_only": True, "vision": snapshot["vision"], "latest_frame_age_ms": snapshot["frame"]["age_ms"] if snapshot["frame"] else None, "error": runtime.error}

    @api.get("/api/snapshot")
    async def snapshot():
        async with runtime.lock:
            return runtime.snapshot()

    @api.get("/api/catalog")
    async def catalog():
        return {"currency": runtime.store.currency, "products": list(runtime.store.products.values()), "demo": True}

    @api.get("/api/reports")
    async def reports():
        """Measured results for the dashboard's Models and Benchmark tabs (read-only files)."""
        def load(name):
            path = ROOT / "models" / name
            return json.loads(path.read_text()) if path.exists() else None
        def scenarios(report):
            return report and {"summary": report["summary"], "scenarios": report["scenarios"]}
        return {"manifest": load("manifest.json"), "static": load("evaluation-static-test.json"),
                "live": load("evaluation-live-c.json") or load("evaluation-live.json"),
                "benchmark": scenarios(load("benchmark-v3-test.json") or load("benchmark-v2-test.json") or load("benchmark-c-final-test.json") or load("benchmark-final-test.json")),
                "benchmark_reference": scenarios(load("benchmark-c-world-1cam-test.json") or load("benchmark-baseline-test.json")),
                "config": json.loads((ROOT / "vision" / "config.json").read_text()),
                "cameras": list(runtime.camera_ids), "geometry": runtime.geometry()}

    @api.get("/api/progress")
    async def pipeline_progress():
        """Where the offline pipeline is: export, training, benchmark recording and scoring (read-only)."""
        return progress(ROOT, len(SCENARIOS))

    @api.get("/api/simulator/control")
    async def control():
        async with runtime.lock:
            return dict(runtime.store.snapshot()["simulator"], paused=runtime.paused)

    return api
