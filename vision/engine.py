"""Learned detector/classifier + tracker + independent physical-item ledger.

Only RGB pixels and source-frame metadata enter process_frames. No simulation
object names, transforms, segmentation masks or ground-truth SKUs are accepted.

With vision/cameras.json present the engine runs in *world mode*: every camera's
detections are placed on the lane map through its calibration, boxes that two
cameras see at the same spot are fused into one observation, and the ledger's
zones are physical lines. Without it, the single lane camera's image is used.
"""
from __future__ import annotations
from dataclasses import dataclass, fields
from math import hypot
from pathlib import Path
import json
import os
import time

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
        self.fuse_radius = float(config.get("fuse_radius_m", 0.45))
        self.ledger = PhysicalLedger(self.skus, LedgerConfig(**ledger))
        self.image_size = int(config.get("image_size", 640))
        self.detector_conf = float(config.get("detector_conf", 0.20))
        self.device_request = config.get("device", os.environ.get("PROPASS_DEVICE", "auto"))
        self.tracker = config.get("tracker", "bytetrack.yaml")
        self.detectors = {}          # one YOLO instance per camera: each keeps its own tracker state
        self.classifier = None
        self.device = "uninitialized"
        self.error = None
        self.last_inference_ms = None
        self.processed_frames = 0
        self._fused: dict[tuple[str, int], int] = {}
        self._next_fused = 1
        self._load_if_present()

    @property
    def detector(self):
        """The lane camera's detector (kept for the offline evaluators)."""
        return self.detectors.get(self.camera_ids[0])

    def _load_if_present(self):
        if self.classifier is not None:
            return
        self.detector_path = self.models_dir/"detector.pt"
        classifier_path = self.models_dir/"classifier.pt"
        if not self.detector_path.exists() or not classifier_path.exists():
            self.error = "Trained detector.pt and classifier.pt are required; no simulated predictions are substituted."
            return
        try:
            import torch
            from torch import nn
            from torchvision.models import efficientnet_b0
            from ultralytics import YOLO
            from .transforms import classifier_transform
            self.torch = torch
            self.device = ("cuda:0" if torch.cuda.is_available() else "cpu") if self.device_request == "auto" else str(self.device_request)
            checkpoint = torch.load(classifier_path, map_location="cpu", weights_only=True)
            if checkpoint.get("skus") != self.skus:
                raise ValueError("Classifier SKU order does not match catalog")
            class_labels = checkpoint.get("class_labels", self.skus)
            network = efficientnet_b0(weights=None)
            network.classifier[1] = nn.Linear(network.classifier[1].in_features, len(class_labels))
            network.load_state_dict(checkpoint["state_dict"])
            network.to(self.device).eval()
            self.transform = classifier_transform()
            self.temperature = float(checkpoint.get("temperature", 1.0))
            self.prototypes = checkpoint.get("prototypes")
            if self.prototypes is not None:
                self.prototypes = self.prototypes.to(self.device)
            self.max_prototype_distance = float(checkpoint.get("max_prototype_distance", 0.45))
            self.detectors = {camera: YOLO(str(self.detector_path)) for camera in self.camera_ids}
            self.classifier = network
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
        self._next_fused = 1
        self.processed_frames = 0

    def status(self):
        return {"ready": self.ready,
                "mode": "learned_rgb" if self.ready else "awaiting_checkpoints",
                "device": self.device, "detector": "YOLO26n merchandise / person / cart",
                "classifier": "EfficientNet-B0 5 SKU + enrolled-product rejection",
                "tracker": f"{Path(self.tracker).stem} + canonical physical ledger",
                "cameras": self.camera_ids, "world_mode": self.calibration is not None,
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
        if self.calibration:
            observations, members = self._fuse(seen)
        else:
            observations = [Observation(o.track_id, o.bbox, o.confidence, o.probabilities,
                                        o.embedding, o.quality, o.unknown) for o in seen]
            members = [[o] for o in seen]
        output = self.ledger.update(observations, frame_id, timestamp, run_id, frame_size)
        # Report each detection as the camera saw it: real image box plus what the ledger decided.
        detections = []
        for decided, boxes in zip(output["detections"], members):
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
        output["cameras"] = list(images)
        output["metrics"].update({"inference_ms": self.last_inference_ms, "vision_ready": True,
                                   "device": self.device, "cameras": len(images)})
        return output

    def _observe(self, camera, image_bgr) -> list[CameraObservation]:
        """Detect, track and classify the merchandise in one camera's image."""
        from PIL import Image
        torch = self.torch
        # Class 0 is merchandise; people and carts are learned so they stop being
        # mistaken for merchandise, but only merchandise enters the tracker.
        results = self.detectors[camera].track(image_bgr, persist=True, tracker=self.tracker,
                                               imgsz=self.image_size, conf=self.detector_conf,
                                               iou=0.65, classes=[0], device=self.device, verbose=False)
        boxes = results[0].boxes
        height, width = image_bgr.shape[:2]
        if boxes is None or boxes.id is None:
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        ids = boxes.id.int().cpu().tolist()
        confs = boxes.conf.cpu().tolist()
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
        with torch.inference_mode():
            features = self.classifier.features(batch)
            pooled = self.classifier.avgpool(features).flatten(1)
            logits = self.classifier.classifier(pooled)
            normalized = torch.nn.functional.normalize(pooled, dim=1)
            softmax = (logits/self.temperature).softmax(1)
            probabilities = softmax[:,:len(self.skus)].cpu().tolist()
            embeddings = normalized.cpu().tolist()
            unknown = softmax.argmax(1)>=len(self.skus)
            if self.prototypes is not None:
                distances = 1-(normalized*self.prototypes[softmax.argmax(1)]).sum(1)
                unknown = unknown | (distances > self.max_prototype_distance)
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
        """Merge boxes that different cameras see at the same spot on the lane map."""
        seen = [o for o in seen if o.world is not None]
        pairs = sorted((hypot(a.world[0]-b.world[0], a.world[1]-b.world[1]), i, j)
                       for i, a in enumerate(seen) for j, b in enumerate(seen)
                       if i < j and a.camera != b.camera)
        groups, grouped = [], {}
        for distance, i, j in pairs:
            if distance > self.fuse_radius or i in grouped or j in grouped:
                continue          # one-to-one: a camera never contributes two boxes to one object
            grouped[i] = grouped[j] = len(groups)
            groups.append([seen[i], seen[j]])
        groups += [[o] for i, o in enumerate(seen) if i not in grouped]
        observations, members = [], []
        used = set()
        for group in groups:
            keys = [(o.camera, o.track_id) for o in group]
            # A fused identity follows whichever camera still sees the object, so a box
            # hidden from one camera keeps its track through the other.
            known = sorted(self._fused[k] for k in keys if k in self._fused and self._fused[k] not in used)
            fused_id = known[0] if known else self._next_fused
            if not known:
                self._next_fused += 1
            used.add(fused_id)
            for key in keys:
                self._fused.setdefault(key, fused_id)
            clear = [o for o in group if not o.unknown] or group
            weight = sum(o.quality for o in clear) or 1.0
            probabilities = tuple(sum(o.probabilities[k]*o.quality for o in clear)/weight
                                  for k in range(len(self.skus)))
            total = sum(o.quality for o in group) or 1.0
            x = sum(o.world[0]*o.quality for o in group)/total
            z = sum(o.world[1]*o.quality for o in group)/total
            u, v = geometry.to_map(x, z)
            cx, cy, half = u*geometry.MAP_SIZE, v*geometry.MAP_SIZE, 20.0
            best = max(clear, key=lambda o: o.quality)
            observations.append(Observation(
                fused_id, (cx-half, cy-half, cx+half, cy+half), max(o.confidence for o in group),
                probabilities, best.embedding, max(o.quality for o in group), all(o.unknown for o in group),
                full_view=any(o.full_view for o in group), at_entry_edge=z <= geometry.ENTRY_EDGE_Z, sized=False))
            members.append(group)
        return observations, members
