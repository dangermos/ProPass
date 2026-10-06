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
from collections import deque
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
        self.detector_iou = float(config.get("detector_iou", 0.65))
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
        on_device = lambda t: t.to(self.device) if t is not None else None
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
        self._next_fused = 1
        self.processed_frames = 0

    def status(self):
        return {"ready": self.ready,
                "mode": "learned_rgb" if self.ready else "awaiting_checkpoints",
                "device": self.device, "detector": "YOLO26n merchandise / person / cart",
                "classifier": "EfficientNet-B0 5 SKU + enrolled-product rejection",
                "prototype_rejection": self.prototype_rejection,
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
                                               iou=self.detector_iou, classes=[0], device=self.device, verbose=False)
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
        """Merge boxes that different cameras see at the same spot on the lane map."""
        seen = [o for o in seen if o.world is not None]
        # A single mistaken crop must not split an established physical unit.
        # Acquiring a pair still rejects immediate strong SKU disagreement;
        # breaking an existing pair requires sustained camera-local evidence.
        if not hasattr(self, "_camera_evidence"):
            self._camera_evidence = {}
        policy = getattr(getattr(self, "ledger", None), "config", LedgerConfig())
        stable_skus = {}
        for obs in seen:
            key = (obs.camera, obs.track_id)
            evidence = self._camera_evidence.setdefault(key, deque(maxlen=policy.evidence_window))
            evidence.append(tuple(1.0/len(self.skus) for _ in self.skus)
                            if obs.unknown or obs.quality < policy.minimum_quality else obs.probabilities)
            if len(evidence) >= policy.minimum_views:
                average = [sum(p[k] for p in evidence)/len(evidence) for k in range(len(self.skus))]
                order = sorted(range(len(average)), key=average.__getitem__, reverse=True)
                if (average[order[0]] >= policy.sku_threshold and
                        average[order[0]] - average[order[1]] >= policy.sku_margin):
                    stable_skus[key] = order[0]
        present = {}
        for obs in seen:
            prior = self._fused.get((obs.camera, obs.track_id))
            if prior is not None:
                present.setdefault(prior, set()).add(obs.camera)
        pairs = []
        for i, a in enumerate(seen):
            for j in range(i + 1, len(seen)):
                b = seen[j]
                if a.camera == b.camera:
                    continue
                distance = hypot(a.world[0]-b.world[0], a.world[1]-b.world[1])
                if distance > self.fuse_radius:
                    continue
                previous_a = self._fused.get((a.camera, a.track_id))
                previous_b = self._fused.get((b.camera, b.track_id))
                same_identity = previous_a is not None and previous_a == previous_b
                # A close projection alone cannot join confidently different
                # products. Keeping separate evidence makes the uncertainty
                # visible rather than contaminating a purchased object's SKU.
                raw_conflict = (not a.unknown and not b.unknown and a.probabilities and b.probabilities
                        and max(a.probabilities) >= .85 and max(b.probabilities) >= .85
                        and max(range(len(a.probabilities)), key=a.probabilities.__getitem__)
                        != max(range(len(b.probabilities)), key=b.probabilities.__getitem__))
                stable_a = stable_skus.get((a.camera, a.track_id))
                stable_b = stable_skus.get((b.camera, b.track_id))
                sustained_conflict = stable_a is not None and stable_b is not None and stable_a != stable_b
                if (sustained_conflict if same_identity else raw_conflict):
                    continue
                if (previous_a is not None and previous_b is not None and previous_a != previous_b
                        and (len(present[previous_a]) > 1 or len(present[previous_b]) > 1)):
                    # Their established partner is still observed elsewhere.
                    # Projection disagreement is not evidence that two units
                    # became one, even if this competing pair is closer.
                    continue
                # Keep a geometrically plausible established camera pair ahead
                # of a nearer competing pair when products pass one another.
                pairs.append((0 if same_identity else 1, distance, i, j))
        pairs.sort()
        groups, grouped = [], {}
        for _, distance, i, j in pairs:
            if distance > self.fuse_radius or i in grouped or j in grouped:
                continue          # one-to-one: a camera never contributes two boxes to one object
            grouped[i] = grouped[j] = len(groups)
            groups.append([seen[i], seen[j]])
        groups += [[o] for i, o in enumerate(seen) if i not in grouped]
        original_ids = dict(self._fused)
        identity_groups = {}
        for index, group in enumerate(groups):
            for obs in group:
                previous = original_ids.get((obs.camera, obs.track_id))
                if previous is not None:
                    identity_groups.setdefault(previous, set()).add(index)
        ambiguous_groups = {index for indices in identity_groups.values() if len(indices) > 1
                            for index in indices}
        observations, members = [], []
        used = set()
        for group_index, group in enumerate(groups):
            keys = [(o.camera, o.track_id) for o in group]
            # A fused identity follows whichever camera still sees the object, so a box
            # hidden from one camera keeps its track through the other.
            known = sorted({self._fused[k] for k in keys if k in self._fused and self._fused[k] not in used})
            ledger = getattr(self, "ledger", None)
            canonical_ids = {ledger.track_to_object[track_id] for track_id in known
                             if ledger is not None and track_id in ledger.track_to_object}
            conflicting_tracks = tuple(known) if len(canonical_ids) > 1 else ()
            fused_id = known[0] if known else self._next_fused
            if not known:
                self._next_fused += 1
            used.add(fused_id)
            # Joining previously independent camera tracks must redirect their
            # aliases too, so losing either camera never resurrects the old ID.
            merged = set(known)
            if len(merged) > 1:
                for key, previous in tuple(self._fused.items()):
                    if previous in merged:
                        self._fused[key] = fused_id
            for key in keys:
                self._fused[key] = fused_id
            clear = [o for o in group if not o.unknown] or group
            strong = []
            for obs in clear:
                ranking = sorted(obs.probabilities, reverse=True)
                if (not obs.unknown and obs.quality >= policy.minimum_quality and
                        ranking and ranking[0] >= policy.sku_threshold and
                        (len(ranking) == 1 or ranking[0]-ranking[1] >= policy.sku_margin)):
                    strong.append(obs)
            # A weak second view must not dilute a confident camera below the
            # temporal SKU threshold or move its position to a partial crop.
            clear = strong or clear
            weight = sum(o.quality for o in clear) or 1.0
            probabilities = tuple(sum(o.probabilities[k]*o.quality for o in clear)/weight
                                  for k in range(len(self.skus)))
            # A rejected partial crop can have a shifted box center. When a
            # clear view exists, use it for location as well as SKU evidence.
            total = sum(o.quality for o in clear) or 1.0
            x = sum(o.world[0]*o.quality for o in clear)/total
            z = sum(o.world[1]*o.quality for o in clear)/total
            u, v = geometry.to_map(x, z)
            cx, cy, half = u*geometry.MAP_SIZE, v*geometry.MAP_SIZE, 20.0
            best = max(clear, key=lambda o: o.quality)
            observations.append(Observation(
                fused_id, (cx-half, cy-half, cx+half, cy+half), max(o.confidence for o in group),
                probabilities, best.embedding, max(o.quality for o in clear), all(o.unknown for o in group),
                full_view=any(o.full_view for o in group), at_entry_edge=z <= geometry.ENTRY_EDGE_Z,
                sized=False, ambiguous_identity=group_index in ambiguous_groups or bool(conflicting_tracks),
                conflicting_tracks=conflicting_tracks))
            members.append(group)
        return observations, members
