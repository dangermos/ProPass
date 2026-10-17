# ProPass

**A checkout lane that rings up the cart as it rolls through, and calls an associate when it is not sure.** A simulated store lane, three cameras, trained vision models, and a ledger that gives every physical item one identity. Built by **Danny Germosen** (SUNY Oswego).

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-CUDA-EE4C2C?logo=pytorch&logoColor=white)
![YOLO26n](https://img.shields.io/badge/Detector-YOLO26n-00B4D8)
![EfficientNet-B0](https://img.shields.io/badge/Classifier-EfficientNet--B0-8E44AD)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/UI-React%20%2B%20Vite-61DAFB?logo=react&logoColor=black)
![Unity 6](https://img.shields.io/badge/Sim-Unity%206.6%20URP-000000?logo=unity&logoColor=white)
![Tests](https://img.shields.io/badge/tests-156%20passing-2EA043)

![The project site](docs/images/site.jpg)

> [!NOTE]
> An independent student project inspired by contractor checkout. It is **not affiliated with or endorsed by The Home Depot**. Every brand, product, price and customer in it is invented, and no payment is taken. Every number below was measured on **simulated images rendered by Unity**. Nothing has been tested on a real camera.

## What it does

1. **See.** A small object detector finds every package, person and cart in two camera views, and a tracker follows each package.
2. **Identify.** A third camera reads the barcode on each package. Where no label is visible, an image classifier recognizes which of the 15 catalog products it is, or says it does not know.
3. **Fuse.** Camera calibration puts both views on one floor plan, so a package seen twice is one object and a hidden package is not lost.
4. **Decide.** Each physical item gets one identity. It is added when it crosses the checkout line, removed if it comes back, and rated for how sure the system is.
5. **Hand off.** Unknown products, restricted tools and anything unsettled go to an associate. The scanned part of the cart is kept.

Unity never tells the vision system what is in the cart. Each camera sends a plain image with a timestamp, and everything else is worked out from pixels.

![Four views of one moment: the follow camera, and the three cameras the system uses](docs/images/tour.jpg)

## Measured results

The current scene has 15 invented products (boxes, pails, a locked tool, bare lumber), customers pushing shopping, flat and lumber carts, and a stocked store. It was scored on **85 held-out runs** (17 scenarios × seeds 15–19) that were recorded after tuning was finished and scored once.

| 85 runs each | Development (seeds 0–4) | **Held-out (seeds 15–19)** |
|---|:-:|:-:|
| Passed: cart exactly right, associate called only when needed | 67 | **68** |
| Closed automatically, exactly right | 57 | **58** |
| Correctly sent to an associate (unknown product, locked tool) | 10 | **10** |
| Sent to an associate unnecessarily | 18 | **17** |
| Closed with a wrong or missing item | 0 | **0** |
| Items the cameras lost (all in carts sent to an associate) | 13 | 13 |
| Wrong lines inside carts sent to an associate | 0 | 1 |
| Charged items settled by barcode | 62 of 101 | 60 of 103 |

- **58 of 85 held-out carts closed with nobody stepping in, and all 10 carts that needed a person were sent to one.**
- **No cart closed with a wrong or missing item** on the held-out runs.
- **The open problem is the 17 unnecessary hand-offs.** 9 of them had an incomplete or wrong cart (13 items the cameras lost, 1 wrong line), which is why they were not closed. Most common reasons: entered merchandise disappeared before an observed checkout or reverse removal (12); product first observed beyond checkout boundary (6); conflicting sku evidence on the same physical object (3).

Models (test split of the training data): gate camera detector mAP50-95 0.818, classifier 95.5%; overhead detector mAP50-95 0.867, classifier 94.6%. Per-scenario scores are in [docs/benchmark.md](docs/benchmark.md). Earlier rounds with 8 products are in [docs/pro-express-v2.md](docs/pro-express-v2.md).

**Read these numbers with care.** 85 runs can find failures but cannot promise a rate: zero wrong closes in 85 runs still allows a true rate of up to about 3.5%. Five runs per scenario are signals, not percentages.

## Quickstart

### 1. Watch it: two minutes, Node.js only

```bash
git clone https://github.com/dangermos/ProPass && cd ProPass/web
npm ci && npm run dev          # open http://127.0.0.1:5173
```

The front page explains the project. **Watch the 17 scenes** opens the recorded tour: every scenario from four camera angles at 60 fps, with the cart the system built and what it decided beside the video, and a **Sound** button. No GPU, Unity or model weights are needed, because the videos are in the repository. Each tour scene is development seed 2 of its scenario, pass or not.

### 2. Run the models live, without Unity

Needs Python 3.12 and ideally a CUDA GPU. The weights and one recorded run per scenario are release assets (they need the [GitHub CLI](https://cli.github.com/) signed in).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-vision.txt -r requirements-api.txt
bash scripts/get_weights.sh          # both camera model pairs, 42 MB
bash scripts/get_recordings.sh       # frames Unity already rendered, about 500 MB
.venv/bin/python -m pytest -q tests  # 156 tests
(cd web && npm ci)
bash scripts/start.sh                # API on :8000, dashboard on :5173
```

Open the dashboard, click **Open the lab** and pick any scenario. The API plays the recorded frames through the trained models at the recorded pace, so the **Live lane** tab shows the real pipeline: boxes, the cart building, ratings, the associate hand-off and checkout.

### 3. Render a scene yourself

Needs Unity **6000.6.4f1** (URP 17.6). Open `unity/` in Unity Hub, load `Assets/ProPass/Scenes/Checkout.unity` and press **Play** with the API running. The dashboard follows the live scene. The animated characters come from a free Asset Store pack that is not in this repository; without it the scene uses capsule people.

### 4. Rebuild everything from scratch

One command exports the training data, trains both camera model pairs, records the development runs and scores them. It runs unattended, throttles itself, and picks up where it stopped.

```bash
scripts/round.sh            # about 40 minutes on an RTX 4070 Super
scripts/round.sh test       # record and score fresh held-out runs, once
scripts/round.sh tour       # render the 60 fps tour videos
tail -f artifacts/logs/round.log
```

## The 17 scenarios

| Group | Scenarios |
|---|---|
| Clean | single item · identical products · mixed cart · temporary occlusion · change of mind · unknown product |
| Messy | busy hands · crossing shopper · crossing flatbed · edge of frame · stacked packages · distractors · next-aisle shopper · hesitation · parked flatbed · locked-cage tool · lumber |

## Known limits

- **Simulated only.** No real camera, lighting, motion blur or lens has been tested.
- **Too many hand-offs.** 17 of 85 held-out carts were sent to an associate without needing it. That rate would not work in a store, and cutting it is the main open problem.
- **Small test.** 15 products and 85 runs.
- **Hidden labels.** A package behind another package on a cart is not scanned and falls back to recognition by look.

## Documentation

| Doc | Read it to… |
|---|---|
| [Getting started](docs/getting-started.md) | Install, run, and fix common problems |
| [Architecture](docs/architecture.md) | Components, the checkout state machine, design decisions |
| [Unity → web pipeline](docs/pipeline.md) | Follow one frame from a camera to the cart on screen |
| [Vision and tracking](docs/vision.md) | Detection, classification, tracking, fusion and the ledger |
| [Training](docs/training.md) | Export data, train, record and score |
| [Benchmark](docs/benchmark.md) | Per-scenario held-out scores (generated) |
| [API reference](docs/api.md) | Endpoints, payloads and the snapshot shape |
| [Extending](docs/extending.md) | Add a product, scenario, camera or model |
| [Project log](docs/pro-express-v2.md) | Earlier rounds, what changed and why |
| [HANDOFF.md](HANDOFF.md) | Working notes for whoever picks this up next |

## Project layout

```text
api/          FastAPI app (routes/, runtime.py, ws.py): frame ingress, replay, cart and session persistence, checkout
vision/       Inference engine, camera calibration, barcode reading, the physical-object ledger
web/          React + TypeScript dashboard: project site, recorded tour, live lab
unity/        The Unity 6.6 project; code, scene and generated label art in unity/Assets/ProPass
training/     Model training and the benchmark scorer
models/       Hash manifests and benchmark reports (weights are release assets)
scripts/      round.sh (the whole pipeline), start.sh, weight and recording downloads, tour builder
tests/        156 tests: ledger, fusion, calibration, barcodes, API, catalog consistency
docs/         Documentation
catalog.json  The 15 invented products: prices, barcodes, label art recipe
```

## Checks

```bash
.venv/bin/python -m pytest tests -q        # ledger, fusion, calibration, barcodes, API, catalog
(cd web && npm run build)                  # type-check and bundle the dashboard
```

## Licensing notes

Ultralytics (the YOLO detector) is AGPL-3.0 or commercially licensed, and nothing in this repository grants a license to its code or weights. Torchvision's pretrained EfficientNet weights carry their own terms. The character models in the videos come from the "Creative Characters FREE" pack by ithappy on the Unity Asset Store and are not redistributed here. All product names, brands and package art were invented for this project and generated by `scripts/prepare_products.py`; the names have not been checked against registered trademarks.
