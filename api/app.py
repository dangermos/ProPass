"""Local simulation API. Pixel-only input; no simulator labels enter inference.

This module is the app factory. The session runtime is in runtime.py and the endpoints are in
routes/ (status, frames, session, replay, assist) and ws.py.
"""
import asyncio
import json
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from . import ws
from .routes import assist, frames, replay, session, status
from .runtime import ROOT, FrameGroup, Runtime, default_vision_factory
from .store import Store

__all__ = ["FrameGroup", "RECORDINGS", "Runtime", "app", "create_app", "default_vision_factory"]

# Recorded runs that /api/replay plays through the live pipeline: one seed of every scenario.
RECORDINGS = Path(os.environ.get("PROPASS_RECORDINGS", ROOT / "artifacts" / "benchmark"))


def create_app(database_url=None, vision_factory: Callable | None = None, camera_ids=None):
    db_url = database_url or os.environ.get("PROPASS_DATABASE_URL", f"sqlite:///{ROOT / 'artifacts' / 'propass.db'}")
    (ROOT / "artifacts").mkdir(exist_ok=True)
    if camera_ids is None:
        config = json.loads((ROOT / "vision" / "config.json").read_text())
        # Tracking cameras first, then the barcode scan cameras: one capture group holds them all.
        camera_ids = config.get("cameras", ["lane"]) + config.get("scan_cameras", [])
    if not camera_ids or len(set(camera_ids)) != len(camera_ids) or any(not isinstance(camera, str) or not camera for camera in camera_ids):
        raise ValueError("Configure a nonempty list of unique camera IDs")
    runtime = Runtime(Store(db_url, ROOT / "catalog.json"), vision_factory or default_vision_factory, camera_ids, RECORDINGS)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(runtime.worker())
        yield
        if runtime.replay_task:
            runtime.replay_task.cancel()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        runtime.store.engine.dispose()

    app = FastAPI(title="ProPass local simulation", lifespan=lifespan)
    app.state.runtime = runtime
    for module in (status, frames, session, replay, assist, ws):
        app.include_router(module.router(runtime))
    return app


app = create_app()
