"""Camera transport/grouping tests; deterministic vision, no claimed CV metrics."""
import concurrent.futures
import io
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.app import create_app


class GroupedVision:
    def __init__(self):
        self.calls = []
        self.resets = []
        self.blocked = False
        self.entered = threading.Event()
        self.release = threading.Event()

    def reset(self, run_id):
        self.resets.append(run_id)

    def status(self):
        return {"ready": True, "mode": "deterministic_test_double", "cameras": ["lane", "overhead"]}

    def geometry(self):
        return {"bounds": {"x": [-5, 5], "z": [-7, 7]}, "lane": {}, "cameras": [{"id": "lane"}, {"id": "overhead"}]}

    def process_frames(self, images, frame_id, timestamp, run_id):
        self.calls.append((run_id, frame_id, tuple(images)))
        self.entered.set()
        if self.blocked:
            assert self.release.wait(4), "Test frame barrier was not released"
        return dict(run_id=run_id, frame_id=frame_id, timestamp=timestamp,
                    detections=[{"camera": camera, "bbox": [1, 1, 10, 10]} for camera in images],
                    objects=[], events=[], review_required=False, metrics={})


def jpeg(color="red"):
    buffer = io.BytesIO()
    Image.new("RGB", (64, 36), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def post(client, run, frame=1, camera="lane", color="red", timestamp=None):
    return client.post("/api/frames", params={"run_id": run, "frame_id": frame,
                        "camera_id": camera, "timestamp": frame / 8 if timestamp is None else timestamp},
                       content=jpeg(color), headers={"Content-Type": "image/jpeg"})


def wait_frame(client, frame):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snapshot = client.get("/api/snapshot").json()
        if snapshot["frame"] and snapshot["frame"]["frame_id"] >= frame:
            return snapshot
        time.sleep(.01)
    pytest.fail(f"Worker did not process camera group {frame}")


def app_for(tmp_path, vision):
    return create_app(f"sqlite:///{tmp_path / 'cameras.db'}", lambda: vision, camera_ids=["lane", "overhead"])


def test_group_is_one_inference_with_camera_matched_images_and_order(tmp_path):
    vision = GroupedVision()
    with TestClient(app_for(tmp_path, vision)) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        first = post(client, run, 10, "overhead", "blue").json()
        assert first["accepted"] and first["pending_cameras"] == ["lane"]
        assert not first["queued"]
        assert client.get("/api/snapshot").json()["frames"] == {}
        assert post(client, run, 10, "overhead").json()["reason"] == "duplicate_camera"
        assert post(client, run, 9, "lane").json()["accepted"] is False
        assert post(client, run, 10, "lane", timestamp=9).status_code == 422
        assert post(client, run, 10, "lane").json()["queued"]
        state = wait_frame(client, 10)
        assert vision.calls == [(run, 10, ("lane", "overhead"))]
        assert state["frame"] == state["frames"]["lane"]
        assert state["cameras"] == ["lane", "overhead"]
        assert state["geometry"] == vision.geometry()
        assert state["metrics"]["missing_cameras"] == []
        for camera, color in (("lane", "red"), ("overhead", "blue")):
            metadata = state["frames"][camera]
            assert metadata["camera_id"] == camera and metadata["frame_id"] == 10
            response = client.get(metadata["url"])
            assert response.content == jpeg(color)
            assert response.headers["x-camera-id"] == camera
            assert response.headers["x-frame-id"] == "10"
        assert post(client, run, 10, "lane").json()["accepted"] is False
        assert post(client, run, 10, "overhead").json()["accepted"] is False
        assert client.get("/api/frame?camera_id=private-camera").status_code == 422
        assert post(client, run, 11, "private-camera").status_code == 422


def test_newer_frame_flushes_missing_camera_and_never_reuses_older_image(tmp_path):
    vision = GroupedVision()
    with TestClient(app_for(tmp_path, vision)) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        post(client, run, 1, "lane")
        post(client, run, 2, "overhead", "blue")
        state = wait_frame(client, 1)
        assert state["metrics"]["incomplete_frame_groups"] == 1
        assert state["metrics"]["pending_camera_group"] == 2
        assert state["metrics"]["pending_cameras"] == ["lane"]
        assert post(client, run, 1, "overhead").json()["accepted"] is False
        prepared = client.post("/api/cart/prepare")
        assert prepared.status_code == 200
        state = prepared.json()
        assert state["cart"]["prepared_frame_id"] == 2
        assert set(state["frames"]) == {"overhead"}
        assert state["frame"]["camera_id"] == "overhead"
        assert state["metrics"]["missing_cameras"] == ["lane"]
        assert state["metrics"]["incomplete_frame_groups"] == 2
        assert vision.calls == [(run, 1, ("lane",)), (run, 2, ("overhead",))]
        assert client.get("/api/frame?camera_id=lane").status_code == 404
        assert client.get("/api/frame", params={"run_id": run, "frame_id": 1, "camera_id": "lane"}).content == jpeg()


def test_prepare_flushes_first_partial_group_then_initializes_vision(tmp_path):
    vision = GroupedVision()
    with TestClient(app_for(tmp_path, vision)) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        assert client.post("/api/cart/prepare").status_code == 409
        post(client, run, 4, "lane")
        prepared = client.post("/api/cart/prepare")
        assert prepared.status_code == 200
        assert prepared.json()["cart"]["prepared_frame_id"] == 4
        assert vision.calls == [(run, 4, ("lane",))]
        assert post(client, run, 4, "overhead").status_code == 409


def test_prepare_drains_inflight_and_pending_group_before_watermark(tmp_path):
    vision = GroupedVision()
    with TestClient(app_for(tmp_path, vision)) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        post(client, run, 1, "lane")
        post(client, run, 1, "overhead")
        wait_frame(client, 1)
        vision.blocked = True
        vision.entered.clear()
        post(client, run, 2, "lane")
        post(client, run, 2, "overhead")
        assert vision.entered.wait(2)
        post(client, run, 3, "lane")
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            preparing = pool.submit(client.post, "/api/cart/prepare")
            deadline = time.monotonic() + 2
            while not client.get("/api/simulator/control").json()["paused"] and time.monotonic() < deadline:
                time.sleep(.01)
            assert post(client, run, 3, "overhead").status_code == 409
            assert post(client, run, 4, "lane").status_code == 409
            assert not preparing.done()
            vision.release.set()
            prepared = preparing.result(3)
        assert prepared.status_code == 200
        assert prepared.json()["cart"]["prepared_frame_id"] == 3
        assert [call[1] for call in vision.calls] == [1, 2, 3]


def test_reset_drops_pending_group_and_stale_inflight_result(tmp_path):
    vision = GroupedVision()
    vision.blocked = True
    with TestClient(app_for(tmp_path, vision)) as client:
        old = client.get("/api/simulator/control").json()["run_id"]
        post(client, old, 1, "lane")
        post(client, old, 1, "overhead")
        assert vision.entered.wait(2)
        post(client, old, 2, "overhead")
        fresh = client.post("/api/scenario", json={"scenario": "parked"}).json()
        run = fresh["session"]["run_id"]
        assert fresh["frames"] == {} and fresh["frame"] is None
        assert fresh["metrics"]["pending_camera_group"] is None
        assert post(client, old, 2, "lane").status_code == 409
        post(client, run, 1, "lane")
        post(client, run, 1, "overhead")
        vision.release.set()
        state = wait_frame(client, 1)
        assert state["session"]["run_id"] == run
        assert all(metadata["run_id"] == run for metadata in state["frames"].values())
        assert vision.calls == [(old, 1, ("lane", "overhead")), (run, 1, ("lane", "overhead"))]
        assert vision.resets == [old, run]
        assert client.get("/api/frame", params={"run_id": old, "frame_id": 1, "camera_id": "lane"}).status_code == 404


def test_reset_during_partial_group_drain_cannot_prepare_new_run(tmp_path):
    vision = GroupedVision()
    with TestClient(app_for(tmp_path, vision)) as client:
        old = client.get("/api/simulator/control").json()["run_id"]
        post(client, old, 1, "lane")
        post(client, old, 1, "overhead")
        wait_frame(client, 1)
        vision.blocked = True
        vision.entered.clear()
        post(client, old, 2, "lane")
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            preparing = pool.submit(client.post, "/api/cart/prepare")
            assert vision.entered.wait(2)
            fresh = client.post("/api/cart/reset").json()
            vision.release.set()
            assert preparing.result(3).status_code == 409
        state = client.get("/api/snapshot").json()
        assert state["session"]["run_id"] == fresh["session"]["run_id"]
        assert state["cart"]["status"] == "OPEN"
        assert state["cart"]["prepared_frame_id"] is None
        assert state["frame"] is None and state["frames"] == {}
        assert state["simulator"]["paused"] is False


def test_invalid_partial_jpeg_cannot_freeze_cart_and_returns_to_open(tmp_path):
    vision = GroupedVision()
    with TestClient(app_for(tmp_path, vision)) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        response = client.post("/api/frames", params={"frame_id": 1, "timestamp": .125,
                               "run_id": run, "camera_id": "lane"}, content=b"\xff\xd8invalid-jpeg",
                               headers={"Content-Type": "image/jpeg"})
        assert response.json()["accepted"]
        assert client.post("/api/cart/prepare").status_code == 409
        state = client.get("/api/snapshot").json()
        assert state["review_required"] is True
        assert "not a valid JPEG" in state["error"]
        assert state["cart"]["status"] == "OPEN"
        assert state["cart"]["prepared_frame_id"] is None
        assert vision.calls == []


def test_bounded_queue_drops_whole_groups_and_keeps_newest_capture(tmp_path):
    vision = GroupedVision()
    vision.blocked = True
    with TestClient(app_for(tmp_path, vision)) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        for camera in ("lane", "overhead"):
            post(client, run, 1, camera)
        assert vision.entered.wait(2)
        for frame in (2, 3, 4):
            for camera in ("lane", "overhead"):
                post(client, run, frame, camera)
        assert client.get("/api/snapshot").json()["metrics"]["dropped_frames"] == 1
        vision.release.set()
        state = wait_frame(client, 4)
        assert [call[1] for call in vision.calls] == [1, 3, 4]
        assert all(call[2] == ("lane", "overhead") for call in vision.calls)
        assert state["metrics"]["queue_depth"] == 0


def test_per_camera_cache_retains_four_groups_then_expires_both_views(tmp_path):
    vision = GroupedVision()
    with TestClient(app_for(tmp_path, vision)) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        for frame in range(1, 6):
            for camera in ("lane", "overhead"):
                post(client, run, frame, camera)
            wait_frame(client, frame)
        for camera in ("lane", "overhead"):
            assert client.get("/api/frame", params={"run_id": run, "frame_id": 1, "camera_id": camera}).status_code == 404
            assert client.get("/api/frame", params={"run_id": run, "frame_id": 2, "camera_id": camera}).status_code == 200


def test_single_camera_legacy_submission_is_immediately_queued(tmp_path):
    vision = GroupedVision()
    app = create_app(f"sqlite:///{tmp_path / 'legacy.db'}", lambda: vision, camera_ids=["lane"])
    with TestClient(app) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        response = client.post("/api/frames", params={"frame_id": 1, "timestamp": .125, "run_id": run},
                               content=jpeg(), headers={"Content-Type": "image/jpeg"})
        assert response.json()["queued"]
        assert wait_frame(client, 1)["frame"]["camera_id"] == "lane"
        assert client.get("/api/frame").content == jpeg()


@pytest.mark.parametrize("timestamp", ["nan", "inf", "-1"])
def test_nonfinite_or_negative_timestamps_are_rejected(tmp_path, timestamp):
    with TestClient(app_for(tmp_path, GroupedVision())) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        assert post(client, run, timestamp=timestamp).status_code == 422
