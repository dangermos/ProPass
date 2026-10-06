# Handoff notes (2026-10-06)

For the next person or AI picking this up. Read this first, then [docs/roadmap.md](docs/roadmap.md).

## Where things stand

`main` holds everything and is verified: Phases A, B and C, plus the title screen and dashboard tabs.

| Check | Result |
|---|---|
| Tests | 124 pass (`.venv/bin/python -m pytest tests -q`) |
| Held-out benchmark, two cameras | 72 / 75 ([docs/benchmark.md](docs/benchmark.md)) |
| Held-out benchmark, lane camera only | 71 / 75 |
| Live check, both cameras | 6 / 6 (`scripts/verify_live.py`) |

Owner: Danny (GitHub `dangermos`, private repo `dangermos/ProPass`). Danny wants real trained models, colorful visual docs, no bloat, and to be asked before deleting or restructuring. Commit and push often.

## Things that are easy to get wrong

- **Models are per camera.** `models/detector.pt` and `models/classifier.pt` are the lane camera's (the v2 weights). `models/overhead/` holds the overhead camera's pair. One shared two-view pair scored 39/75 through the lane camera, so don't merge them back. Weights are git-ignored. Earlier sets are in `models/v1/`, `models/v2/`.
- **Fusion is lane-primary** (`VisionEngine._fuse`). Only the lane camera starts objects. A symmetric version scored 45–58/75 because stray overhead detections blocked checkout.
- **Tune on `artifacts/benchmark` (seeds 0–4), report on `artifacts/benchmark-test` (seeds 5–9).** Both hold two-camera recordings of 15 scenarios × 5 seeds. The older single-camera sets are `artifacts/benchmark-1cam` and `artifacts/benchmark-test-1cam`.
- After moving a camera, re-export `vision/cameras.json` (Unity menu: ProPass → Export camera calibration) and restart the API.

## Open problems, in rough priority

1. **Stacked identical boxes pass 60%.** Two copies pressed together look like one box from both cameras. Needs instance segmentation or a count-aware detector, or should stay a review case.
2. **One edge-of-frame run fails**, and the two-camera run misses two items there that the lane camera alone gets. Worth tracing.
3. **Roadmap leftovers:** thumbnail crops per event in the Decisions tab, a 60–90 s demo video, and real-camera data (nothing has been tested outside Unity).
4. `docs/training.md` still describes `training/replay.py`, which the benchmark recorder has replaced. Remove the script and that section together.

## Working notes

- Unity Editor is usually open on `propass/unity`. Drive it with the Unity CLI: `unity command recompile`, `recompile_status`, `eval --code '...'`, `editor_play`, `editor_stop`. Long work goes through `RecordDeferred` or `ProPassDatasetExporter.Begin` (both return at once). If the Editor is closed: `unity projects open "$PWD/unity"`.
- Start services with `bash scripts/start.sh`, or separately: `nohup .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --no-access-log > artifacts/logs/api.log 2>&1 &` and `npm run dev` in `web/`. To restart the API, kill the pid from `ss -ltnp 'sport = :8000'`.
- Never `git add -A` without checking for `*.pt` or data folders. `main`'s history was rewritten once to remove them. A backup of the old history is at `artifacts/propass-history-before-clean.bundle`.
- Validate Mermaid diagrams and relative links before pushing docs.
- Another AI tool (Codex) has also worked in this folder. Check `git status` for uncommitted work before starting.
