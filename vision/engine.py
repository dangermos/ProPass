"""Learned detector/classifier + tracker + independent physical-item ledger.

Only RGB pixels and source-frame metadata enter process_frames. No simulation
object names, transforms, segmentation masks or ground-truth SKUs are accepted.

With vision/cameras.json present the engine runs in *world mode*: every camera's
detections are placed on the lane map through its calibration, boxes that two
cameras see at the same spot are fused into one observation, and the ledger's
zones are physical lines. Without it, the single lane camera's image is used.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, fields
from math import hypot
from pathlib import Path

from . import geometry
from .ledger import LedgerConfig, Observation, PhysicalLedger


@dataclass
class CameraObservation:
    """One tracked merchandise box in one camera's image."""
    camera: str
    track_id: int
    bbox: tuple[float, float, float, float]
    confidence: float
    probabilities: tuple[float, ...]
    embedding: tuple[float, ...]
    quality: float
    unknown: bool
    full_view: bool
    world: tuple[float, float] | None = None


def box_iou(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    return float(w * h / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - w * h))


def merchandise_only(xyxy, classes, confidences, same_region_iou=0.5):
    """Indices of merchandise boxes, minus any whose region a more confident box already claims.

    The detector has no suppression step of its own, so it can report one region twice:
    as a person and a product, or as two nearly identical products.
    """
    keep = []
    for i, cls in enumerate(classes):
        if cls != 0:
            continue
        rivals = (j for j in range(len(classes)) if j != i and confidences[j] > confidences[i])
        if not any(box_iou(xyxy[i], xyxy[j]) >= same_region_iou for j in rivals):
            keep.append(i)
    return keep


