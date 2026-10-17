"""Distance-gate ablation keeps the reject head and temporal SKU policy intact.

Fake detector boxes and controlled CPU tensors exercise the real crop/inference
adapter. No checkpoints, GPU, simulator labels or benchmark clips are loaded.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from vision.engine import VisionEngine
from vision.ledger import LedgerConfig, Observation, PhysicalLedger

SKUS = [f"PEX-00{index + 1}" for index in range(5)]
ROOT = Path(__file__).resolve().parents[1]
IMAGE = np.zeros((64, 96, 3), dtype=np.uint8)


class FakeDetector:
    def track(self, image, **kwargs):
        boxes = SimpleNamespace(
            xyxy=torch.tensor([[10., 10., 40., 40.]]),
            id=torch.tensor([7]), conf=torch.tensor([.95]),
        )
        return [SimpleNamespace(boxes=boxes)]


class FakeClassifier:
    """One feature vector, with independent controlled six-output logits."""
    def __init__(self, logits):
        self.logits = torch.tensor(logits, dtype=torch.float32)

    def features(self, batch):
        return torch.tensor([0., 1.]).reshape(1, 2, 1, 1).expand(len(batch), -1, -1, -1)

    def avgpool(self, features):
        return features

    def classifier(self, pooled):
        return self.logits.reshape(1, 6).expand(len(pooled), -1)


def fake_engine(enabled, logits):
    # Bypass model deserialization, but execute the production _observe method.
    engine = VisionEngine.__new__(VisionEngine)
    engine.skus = SKUS
    engine.torch = torch
    engine.device = "cpu"
    engine.detectors = {"lane": FakeDetector()}
    engine.classifier = FakeClassifier(logits)
    engine.transform = lambda image: torch.zeros(3, 16, 16)
    engine.temperature = 1.
    engine.image_size = 640
    engine.detector_conf = .2
    engine.detector_iou = .65
    engine.tracker = "botsort.yaml"
    engine.calibration = None
    engine.prototype_rejection = enabled
    # Every known class is a distance-one outlier. The explicit reject class
    # matches the feature exactly, proving rejection is also independent of distance.
    engine.prototypes = torch.tensor([[1., 0.]] * 5 + [[0., 1.]])
    engine.prototype_bank = None
    engine.max_prototype_distance = .2
    return engine


@pytest.mark.parametrize("enabled,expected_unknown", [(True, True), (False, False)])
def test_high_confidence_known_outlier_is_rejected_only_when_distance_gate_enabled(enabled, expected_unknown):
    logits = [9., 0., 0., 0., 0., 0.]
    result = fake_engine(enabled, logits)._observe("lane", IMAGE)
    assert len(result) == 1
    observation = result[0]
    assert observation.unknown is expected_unknown
    assert observation.probabilities[0] > .99
    assert len(observation.probabilities) == len(SKUS)
    assert observation.probabilities == pytest.approx(torch.tensor(logits).softmax(0)[:5].tolist())
    assert observation.embedding == (0., 1.)
    assert observation.camera == "lane" and observation.track_id == 7


@pytest.mark.parametrize("enabled", [True, False])
def test_explicit_unknown_head_rejects_in_both_modes_even_when_prototype_matches(enabled):
    logits = [0., 0., 0., 0., 0., 9.]
    observation = fake_engine(enabled, logits)._observe("lane", IMAGE)[0]
    assert observation.unknown is True
    assert len(observation.probabilities) == len(SKUS)
    assert max(observation.probabilities) < .001
    assert observation.probabilities == pytest.approx(torch.tensor(logits).softmax(0)[:5].tolist())
    # The known vector stays unrenormalized. Reject-head mass cannot become
    # fabricated known-SKU confidence by dropping the sixth output.
    assert sum(observation.probabilities) < .001


def test_disabled_gate_never_calls_prototype_distance(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Prototype distance ran with rejection disabled")

    monkeypatch.setattr("vision.rejection.prototype_distance", forbidden)
    observation = fake_engine(False, [9., 0., 0., 0., 0., 0.])._observe("lane", IMAGE)[0]
    assert observation.unknown is False


@pytest.mark.parametrize("configured,expected", [(None, True), (True, True), (False, False)])
def test_config_flag_defaults_enabled_and_round_trips_in_status(tmp_path, monkeypatch, configured, expected):
    config = {"world_mode": False, "cameras": ["lane"]}
    if configured is not None:
        config["prototype_rejection"] = configured
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    monkeypatch.setattr(VisionEngine, "_load_if_present", lambda self: None)
    monkeypatch.setenv("YOLO_CONFIG_DIR", str(tmp_path / "settings"))
    engine = VisionEngine(ROOT / "catalog.json", tmp_path / "models", path)
    assert engine.prototype_rejection is expected
    assert engine.status()["prototype_rejection"] is expected
    assert engine.ledger.config.sku_threshold == .85
    assert engine.ledger.config.sku_margin == .20


@pytest.mark.parametrize("logits,policy", [
    ([1., 0., 0., 0., 0., 0.], "below confidence threshold"),
    ([4., 4., 0., 0., 0., 0.], "ambiguous SKU margin"),
])
def test_distance_ablation_does_not_make_weak_or_ambiguous_logits_purchase_evidence(logits, policy):
    camera_observation = fake_engine(False, logits)._observe("lane", IMAGE)[0]
    assert camera_observation.unknown is False
    ledger = PhysicalLedger(SKUS, LedgerConfig(dwell_seconds=.08, evidence_interval=.08))
    ledger.reset("ablation-test")
    events = []
    for number, y in enumerate([800., 800., 600., 500., 300., 300., 300., 300.]):
        observation = Observation(7, (265., y - 25., 335., y + 25.),
                                  camera_observation.confidence,
                                  camera_observation.probabilities,
                                  camera_observation.embedding, 1., camera_observation.unknown)
        state = ledger.update([observation], number, number * .2, "ablation-test", (1000, 1000))
        events.extend(state["events"])
    assert ledger.config.sku_threshold == .85 and ledger.config.sku_margin == .20
    assert state["objects"][0]["sku"] is None, policy
    assert state["metrics"]["cart_units"] == 0
    assert state["review_required"] is True
    assert not any(event["type"] == "ITEM_ADDED" for event in events)
