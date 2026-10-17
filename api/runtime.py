"""Session runtime: frame grouping, the inference worker and the published snapshot."""
import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]


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
    def __init__(self, store, vision_factory, camera_ids, recordings=None):
        self.store = store
        self.vision_factory = vision_factory
        self.vision = None
        self.vision_run_id = None
        self.lock = asyncio.Lock()
        self.queue = asyncio.Queue(maxsize=2)
        self.paused = False
        self.replay_run = None      # run_id being fed from recorded frames instead of a live scene
        self.replay_task = None
        self.recordings = recordings  # directory of recorded runs that /api/replay plays
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
        return {"ready": False, "mode": "loading" if self.loading else "awaiting_frames", "cameras": list(self.camera_ids),
                "message": self.error or "Waiting for Unity frames. Recognition initializes on the first image."}

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

    async def reset_run(self, scenario):
        async with self.lock:
            self.store.reset(scenario)
            self.paused = False
            self.result, self.frames, self.frame = {}, {}, None
            self.camera_frames = {}
            self.pending_group = None
            self.error = None
            self.last_accepted_id = -1
            while not self.queue.empty():
                self.queue.get_nowait()
                self.queue.task_done()
            # Inference owns its tracker on one worker thread. reset is deferred to
            # process_frames' run switch, never called concurrently with inference.
            state = self.snapshot()
        await self.publish()
        return state

    def stop_replay(self):
        if self.replay_task and not self.replay_task.done():
            self.replay_task.cancel()
        self.replay_task, self.replay_run = None, None