class VisionEngine:
    def __init__(self, catalog_path, models_dir, config_path=None, cameras=None, world_mode=None):
        self.catalog_path = Path(catalog_path)
        self.models_dir = Path(models_dir)
        os.environ.setdefault("YOLO_CONFIG_DIR",str(self.models_dir/"ultralytics-settings"))
        catalog = json.loads(self.catalog_path.read_text())
        self.products = sorted(catalog["products"], key=lambda p: p["class_index"])
        self.skus = [p["sku"] for p in self.products]
        config = json.loads(Path(config_path).read_text()) if config_path else {}
        permitted = {f.name for f in fields(LedgerConfig)}
        ledger = {k: v for k, v in config.get("ledger", config).items() if k in permitted}
        # Which cameras to use. "lane" alone with no calibration is image mode.
        self.camera_ids = list(cameras or config.get("cameras", ["lane"]))
        calibration_path = Path(config_path).parent/"cameras.json" if config_path else None
        self.calibration = None
        if world_mode is None:
            world_mode = config.get("world_mode", True)
        if world_mode and calibration_path and calibration_path.exists():
            self.calibration = geometry.Calibration(calibration_path)
            ledger.update(self.calibration.ledger_overrides())
            ledger.update({k: v for k, v in config.get("world_ledger", {}).items() if k in permitted})
        # Restricted products come from the catalog and always go to an associate.
        ledger["restricted_skus"] = tuple(p["sku"] for p in self.products if p.get("restricted"))
        self.fuse_radius = float(config.get("fuse_radius_m", 0.45))
        # Scan cameras are read for barcodes only; they never detect or track.
        self.scan_cameras = [c for c in config.get("scan_cameras", []) if self.calibration and c in self.calibration.cameras]
        self.barcode_to_sku = {str(p["barcode"]): p["sku"] for p in self.products if p.get("barcode")}
        self.ledger = PhysicalLedger(self.skus, LedgerConfig(**ledger))
        self.image_size = int(config.get("image_size", 640))
        self.detector_conf = float(config.get("detector_conf", 0.20))
        self.detector_iou = float(config.get("detector_iou", 0.65))
        self.same_region_iou = float(config.get("same_region_iou", 0.5))
        self.prototype_rejection = bool(config.get("prototype_rejection", True))
        self.device_request = config.get("device", os.environ.get("PROPASS_DEVICE", "auto"))
        self.tracker = config.get("tracker", "bytetrack.yaml")
        self.detectors = {}          # one YOLO instance per camera: each keeps its own tracker state
        self.classifier = None
        self.device = "uninitialized"
        self.error = None
        self.last_inference_ms = None
        self.processed_frames = 0
        self._fused: dict[tuple[str, int], int] = {}
        self._camera_evidence = {}
        self._next_fused = 1
        self._load_if_present()

    @property
    def detector(self):
        """The lane camera's detector (kept for the offline evaluators)."""
        return self.detectors.get(self.camera_ids[0])

    def _model_dir(self, camera) -> Path:
        """A camera can have specialist checkpoints in models/<camera>/; otherwise the shared ones."""
        specialist = self.models_dir/camera
        return specialist if (specialist/"detector.pt").exists() and (specialist/"classifier.pt").exists() else self.models_dir

    def _load_classifier(self, path):
        from types import SimpleNamespace

        from torch import nn
        from torchvision.models import efficientnet_b0
        torch = self.torch
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        if checkpoint.get("skus") != self.skus:
            raise ValueError(f"Classifier SKU order does not match catalog: {path}")
        class_labels = checkpoint.get("class_labels", self.skus)
        network = efficientnet_b0(weights=None)
        network.classifier[1] = nn.Linear(network.classifier[1].in_features, len(class_labels))
        network.load_state_dict(checkpoint["state_dict"])
        network.to(self.device).eval()
        def on_device(t):
            return t.to(self.device) if t is not None else None
        return SimpleNamespace(network=network, temperature=float(checkpoint.get("temperature", 1.0)),
                               prototypes=on_device(checkpoint.get("prototypes")),
                               prototype_bank=on_device(checkpoint.get("prototype_bank")),
                               max_prototype_distance=float(checkpoint.get("max_prototype_distance", 0.45)))

    def _load_if_present(self):
        if self.classifier is not None:
            return
        directories = {camera: self._model_dir(camera) for camera in self.camera_ids}
        self.detector_path = directories[self.camera_ids[0]]/"detector.pt"
        missing = [str(d) for d in directories.values() if not (d/"detector.pt").exists() or not (d/"classifier.pt").exists()]
        if missing:
            self.error = "Trained detector.pt and classifier.pt are required; no simulated predictions are substituted."
            return
        try:
            import torch
            from ultralytics import YOLO

            from .transforms import classifier_transform
            self.torch = torch
            self.device = ("cuda:0" if torch.cuda.is_available() else "cpu") if self.device_request == "auto" else str(self.device_request)
            self.transform = classifier_transform()
            loaded = {}
            self.classifiers = {camera: loaded.setdefault(directory, self._load_classifier(directory/"classifier.pt"))
                                if directory not in loaded else loaded[directory]
                                for camera, directory in directories.items()}
            # One YOLO instance per camera: each keeps its own tracker state.
            self.detectors = {camera: YOLO(str(directory/"detector.pt")) for camera, directory in directories.items()}
            self.model_dirs = {camera: str(directory.relative_to(self.models_dir)) or "." for camera, directory in directories.items()}
            # The first camera's classifier under the old attribute names, for the offline evaluators.
            first = self.classifiers[self.camera_ids[0]]
            self.temperature, self.prototypes = first.temperature, first.prototypes
            self.prototype_bank, self.max_prototype_distance = first.prototype_bank, first.max_prototype_distance
            self.classifier = first.network
            self.error = None
        except Exception as exc:
            self.detectors, self.classifier = {}, None
            self.error = f"Model initialization failed: {type(exc).__name__}: {exc}"

    @property
    def ready(self):
        return bool(self.detectors) and self.classifier is not None

    def reset(self, run_id):
        self.ledger.reset(run_id)
        for detector in self.detectors.values():
            if detector.predictor is not None:
                for tracker in getattr(detector.predictor, "trackers", []):
                    tracker.reset()
        self._fused.clear()
        self._camera_evidence.clear()
        self.__dict__.pop("_height_offsets", None)
        self._next_fused = 1
        self.processed_frames = 0

    def status(self):
        return {"ready": self.ready,
                "mode": "learned_rgb" if self.ready else "awaiting_checkpoints",
                "device": self.device, "detector": "YOLO26n merchandise / person / cart",
                "classifier": "EfficientNet-B0 5 SKU + enrolled-product rejection",
                "prototype_rejection": self.prototype_rejection,
                "tracker": f"{Path(self.tracker).stem} + canonical physical ledger",
                "cameras": self.camera_ids, "scan_cameras": self.scan_cameras, "world_mode": self.calibration is not None,
                "error": self.error, "processed_frames": self.processed_frames,
                "last_inference_ms": self.last_inference_ms,
                "ground_truth_runtime": False}

    def geometry(self):
        """Lane map geometry for the dashboard, or None in image mode."""
        if self.calibration is None:
            return None
        described = self.calibration.describe()
        described["cameras"] = [c for c in described["cameras"] if c["id"] in self.camera_ids]
        return described

    def process_frame(self, image_bgr, frame_id, timestamp, run_id, camera_id=None):
        return self.process_frames({camera_id or self.camera_ids[0]: image_bgr}, frame_id, timestamp, run_id)

    def process_frames(self, images: dict, frame_id, timestamp, run_id):
        """Process the images every camera captured for one frame_id."""
        if run_id != self.ledger.run_id:
            raise ValueError("Run ID mismatch: reset(run_id) must precede frame processing")
        scans = {camera: image for camera, image in images.items() if camera in self.scan_cameras}
        images = {camera: image for camera, image in images.items() if camera in self.camera_ids}
        if not images:
            raise ValueError("No image from a configured camera")
        first = next(iter(images.values()))
        frame_size = ((geometry.MAP_SIZE, geometry.MAP_SIZE) if self.calibration
                      else (first.shape[1], first.shape[0]))
        if frame_id <= self.ledger.last_frame_id:
            return self.ledger.update([], frame_id, timestamp, run_id, frame_size)
        self._load_if_present()
        if not self.ready:
            return {"frame_id": frame_id, "timestamp": timestamp, "run_id": run_id,
                    "detections": [], "objects": [], "events": [],
                    "review_required": True, "metrics": {"vision_ready": False,
                    "reason": self.error}}
        start = time.perf_counter()
        seen = [obs for camera, image in images.items() for obs in self._observe(camera, image)]
        barcodes = []
        if self.calibration:
            observations, members = self._fuse(seen)
            barcodes = self._read_barcodes(scans)
            observations = self._attach_barcodes(observations, barcodes)
        else:
            observations = [Observation(o.track_id, o.bbox, o.confidence, o.probabilities,
                                        o.embedding, o.quality, o.unknown) for o in seen]
            members = [[o] for o in seen]
        output = self.ledger.update(observations, frame_id, timestamp, run_id, frame_size)
        # Report each detection as the camera saw it: real image box plus what the ledger decided.
        detections = []
        for decided, boxes in zip(output["detections"], members, strict=False):
            for box in boxes:
                detections.append({**decided, "bbox": list(box.bbox), "camera": box.camera,
                                   "detector_confidence": box.confidence})
        output["detections"] = detections
        if self.calibration:
            for obj in output["objects"]:
                u = (obj["bbox"][0] + obj["bbox"][2]) / 2 / geometry.MAP_SIZE
                v = (obj["bbox"][1] + obj["bbox"][3]) / 2 / geometry.MAP_SIZE
                obj["world"] = [round(c, 3) for c in geometry.from_map(u, v)]
        self.last_inference_ms = (time.perf_counter()-start)*1000
        self.processed_frames += 1
        output["cameras"] = list(images) + list(scans)
        output["barcodes"] = [{k: b[k] for k in ("camera", "text", "sku", "corners", "track_id")} for b in barcodes]
        output["metrics"].update({"inference_ms": self.last_inference_ms, "vision_ready": True,
                                   "device": self.device, "cameras": len(images)})
        return output

    def _read_barcodes(self, scans: dict) -> list[dict]:
        """Decode every Code 128 label visible to the scan cameras and place it on the lane map."""
        import re

        import zxingcpp
        found = []
        for camera, image in scans.items():
            height, width = image.shape[:2]
            for result in zxingcpp.read_barcodes(image[:, :, 1], formats=zxingcpp.BarcodeFormat.Code128):
                # A damaged read can still pass the checksum, so the text must look like a store label.
                match = re.fullmatch(r"SKU=(\d{10})", result.text)
                if not match:
                    continue
                p = result.position
                corners = [[c.x, c.y] for c in (p.top_left, p.top_right, p.bottom_right, p.bottom_left)]
                cx, cy = sum(c[0] for c in corners)/4, sum(c[1] for c in corners)/4
                found.append({"camera": camera, "text": result.text, "corners": corners, "track_id": None,
                              # A code that is not in the catalog is still reported, as an unknown product.
                              "sku": self.barcode_to_sku.get(match.group(1), f"unlisted:{match.group(1)}"),
                              "world": self.calibration.cameras[camera].to_world(cx, cy, width, height)})
        return found

    def _attach_barcodes(self, observations, barcodes):
        """Give each decoded label to the tracked box it sits on: the nearest one on the lane map."""
        from dataclasses import replace
        taken = {}
        for barcode in barcodes:
            best = None
            camera = self.calibration.cameras.get(barcode.get("camera")) if self.calibration else None
            # Lane direction from the label toward the scan camera: +1, -1, or 0 when unknown.
            toward = 0 if camera is None else (1 if camera.position[2] >= barcode["world"][1] else -1)
            for index, obs in enumerate(observations):
                x, z = geometry.from_map(obs.center[0]/geometry.MAP_SIZE, obs.center[1]/geometry.MAP_SIZE)
                dx, dz = abs(x - barcode["world"][0]), abs(z - barcode["world"][1])
                # The label is on the box's front face and below the calibration height, so it
                # projects a little off the box center, mostly along the lane.
                if dx > self.fuse_radius or dz > 2*self.fuse_radius:
                    continue
                # A label on a cart sits below the calibration plane, so it projects toward the
                # camera: its box is the first one behind it, not the neighbor it lands on.
                behind = (barcode["world"][1] - z)*toward >= -0.05
                score = (0 if behind else 1, dx + dz/2)
                if best is None or score < best[0]:
                    best = (score, index)
            if best is not None and best[1] not in taken:
                taken[best[1]] = barcode
                barcode["track_id"] = observations[best[1]].track_id
        return [replace(obs, barcode=taken[i]["sku"]) if i in taken else obs for i, obs in enumerate(observations)]

    def _observe(self, camera, image_bgr) -> list[CameraObservation]:
        """Detect, track and classify the merchandise in one camera's image."""
        from PIL import Image
        torch = self.torch
        # Class 0 is merchandise. People and carts are tracked too, so that a region the
        # detector reads more confidently as a person (a hat showing above a carried box)
        # is not also counted as a product. Only merchandise goes on to the classifier.
        results = self.detectors[camera].track(image_bgr, persist=True, tracker=self.tracker,
                                               imgsz=self.image_size, conf=self.detector_conf,
                                               iou=self.detector_iou, device=self.device, verbose=False)
        boxes = results[0].boxes
        height, width = image_bgr.shape[:2]
        if boxes is None or boxes.id is None:
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        ids = boxes.id.int().cpu().tolist()
        confs = boxes.conf.cpu().tolist()
        classes = boxes.cls.int().cpu().tolist() if getattr(boxes, "cls", None) is not None else [0] * len(ids)
        keep = merchandise_only(xyxy, classes, confs, getattr(self, "same_region_iou", 0.5))
        xyxy, ids, confs = xyxy[keep], [ids[i] for i in keep], [confs[i] for i in keep]
        crops, valid = [], []
        for i, bbox in enumerate(xyxy):
            x1,y1,x2,y2 = bbox
            # Slight padding recovers packaging edges without using masks.
            pad_x, pad_y = (x2-x1)*0.025, (y2-y1)*0.025
            left, top = max(0,int(x1-pad_x)), max(0,int(y1-pad_y))
            right,bottom = min(width,int(x2+pad_x)), min(height,int(y2+pad_y))
            crop = image_bgr[top:bottom,left:right]
            if crop.size == 0 or min(crop.shape[:2]) < 8:
                continue
            crops.append(self.transform(Image.fromarray(crop[:,:,::-1])))
            valid.append(i)
        if not crops:
            return []
        batch = torch.stack(crops).to(self.device)
        model = getattr(self, "classifiers", {}).get(camera)
        if model is None:   # a single shared classifier set directly on the engine
            from types import SimpleNamespace
            model = SimpleNamespace(network=self.classifier, temperature=self.temperature, prototypes=self.prototypes,
                                    prototype_bank=getattr(self, "prototype_bank", None),
                                    max_prototype_distance=self.max_prototype_distance)
        with torch.inference_mode():
            features = model.network.features(batch)
            pooled = model.network.avgpool(features).flatten(1)
            logits = model.network.classifier(pooled)
            normalized = torch.nn.functional.normalize(pooled, dim=1)
            softmax = (logits/model.temperature).softmax(1)
            probabilities = softmax[:,:len(self.skus)].cpu().tolist()
            embeddings = normalized.cpu().tolist()
            unknown = softmax.argmax(1)>=len(self.skus)
            if model.prototypes is not None and self.prototype_rejection:
                from .rejection import prototype_distance
                distances = prototype_distance(normalized, softmax.argmax(1), model.prototypes, model.prototype_bank)
                unknown = unknown | (distances > model.max_prototype_distance)
            unknowns = unknown.cpu().tolist()
        calibrated = self.calibration.cameras.get(camera) if self.calibration else None
        observed = []
        for j, i in enumerate(valid):
            bbox = tuple(float(v) for v in xyxy[i])
            # Tiny/sliver detections do not dominate temporal identity.
            area = max(0,(bbox[2]-bbox[0])*(bbox[3]-bbox[1]))
            full_view = bbox[0] > 3 and bbox[1] > 3 and bbox[2] < width-3 and bbox[3] < height-3
            world = (calibrated.to_world((bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2, width, height)
                     if calibrated else None)
            observed.append(CameraObservation(camera, ids[i], bbox, float(confs[i]), tuple(probabilities[j]),
                                              tuple(embeddings[j]), min(1.0, area/1800.0), unknowns[j], full_view, world))
        return observed

    def _fuse(self, seen: list[CameraObservation]):
        """Combine the cameras into one observation per physical box.

        The first configured camera (the lane camera) is primary: only it can start an
        object. Other cameras assist. A box they see at the same spot is merged into the
        lane camera's observation, and once merged they keep the object alive while the
        lane camera cannot see it. An assisting camera never starts an object on its own,
        so its stray detections cannot block checkout.
        """
        primary_camera = self.camera_ids[0]
        primary = [o for o in seen if o.world is not None and o.camera == primary_camera]
        assist = [o for o in seen if o.world is not None and o.camera != primary_camera]
        offsets = self.__dict__.setdefault("_height_offsets", {})

        def confident_sku(o):
            if o.unknown or not o.probabilities or max(o.probabilities) < 0.85:
                return None
            return max(range(len(o.probabilities)), key=o.probabilities.__getitem__)

        def corrected(o):
            # An item carried above or below the calibration plane lands at a shifted spot in
            # the oblique lane camera. The shift is learned whenever an overhead view agrees.
            dx, dz = offsets.get(self._fused.get((o.camera, o.track_id)), (0.0, 0.0))
            return o.world[0] + dx, o.world[1] + dz

        pairs = []
        for i, a in enumerate(primary):
            ax, az = corrected(a)
            for j, b in enumerate(assist):
                dx, dz = b.world[0] - ax, b.world[1] - az
                # Height error moves the lane camera's estimate along the lane (z) far more
                # than across it, so the gate is longer in z.
                if abs(dx) > self.fuse_radius or abs(dz) > 2 * self.fuse_radius:
                    continue
                sku_a, sku_b = confident_sku(a), confident_sku(b)
                if sku_a is not None and sku_b is not None and sku_a != sku_b:
                    continue        # two confidently different products are not one box
                id_a, id_b = self._fused.get((a.camera, a.track_id)), self._fused.get((b.camera, b.track_id))
                established = id_a is not None and id_a == id_b
                pairs.append((0 if established else 1, hypot(dx, dz / 2), i, j))
        partner, taken = {}, set()
        for _, _, i, j in sorted(pairs):      # one-to-one, established pairs first
            if i not in partner and j not in taken:
                partner[i] = j
                taken.add(j)
        groups = [[a] + ([assist[partner[i]]] if i in partner else []) for i, a in enumerate(primary)]
        # An assisting view alone continues an object it was already merged into.
        groups += [[b] for j, b in enumerate(assist) if j not in taken and (b.camera, b.track_id) in self._fused]

        observations, members, used = [], [], set()
        for group in groups:
            keys = [(o.camera, o.track_id) for o in group]
            known = [self._fused[k] for k in keys if k in self._fused and self._fused[k] not in used]
            if known:
                fused_id = known[0]
            elif group[0].camera != primary_camera:
                continue            # its object is already represented this frame
            else:
                fused_id = self._next_fused
                self._next_fused += 1
            used.add(fused_id)
            for key in keys:
                self._fused[key] = fused_id
            lane_view = next((o for o in group if o.camera == primary_camera), None)
            other_view = next((o for o in group if o.camera != primary_camera), None)
            if other_view is not None:
                x, z = other_view.world       # the overhead view has almost no height error
                if lane_view is not None:
                    old = offsets.get(fused_id, (x - lane_view.world[0], z - lane_view.world[1]))
                    offsets[fused_id] = (0.7*old[0] + 0.3*(x - lane_view.world[0]),
                                         0.7*old[1] + 0.3*(z - lane_view.world[1]))
            else:
                dx, dz = offsets.get(fused_id, (0.0, 0.0))
                x, z = lane_view.world[0] + dx, lane_view.world[1] + dz
            clear = [o for o in group if not o.unknown] or group
            weight = sum(o.quality for o in clear) or 1.0
            probabilities = tuple(sum(o.probabilities[k]*o.quality for o in clear)/weight
                                  for k in range(len(self.skus)))
            u, v = geometry.to_map(x, z)
            cx, cy, half = u*geometry.MAP_SIZE, v*geometry.MAP_SIZE, 20.0
            appearance = lane_view if lane_view is not None and not lane_view.unknown else max(clear, key=lambda o: o.quality)
            observations.append(Observation(
                fused_id, (cx-half, cy-half, cx+half, cy+half), max(o.confidence for o in group),
                probabilities, appearance.embedding, max(o.quality for o in clear), all(o.unknown for o in group),
                full_view=any(o.full_view for o in group), at_entry_edge=z <= geometry.ENTRY_EDGE_Z, sized=False))
            members.append(group)
        return observations, members
