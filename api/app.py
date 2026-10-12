"""Local simulation API. Pixel-only input; no simulator labels enter inference."""
import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import time
from typing import Callable
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .progress import progress
from .store import CheckoutConflict, SCENARIOS, Store

ROOT = Path(__file__).resolve().parents[1]
# Recorded runs that /api/replay plays through the live pipeline: one seed of every scenario.
RECORDINGS = Path(os.environ.get("PROPASS_RECORDINGS", ROOT / "artifacts" / "benchmark"))
REPLAY_SEED = "seed_02"


class ScenarioRequest(BaseModel):
    scenario: str


class CustomerRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=80)


class AssistAddRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    object_id: str | None = Field(default=None, max_length=100)


class AssistDismissRequest(BaseModel):
    object_id: str = Field(min_length=1, max_length=100)


class ConfirmationRequest(BaseModel):
    version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=100)


def default_vision_factory():
    from vision.engine import VisionEngine
    return VisionEngine(str(ROOT / "catalog.json"), str(ROOT / "models"), str(ROOT / "vision" / "config.json"))


@dataclass
class FrameGroup:
    """One capture instant; camera payloads never cross frame or run boundaries."""
    frame_id: int
    timestamp: float
    run_id: str
    received_at: float
    payloads: dict[str, bytes] = field(default_factory=dict)


