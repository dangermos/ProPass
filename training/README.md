# ProPass learned vision

The Unity simulator generates RGB images and visible instance-mask annotations.
Those annotations are used **offline** to train and evaluate models. The running
checkout engine accepts RGB frames plus frame/run timing, and has no simulator
object identity, SKU, transform or segmentation input.

## Dataset

The initial export contains 450 training, 90 validation and 60 test scene images.
Each split uses a separate random-seed range. Camera pose, package orientation,
lighting, customer placement and occlusion vary across scenes; nearby frames of
the same checkout recording are not split across train and test.

```text
training/data/
  detection/
    images/{train,val,test}/scene_00001.jpg
    labels/{train,val,test}/scene_00001.txt
    dataset.yaml
  crops/{train,val,test}/{PEX-001,...,PEX-005,ZZZ-UNKNOWN}/
  manifests/{train,val,test}/scene_00001.json
```

Detection labels use YOLO normalized boxes with one class, `merchandise`, even
for the unenrolled gray package. The five catalog classes are separate from
physical instances: two identical packages have one SKU and two ground-truth
physical identities. The assets are fictional, visually distinct package designs
created for this portfolio demo.

## Training

From the project root:

```sh
.venv/bin/python -m training.train detector --epochs 35 --batch 8 --device 0
.venv/bin/python -m training.extract_outliers
.venv/bin/python -m training.train classifier --epochs 12 --head-epochs 4 --batch 24 --device cuda:0
```

The detector starts from the official COCO-pretrained `yolo26n.pt`. It uses 640px
images, AdamW, mixed precision, mild geometry/lighting augmentation, no mirrored
packaging text, and validation-selected weights. Its operating confidence is
0.20; the reported mAP is separately computed across detection thresholds.

The SKU classifier starts from torchvision's ImageNet-pretrained EfficientNet-B0.
Whole crops are aspect-preserving padded to 224px. Four epochs train the head,
then eight epochs fine-tune the last feature stages while BatchNorm statistics
remain frozen. A small training-only outlier-exposure class represents unenrolled
gray packages (26 train crops, 5 validation crops, 3 test crops). It is a rejection
output, never a purchasable SKU. Temperature and class-feature distance thresholds
are calibrated on validation only. Classifier checkpoints include catalog order,
feature prototypes and calibration metadata.

The first closed-set classifier exposed a genuine failure: it falsely accepted
one of three held-out unknown detected crops. Its checkpoint and evaluation are
preserved in `models/baseline/`. The explicit rejection output fixes the observed
gray-package case, but this is **not evidence of general open-world rejection**.

## Measured static results

See `models/manifest.json` and `models/evaluation-static-test.json` for the complete
records and hashes.

| Measurement | Result |
|---|---:|
| Detector holdout | 60 scenes, 143 merchandise instances |
| Detection mAP50 | 0.995 |
| Detection mAP50–95 | 0.8681 |
| Detections matched at IoU ≥ 0.5, confidence ≥ 0.20 | 143 / 143 |
| SKU top-1 on actual detected known-product crops | 139 / 140 |
| Accepted known-product predictions correct | 135 / 135 |
| Known-product abstentions | 5 / 140 |
| Gray unenrolled detected-crop rejection | 3 / 3 |
| Empty scenes with false merchandise detections | 0 / 2 |

Native clean-crop classification is 142 / 142 including the three reject-class
crops. The detector-crop result is the more relevant recognition measure; it
includes a heavily occluded known product omitted from the clean-crop export.

Initial local training took 71.5 seconds for the detector and approximately 25
seconds per classifier experiment on the RTX 4070 Super. These are measurements
for this small synthetic dataset, not general training-time estimates. GPU static
detector + classifier processing measured about 9.8ms median and 12.8ms p95 after
warmup; browser transport and scene rendering are not included in those numbers.

## Temporal pipeline

`vision.engine.VisionEngine` explicitly uses ByteTrack, then reconciles short lost
track fragments into canonical physical-object records. Matching gates motion,
appearance, area and SKU compatibility, is one-to-one, and defers ambiguous
identical-product matches to review. A track ID is not a purchase ID.

SKU decisions average several spaced usable views. Forward observed zone motion
creates membership only when the SKU is accepted. Reverse observed motion removes
it. Lost visibility alone never removes membership. Unfinished merchandise blocks
cart preparation; lost precommit merchandise eventually requires explicit review.
Repeated source frames do not repeat events.

```sh
.venv/bin/python -m pytest tests/test_vision_ledger.py tests/test_vision_engine.py -q
.venv/bin/python -m training.evaluate
.venv/bin/python -m training.replay --root artifacts/replays --output models/evaluation-temporal.json
```

The replay evaluator sends only JPEGs and source timing into inference. It reads
the separate JSON ground truth afterward to construct an expected cart. Results
include exact cart, review behavior, canonical counts, event idempotency and GPU
latency. Test observations injected into ledger unit tests verify event logic;
they are never reported as model-accuracy measurements.

## Limits

These results describe visually distinct fictional packaging in a controlled
single-customer Unity lane. They do not establish exact real retail SKU accuracy,
robustness to arbitrary unknown objects, hidden stack quantities, multi-customer
ownership, or transfer to a real camera. Next experiments should hold out larger
pose/lighting families and then evaluate synthetic-only and mixed synthetic/real
training on untouched phone footage.

Ultralytics code and model usage follow its AGPL/enterprise terms; torchvision's
source and pretrained-weight provenance should remain attributed in any released
repository. No external dataset or scraped real surveillance footage is used by
this MVP.
