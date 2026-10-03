"""Backend correctness tests use deterministic vision events, not claimed CV accuracy."""
import concurrent.futures
import io
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import func, select

from api.app import create_app
from api.models import CheckoutEvent, Receipt
from api.store import CheckoutConflict, Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(tmp_path):
    return Store(f"sqlite:///{tmp_path / 'checkout.db'}", ROOT / "catalog.json")


def result(store, *events, run_id=None):
    return {"run_id": run_id or store.snapshot()["session"]["run_id"], "timestamp": 1.0, "events": list(events)}


def event(event_id, kind="ITEM_ADDED", oid="physical-1", sku="PEX-001"):
    return dict(event_id=event_id, type=kind, object_id=oid, sku=sku, timestamp=1.0)


def test_hundred_frames_and_event_retries_are_one_unit(store):
    for _ in range(100):
        store.apply_result(result(store, event("crossing-1")))
    cart = store.snapshot()["cart"]
    assert cart["items"][0]["quantity"] == 1
    assert cart["version"] == 1
    with store.db() as db:
        assert db.scalar(select(func.count()).select_from(CheckoutEvent)) == 1


def test_identical_sku_has_two_physical_memberships_and_reverse_removes_one(store):
    store.apply_result(result(store, event("one"), event("two", oid="physical-2")))
    assert store.snapshot()["cart"]["items"][0]["quantity"] == 2
    store.apply_result(result(store, event("reverse", "ITEM_REMOVED")))
    assert store.snapshot()["cart"]["items"][0]["quantity"] == 1
    # A lost track, repeated resolution or class observation never removes the other unit.
    store.apply_result(result(store, event("lost", "TRACK_LOST", oid="physical-2")))
    assert store.snapshot()["cart"]["items"][0]["quantity"] == 1


def test_unknown_membership_blocks_preparation(store):
    store.apply_result(result(store, event("unknown", sku=None)))
    run = store.begin_prepare()
    with pytest.raises(CheckoutConflict, match="Unresolved"):
        store.finish_prepare(run, 12, False)
    assert store.snapshot()["cart"]["status"] == "OPEN"


def test_new_evidence_invalidates_preparation_and_is_not_lost(store):
    store.apply_result(result(store, event("one")))
    run = store.begin_prepare()
    version = store.finish_prepare(run, 12, False)
    store.apply_result(result(store, event("two", oid="physical-2")))
    assert store.snapshot()["cart"]["status"] == "OPEN"
    assert store.snapshot()["cart"]["items"][0]["quantity"] == 2
    with pytest.raises(CheckoutConflict, match="changed"):
        store.confirm(version, "test-key-001", run)


def test_stale_run_cannot_mutate_new_cart(store):
    old_run = store.snapshot()["session"]["run_id"]
    new_run = store.reset("duplicate")
    assert new_run != old_run
    assert store.apply_result(result(store, event("old"), run_id=old_run)) is False
    assert store.snapshot()["cart"]["items"] == []


def test_review_evidence_invalidates_prepared_version(store):
    store.apply_result(result(store, event("one")))
    run = store.begin_prepare()
    version = store.finish_prepare(run, 12, False)
    store.apply_result(result(store, event("uncertain", "REVIEW_REQUIRED", oid="unresolved", sku=None)))
    assert store.snapshot()["cart"]["status"] == "OPEN"
    with pytest.raises(CheckoutConflict):
        store.confirm(version, "review-test-001", run)


def test_receipt_is_immutable_idempotent_and_survives_session_reset(store):
    store.apply_result(result(store, event("one")))
    run = store.begin_prepare()
    version = store.finish_prepare(run, 12, False)
    receipt = store.confirm(version, "test-key-001", run)
    assert store.confirm(version, "test-key-001", run) == receipt
    with pytest.raises(CheckoutConflict, match="different"):
        store.confirm(version, "test-key-002", run)
    assert store.apply_result(result(store, event("too-late", "ITEM_REMOVED"))) is False
    store.reset("mixed")
    with store.db() as db:
        saved = db.get(Receipt, receipt["id"])
        assert saved.lines[0]["quantity"] == 1
        assert saved.total == 129.0


def jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 36), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeVision:
    def __init__(self, blocked=False, unknown=False):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.blocked = blocked
        self.unknown = unknown

    def reset(self, run_id):
        self.run_id = run_id

    def status(self):
        return {"ready": True, "mode": "deterministic_test_double"}

    def process_frame(self, image, frame_id, timestamp, run_id):
        self.entered.set()
        if self.blocked:
            assert self.release.wait(4), "Test frame barrier was not released"
        return dict(run_id=run_id, frame_id=frame_id, timestamp=timestamp, detections=[], objects=[], events=[event("crossing", sku="PEX-001")] if not self.unknown else [], review_required=self.unknown, metrics={})