class Runtime:
    def __init__(self, store, vision_factory, camera_ids):
        self.store = store
        self.vision_factory = vision_factory
        self.vision = None
        self.vision_run_id = None
        self.lock = asyncio.Lock()
        self.queue = asyncio.Queue(maxsize=2)
        self.paused = False
        self.replay_run = None      # run_id being fed from recorded frames instead of a live scene
        self.replay_task = None
        self.loading = False
        self.error = None
        self.result = {}
        self.frame = None
        self.camera_ids = tuple(camera_ids)
        self.camera_frames = {}
        self.frames = {}  # JPEG cache keyed by (run_id, frame_id, camera_id)
        self.pending_group = None
        self.last_accepted_id = -1
        self.last_received_at = None
        self.dropped_frames = 0
        self.processed_frames = 0
        self.incomplete_frame_groups = 0
        self.clients = set()
        self._geometry = None
        calibration_path = ROOT / "vision" / "cameras.json"
        if calibration_path.exists():
            from vision.geometry import Calibration
            self._geometry = Calibration(calibration_path).describe()
            self._geometry["cameras"] = [camera for camera in self._geometry["cameras"] if camera["id"] in self.camera_ids]

    def vision_status(self):
        if self.vision is not None:
            return self.vision.status()
        return {"ready": False, "mode": "loading" if self.loading else "awaiting_frames", "cameras": list(self.camera_ids), "message": self.error or "Waiting for Unity frames. Recognition initializes on the first image."}

    def geometry(self):
        if self.vision is not None and hasattr(self.vision, "geometry"):
            return self.vision.geometry()
        return self._geometry

    def assist_state(self):
        """(items still moving, items waiting for an associate). A vision result without
        these fields (an older or stub engine) is treated as all-or-nothing review."""
        if "assist" not in self.result:
            return (1 if self.result.get("review_required") else 0), []
        return self.result.get("in_progress", 0), [a for a in self.result["assist"] if a["object_id"] not in self.store.resolved]

    def snapshot(self):
        state = self.store.snapshot()
        state["simulator"]["paused"] = self.paused
        state["simulator"]["replay"] = self.replay_run is not None and self.replay_run == state["simulator"]["run_id"]
        state["vision"] = self.vision_status()
        state["cameras"] = list(self.camera_ids)
        state["geometry"] = self.geometry()
        state["frames"] = {}
        for camera_id, metadata in self.camera_frames.items():
            public = dict(metadata)
            public["age_ms"] = round((time.monotonic() - public.pop("received_at")) * 1000)
            state["frames"][camera_id] = public
        state["frame"] = state["frames"].get(self.frame["camera_id"]) if self.frame else None
        state["detections"] = self.result.get("detections", [])
        state["objects"] = self.result.get("objects", [])
        state["barcodes"] = self.result.get("barcodes", [])
        in_progress, assist = self.assist_state()
        state["in_progress"], state["assist"] = in_progress, assist
        state["review_required"] = bool(in_progress or assist or self.error)
        # Rate each cart line by its least certain member; an associate's addition is its own rating.
        order = ["verified", "high", "medium", "needs_associate"]
        for line in state["cart"]["items"]:
            ratings = [o.get("rating") for o in state["objects"] if o.get("membership") and o.get("sku") == line["sku"] and o.get("rating")]
            line["rating"] = max(ratings, key=order.index) if ratings else ("associate" if line.get("added_by_associate") else None)
        state["metrics"] = dict(self.result.get("metrics", {}), processed_frames=self.processed_frames,
                                dropped_frames=self.dropped_frames, queue_depth=self.queue.qsize(),
                                incomplete_frame_groups=self.incomplete_frame_groups,
                                missing_cameras=[camera for camera in self.camera_ids if camera not in self.camera_frames],
                                pending_camera_group=self.pending_group.frame_id if self.pending_group else None,
                                pending_cameras=[camera for camera in self.camera_ids if camera not in self.pending_group.payloads] if self.pending_group else [])
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

    def flush_pending(self):
        """Close a group under the session lock; bounded queue drops whole groups."""
        group = self.pending_group
        if group is None:
            return
        self.pending_group = None
        if len(group.payloads) < len(self.camera_ids):
            self.incomplete_frame_groups += 1
        if self.queue.full():
            self.queue.get_nowait()
            self.queue.task_done()
            self.dropped_frames += 1
        self.queue.put_nowait(group)

    def _infer(self, group):
        import cv2
        import numpy as np
        images = {}
        for camera_id in self.camera_ids:
            if camera_id not in group.payloads:
                continue
            image = cv2.imdecode(np.frombuffer(group.payloads[camera_id], dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"Frame from {camera_id} is not a valid JPEG image")
            if image.shape[0] > 2160 or image.shape[1] > 3840:
                raise ValueError("Frame exceeds the supported 3840 × 2160 image bounds")
            images[camera_id] = image
        if self.vision is None:
            self.vision = self.vision_factory()
        if self.vision_run_id != group.run_id:
            self.vision.reset(group.run_id)
            self.vision_run_id = group.run_id
        if hasattr(self.vision, "process_frames"):
            result = self.vision.process_frames(images, group.frame_id, group.timestamp, group.run_id)
        elif len(self.camera_ids) == 1:
            # Existing single-camera engines retain their original interface.
            result = self.vision.process_frame(next(iter(images.values())), group.frame_id, group.timestamp, group.run_id)
        else:
            raise ValueError("A multi-camera configuration requires vision.process_frames")
        dimensions = {camera_id: (image.shape[1], image.shape[0]) for camera_id, image in images.items()}
        return result, dimensions

    async def worker(self):
        while True:
            group = await self.queue.get()
            try:
                async with self.lock:
                    current_run = self.store.snapshot()["session"]["run_id"]
                    if current_run != group.run_id:
                        continue
                    self.loading = self.vision is None
                started = time.perf_counter()
                result, dimensions = await asyncio.to_thread(self._infer, group)
                async with self.lock:
                    if self.store.apply_result(result):
                        self.result = result
                        self.error = None
                        self.processed_frames += 1
                        self.camera_frames = {}
                        for camera_id, (width, height) in dimensions.items():
                            self.frames[(group.run_id, group.frame_id, camera_id)] = group.payloads[camera_id]
                            query = urlencode(dict(run_id=group.run_id, frame_id=group.frame_id, camera_id=camera_id))
                            self.camera_frames[camera_id] = dict(frame_id=group.frame_id, timestamp=group.timestamp,
                                run_id=group.run_id, camera_id=camera_id, width=width, height=height,
                                received_at=group.received_at, url=f"/api/frame?{query}")
                        # Four capture instants, each with every available camera.
                        cached_groups = list(dict.fromkeys((key[0], key[1]) for key in self.frames))
                        for expired in cached_groups[:-4]:
                            for key in [key for key in self.frames if key[:2] == expired]:
                                del self.frames[key]
                        primary = "lane" if "lane" in self.camera_frames else next(iter(self.camera_frames))
                        self.frame = self.camera_frames[primary]
                        self.result.setdefault("metrics", {})["pipeline_ms"] = round((time.perf_counter() - started) * 1000, 1)
            except Exception as exc:
                async with self.lock:
                    if self.store.snapshot()["session"]["run_id"] == group.run_id:
                        self.error = f"Vision processing failed: {exc}"
            finally:
                self.loading = False
                self.queue.task_done()
                await self.publish()


def create_app(database_url=None, vision_factory: Callable | None = None, camera_ids=None):
    db_url = database_url or os.environ.get("PROPASS_DATABASE_URL", f"sqlite:///{ROOT / 'artifacts' / 'propass.db'}")
    (ROOT / "artifacts").mkdir(exist_ok=True)
    if camera_ids is None:
        config = json.loads((ROOT / "vision" / "config.json").read_text())
        # Tracking cameras first, then the barcode scan cameras: one capture group holds them all.
        camera_ids = config.get("cameras", ["lane"]) + config.get("scan_cameras", [])
    if not camera_ids or len(set(camera_ids)) != len(camera_ids) or any(not isinstance(camera, str) or not camera for camera in camera_ids):
        raise ValueError("Configure a nonempty list of unique camera IDs")
    runtime = Runtime(Store(db_url, ROOT / "catalog.json"), vision_factory or default_vision_factory, camera_ids)

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

    @app.get("/api/reports")
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

    @app.get("/api/progress")
    async def pipeline_progress():
        """Where the offline pipeline is: export, training, benchmark recording and scoring (read-only)."""
        return progress(ROOT, len(SCENARIOS))

    @app.get("/api/simulator/control")
    async def control():
        async with runtime.lock:
            return dict(runtime.store.snapshot()["simulator"], paused=runtime.paused)

    @app.post("/api/frames")
    async def frames(request: Request, frame_id: int, timestamp: float, run_id: str, camera_id: str = "lane"):
        if frame_id < 0 or not math.isfinite(timestamp) or timestamp < 0:
            raise HTTPException(422, "Frame ID and capture timestamp must be nonnegative")
        if camera_id not in runtime.camera_ids:
            raise HTTPException(422, "Camera ID is not configured")
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
            if runtime.replay_run == run_id:
                raise HTTPException(409, "This run is being replayed from recorded frames")
            if runtime.paused or current["cart"]["status"] == "CONFIRMED":
                raise HTTPException(409, "Capture is paused for checkout review")
            if frame_id < runtime.last_accepted_id or (frame_id == runtime.last_accepted_id and runtime.pending_group is None):
                return {"accepted": False, "reason": "duplicate_or_out_of_order", "frame_id": frame_id, "camera_id": camera_id}
            received_at = time.monotonic()
            if frame_id > runtime.last_accepted_id:
                runtime.flush_pending()
                runtime.last_accepted_id = frame_id
                runtime.pending_group = FrameGroup(frame_id, timestamp, run_id, received_at)
            group = runtime.pending_group
            if camera_id in group.payloads:
                return {"accepted": False, "reason": "duplicate_camera", "frame_id": frame_id, "camera_id": camera_id}
            if not math.isclose(timestamp, group.timestamp, abs_tol=0.001, rel_tol=0):
                raise HTTPException(422, "All cameras in a frame group must share a capture timestamp")
            group.payloads[camera_id] = payload
            runtime.last_received_at = received_at
            missing = [camera for camera in runtime.camera_ids if camera not in group.payloads]
            if not missing:
                runtime.flush_pending()
        return {"accepted": True, "frame_id": frame_id, "camera_id": camera_id,
                "pending_cameras": missing, "queued": not missing, "queue_depth": runtime.queue.qsize()}

    @app.get("/api/frame")
    async def frame(run_id: str | None = None, frame_id: int | None = None, camera_id: str | None = None):
        async with runtime.lock:
            if not runtime.frame:
                raise HTTPException(404, "No processed frame yet")
            camera_id = camera_id or runtime.frame["camera_id"]
            if camera_id not in runtime.camera_ids:
                raise HTTPException(422, "Camera ID is not configured")
            key = (run_id or runtime.frame["run_id"], frame_id if frame_id is not None else runtime.frame["frame_id"], camera_id)
            payload = runtime.frames.get(key)
            if payload is None:
                raise HTTPException(404, "Frame has advanced. Refresh the snapshot.")
        return Response(payload, media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Frame-ID": str(key[1]), "X-Camera-ID": key[2]})

    async def reset_run(scenario):
        async with runtime.lock:
            run_id = runtime.store.reset(scenario)
            runtime.paused = False
            runtime.result, runtime.frames, runtime.frame = {}, {}, None
            runtime.camera_frames = {}
            runtime.pending_group = None
            runtime.error = None
            runtime.last_accepted_id = -1
            while not runtime.queue.empty():
                runtime.queue.get_nowait()
                runtime.queue.task_done()
            # Inference owns its tracker on one worker thread. reset is deferred to
            # process_frames' run switch, never called concurrently with inference.
            state = runtime.snapshot()
        await runtime.publish()
        return state

    def stop_replay():
        if runtime.replay_task and not runtime.replay_task.done():
            runtime.replay_task.cancel()
        runtime.replay_task, runtime.replay_run = None, None

    @app.post("/api/scenario")
    async def scenario(body: ScenarioRequest):
        if body.scenario not in SCENARIOS:
            raise HTTPException(422, "Unknown checkout scenario")
        stop_replay()
        return await reset_run(body.scenario)

    async def feed_recording(run_id, files):
        """Send a recorded run through the same queue a live scene uses, at the pace it was recorded.

        Unlike a live scene, a recording can wait: no frame group is dropped when inference is busy.
        """
        started, first = time.monotonic(), None
        for frame_id, path in enumerate(files, start=1):
            record = json.loads(path.with_suffix(".json").read_text())
            payloads = {camera: (path if camera == "lane" else path.with_suffix(f".{camera}.jpg")).read_bytes()
                        for camera in runtime.camera_ids}
            first = record["timestamp"] if first is None else first
            while True:
                async with runtime.lock:
                    current = runtime.store.snapshot()
                    if current["session"]["run_id"] != run_id or runtime.replay_run != run_id or current["cart"]["status"] == "CONFIRMED":
                        return
                    due = time.monotonic() - started >= record["timestamp"] - first
                    if due and not runtime.paused and not runtime.queue.full():
                        runtime.last_accepted_id = frame_id
                        runtime.pending_group = FrameGroup(frame_id, record["timestamp"], run_id, time.monotonic(), payloads)
                        runtime.last_received_at = runtime.pending_group.received_at
                        runtime.flush_pending()
                        break
                await asyncio.sleep(0.01)

    async def start_replay(scenario_name):
        directory = RECORDINGS / scenario_name / REPLAY_SEED
        files = sorted(p for p in directory.glob("*.jpg") if "." not in p.stem) if directory.is_dir() else []
        if not files:
            raise HTTPException(404, "No recorded run for this scenario. Run scripts/get_recordings.sh, or record the benchmark in Unity.")
        stop_replay()
        state = await reset_run(scenario_name)
        runtime.replay_run = state["session"]["run_id"]
        runtime.replay_task = asyncio.create_task(feed_recording(runtime.replay_run, files))
        state["simulator"]["replay"] = True
        return state

    @app.post("/api/replay")
    async def replay(body: ScenarioRequest):
        """Run a scenario from frames Unity already rendered: the full live pipeline, no scene needed."""
        if body.scenario not in SCENARIOS:
            raise HTTPException(422, "Unknown checkout scenario")
        return await start_replay(body.scenario)

    @app.post("/api/cart/reset")
    async def reset():
        async with runtime.lock:
            scenario_name = runtime.store.snapshot()["simulator"]["scenario"]
        if runtime.replay_run is not None:
            return await start_replay(scenario_name)
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
            if not runtime.frame and runtime.pending_group is None and runtime.queue.empty() and not runtime.loading:
                raise HTTPException(409, "Wait for the first accepted Unity frame")
            try:
                run_id = runtime.store.begin_prepare()
            except CheckoutConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            runtime.paused = True
            runtime.flush_pending()
        await runtime.publish()
        try:
            await asyncio.wait_for(runtime.queue.join(), timeout=30)
        except asyncio.TimeoutError:
            return Response(status_code=202, content='{"pending":true,"message":"Draining accepted camera frames"}', media_type="application/json")
        async with runtime.lock:
            conflict = None
            try:
                if runtime.store.snapshot()["session"]["run_id"] != run_id:
                    raise CheckoutConflict("The checkout session changed during preparation")
                if runtime.error:
                    runtime.store.abort_prepare()
                    raise CheckoutConflict(runtime.error)
                if runtime.frame is None:
                    runtime.store.abort_prepare()
                    raise CheckoutConflict("No camera frame was processed during preparation")
                if not runtime.vision_status().get("ready", False):
                    runtime.store.abort_prepare()
                    raise CheckoutConflict("The vision checkpoint is not ready")
                in_progress, assist = runtime.assist_state()
                runtime.store.finish_prepare(run_id, runtime.frame["frame_id"], bool(in_progress), bool(assist))
            except CheckoutConflict as exc:
                conflict = str(exc)
            state = runtime.snapshot()
        await runtime.publish()
        if conflict:
            raise HTTPException(409, conflict)
        return state

    async def associate(action):
        async with runtime.lock:
            try:
                action()
                if not runtime.assist_state()[1]:
                    runtime.store.finish_assist()
            except CheckoutConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            state = runtime.snapshot()
        await runtime.publish()
        return state

    @app.post("/api/assist/add")
    async def assist_add(body: AssistAddRequest):
        """An associate adds an item (optionally settling a flagged object) or releases a restricted one."""
        return await associate(lambda: runtime.store.associate_add(body.sku, body.object_id))

    @app.post("/api/assist/dismiss")
    async def assist_dismiss(body: AssistDismissRequest):
        """An associate confirms a flagged detection is nothing to charge."""
        return await associate(lambda: runtime.store.associate_dismiss(body.object_id))

    @app.post("/api/cart/confirm")
    async def confirm(body: ConfirmationRequest):
        async with runtime.lock:
            state = runtime.store.snapshot()
            try:
                in_progress, assist = runtime.assist_state()
                receipt = runtime.store.confirm(body.version, body.idempotency_key, state["session"]["run_id"], bool(in_progress or assist or runtime.error))
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
