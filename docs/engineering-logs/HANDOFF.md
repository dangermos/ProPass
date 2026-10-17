# Handoff notes (2026-10-12)

For the next person or AI picking this up. Read this first, then [docs/roadmap.md](../roadmap.md).

## Where things stand

**Everything is on `main`.** The current scene has 15 invented products (boxes, pails, a locked tool, bare lumber) from six invented brands, customers pushing three kinds of cart, and a stocked store. Both camera model pairs were retrained on 4,400 scenes of it on 2026-10-12.

| | Development seeds 0–4 | Held-out seeds 15–19 (scored once) |
|---|:-:|:-:|
| Passed | 67 | **68** |
| Closed automatically, exactly right | 57 | **58** |
| Correctly sent to an associate | 10 | 10 |
| Sent to an associate unnecessarily | 18 | 17 |
| Closed with a wrong or missing item | 0 | 0 |

The README, the project site (`web/public/results.json`) and `docs/benchmark.md` are generated from the reports: run `.venv/bin/python scripts/publish_results.py` after any new score instead of typing numbers. 156 tests pass.

Owner: Danny Germosen (SUNY Oswego, GitHub `dangermos`, private repo `dangermos/ProPass`). Danny wants real trained models, colorful visual docs, no bloat, and to be asked before deleting or restructuring. Commit and push often. He wants a reply at each milestone, not only status edits. **Run one heavy job at a time on his desktop**; `scripts/round.sh` and `scripts/unity_run.sh` already do that and throttle themselves.

**Held-out seeds 15–19 are now spent.** Record seeds 20–24 for the next reported number (`TEST_SEED_START` in `scripts/round.sh`).

## Things that are easy to get wrong

- **Models are per camera.** `models/detector.pt` and `models/classifier.pt` are the lane camera's. `models/overhead/` holds the overhead camera's pair. Train each with `training.train ... --camera lane|overhead`. They must match `catalog.json` (eight products): after changing the catalog, re-export data, retrain both pairs and re-record the benchmark. One shared two-view pair scored 39/75 through the lane camera, so don't merge them back. Weights are git-ignored. Earlier sets are in `models/v1/`, `v2/`, `v4/`, `v5/` (capsules), `v6/` (characters), `v7/` (carts, same as current).
- **Fusion is lane-primary** (`VisionEngine._fuse`). Only the lane camera starts objects. A symmetric version scored 45–58/75 because stray overhead detections blocked checkout.
- **Tune on `artifacts/benchmark` (seeds 0–4), report on `artifacts/benchmark-test` (seeds 10–14 since the cart round; they have now been scored once, so record 15–19 for the next report).** Both hold three-camera recordings (lane, overhead, scan) of 17 scenarios × 5 seeds with the eight-product catalog. Older sets are kept beside them (`-1cam`, `-2cam`, `-v2a`, `-v2b`, `-nocart`).
- After moving a camera, re-export `vision/cameras.json` (Unity menu: ProPass → Export camera calibration) and restart the API.

## Waiting on Danny

- More product photo and barcode pairs in `Barcodes/` (git-ignored, two files per 10-digit SKU). Claude does not copy images from homedepot.com. Run `scripts/prepare_products.py`, add catalog entries, rebuild the scene, then retrain.
- Which number to lead with: the README now shows all three rounds (78, 71, 60 of 85) side by side.

## Open problems, in rough priority

