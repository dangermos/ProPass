# 🧪 Training and results

> [!TIP]
> **The short way: `scripts/round.sh`.** One command exports the training data, trains both camera model pairs, records the 85 development runs and scores them, unattended and throttled, and it resumes where it stopped. `scripts/round.sh test` records and scores fresh held-out runs once; `scripts/round.sh tour` renders the 60 fps tour videos; `.venv/bin/python scripts/publish_results.py` then writes the numbers into the README and the site. Watch it with `tail -f artifacts/logs/round.log`. The sections below explain each stage and how to run it by hand.

> [!NOTE]
> **Current results live in the [README](../README.md#measured-results) and [benchmark.md](benchmark.md).** Tables on this page that mention 5 or 8 products, or held-out seeds 5–9, are from earlier rounds and are kept as history.


Both models are trained only on **procedural Unity data** from the lane and overhead views. There's no human footage and no scraped imagery. Unity's labels are used offline and never at runtime. The two-view training set has **2,100 scenes**. The scenario benchmark uses separate recordings and seeds.

```mermaid
flowchart LR
    U[🎮 Unity<br/>ProPassDatasetExporter]:::u --> D[(training/data<br/>images · YOLO labels<br/>crops · manifests)]:::d
    D --> O[extract_outliers<br/>gray unknown crops]:::t
    D --> TD[train detector<br/>YOLO26n ← COCO]:::t
    O --> TC[train classifier<br/>EfficientNet-B0 ← ImageNet]:::t
    TD --> M[(models/<br/>detector.pt · classifier.pt<br/>manifest.json)]:::m
    TC --> M
    M --> E1[evaluate<br/>static held-out scenes]:::e
    M --> E2[benchmark<br/>synchronized lane + overhead RGB]:::e
    M --> E3[verify_live<br/>Unity + API end to end]:::e

    classDef u fill:#ffe9df,stroke:#ff7a3d,color:#4a1800
    classDef d fill:#f2f4f8,stroke:#8fa3bf,color:#1b2533
    classDef t fill:#f1e9ff,stroke:#bd9aff,color:#2c1660
    classDef m fill:#e6efff,stroke:#6aa8ff,color:#0b2a5c
    classDef e fill:#d9f7e8,stroke:#2ea043,color:#0b3d1d
```

> 📈 **Watching a run.** The dashboard's **Training** tab shows each step below as a progress bar and refreshes every 3 seconds. It reads `training/data/export-progress.json`, the newest `artifacts/logs/train-*.log` (so send training output there, for example `... 2>&1 | tee artifacts/logs/train-v7.log`), and the run folders under `artifacts/benchmark*`. It only watches. It never starts anything.

## 📦 1. Export a dataset from Unity

Each randomized scene selects the lane or overhead camera with equal probability, then varies camera pose, lighting and its color, and package placement, rotation and scale. This creates approximately equal numbers of both views; it does not render a paired training image for every scene. The manifest records `camera`. Scenes are deliberately cluttered with the same actors the messy scenarios use:

| In the scene | Label | Why |
|---|---|---|
| 📦 Products, including stacked pairs, rail-edge and half-out-of-frame placements | `0 merchandise` + an SKU crop | What the system must find and recognize |
| 🧍 The customer, other shoppers, loose hands and arms | `1 person` | So people stop being mistaken for products |
| 🪵 Lumber flatbeds | `2 cart` | So large occluders stop being mistaken for products |
| 📱☕👜 Phones, cups, bags | *unlabeled* | **Hard negatives:** learned as background |

Labels come from **one mask render per instance**, with everything else drawn black, so boxes are tight to the *visible* pixels and a half-hidden box gets a half-size label.

Stop Play mode, open the Checkout scene, and run this Editor C# (through Unity CLI or an Editor script), using your absolute path:

```csharp
ProPass.Editor.ProPassDatasetExporter.Begin("/absolute/path/propass/training/data", 1600, 250, 250);
```

With the Unity CLI against the open Editor, wrap it in `unity command eval --code '...; return "ok";' --project-path "$PWD/unity"`. It runs in the background and writes `export-progress.json`; time depends on scene clutter and mask renders. Wait for `ProPassDatasetExporter.Running == false`, then check that `LastError` is empty. You'll get:

```text
training/data/
  detection/images/{train,val,test}/scene_00001.jpg
  detection/labels/{train,val,test}/scene_00001.txt   ← YOLO: 0 merchandise · 1 person · 2 cart
  detection/dataset.yaml
  crops/{train,val,test}/{PEX-001…PEX-005, ZZZ-UNKNOWN}/
  manifests/{train,val,test}/scene_00001.json          ← camera, per-object SKU + physical ID
```

The splits are **whole scenes with disjoint random-seed ranges** (1,600 / 250 / 250), so related frames from one recording never land in both train and test. The current classifier has 4,054 training, 631 validation and 637 test crops, including the gray reject class. The scenario benchmark uses entirely separate seeds and recordings. These are held-out scene seeds, not held-out assets, stores or real cameras.

## 🏋️ 2. Train

```bash
.venv/bin/python -m training.extract_outliers
.venv/bin/python -m training.train detector   --epochs 60 --batch 16 --imgsz 640 --device 0
.venv/bin/python -m training.train classifier --epochs 12 --head-epochs 4 --batch 32 --device cuda:0
```

| | 🔵 Detector | 🟣 Classifier |
|---|---|---|
| Start | COCO-pretrained `yolo26n.pt` | ImageNet EfficientNet-B0 (torchvision) |
| Task | 3 classes: merchandise, person, cart (only merchandise is tracked) | 5 SKUs + 1 reject (training-only gray package) |
| Recipe | 640 px, AdamW lr 1e-3, mild geometry and lighting augmentation, **no horizontal flip** (it would mirror packaging text), patience 10 | 4 epochs head-only, then 8 epochs fine-tuning the last two feature stages with BatchNorm frozen |
| Calibration | Operating confidence 0.20 | Temperature and per-class prototype distance, chosen on **validation only** |
| Output | `models/detector.pt` | `models/classifier.pt` (also holds SKU order, prototypes and calibration) |

Each run records its checkpoint SHA-256, settings and metrics in [models/manifest.json](../models/manifest.json). AMP is on when CUDA is available. Restart the API after replacing weights.

### 🎯 One model pair per camera

Training writes to `models/detector.pt` and `models/classifier.pt`. The engine loads a camera's own pair from `models/<camera>/` when that folder exists, and the shared pair otherwise.

| Camera | Checkpoints | Trained on |
|---|---|---|
| 🔵 Lane | `models/detector.pt`, `models/classifier.pt` (v2) | 1,200 cluttered scenes from the lane camera |
| 🟣 Overhead | `models/overhead/` | 2,100 scenes, half from each camera |

To retrain a camera's pair, export data (the exporter renders half the scenes from each camera) and pass `--camera lane` or `--camera overhead` to both `training.train` commands. That trains on that camera's scenes only and saves into that camera's folder.

**Why not one shared pair?** That was tried first. The two-view pair scored **39 / 75** development runs through the lane camera, against **68 / 75** for the lane-only pair on the same recordings. The earlier weights are kept in `models/v1/` and `models/v2/`.

> [!TIP]
> These training times are for this small synthetic dataset. They aren't estimates for real retail-scale training.

## 📊 3. Results

### Static held-out test, lane camera models (150 cluttered scenes, 387 packages)

| Metric | v2 (cluttered lane view) | v1 (clean lane view) |
|---|---:|---:|
| 🎯 Detector mAP50–95, merchandise class | **0.843** | 0.868 |
| 🎯 Detector mAP50–95, all classes | 0.877 | — |
| 📦 Packages found (IoU ≥ 0.5, conf ≥ 0.20) | **380 / 387** | 143 / 143 |
| 🏷️ SKU top-1 on real detector crops | 359 / 372 | 139 / 140 |
| ✅ Accepted SKU predictions that were correct | **301 / 301** | 135 / 135 |
| 🤚 Known products abstained (sent to review) | 71 / 372 | 5 / 140 |
| ❓ Unknown gray package rejected | **8 / 8** | 3 / 3 |
| 👻 Empty scenes with a false box | 1 / 7 | 0 / 2 |
| ⚡ Detector + classifier latency (GPU) | 8.6 ms median · 10.3 ms p95 | 9.8 · 12.8 ms |

The v2 test set was harder than v1: people, hands, flatbeds, distractors, stacked and half-visible boxes. The two columns aren't directly comparable. On that v2 report, **301/301 accepted detected-crop predictions were correct**, with 71 known crops abstained. Those historical results do not describe the current two-view checkpoint. The v1 and v2 checkpoints are preserved locally in `models/v1/` and `models/v2/`.

The historical v2 per-scene report is [models/v2/evaluation-static-test.json](../models/v2/evaluation-static-test.json); the root-level static report is regenerated for the active weights.

### A failure the evaluation caught

The first classifier had **no reject class**, and it accepted 1 of the 3 unknown crops as a known SKU (only 2 of 3 rejected). Adding outlier exposure and the prototype gate fixed that case. The baseline checkpoint and its report are kept in [models/baseline/](../models/baseline) for comparison.

| | Initial closed-set baseline | Initial v1 model with reject |
|---|:---:|:---:|
| Unknown detected crops rejected | 2 / 3 ❌ | 3 / 3 ✅ |
| Accepted known predictions correct | 137 / 138 | 135 / 135 |

The trade-off is visible here: the stricter model sends a few more known items to review instead of risking a wrong SKU.

### 🔁 Temporal evaluation

Use [training/benchmark.py](../training/benchmark.py) for current lane-plus-overhead recordings, as described below. It calls `process_frames` once per synchronized group and reads product ground truth only to score the output.

The older [training/replay.py](../training/replay.py), recordings under `artifacts/replays/`, and [initial single-item report](../models/evaluation-temporal-initial-single.json) remain as historical artifacts. That script's oracle uses the original lane image-space zones and is not the dual-camera benchmark. The live component no longer has Replay Directory or Maximum Replay Frames Inspector settings.

### 🎮 Live end-to-end (Unity → API → cart)

```bash
.venv/bin/python scripts/verify_live.py   # needs Unity in Play mode + the API
```

| Scenario | Expected | Got |
|---|---|:---:|
| Single | 1× PEX-001 | ✅ |
| Identical products | 2× PEX-001 | ✅ |
| Mixed | PEX-001, PEX-003, PEX-005 | ✅ |
| Temporary occlusion | 1× PEX-001 | ✅ |
| Change of mind | empty cart | ✅ |
| Unknown product | empty cart, review required | ✅ |

The table above is the verified **Phase B v2 reference run**. Current live verification is recorded in the report below; inspect it rather than assuming those earlier results still apply after changing models, calibration or fusion.

Source: [models/evaluation-live.json](../models/evaluation-live.json).

## 🎯 Scenario benchmark

The benchmark scores **15 scenarios × 5 seeds = 75 runs** per split. It includes the six classic scenarios, clutter/interaction cases and **parked**, where a flatbed hides merchandise from the lane camera for 7–9 seconds. That scenario tests whether the overhead view adds usable evidence during a prolonged lane-view occlusion.

![Messy scenarios](images/messy-scenarios.jpg)

**1. Record** (Unity renders every run offline at 8 fps, with no Play mode and no API):

- From the menu: **ProPass → Record benchmark suite**, then choose an output folder. The menu's quick-run default is four seeds; use the explicit commands below for the five-seed development/test protocol.
- Or with the Unity CLI against the open Editor:
  ```bash
  unity command eval --code 'return ProPass.Editor.ProPassBenchmarkRecorder.RecordDeferred("/abs/path/propass/artifacts/benchmark", 5);' --project-path "$PWD/unity"
  unity command eval --code 'return ProPass.Editor.ProPassBenchmarkRecorder.RecordDeferred("/abs/path/propass/artifacts/benchmark-test", 5, null, 5);' --project-path "$PWD/unity"
  ```
- Or headless, with the project closed:
  ```bash
  Unity -batchmode -quit -projectPath unity -executeMethod ProPass.Editor.ProPassBenchmarkRecorder.RunFromCommandLine -benchmarkOut "$PWD/artifacts/benchmark" -benchmarkSeeds 5
  ```

Run these recording calls **one at a time**, waiting for the completion log before scheduling another. Recording replaces matching output run folders, so choose a fresh directory if you need to preserve them. The existing development and held-out dual-view recordings are already complete; scoring them does not require Unity or re-recording.

```text
artifacts/benchmark/<scenario>/seed_00/
  000001.jpg           lane RGB
  000001.overhead.jpg  overhead RGB at the same instant
  000001.json          timing and separate offline truth
  run.json             seeded scenario and expected cart/review
```

The per-frame truth stores SKU, physical ID, lane projected bounds and world position. The expected cart comes from **world-space motion**: a product counts when carried inside the lane from behind the orange marker to past the teal marker. The same `(scenario, seed)` renders the same run. Only JPEGs and source timing enter inference; the scorer reads truth separately. Identity-switch/recall matching uses the **lane view's** ground-truth boxes, so those metrics do not measure overhead visibility directly.

**2. Score:**

```bash
.venv/bin/python -m training.benchmark --root artifacts/benchmark --label dev-1cam --cameras lane
.venv/bin/python -m training.benchmark --root artifacts/benchmark --label dev-2cam
```

`--cameras lane` scores the lane camera alone on the same recordings, so the second camera's contribution is isolated. `--image-mode` ignores the calibration and uses image-space zones. `--models <dir>` scores a different set of checkpoints.

**Tune on development seeds 0–4 only.** Once settings are fixed, score held-out seeds 5–9 once and update [benchmark.md](benchmark.md):

```bash
.venv/bin/python -m training.benchmark --root artifacts/benchmark-test --label "One camera" --cameras lane --output models/benchmark-c-world-1cam-test.json
.venv/bin/python -m training.benchmark --root artifacts/benchmark-test --label "Two cameras" --output models/benchmark-c-final-test.json --docs --compare models/benchmark-c-world-1cam-test.json
```

| 75 runs each | One camera | Two cameras |
|---|:-:|:-:|
| Development seeds 0–4 | 68 | **71** |
| Held-out seeds 5–9 | 71 | **72** |

The second camera's clear win is the **parked flatbed** scenario, where the lane camera can't see the products for 7–9 seconds: 40% → 100% on development seeds and 80% → 100% on held-out seeds. Everything else is level. Stacked identical boxes and one edge run still fail with either setup.

## ⚠️ What these numbers don't prove

- The five packages are visually distinct colored boxes. Look-alike SKUs haven't been tested.
- Unknown rejection was measured against **one** gray package family, so it isn't open-world detection.
- Training and test share procedural assets and environment, so held-out assets, stores and real cameras are untested. A second synthetic camera does not establish synthetic-to-real transfer.
- Static accuracy doesn't establish cart accuracy. That's why replay and live results are reported separately.

**Next experiments:** textured package assets with confusing variants and held-out textures, carry-height variation and calibration error, and a small consented real-camera dataset comparing synthetic-only against synthetic+real fine-tuning.
