"""Local simulation API. Pixel-only input; no simulator labels enter inference."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import time
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .store import CheckoutConflict, SCENARIOS, Store

ROOT = Path(__file__).resolve().parents[1]


class ScenarioRequest(BaseModel):
    scenario: str


class CustomerRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=80)


class ConfirmationRequest(BaseModel):
    version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=100)


def default_vision_factory():
    from vision.engine import VisionEngine
    return VisionEngine(str(ROOT / "catalog.json"), str(ROOT / "models"))


class Runtime:
    def __init__(self, store, vision_factory):
        self.store = store
        self.vision_factory = vision_factory
        self.vision = None
        self.vision_run_id = None
        self.lock = asyncio.Lock()
        self.queue = asyncio.Queue(maxsize=2)
        self.paused = False
        self.loading = False
        self.error = None
        self.result = {}
        self.frame = None
        self.frames = {}
        self.last_accepted_id = -1
        self.last_received_at = None
        self.dropped_frames = 0
        self.processed_frames = 0
        self.clients = set()

    def vision_status(self):
        if self.vision is not None:
            return self.vision.status()
        return {"ready": False, "mode": "loading" if self.loading else "awaiting_frames", "message": self.error or "Waiting for Unity frames. Recognition initializes on the first image."}

    def snapshot(self):
        state = self.store.snapshot()
        state["simulator"]["paused"] = self.paused
        state["vision"] = self.vision_status()
        state["frame"] = dict(self.frame) if self.frame else None
        if state["frame"]:
            state["frame"]["age_ms"] = round((time.monotonic() - self.frame["received_at"]) * 1000)
            state["frame"].pop("received_at", None)
        state["detections"] = self.result.get("detections", [])
        state["objects"] = self.result.get("objects", [])
        state["review_required"] = bool(self.result.get("review_required", False) or self.error)
        state["metrics"] = dict(self.result.get("metrics", {}), processed_frames=self.processed_frames, dropped_frames=self.dropped_frames, queue_depth=self.queue.qsize())
        state["error"] = self.error
        state["demo"] = True
        return state

    async def publish(self):
        async with self.lock:
            state = self.snapshot()
        dead = []
        for client in tuple(self.clients):
            try:
                await asyncio.wait_for(client.send_json(state), timeout=0.5)
            except Exception:
                dead.append(client)
        for client in dead:
            self.clients.discard(client)

    def _infer(self, payload, frame_id, timestamp, run_id):
        import cv2
        import numpy as np
        image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Frame is not a valid JPEG image")
        if image.shape[0] > 2160 or image.shape[1] > 3840:
            raise ValueError("Frame exceeds the supported 3840 × 2160 image bounds")
        if self.vision is None:
            self.vision = self.vision_factory()
        if self.vision_run_id != run_id:
            self.vision.reset(run_id)
            self.vision_run_id = run_id
        result = self.vision.process_frame(image, frame_id, timestamp, run_id)
        return result, image.shape[1], image.shape[0]

    async def worker(self):
        while True:
            payload, frame_id, timestamp, run_id, received_at = await self.queue.get()
            try:
                async with self.lock:
                    current_run = self.store.snapshot()["session"]["run_id"]
                    if current_run != run_id:
                        continue
                    self.loading = self.vision is None
                started = time.perf_counter()
                result, width, height = await asyncio.to_thread(self._infer, payload, frame_id, timestamp, run_id)
                async with self.lock:
                    if self.store.apply_result(result):
                        self.result = result
                        self.error = None
                        self.processed_frames += 1
                        self.frames[(run_id, frame_id)] = payload
                        while len(self.frames) > 4:
                            del self.frames[next(iter(self.frames))]
                        self.frame = dict(frame_id=frame_id, timestamp=timestamp, run_id=run_id, width=width, height=height, received_at=received_at, url=f"/api/frame?run_id={run_id}&frame_id={frame_id}")
                        self.result.setdefault("metrics", {})["pipeline_ms"] = round((time.perf_counter() - started) * 1000, 1)
            except Exception as exc:
                async with self.lock:
                    if self.store.snapshot()["session"]["run_id"] == run_id:
                        self.error = f"Vision processing failed: {exc}"
            finally:
                self.loading = False
                self.queue.task_done()
                await self.publish()


def create_app(database_url=None, vision_factory: Callable | None = None):
    db_url = database_url or os.environ.get("PROPASS_DATABASE_URL", f"sqlite:///{ROOT / 'artifacts' / 'propass.db'}")
    (ROOT / "artifacts").mkdir(exist_ok=True)
    runtime = Runtime(Store(db_url, ROOT / "catalog.json"), vision_factory or default_vision_factory)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(runtime.worker())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        runtime.store.engine.dispose()

    app = FastAPI(title="ProPass local simulation", lifespan=lifespan)
    app.state.runtime = runtime

    @app.get("/api/health")
    async def health():
        async with runtime.lock:
            snapshot = runtime.snapshot()
            return {"status": "ok", "simulation_only": True, "vision": snapshot["vision"], "latest_frame_age_ms": snapshot["frame"]["age_ms"] if snapshot["frame"] else None, "error": runtime.error}

    @app.get("/api/snapshot")
    async def snapshot():
        async with runtime.lock:
            return runtime.snapshot()

    @app.get("/api/catalog")
    async def catalog():
        return {"currency": runtime.store.currency, "products": list(runtime.store.products.values()), "demo": True}

    @app.get("/api/simulator/control")
    async def control():
        async with runtime.lock:
            return dict(runtime.store.snapshot()["simulator"], paused=runtime.paused)

    @app.post("/api/frames")
    async def frames(request: Request, frame_id: int, timestamp: float, run_id: str):
        if frame_id < 0 or timestamp < 0:
            raise HTTPException(422, "Frame ID and capture timestamp must be nonnegative")
        if request.headers.get("content-type", "").split(";")[0] != "image/jpeg":
            raise HTTPException(415, "Send raw JPEG pixels with Content-Type: image/jpeg")
        length = request.headers.get("content-length")
        if length and int(length) > 8 * 1024 * 1024:
            raise HTTPException(413, "JPEG frame exceeds 8 MiB")
        payload = await request.body()
        if len(payload) > 8 * 1024 * 1024:
            raise HTTPException(413, "JPEG frame exceeds 8 MiB")
        if not payload.startswith(b"\xff\xd8"):
            raise HTTPException(422, "Expected JPEG encoded pixels")
        async with runtime.lock:
            current = runtime.store.snapshot()
            if current["session"]["run_id"] != run_id:
                raise HTTPException(409, "Stale simulator run. Poll /api/simulator/control again.")
            if runtime.paused or current["cart"]["status"] == "CONFIRMED":
                raise HTTPException(409, "Capture is paused for checkout review")
            if frame_id <= runtime.last_accepted_id:
                return {"accepted": False, "reason": "duplicate_or_out_of_order", "frame_id": frame_id}
            runtime.last_accepted_id = frame_id
            received_at = time.monotonic()
            runtime.last_received_at = received_at
            if runtime.queue.full():
                runtime.queue.get_nowait()
                runtime.queue.task_done()
                runtime.dropped_frames += 1
            runtime.queue.put_nowait((payload, frame_id, timestamp, run_id, received_at))
        return {"accepted": True, "frame_id": frame_id, "queue_depth": runtime.queue.qsize()}

    @app.get("/api/frame")
    async def frame(run_id: str | None = None, frame_id: int | None = None):
        async with runtime.lock:
            if not runtime.frame:
                raise HTTPException(404, "No processed frame yet")
            key = (run_id or runtime.frame["run_id"], frame_id if frame_id is not None else runtime.frame["frame_id"])
            payload = runtime.frames.get(key)
            if payload is None:
                raise HTTPException(404, "Frame has advanced. Refresh the snapshot.")
        return Response(payload, media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Frame-ID": str(key[1])})

    async def reset_run(scenario):
        async with runtime.lock:
            run_id = runtime.store.reset(scenario)
            runtime.paused = False
            runtime.result, runtime.frames, runtime.frame = {}, {}, None
            runtime.error = None
            runtime.last_accepted_id = -1
            while not runtime.queue.empty():
                runtime.queue.get_nowait()
                runtime.queue.task_done()
            # Inference owns its tracker on one worker thread. reset is deferred to
            # process_frame's run switch, never called concurrently with inference.
            state = runtime.snapshot()
        await runtime.publish()
        return state

    @app.post("/api/scenario")
    async def scenario(body: ScenarioRequest):
        if body.scenario not in SCENARIOS:
            raise HTTPException(422, "Unknown checkout scenario")
        return await reset_run(body.scenario)

    @app.post("/api/cart/reset")
    async def reset():
        async with runtime.lock:
            scenario_name = runtime.store.snapshot()["simulator"]["scenario"]
        return await reset_run(scenario_name)

    @app.post("/api/session")
    async def session(body: CustomerRequest):
        if not body.customer_name.strip():
            raise HTTPException(422, "A demo customer name is required")
        async with runtime.lock:
            try:
                runtime.store.bind_customer(body.customer_name.strip())
            except CheckoutConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            runtime.paused = False
            state = runtime.snapshot()
        await runtime.publish()
        return state

    @app.post("/api/cart/resume")
    async def resume():
        async with runtime.lock:
            if runtime.store.snapshot()["cart"]["status"] == "CONFIRMED":
                raise HTTPException(409, "Start a new scenario after confirmation")
            runtime.store.abort_prepare()
            runtime.paused = False
            state = runtime.snapshot()
        await runtime.publish()
        return state

    @app.post("/api/cart/prepare")
    async def prepare():
        async with runtime.lock:
            if not runtime.frame:
                raise HTTPException(409, "Wait for the first processed Unity frame")
            if runtime.error or not runtime.vision_status().get("ready", False):
                raise HTTPException(409, runtime.error or "The vision checkpoint is not ready")
            try:
                run_id = runtime.store.begin_prepare()
            except CheckoutConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            runtime.paused = True
        await runtime.publish()
        try:
            await asyncio.wait_for(runtime.queue.join(), timeout=30)
        except asyncio.TimeoutError:
            return Response(status_code=202, content='{"pending":true,"message":"Draining accepted camera frames"}', media_type="application/json")
        async with runtime.lock:
            conflict = None
            try:
                if runtime.store.snapshot()["session"]["run_id"] != run_id or runtime.frame is None:
                    raise CheckoutConflict("The checkout session changed during preparation")
                if runtime.error:
                    runtime.store.abort_prepare()
                    raise CheckoutConflict(runtime.error)
                runtime.store.finish_prepare(run_id, runtime.frame["frame_id"], bool(runtime.result.get("review_required", False)))
            except CheckoutConflict as exc:
                conflict = str(exc)
            state = runtime.snapshot()
        await runtime.publish()
        if conflict:
            raise HTTPException(409, conflict)
        return state

    @app.post("/api/cart/confirm")
    async def confirm(body: ConfirmationRequest):
        async with runtime.lock:
            state = runtime.store.snapshot()
            try:
                receipt = runtime.store.confirm(body.version, body.idempotency_key, state["session"]["run_id"], bool(runtime.result.get("review_required", False) or runtime.error))
            except CheckoutConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            runtime.paused = True
        await runtime.publish()
        return receipt

    @app.websocket("/api/ws")
    async def websocket(socket: WebSocket):
        await socket.accept()
        runtime.clients.add(socket)
        try:
            async with runtime.lock:
                await socket.send_json(runtime.snapshot())
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            runtime.clients.discard(socket)

    return app


app = create_app()
