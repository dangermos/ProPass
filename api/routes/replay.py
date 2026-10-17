"""Replay: play a run Unity already rendered through the live pipeline, no scene needed."""
import asyncio
import json
import time

from fastapi import APIRouter, HTTPException

from ..runtime import FrameGroup
from ..schemas import ScenarioRequest
from ..store import SCENARIOS

# One seed of every scenario is published as a recording.
REPLAY_SEED = "seed_02"


async def feed_recording(runtime, run_id, files):
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


async def start_replay(runtime, scenario_name):
    directory = runtime.recordings / scenario_name / REPLAY_SEED
    files = sorted(p for p in directory.glob("*.jpg") if "." not in p.stem) if directory.is_dir() else []
    if not files:
        raise HTTPException(404, "No recorded run for this scenario. Run scripts/get_recordings.sh, or record the benchmark in Unity.")
    runtime.stop_replay()
    state = await runtime.reset_run(scenario_name)
    runtime.replay_run = state["session"]["run_id"]
    runtime.replay_task = asyncio.create_task(feed_recording(runtime, runtime.replay_run, files))
    state["simulator"]["replay"] = True
    return state


def router(runtime):
    api = APIRouter()

    @api.post("/api/replay")
    async def replay(body: ScenarioRequest):
        """Run a scenario from frames Unity already rendered: the full live pipeline, no scene needed."""
        if body.scenario not in SCENARIOS:
            raise HTTPException(422, "Unknown checkout scenario")
        return await start_replay(runtime, body.scenario)

    return api