1. **17 of 85 held-out carts go to an associate without needing it.** The top reason is "entered merchandise disappeared before an observed checkout": an item is lost from view before the line (stacked packages 2 of 5, lumber 2 of 5, hesitation 3 of 5). Start from `models/benchmark-dev.json` review reasons and `python -m training.inspect_run` on development runs.
2. **Barcodes settle only 60 of 103 charged items.** A package behind another on a cart hides its label. A side scan camera or labels on two faces would help.
3. **A barcode that disagrees with how a package looks now always goes to an associate** (`PhysicalLedger._scan`). That removed the one wrong charge on development runs (a pail standing on a box took the box's label), at the cost of some automation when the classifier is the one that is wrong. A height-aware label assignment would be the better fix.
4. **Nothing real has been tested.** The smallest useful experiment: one real camera, one real cart, printed copies of these labels.
5. **Not redone for the new scene:** `docs/images/dashboard.jpg`, `v2-*.jpg`, `two-camera-live.jpg`, `messy-scenarios.jpg` and `models/evaluation-live.json` show the older scene; latency (36 ms per frame) was measured on the 8-product round.
6. **The follow camera passes behind the gate post** near the end of each run (`RecordVideo` in `ProPassBenchmarkRecorder.cs`: clamp its z further back, then `scripts/round.sh tour`). The flatbed scenes' thumbnails are also blocked by the flatbed.
7. **From the outside reviews, still open:** a confusion-matrix or failure-frame figure on the site, an automation-versus-safety curve, tracking metrics, and a check of the invented brand names against trademarks.

## Working notes

- **One command runs a round: `scripts/round.sh`.** Stages: label art, scene, training-data export (headless, 800 scenes per Unity launch), both camera model pairs, development recording (three Unity launches), development score on 4 processes. Each stage is skipped when rerun from a later one: `scripts/round.sh score`. Held-out and video stages run only when named: `scripts/round.sh test` and `scripts/round.sh tour`. Progress goes to `artifacts/logs/round.log`. It checks free memory before each heavy stage and stops under 6 GB. Measured on 2026-10-11 with nothing else running: export of 4,400 scenes 5 minutes, gate camera models 7 minutes, overhead models 7 minutes, recording 85 runs 18 minutes, scoring about 3 minutes.
- **Headless Unity goes through `scripts/unity_run.sh <log name> <Class.Method> [args]`**: half the cores, 12 GB cap, low priority, and it reverts the render-settings files Unity rewrites. Never name a bash variable `GROUPS`; it is reserved and cost one failed stage.
- **The catalog lives in three places that must agree:** `catalog.json` (prices, barcodes, art recipe), `unity/Assets/ProPass/Runtime/ProPassCatalog.cs` (prefab order, sizes, shapes, colors) and the generated art in `unity/Assets/ProPass/Products/` (`scripts/prepare_products.py`). All brands and products are invented; the names have not been checked against trademarks. Adding a product means: both tables, `scripts/round.sh` from `art`.
- **Old rounds are kept beside the new one:** `training/data-v6-carts`, `artifacts/benchmark-carts8`, `artifacts/benchmark-test-carts8`, weights in `models/v7/` (8 products, including the real-brand box that was removed).

- **Replay is the default way to run a scene without Unity.** `POST /api/replay {scenario}` (`api/app.py`, `feed_recording`) feeds `artifacts/benchmark/<scenario>/seed_02` through the same queue a live scene uses, at the recorded pace, waiting instead of dropping when inference is busy. Scenario cards use it whenever no live scene is streaming, and fall back to the recorded tour when the API or recordings are missing. `/api/frames` returns 409 for a replayed run; `/api/scenario` ends the replay. The recordings are a release asset (`recordings-carts-seed02`, `scripts/get_recordings.sh`); upload a new one after re-recording. Tests: `tests/test_api_replay.py`.
- **The WebGL build** (`ProPass/Build for the browser`, `ProPassWebBuild.cs`) writes `web/public/unity` (17 MB, committed). In the browser `ProPassSimulation` takes the API address from the page's origin and scales scene time to the measured capture rate (`playbackSpeed`). It was measured at 1 to 3 seconds per frame group in the desktop app's browser pane, so runs are slow motion. Faster options: skip the 4K barcode camera on alternate frames, or encode off the main thread. The asset pack's editor scripts needed their own editor-only asmdef to build a player (`Assets/ithappy/.../Scripts/Editor/*.Editor.asmdef`, a local file because the pack is git-ignored). The build rewrites `Assets/Settings/*.asset` and `GraphicsSettings.asset`; revert those with `git checkout` afterwards. Headless build, capped so it cannot starve the desktop: `scripts/webgl_build.sh`.
- **The project site** is the dashboard's front page (`#/`, `web/src/Project.tsx`). Its numbers are copied by hand from the reports in `models/`; update them with every new benchmark. The scenario picker moved to `#/scenarios`. Per-camera videos in `web/public/angles/` come from the same build script (`ANGLES` list).
- **Site and tour videos are 60 fps.** `scripts/record_video.sh` renders seed 2 of each scenario at 60 fps into `artifacts/video60` (pictures only, 4.4 GB, not in git). `scripts/build_tour.py` runs the models on the 8 fps benchmark recording of the same seed and draws those decisions over the 60 fps frames, sliding each box evenly between the moments the models saw; without `artifacts/video60` it falls back to the 8 fps frames. The recorder's memory grows by about 1 GB per scene, so record at most four scenes per Unity launch (`scripts/record_video.sh a,b,c,d`). Encoding all 17 takes about 25 minutes on half the cores.
- **Tour sound** is made in the browser (`web/src/sound.ts`, Web Audio, no audio files): a lane bed and cart wheels while a run plays, and one cue per decision, keyed off `kind` on each note in `web/public/tour/<scenario>.json`. The videos themselves carry no audio track. It is off until the viewer presses the Sound button, because browsers block audio before a click.
- **Four outside reviews (2026-10-11)** corrected the headline numbers: 50 carts close automatically in round 3, not 60, and round 1 closed one cart a board short. Keep the three-way split (automatic, correct hand-off, unnecessary hand-off) whenever results are quoted. Still open from the reviews: an author line (name, school, contact), the RIDGID box and product photo, a confusion-matrix or failure-frame figure, an automation-versus-safety curve, and one real-camera test.
- **The recorded tour** (`#/tour/<scenario>`, `web/src/Tour.tsx`) plays `web/public/tour/<scenario>.webm` and `.json`, built by `scripts/build_tour.py` from seed 2 of each development scenario with the current weights. Rebuild it after retraining or re-recording (about 5 minutes, light). `#/tour/mixed/10.3` opens paused at 10.3 s, which is how `docs/images/tour.jpg` was taken. Videos are small only when an `ffmpeg` is found; see the `Video` class.
- **Weights are a release asset** (`weights-v7-carts`), installed by `scripts/get_weights.sh`. Publish a new release after retraining and change the default tag in the script.

- **Run one heavy job at a time on Danny's machine.** On 2026-10-11 training both pairs while Unity recorded took the desktop down. Use `nice -n 10 ionice -c2 -n7`, log to `artifacts/logs/`, and check `free -h` and `nvidia-smi` first. Scoring is light (about 400 MB of GPU, 10 minutes per set). Headless recording of a few runs: see `scripts/record_missing.sh`.

- The dashboard's **Training** tab (`/api/progress`) shows export, training, recording and scoring progress. Send training output to `artifacts/logs/train-*.log` so it can follow.
- A `MaterialPropertyBlock` color on any renderer leaks into the exporter's mask render unless it is lifted first (`ProPassDatasetExporter` does this). Check a few crops by eye after any export.
- Recording and exporting fail while the Editor is in Play mode, and Danny often leaves it playing. Check `unity command editor_status` first and ask before stopping it. `RecordDeferred` did not always fire when the Editor was unfocused: call `ProPassBenchmarkRecorder.Record(...)` through `eval` instead (the CLI times out after 5 s, but the recording continues).
- Unity Editor is usually open on `propass/unity`. Drive it with the Unity CLI: `unity command recompile`, `recompile_status`, `eval --code '...'`, `editor_play`, `editor_stop`. Long work goes through `RecordDeferred` or `ProPassDatasetExporter.Begin` (both return at once). If the Editor is closed: `unity projects open "$PWD/unity"`.
- Start services with `bash scripts/start.sh`, or separately: `nohup .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --no-access-log > artifacts/logs/api.log 2>&1 &` and `npm run dev` in `web/`. To restart the API, kill the pid from `ss -ltnp 'sport = :8000'`.
- Never `git add -A` without checking for `*.pt` or data folders. `main`'s history was rewritten once to remove them. A backup of the old history is at `artifacts/propass-history-before-clean.bundle`.
- Validate Mermaid diagrams and relative links before pushing docs.
- Another AI tool (Codex) has also worked in this folder. Check `git status` for uncommitted work before starting.