def wait_frame(client, frame_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        state = client.get("/api/snapshot").json()
        if state["frame"] and state["frame"]["frame_id"] >= frame_id:
            return state
        time.sleep(.02)
    pytest.fail("Worker did not process the test frame")


def post_frame(client, run_id, frame_id=1):
    return client.post(f"/api/frames?frame_id={frame_id}&timestamp={frame_id / 8}&run_id={run_id}", content=jpeg(), headers={"Content-Type": "image/jpeg"})


def test_api_prepare_drains_inflight_and_rejects_new_capture(tmp_path):
    vision = FakeVision()
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", lambda: vision)
    with TestClient(app) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        assert post_frame(client, run).json()["accepted"]
        first = wait_frame(client, 1)
        assert first["cart"]["items"][0]["quantity"] == 1
        vision.blocked = True
        vision.entered.clear()
        assert post_frame(client, run, 2).status_code == 200
        assert vision.entered.wait(2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            preparing = pool.submit(client.post, "/api/cart/prepare")
            deadline = time.monotonic() + 2
            while not client.get("/api/simulator/control").json()["paused"] and time.monotonic() < deadline:
                time.sleep(.02)
            assert post_frame(client, run, 3).status_code == 409
            assert not preparing.done()
            vision.release.set()
            prepared = preparing.result(3)
        assert prepared.status_code == 200
        state = prepared.json()
        assert state["cart"]["prepared_frame_id"] == 2
        payload = {"version": state["cart"]["version"], "idempotency_key": "api-test-key-001"}
        receipt = client.post("/api/cart/confirm", json=payload)
        assert receipt.status_code == 200
        assert client.post("/api/cart/confirm", json=payload).json() == receipt.json()
        assert client.get("/api/frame").headers["content-type"] == "image/jpeg"


def test_api_new_run_rejects_stale_frames_and_invalid_payload(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", FakeVision)
    with TestClient(app) as client:
        old = client.get("/api/simulator/control").json()["run_id"]
        state = client.post("/api/scenario", json={"scenario": "duplicate"}).json()
        assert post_frame(client, old).status_code == 409
        assert post_frame(client, state["session"]["run_id"]).status_code == 200
        wait_frame(client, 1)
        assert post_frame(client, state["session"]["run_id"]).json()["accepted"] is False
        assert client.post("/api/frames?frame_id=2&timestamp=1&run_id=" + state["session"]["run_id"], content=b'fake', headers={"Content-Type": "image/jpeg"}).status_code == 422


def test_api_reset_while_preparing_rejects_old_barrier_without_server_error(tmp_path):
    vision = FakeVision()
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", lambda: vision)
    with TestClient(app) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        post_frame(client, run)
        wait_frame(client, 1)
        vision.blocked = True
        vision.entered.clear()
        post_frame(client, run, 2)
        assert vision.entered.wait(2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            preparing = pool.submit(client.post, "/api/cart/prepare")
            deadline = time.monotonic() + 2
            while not client.get("/api/simulator/control").json()["paused"] and time.monotonic() < deadline:
                time.sleep(.02)
            fresh = client.post("/api/scenario", json={"scenario": "mixed"}).json()
            vision.release.set()
            assert preparing.result(3).status_code == 409
        state = client.get("/api/snapshot").json()
        assert state["session"]["run_id"] == fresh["session"]["run_id"]
        assert state["cart"]["items"] == []
        assert state["cart"]["status"] == "OPEN"


def test_api_resume_invalidates_confirmation(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", FakeVision)
    with TestClient(app) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        post_frame(client, run)
        wait_frame(client, 1)
        prepared = client.post("/api/cart/prepare").json()
        client.post("/api/cart/resume")
        assert client.post("/api/cart/confirm", json={"version": prepared["cart"]["version"], "idempotency_key": "resume-test-001"}).status_code == 409


def test_api_uncertain_recognition_cannot_prepare(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}", lambda: FakeVision(unknown=True))
    with TestClient(app) as client:
        run = client.get("/api/simulator/control").json()["run_id"]
        post_frame(client, run)
        wait_frame(client, 1)
        assert client.post("/api/cart/prepare").status_code == 409
