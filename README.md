# ProPass

A cashierless checkout research prototype: Unity generates a retail checkout world; trained computer vision reads its camera pixels; persistent physical objects become a reversible, versioned cart; a React dashboard confirms a simulated receipt.

**The first MVP is implemented.** It uses real PyTorch inference on rendered RGB images. Unity's SKU labels, object instance IDs, transforms, and trigger callbacks are never sent to the checkout API. Ground truth is exported separately for training and offline evaluation.

This is an independent portfolio project. The five products, prices, and customer identities are fictional. The current system has one customer in one lane, simulated identity selection, and simulated confirmation. It has no Home Depot integration, real authentication, payment processing, or demonstrated real-camera transfer.

## Run the existing local build

The Unity project is `/home/dangermos/ProPass`. The Python/web prototype is currently in `/home/dangermos/Home Depot Internship Project/propass`.

1. Open `Assets/ProPass/Scenes/Checkout.unity` in Unity and press **Play**. Ensure the Editor's Pause button is off.
2. From this directory, run `bash scripts/start.sh`. Keep its terminal open.
3. Open [the dashboard](http://127.0.0.1:5173/). Choose **Identical products**, watch two boxes cross, then select **Review checkout** and **Confirm simulated checkout**.

The script recognizes an already-running dashboard/API. API health is at [localhost:8000/api/health](http://127.0.0.1:8000/api/health); interactive endpoint documentation is at [localhost:8000/docs](http://127.0.0.1:8000/docs).

The current machine already has the dependencies and trained weights. A new checkout needs `models/detector.pt` and `models/classifier.pt`, either copied from these local artifacts or reproduced below. Checkpoint hashes are recorded in `models/manifest.json`.

## Install on another machine

Use Python 3.12, Node.js, and a CUDA-capable PyTorch installation appropriate for that machine. The tested machine used an RTX 4070 Super, CUDA PyTorch wheels, and Unity **6000.6.4f1** with URP **17.6**.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-vision.txt -r requirements-api.txt
cd web
npm ci
cd ..
bash scripts/start.sh
```

If PyTorch reports no CUDA device, verify the official PyTorch wheel/driver combination before training. CPU inference is supported as a fallback. Dependencies are pinned in `requirements-vision.txt`; web dependencies have `web/package-lock.json`.

For a fresh Unity URP project, copy `unity/Assets/ProPass` into its `Assets` directory, allow scripts to compile, and run **ProPass → Build checkout scene**. This creates `Assets/ProPass/Scenes/Checkout.unity`. The builder writes only the ProPass scene/assets. Product geometry and materials are generated locally; there are no third-party store assets.

## What to demonstrate

| Scenario | Expected result after about 15 seconds |
|---|---|
| Single item | One drill kit, despite repeated observations |
| Identical products | Two distinct physical drill kits; SKU quantity 2 |
| Mixed cart | Drill kit, measuring tape, work gloves |
| Temporary occlusion | One drill kit after a brief disappearance |
| Change of mind | Driver kit added forward, removed on observed reverse crossing; finishes around 29 seconds |
| Unknown product | Gray package tracked, checkout blocked for review |

Review pauses acquisition, drains the accepted frame queue, and freezes a cart version and frame watermark. Confirmation creates an immutable local receipt. Repeated requests with the same idempotency key return the same receipt. Restarting a run resets current tracking/cart state and preserves confirmed receipts.

An item still traversing the lane, ambiguous identity recovery, an unknown item at the boundary, or an unresolved product disappearance prevents confirmation. Pausing is intentionally conservative: physical visibility can be insufficient to infer a correct receipt.

## How it works

```mermaid
flowchart LR
  U[Unity scenario and RGB camera] -->|JPEG + frame/time/run| A[FastAPI bounded frame queue]
  A --> D[Fine-tuned YOLO26n merchandise detector]
  D --> C[EfficientNet-B0 crop classifier and rejection]
  C --> T[ByteTrack + canonical physical-object ledger]
  T --> E[Observed zone transitions and event engine]
  E --> S[Versioned cart and receipt service]
  S --> DB[(SQLite / optional PostgreSQL)]
  S -->|WebSocket snapshots| R[React demo dashboard]
  R -->|Scenario / prepare / confirm| A
  A -->|Scenario control only| U
  U -.->|Separate offline annotations| G[Training and evaluation data]
```

The detector learns **merchandise**, rather than making an object's SKU its tracking identity. The classifier combines learned probabilities with a feature-prototype distance gate, then the ledger aggregates accepted SKU evidence over time. ByteTrack IDs are associated with canonical object IDs using gated location, appearance, and one-to-one matching. Short-gap reattachment can recover a detector/tracker interruption; indistinguishable alternatives trigger review. Exact identical-object identity through arbitrary full occlusion is unresolved.

Forward travel must be observed in APPROACH and subsequently COMMIT, with hysteresis and dwell. Membership is keyed by canonical object, not by detection/frame or SKU. Reverse travel back to APPROACH removes that membership. A lost track does not automatically remove a purchased object. Backend uniqueness constraints and cart versioning protect against replayed events and stale confirmation.

See [architecture notes](docs/architecture.md), [implementation contract](docs/mvp-contract.md), and the training/evaluation artifacts in `models`.

## Reproduce training

Training data is procedural and contains no human footage. The exporter uses visible-instance masks for tight boxes, exports cropped SKU examples, and splits entire randomized scenes into **450 train / 90 validation / 60 test** images with disjoint seeds. A gray unenrolled package supplies limited outlier exposure. The current dataset has 1,081 training, 216 validation, and 142 test classifier crops including reject examples.

Stop Unity Play mode, open Checkout, and invoke this Editor C# through Unity CLI or an Editor script, substituting your absolute prototype directory:

```csharp
ProPass.Editor.ProPassDatasetExporter.Begin("/absolute/path/propass/training/data", 450, 90, 60);
```

Wait for `ProPassDatasetExporter.Running == false` and confirm `LastError` is empty. Then:

```bash
.venv/bin/python -m training.extract_outliers
.venv/bin/python -m training.train detector --epochs 35 --batch 8 --imgsz 640 --device 0
.venv/bin/python -m training.train classifier --epochs 12 --head-epochs 4 --batch 24 --device cuda:0
.venv/bin/python -m training.evaluate
```

The detector starts from COCO-pretrained YOLO26n. The classifier starts from ImageNet-pretrained torchvision EfficientNet-B0, trains its head for four epochs, then fine-tunes the last two feature stages. AMP is enabled on CUDA; prototype distance and temperature are selected from validation data. Test data is used for reporting, not checkpoint selection. Restart the API after replacing weights.

The local training runs took about **71 seconds for detection** and **25 seconds for the final classifier**. These times apply to this small synthetic dataset and this GPU; they are not estimates for real retail-scale training.

## Evaluate

```bash
.venv/bin/python -m pytest tests -q
cd web && npm run build && cd ..
# Requires Unity Play mode and the API; changes the current demo run:
.venv/bin/python scripts/verify_live.py
# Offline RGB replay; GT is used only for scoring:
.venv/bin/python -m training.replay --root artifacts/replays --output models/evaluation-temporal.json
```

The static image test detected 143/143 annotated packages at IoU ≥ 0.5. The SKU pipeline accepted 135/140 known detected crops, with 135/135 accepted classifications correct; three gray-package examples were rejected. Detector mAP50:95 was 0.868. These are **synthetic-domain measurements**, not general retail or real-camera accuracy. Full reports retain false/rejected examples and limitations. Unknown rejection has only been measured against one gray-package family.

Live and replay results are recorded separately because static crop accuracy does not establish cart accuracy. Unit tests cover membership deduplication, identical products, short-gap recovery, reverse removal, ambiguous matching, unfinished/lost merchandise, duplicate frames/events, stale versions, and confirmation races.

## Project layout

```text
api/                  frame ingress, session/cart/event persistence, confirmation
web/                  React/TypeScript camera, cart, events and scenario controls
vision/               learned RGB inference, SKU evidence, canonical object ledger
unity/Assets/ProPass/  source mirror of the installed Unity runtime and Editor scripts
training/             transfer learning, crop generation, static and replay evaluation
models/               local weights, hash manifest, measured evaluation reports
catalog.json          fictional products, prices and class mapping
scripts/              launch and full live integration check
tests/                tracker/event/backend edge cases
docs/                 system contract and architecture
artifacts/            ignored receipts database, replay frames and logs
compose.yaml          optional PostgreSQL; not required for the MVP
```

SQLite is the default and is sufficient for one local lane. To try PostgreSQL, run `docker compose up -d postgres` and set `PROPASS_DATABASE_URL=postgresql+psycopg://propass:propass_local_demo@127.0.0.1:5433/propass` before starting the API. Run **one API worker**: inference, sequencing, and the simulator session are currently in one process. PostgreSQL is optional and has not been the live demo's database.

Generated data, model binaries, receipts and dependency folders are ignored by Git. Keep evaluation reports and manifests; distribute weights only after reviewing their upstream license. Ultralytics uses AGPL-3.0 / commercial licensing; this README does not grant a license to its code or weights. All customer information in the demo is fabricated.

## Next experiments

1. Replace colored boxes with accurately textured package assets, adding confusing variants and held-out textures rather than merely more random colors.
2. Evaluate fresh temporal trajectories, complete occlusions, stacked merchandise, and camera perturbations against exact-cart and review rates.
3. Record a small consented real-camera dataset and measure synthetic-only versus synthetic-plus-real fine-tuning on a separate real test set.
4. Add QR session binding and a second camera only after defining the evidence needed to resolve a measured failure.

The meaningful portfolio claim today is: **a pixel-driven checkout system trained from a procedural Unity world, with measured synthetic perception and explicit transaction correctness rules**.
