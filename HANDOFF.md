# Handoff checkpoint (2026-10-03)

For the next person or AI picking this up. Read this first, then [docs/roadmap.md](docs/roadmap.md).

## Where things stand

| Branch | State |
|---|---|
| `main` | **Working and verified.** Phases A and B, the title screen and the four dashboard tabs. 39 tests pass, live check 6/6, held-out benchmark 67/70 (single lane camera, image-space zones). |
| `phase-c-wip` (this branch) | **Phase C in progress: second (overhead) camera + world-space fusion.** Code is written but the Python side has never been run end to end. Do not merge until the steps below are done. |

Owner: Danny (GitHub `dangermos`, private repo `dangermos/ProPass`). Danny approved roadmap phases A→D in order, wants real trained models, colorful visual docs, no bloat, and to be asked before deleting or restructuring. Commit and push often.

## What Phase C has so far (all on this branch)

**Done and checked**
- `unity/Assets/ProPass/Runtime/ProPassCameras.cs`: creates the overhead camera at runtime (y = 7.55 m, looking down, image right = +z). Ids are `lane` and `overhead`.
- `ProPassSimulation.cs`: captures both cameras per frame and POSTs each to `/api/frames?...&camera_id=<id>`. The old live replay recording was removed (the benchmark recorder replaces it).
- `ProPassBenchmarkRecorder.cs`: writes `000001.jpg` (lane) and `000001.overhead.jpg`. Forces the capture aspect so projections are right.
- `ProPassCalibration.cs` → `vision/cameras.json`: plane↔image point pairs and each camera's footprint at carry height (0.9 m).
- `ProPassDatasetExporter.cs`: half the scenes render from the overhead camera.
- New scenario `parked` (flatbed hides products from the lane camera for 7–9 s) in `ProPassScenario.cs`, `api/store.py`, `web/src/scenarios.ts`, `training/benchmark.py`. It still needs a thumbnail at `web/public/scenarios/parked.jpg`.
- Models retrained on 2,100 two-view scenes (v3, in `models/`, git-ignored): detector mAP50-95 ≈ 0.9 on carts, classifier ≈ 98% on crops. Log: `artifacts/logs/train-v3.log`. Earlier weights are in `models/v2/` and `models/v1/`.
- Recordings with both cameras, 15 scenarios × 5 seeds each: `artifacts/benchmark` (dev seeds 0–4) and `artifacts/benchmark-test` (held-out seeds 5–9). The old single-camera sets are `artifacts/benchmark-1cam` and `artifacts/benchmark-test-1cam`.

**Written but never run**
- `vision/geometry.py`: homography per camera, lane map coordinates.
- `vision/engine.py`: rewritten. `process_frames({camera: image}, ...)`, one YOLO instance per camera, `_fuse` merges boxes within `fuse_radius_m` across cameras and keeps a fused track id through whichever camera still sees the object. World mode turns on when `vision/cameras.json` exists.
- `vision/ledger.py`: `Observation` gained `full_view`, `at_entry_edge`, `sized` for map-space observations.
- `vision/config.json`: `cameras`, `fuse_radius_m`, `world_ledger` overrides (guesses, untuned).
- `training/benchmark.py`: `--cameras lane,overhead` and `--image-mode`.

## Next steps, in order

1. **Run the benchmark three ways on the dev set** and fix whatever breaks (expect bugs in `_fuse` and the world-mode ledger settings):
   ```bash
   .venv/bin/python -m training.benchmark --root artifacts/benchmark --label c-image --image-mode
   .venv/bin/python -m training.benchmark --root artifacts/benchmark --label c-world-1cam --cameras lane
   .venv/bin/python -m training.benchmark --root artifacts/benchmark --label c-world-2cam
   ```
   Tune `world_ledger` on seeds 0–4 only. `parked` should fail with one camera and pass with two.
2. **Score once on `artifacts/benchmark-test`** and regenerate `docs/benchmark.md` with `--docs --compare`.
3. **API** (`api/app.py`): accept `camera_id` on `POST /api/frames`, group frames by `frame_id` until every configured camera has arrived (flush an incomplete group when a newer frame arrives, and before `prepare` drains), call `process_frames`, keep per-camera JPEGs, serve `/api/frame?camera_id=`, add `geometry` to `/api/reports`. Right now the API ignores `camera_id`, so the overhead frame is dropped as a duplicate and the live demo behaves as single-camera.
4. **Dashboard**: camera switcher on the Live tab, and a top-down coverage map (lane, zone lines, each camera's footprint from `engine.geometry()`, object dots from `objects[].world`).
5. Re-run `training.evaluate`, `scripts/verify_live.py`, add tests for `_fuse` and the map-space ledger flags, update docs (roadmap Phase C, vision.md, pipeline.md, api.md, training.md's replay section is now obsolete), then merge to `main`.

## Working notes

- Unity Editor is usually open on `propass/unity`. Drive it with the Unity CLI: `unity command recompile`, `recompile_status`, `eval --code '...'`, `editor_play`, `editor_stop`. Long work goes through `RecordDeferred` or `ProPassDatasetExporter.Begin` (both return at once). If the Editor is closed: `unity projects open "$PWD/unity"`.
- Restart the API by killing the pid from `ss -ltnp 'sport = :8000'`, then `nohup .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --no-access-log > artifacts/logs/api.log 2>&1 &`. Don't `pkill -f uvicorn` from a command that also contains that word.
- Never `git add -A` without checking for `*.pt` or data folders. `main`'s history was rewritten once to remove them. A backup of the old history is at `artifacts/propass-history-before-clean.bundle`.
- Validate Mermaid diagrams and relative links before pushing docs.
- To get back to the verified state: `git checkout main`, and copy `models/v2/detector.pt` and `models/v2/classifier.pt` into `models/`.
