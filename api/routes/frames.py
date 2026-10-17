"""Camera ingress: Unity posts one JPEG per camera per capture instant; the dashboard reads them back."""
import math
import time

from fastapi import APIRouter, HTTPException, Request, Response

from ..runtime import FrameGroup


def router(runtime):
    api = APIRouter()

    @api.post("/api/frames")
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

    @api.get("/api/frame")
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

    return api
