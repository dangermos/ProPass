# Handoff notes (2026-10-06)

For the next person or AI picking this up. Read this first, then [docs/roadmap.md](docs/roadmap.md).

## Where things stand

| Branch | State |
|---|---|
| `main` | **Everything.** Phases A–C, the dashboard, and Pro Express v2: barcode scanning, ratings, locked items, associate hand-off, customer phone view, eight products. Animated characters, and a Training tab in the dashboard. Held-out with characters: **71/85** fully automatic, nothing wrongly charged (capsule people scored 78/85; those weights are in `models/v5/`). 149 tests pass. |
| `pro-express-v2` | Merged into `main` on 2026-10-06 (Danny's request). |

Owner: Danny (GitHub `dangermos`, private repo `dangermos/ProPass`). Danny wants real trained models, colorful visual docs, no bloat, and to be asked before deleting or restructuring. Commit and push often. He likes short progress updates as work goes on.

**The plan, progress checklist and results for the current work are in [docs/pro-express-v2.md](docs/pro-express-v2.md). Start there.**

## Things that are easy to get wrong

- **Models are per camera.** `models/detector.pt` and `models/classifier.pt` are the lane camera's. `models/overhead/` holds the overhead camera's pair. Train each with `training.train ... --camera lane|overhead`. They must match `catalog.json` (eight products): after changing the catalog, re-export data, retrain both pairs and re-record the benchmark. One shared two-view pair scored 39/75 through the lane camera, so don't merge them back. Weights are git-ignored. Earlier sets are in `models/v1/`, `v2/`, `v4/`.
- **Fusion is lane-primary** (`VisionEngine._fuse`). Only the lane camera starts objects. A symmetric version scored 45–58/75 because stray overhead detections blocked checkout.
- **Tune on `artifacts/benchmark` (seeds 0–4), report on `artifacts/benchmark-test` (seeds 5–9).** Both hold three-camera recordings (lane, overhead, scan) of 17 scenarios × 5 seeds with the eight-product catalog. Older sets are kept beside them (`-1cam`, `-2cam`, `-v2a`).
- After moving a camera, re-export `vision/cameras.json` (Unity menu: ProPass → Export camera calibration) and restart the API.

## Waiting on Danny

- More product photo and barcode pairs in `Barcodes/` (git-ignored, two files per 10-digit SKU). Claude does not copy images from homedepot.com. Run `scripts/prepare_products.py`, add catalog entries, rebuild the scene, then retrain.
- Whether to keep characters at 71/85 or go back to capsule people at 78/85 for the published numbers.

## Open problems, in rough priority

1. **Lumber and the parked flatbed pass 1 of 5 held-out runs with characters** (4–5 of 5 with capsule people, and 3–4 of 5 on development seeds). Most reviews say a product was first seen beyond the checkout boundary. Work on development seeds only, then record fresh held-out seeds (10–14) to report, because seeds 5–9 have now been looked at.
1. **Hats are switched off** (`ProPassCharacters.cs`). A straw hat above a carried box is read as a small yellow product. The flatbed's tan deck is also sometimes read as lumber when it waits off-lane.
1. **Stacked identical boxes pass 60%.** Two copies pressed together look like one box from both cameras. Needs instance segmentation or a count-aware detector, or should stay a review case.
2. **One edge-of-frame run fails**, and the two-camera run misses two items there that the lane camera alone gets. Worth tracing.
3. **Roadmap leftovers:** thumbnail crops per event in the Decisions tab, a 60–90 s demo video, and real-camera data (nothing has been tested outside Unity).
4. `docs/training.md` still describes `training/replay.py`, which the benchmark recorder has replaced. Remove the script and that section together.

## Working notes

- The dashboard's **Training** tab (`/api/progress`) shows export, training, recording and scoring progress. Send training output to `artifacts/logs/train-*.log` so it can follow.
- A `MaterialPropertyBlock` color on any renderer leaks into the exporter's mask render unless it is lifted first (`ProPassDatasetExporter` does this). Check a few crops by eye after any export.
- Recording and exporting fail while the Editor is in Play mode, and Danny often leaves it playing. Check `unity command editor_status` first and ask before stopping it. `RecordDeferred` did not always fire when the Editor was unfocused: call `ProPassBenchmarkRecorder.Record(...)` through `eval` instead (the CLI times out after 5 s, but the recording continues).
- Unity Editor is usually open on `propass/unity`. Drive it with the Unity CLI: `unity command recompile`, `recompile_status`, `eval --code '...'`, `editor_play`, `editor_stop`. Long work goes through `RecordDeferred` or `ProPassDatasetExporter.Begin` (both return at once). If the Editor is closed: `unity projects open "$PWD/unity"`.
- Start services with `bash scripts/start.sh`, or separately: `nohup .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --no-access-log > artifacts/logs/api.log 2>&1 &` and `npm run dev` in `web/`. To restart the API, kill the pid from `ss -ltnp 'sport = :8000'`.
- Never `git add -A` without checking for `*.pt` or data folders. `main`'s history was rewritten once to remove them. A backup of the old history is at `artifacts/propass-history-before-clean.bundle`.
- Validate Mermaid diagrams and relative links before pushing docs.
- Another AI tool (Codex) has also worked in this folder. Check `git status` for uncommitted work before starting.
