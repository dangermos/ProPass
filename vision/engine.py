"""Learned detector/classifier + ByteTrack + independent physical-item ledger.

Only RGB pixels and source-frame metadata enter process_frame. No simulation
object names, transforms, segmentation masks or ground-truth SKUs are accepted.
"""
from __future__ import annotations
from dataclasses import fields
from pathlib import Path
import json
import os
import time

from .ledger import LedgerConfig, Observation, PhysicalLedger


class VisionEngine:
    def __init__(self, catalog_path, models_dir, config_path=None):
        self.catalog_path = Path(catalog_path)
        self.models_dir = Path(models_dir)
        os.environ.setdefault("YOLO_CONFIG_DIR",str(self.models_dir/"ultralytics-settings"))
        catalog = json.loads(self.catalog_path.read_text())
        self.products = sorted(catalog["products"], key=lambda p: p["class_index"])
        self.skus = [p["sku"] for p in self.products]
        config = json.loads(Path(config_path).read_text()) if config_path else {}
        permitted = {f.name for f in fields(LedgerConfig)}
        self.ledger = PhysicalLedger(self.skus, LedgerConfig(**{
            k: v for k, v in config.get("ledger", config).items() if k in permitted}))
        self.image_size = int(config.get("image_size", 640))
        self.detector_conf = float(config.get("detector_conf", 0.20))
        self.device_request = config.get("device", os.environ.get("PROPASS_DEVICE", "auto"))
        self.tracker = config.get("tracker", "bytetrack.yaml")
        self.detector = None
        self.classifier = None
        self.device = "uninitialized"
        self.error = None
        self.last_inference_ms = None
        self.processed_frames = 0
        self._load_if_present()

    def _load_if_present(self):
        if self.detector is not None:
            return
        detector_path = self.models_dir/"detector.pt"
        classifier_path = self.models_dir/"classifier.pt"
        if not detector_path.exists() or not classifier_path.exists():
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
            self.classifier = network
            self.transform = classifier_transform()
            self.temperature = float(checkpoint.get("temperature", 1.0))
            self.prototypes = checkpoint.get("prototypes")
            if self.prototypes is not None:
                self.prototypes = self.prototypes.to(self.device)
            self.max_prototype_distance = float(checkpoint.get("max_prototype_distance", 0.45))
            self.detector = YOLO(str(detector_path))
            self.error = None
        except Exception as exc:
            self.detector = self.classifier = None
            self.error = f"Model initialization failed: {type(exc).__name__}: {exc}"

    def reset(self, run_id):
        self.ledger.reset(run_id)
        if self.detector is not None and self.detector.predictor is not None:
            for tracker in getattr(self.detector.predictor, "trackers", []):
                tracker.reset()
        self.processed_frames = 0

    def status(self):
        return {"ready": self.detector is not None and self.classifier is not None,
                "mode": "learned_rgb" if self.detector is not None else "awaiting_checkpoints",
                "device": self.device, "detector": "YOLO26n merchandise",
                "classifier": "EfficientNet-B0 5 SKU + enrolled-product rejection",
                "tracker": f"{Path(self.tracker).stem} + canonical physical ledger",
                "error": self.error, "processed_frames": self.processed_frames,
                "last_inference_ms": self.last_inference_ms,
                "ground_truth_runtime": False}

    def process_frame(self, image_bgr, frame_id, timestamp, run_id):
        if run_id != self.ledger.run_id:
            raise ValueError("Run ID mismatch: reset(run_id) must precede frame processing")
        if frame_id <= self.ledger.last_frame_id:
            return self.ledger.update([], frame_id, timestamp, run_id,
                                      (image_bgr.shape[1], image_bgr.shape[0]))
        self._load_if_present()
        if self.detector is None or self.classifier is None:
            return {"frame_id": frame_id, "timestamp": timestamp, "run_id": run_id,
                    "detections": [], "objects": [], "events": [],
                    "review_required": True, "metrics": {"vision_ready": False,
                    "reason": self.error}}
        start = time.perf_counter()
        from PIL import Image
        import numpy as np
        torch = self.torch
        # Class 0 is merchandise; people and carts are learned so they stop being
        # mistaken for merchandise, but only merchandise enters the tracker.
        results = self.detector.track(image_bgr, persist=True, tracker=self.tracker,
                                      imgsz=self.image_size, conf=self.detector_conf,
                                      iou=0.65, classes=[0], device=self.device, verbose=False)
        boxes = results[0].boxes
        observations = []
        height, width = image_bgr.shape[:2]
        if boxes is not None and boxes.id is not None:
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
            if crops:
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
                for j,i in enumerate(valid):
                    bbox = tuple(float(v) for v in xyxy[i])
                    # Tiny/sliver detections do not dominate temporal identity.
                    area = max(0,(bbox[2]-bbox[0])*(bbox[3]-bbox[1]))
                    quality = min(1.0, area/1800.0)
                    observations.append(Observation(ids[i], bbox, float(confs[i]),
                                        tuple(probabilities[j]), tuple(embeddings[j]), quality, unknowns[j]))
        output = self.ledger.update(observations, frame_id, timestamp, run_id, (width,height))
        self.last_inference_ms = (time.perf_counter()-start)*1000
        self.processed_frames += 1
        output["metrics"].update({"inference_ms": self.last_inference_ms,
                                   "vision_ready": True, "device": self.device})
        return output
