"""Replay: frames Unity already rendered go through the live pipeline, with no scene running."""
import json
import time

from fastapi.testclient import TestClient

import api.app
from api.app import create_app
from tests.test_api_assist import AssistVision


def _jpeg():
    import io

    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (64, 36), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


JPEG = _jpeg()


def recorded(tmp_path, monkeypatch, frames=4):
    run = tmp_path / "recordings" / "single" / "seed_02"
    run.mkdir(parents=True)
    for i in range(1, frames + 1):
        (run / f"{i:06d}.jpg").write_bytes(JPEG)
        (run / f"{i:06d}.json").write_text(json.dumps({"frame_id": i, "timestamp": (i - 1) * 0.01}))
    monkeypatch.setattr(api.app, "RECORDINGS", tmp_path / "recordings")
    return TestClient(create_app(f"sqlite:///{tmp_path / 'replay.db'}", lambda: AssistVision(), camera_ids=["lane"]))


def wait_for(client, condition, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        state = client.get("/api/snapshot").json()
        if condition(state):
            return state
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for the replay")


def test_replay_plays_every_recorded_frame_and_builds_the_cart(tmp_path, monkeypatch):
    with recorded(tmp_path, monkeypatch) as client:
        started = client.post("/api/replay", json={"scenario": "single"}).json()
        assert started["simulator"]["replay"] is True
        state = wait_for(client, lambda s: (s.get("frame") or {}).get("frame_id") == 4)
        assert state["metrics"]["dropped_frames"] == 0
        assert [line["sku"] for line in state["cart"]["items"]] == ["PEX-001"]


def test_a_live_scene_cannot_post_into_a_replayed_run(tmp_path, monkeypatch):
    with recorded(tmp_path, monkeypatch, frames=200) as client:
        run = client.post("/api/replay", json={"scenario": "single"}).json()["session"]["run_id"]
        response = client.post(f"/api/frames?frame_id=1&timestamp=0&run_id={run}", content=JPEG, headers={"Content-Type": "image/jpeg"})
        assert response.status_code == 409
        # Choosing a scenario the normal way ends the replay and accepts live frames again.
        run = client.post("/api/scenario", json={"scenario": "single"}).json()["session"]["run_id"]
        assert client.get("/api/snapshot").json()["simulator"]["replay"] is False
        response = client.post(f"/api/frames?frame_id=1&timestamp=0&run_id={run}", content=JPEG, headers={"Content-Type": "image/jpeg"})
        assert response.status_code == 200


def test_replay_without_recordings_says_how_to_get_them(tmp_path, monkeypatch):
    with recorded(tmp_path, monkeypatch) as client:
        response = client.post("/api/replay", json={"scenario": "mixed"})
        assert response.status_code == 404 and "get_recordings" in response.json()["detail"]
