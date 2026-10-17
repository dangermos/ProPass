# Handoff: put animated characters into the ProPass lane

> ✅ **Done on 2026-10-07.** Result and what it took: [docs/pro-express-v2.md](../pro-express-v2.md#with-animated-characters). Held-out 71 / 85 with nothing wrongly charged, against 78 / 85 with capsule people. This file is kept as the record of the task.

You are picking up one self-contained task in an existing project. Read this file fully, then `HANDOFF.md` and `docs/pro-express-v2.md` for wider context.

## The task

Replace the capsule "people" in the Unity checkout simulation with the animated characters from the Asset Store pack the owner imported, without breaking the vision pipeline or the benchmark.

**Done means all of these:**
1. The customer, crossing shoppers and the next-aisle shopper are pack characters that walk with a walking animation and stand with an idle one, in live Play mode **and** in the offline benchmark recorder.
2. With the pack folder missing, the project still compiles and runs with the current capsule people.
3. Nothing from the pack is committed to git.
4. Both camera model pairs are retrained on the new look, and the held-out benchmark is re-scored and published. Report the result honestly next to the current one (78 / 85, nothing wrongly charged).
5. Tests pass, docs are updated, work is pushed.

## The project in five lines

- Repo: `/home/dangermos/Home Depot Internship Project/propass`, GitHub `dangermos/ProPass` (private), branch `main`. Unity 6000.6.4f1 URP project in `unity/`.
- Unity renders a checkout lane and sends JPEGs from three cameras (lane, overhead, scan) to a FastAPI server. Trained models (YOLO26n + EfficientNet-B0 per camera) and a zxing-cpp barcode reader build a cart. A React dashboard shows it.
- **Rule that must never break:** only pixels and frame timing go from Unity to the API. No object names, IDs, SKUs or transforms.
- The detector has three classes: `merchandise`, `person`, `cart`. People are labeled `person` so they aren't mistaken for products. That is why changing how people look means retraining.
- Owner: Danny. He wants short progress updates, real trained models, no bloat, and to be asked before anything is deleted or restructured.

## What's there now

| Thing | Where |
|---|---|
| The pack (git-ignored) | `unity/Assets/ithappy/Creative_Characters_FREE/` |
| Character base | `Prefabs/Base_Mesh.prefab` (has an Animator), plus part prefabs in `Prefabs/Body`, `Outfit`, `Outwear`, `Pants`, `Shoes`, `Hairstyle`, `Faces`, and complete looks in `Prefabs/Costumes`, `Prefabs/Mascots` |
| Animations | `Animations/Other_Animations/*.anim`: `Walk_Forward`, `Walk_Backward`, `Idle_Relaxed`, `Idle_Breathing`, `Idle_Look_Around`, strafes, runs, jumps. Controller: `Animations/Animation_Controllers/Character_Movement.controller` (parameters `Vert`, `Hor`, `State`, `IsJump`) |
| The pack's own demo | `Scenes/Demonstration.unity`, scripts in `Scripts/Character_Controller` (player input: not needed here) |
| Capsule people today | `ProPassActorFactory.Shopper()` and `.Arm()` in `unity/Assets/ProPass/Runtime/ProPassActorFactory.cs`; the scene's "Customer proxy" built in `ProPassSceneBuilder.Build()` |
| Who moves them | `ProPassScenarioRunner.Apply(t)` places every actor from a `ScenarioPlan`. The customer follows the first in-lane product at `z + 0.65`. |
| Offline rendering | `ProPassBenchmarkRecorder` and `ProPassDatasetExporter` run in **Edit mode** and call `runner.Apply(t)` or place actors directly, then render. There is no Play mode and no `Update()`. |

The import also added the `com.unity.postprocessing` package and a scripting define. Those are committed. The pack is already URP.

## How to build it (recommended approach)

1. **Find the prefabs without hard references.** The pack may be absent, so don't reference its types or GUIDs from `Runtime` code. In `ProPassSceneBuilder.Build()` (Editor code), look the prefabs and clips up with `AssetDatabase.LoadAssetAtPath` under `Assets/ithappy/...` and store them in new serialized fields on `ProPassSimulation` (for example `GameObject[] characterPrefabs`, `AnimationClip walkClip`, `AnimationClip idleClip`). If they're null, everything falls back to capsules. The dataset exporter and recorder get them from the `ProPassSimulation` in the scene.
2. **Make a few distinct looks.** Assemble 4 to 6 characters (base mesh plus outfit parts, or the costume prefabs) so shoppers differ. Decide which is the customer. Scale to roughly 1.75 m: the capsule person's head is at about y = 2.0.
3. **Pose by time, not by Animator ticking.** Every actor's pose must be a pure function of scenario time `t`, because the recorder renders in Edit mode and runs must replay exactly. Use `clip.SampleAnimation(character, time)` with `time = (distanceWalked / strideLength) % clip.length` (or `t * speed`), choosing the walk clip when the actor is moving and an idle clip when it isn't. Disable root motion and don't let the Animator drive position: the plan owns position. Face the direction of travel (rotate toward the velocity from two nearby samples of the plan).
4. **Keep the factory interface.** Give `ProPassActorFactory` the character prefabs and return a character from `Shopper()` when they exist. Add a small per-actor "pose at time t" hook that `ProPassScenarioRunner.Apply` calls. Replace the scene's customer proxy the same way, keeping `simulation.customer` as its transform.
5. **Carrying.** Products float at carry height in front of the customer today. A simple, acceptable result is the character walking just behind its product with arms roughly forward. Don't parent products to hand bones unless it stays deterministic and the product's plan position is unchanged, because ground truth and the expected cart come from the plan.
6. **Hands.** `Arm()` (the "busy hands" occluder) can stay a simple arm, or become a character reaching in. Keep it an occluder in front of the box face.
7. **Labels.** In `ProPassDatasetExporter.ExportOne`, people are added to `instances` with class 1. Make sure the new characters (all their renderers, including `SkinnedMeshRenderer`) are included the same way, so masks and boxes are right. Sample a random walk or idle pose per scene for variety.

## Then retrain and re-measure (required)

People look different, so the `person` class and everything near people changes. From the repo root:

```bash
# 1. Unity must be out of Play mode. Rebuild the scene, then export data (returns at once; poll training/data/export-progress.json)
unity command --timeout 180 eval --code 'ProPass.Editor.ProPassSceneBuilder.Build(); return "built";'
mv training/data training/data-v5 && mkdir training/data
unity command eval --code 'ProPass.Editor.ProPassDatasetExporter.Begin("/home/dangermos/Home Depot Internship Project/propass/training/data", 2000, 320, 320); return 1;'

# 2. Keep the current weights, then train a pair per camera (about 25 minutes in total)
mkdir -p models/v5/overhead && cp models/*.pt models/manifest.json models/v5/ && cp models/overhead/* models/v5/overhead/
.venv/bin/python -m training.extract_outliers
for cam in lane overhead; do
  .venv/bin/python -m training.train detector   --epochs 60 --batch 16 --imgsz 640 --device 0 --camera $cam
  .venv/bin/python -m training.train classifier --epochs 12 --head-epochs 4 --batch 32 --device cuda:0 --camera $cam
done

# 3. Re-record both benchmark sets (the CLI call times out after 5 s; the recording keeps going. Wait for 85 run.json files each.)
mv artifacts/benchmark artifacts/benchmark-v2b && mv artifacts/benchmark-test artifacts/benchmark-test-v2b
unity command eval --code 'ProPass.Editor.ProPassBenchmarkRecorder.Record("/home/dangermos/Home Depot Internship Project/propass/artifacts/benchmark", 5, ProPass.ProPassScenarios.All); return 1;'
unity command eval --code 'ProPass.Editor.ProPassBenchmarkRecorder.Record("/home/dangermos/Home Depot Internship Project/propass/artifacts/benchmark-test", 5, ProPass.ProPassScenarios.All, 5); return 1;'

# 4. Score. Tune only on the development set. Score the held-out set once.
.venv/bin/python -m training.benchmark --root artifacts/benchmark --label characters-dev --output models/benchmark-v2-dev.json
.venv/bin/python -m training.benchmark --root artifacts/benchmark-test --label "Pro Express v2 · characters · held-out seeds 5–9" --output models/benchmark-v2-test.json --docs
```

Current numbers to compare against: development 78 / 85, held-out 78 / 85, no wrongly charged items on held-out. If the new result is clearly worse, look at the failing runs before publishing (`models/benchmark-*.json` has per-run review reasons). The old weights in `models/v5/` let you go back.

Finally run the live check with Unity in Play mode and the API restarted: `.venv/bin/python scripts/verify_live.py` (expects 6 of 6).

## Rules and traps

- **Never commit the pack.** `unity/Assets/ithappy/` is in `.gitignore`. Check `git status` before every commit. Also never commit `*.pt`, `training/data*`, `artifacts/` or `Barcodes/`. Don't use `git add -A` blindly.
- **Play mode blocks recording and exporting.** Danny often leaves Unity playing. Check `unity command editor_status` and ask him before stopping it.
- **Unity CLI basics:** `unity command recompile`, then poll `unity command recompile_status --json` until `"status": "completed"` and check `failed`. `unity command eval --code '...'` runs Editor C#. `unity command editor_play` / `editor_stop`. If the Editor is closed: `unity projects open "$PWD/unity"`.
- **Restart the API** after changing models: kill the pid from `ss -ltnp 'sport = :8000'`, then `nohup .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --no-access-log > artifacts/logs/api.log 2>&1 &`. Don't `pkill -f uvicorn` from a command line that contains that word.
- **Determinism:** no `Time.time`, `Random` without the plan's seed, or Animator state in anything the recorder renders.
- **Skinned mesh bounds:** make sure characters aren't culled when partly off-screen (`updateWhenOffscreen` or generous bounds), or the mask renders will miss them.
- **Scan camera:** a character walking in front of a box face hides its barcode. That is realistic, but keep the customer behind its products as now, or barcode reads will drop.
- **Tests:** `.venv/bin/python -m pytest tests -q` (143 pass today). `cd web && npm run build` if you touch the dashboard.

## Docs to update when done

- `docs/pro-express-v2.md`: tick **E6 Characters** and add the new result row.
- `docs/benchmark.md` is regenerated by `--docs`.
- `docs/getting-started.md`: say the pack is optional, where it goes (`unity/Assets/ithappy/`, imported through Package Manager → My Assets), and that capsules are used without it.
- `HANDOFF.md`: update the status table.
- Refresh `web/public/scenarios/*.jpg` and the README screenshots if people are visible in them. Screenshots that show pack characters are fine to commit. The pack's files are not.
- Commit in small steps with clear messages, and push to `main` (or a branch plus a note to Danny if the benchmark got worse).
