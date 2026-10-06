"""Camera-local temporal SKU evidence controls established-pair disagreement.

Deterministic observations verify identity and confidence policy. No model
checkpoints, GPU or development/held-out footage is loaded by these tests.
"""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from vision import geometry
from vision.engine import CameraObservation, VisionEngine
from vision.ledger import LedgerConfig, PhysicalLedger


SKUS = [f"PEX-00{index + 1}" for index in range(5)]
RUN = "temporal-fusion"
IMAGE = SimpleNamespace(shape=(540, 960))
PATH = [-3.4, -3.4, -2.6, -1., 1., 2.3, 2.3, 2.3]


def engine():
    result = VisionEngine.__new__(VisionEngine)
    result.skus = SKUS
    result.camera_ids = ["lane", "overhead"]
    result.calibration = object()
    result.fuse_radius = .45
    result._fused = {}
    result._camera_evidence = {}
    result._next_fused = 1
    result.detectors = {camera: SimpleNamespace(predictor=None) for camera in result.camera_ids}
    result.classifier = object()
    result.device = "cpu"
    result.processed_frames = 0
    left, _ = geometry.to_map(-1.7, 0)
    right, _ = geometry.to_map(1.7, 0)
    result.ledger = PhysicalLedger(SKUS, LedgerConfig(
        approach_y=geometry.to_map(0, -2)[1], commit_y=geometry.to_map(0, 1.6)[1],
        lane_polygon=((left, 0), (right, 0), (right, 1), (left, 1)),
        hysteresis=.015, dwell_seconds=.08, evidence_interval=.08,
        reattach_distance=.06, reattach_margin=.03,
    ))
    result.ledger.reset(RUN)
    return result


def box(camera, track, x=0., z=2.3, sku=0, confidence=.99, unknown=False):
    probabilities = [(1 - confidence) / 4] * len(SKUS)
    probabilities[sku] = confidence
    embedding = tuple(float(index == sku) for index in range(len(SKUS)))
    return CameraObservation(camera, track, (100, 100, 160, 145), .95,
                             tuple(probabilities), embedding, 1., unknown, True, (x, z))


def frame(inference, number, observations, run_id=RUN):
    inference._observe = lambda camera, image: observations[camera]
    return inference.process_frames({camera: IMAGE for camera in observations},
                                    number, number * .2, run_id)


def pair(z=2.3, wrong=False, unknown=False):
    return {
        "lane": [box("lane", 1, -.48, z), box("lane", 2, .48, z)],
        "overhead": [box("overhead", 10, -.46, z, sku=1 if wrong else 0,
                         confidence=.865 if wrong else .99, unknown=unknown),
                     box("overhead", 20, .46, z)],
    }


def completed_duplicate(inference):
    for number, z in enumerate(PATH):
        state = frame(inference, number, pair(z))
    assert state["metrics"]["cart_units"] == 2
    assert state["review_required"] is False
    return state


def test_one_wrong_crop_does_not_split_established_identical_product_pairs():
    inference = engine()
    before = completed_duplicate(inference)
    identities = dict(inference._fused)
    originals = {obj["object_id"] for obj in before["objects"]}
    state = frame(inference, 8, pair(wrong=True))
    assert inference._fused == identities
    assert len(state["objects"]) == 2
    assert {obj["object_id"] for obj in state["objects"]} == originals
    assert state["metrics"]["cart_units"] == 2
    assert state["review_required"] is False
    assert all(obj["sku"] == SKUS[0] for obj in state["objects"])
    assert not any(event["type"] in {"REVIEW_REQUIRED", "ITEM_ADDED", "ITEM_REMOVED"}
                   for event in state["events"])


def test_sustained_different_camera_sku_eventually_splits_and_requires_review():
    inference = engine()
    before = completed_duplicate(inference)
    originals = {obj["object_id"] for obj in before["objects"]}
    events = []
    for number in range(8, 16):
        state = frame(inference, number, pair(wrong=True))
        events.extend(state["events"])
    assert inference._fused[("lane", 1)] != inference._fused[("overhead", 10)]
    assert state["review_required"] is True
    assert any(event["type"] == "REVIEW_REQUIRED" for event in events)
    assert all(obj["membership"] for obj in state["objects"] if obj["object_id"] in originals)
    assert state["metrics"]["cart_units"] == 2
    assert not any(event["type"] == "ITEM_REMOVED" for event in events)


def test_unknown_camera_votes_are_uniform_and_cannot_invent_sustained_sku_conflict():
    inference = engine()
    completed_duplicate(inference)
    identities = dict(inference._fused)
    for number in range(8, 16):
        # A rejected crop can still have a misleading high raw known-class logit.
        state = frame(inference, number, pair(wrong=True, unknown=True))
    assert inference._fused == identities
    assert all(vote == (.2,) * 5 for vote in inference._camera_evidence[("overhead", 10)])
    assert state["metrics"]["cart_units"] == 2
    assert state["review_required"] is False
    assert all(obj["sku"] == SKUS[0] for obj in state["objects"])


def test_reset_clears_camera_votes_aliases_and_physical_cart_history():
    inference = engine()
    completed_duplicate(inference)
    for number in range(8, 16):
        frame(inference, number, pair(wrong=True))
    assert inference._camera_evidence[("overhead", 10)][-1][1] == pytest.approx(.865)
    fresh_run = "fresh-temporal-run"
    inference.reset(fresh_run)
    assert inference._camera_evidence == {}
    assert inference._fused == {}
    assert inference.ledger.objects == {}
    for number in range(3):
        state = frame(inference, number, pair(-3.4), fresh_run)
    assert inference._fused[("lane", 1)] == inference._fused[("overhead", 10)]
    assert all(vote[0] == pytest.approx(.99) for vote in inference._camera_evidence[("overhead", 10)])
    assert len(inference._camera_evidence[("overhead", 10)]) == 3
    assert state["metrics"]["cart_units"] == 0
    assert not any(obj["review_reason"] for obj in state["objects"])


def test_strong_view_preserves_sku_confidence_and_position_when_other_view_is_weak():
    inference = engine()
    strong = box("lane", 1, x=0., z=1., confidence=.99)
    weak = box("overhead", 10, x=.25, z=1.2, confidence=.55)
    observations, members = inference._fuse([strong, weak])
    assert len(observations) == 1 and len(members[0]) == 2
    observation = observations[0]
    assert observation.probabilities == pytest.approx(strong.probabilities)
    assert max(observation.probabilities) == pytest.approx(.99)
    assert geometry.from_map(observation.center[0] / geometry.MAP_SIZE,
                             observation.center[1] / geometry.MAP_SIZE) == pytest.approx((0., 1.))


def test_two_weak_views_never_create_strong_confidence_or_a_purchase():
    inference = engine()
    observations, _ = inference._fuse([
        box("lane", 1, confidence=.55), box("overhead", 10, x=.02, confidence=.55),
    ])
    assert len(observations) == 1
    assert max(observations[0].probabilities) == pytest.approx(.55)
    for number, z in enumerate(PATH):
        state = frame(inference, number, {
            "lane": [box("lane", 1, z=z, confidence=.55)],
            "overhead": [box("overhead", 10, x=.02, z=z, confidence=.55)],
        })
    assert state["metrics"]["cart_units"] == 0
    assert state["review_required"] is True
    assert all(obj["sku"] is None for obj in state["objects"])


def test_tiny_high_confidence_crop_does_not_override_large_weak_view_or_create_purchase():
    inference = engine()
    tiny = replace(box("lane", 1, confidence=.99), quality=.1)
    large_weak = box("overhead", 10, x=.02, confidence=.55)
    observations, _ = inference._fuse([tiny, large_weak])
    assert len(observations) == 1
    assert max(observations[0].probabilities) < inference.ledger.config.sku_threshold
    assert inference._camera_evidence[("lane", 1)][-1] == (.2,) * 5
    for number, z in enumerate(PATH):
        state = frame(inference, number, {
            "lane": [replace(box("lane", 1, z=z, confidence=.99), quality=.1)],
            "overhead": [box("overhead", 10, x=.02, z=z, confidence=.55)],
        })
    assert all(vote == (.2,) * 5 for vote in inference._camera_evidence[("lane", 1)])
    assert state["metrics"]["cart_units"] == 0
    assert state["review_required"] is True
    assert all(obj["sku"] is None for obj in state["objects"])


def test_rejected_high_quality_view_cannot_boost_selected_tiny_crop_quality_gate():
    inference = engine()
    tiny = replace(box("lane", 1, confidence=.99), quality=.1)
    large_rejected = box("overhead", 10, x=.02, sku=1, confidence=.99, unknown=True)
    observations, _ = inference._fuse([tiny, large_rejected])
    assert len(observations) == 1
    fused = observations[0]
    assert max(fused.probabilities) == pytest.approx(.99)
    assert fused.unknown is False
    # High classifier confidence still needs the selected crop's valid quality.
    assert fused.quality == pytest.approx(.1)
    assert fused.quality < inference.ledger.config.minimum_quality
    for number, z in enumerate(PATH):
        state = frame(inference, number, {
            "lane": [replace(box("lane", 1, z=z, confidence=.99), quality=.1)],
            "overhead": [box("overhead", 10, x=.02, z=z, sku=1, confidence=.99, unknown=True)],
        })
    assert state["metrics"]["cart_units"] == 0
    assert state["review_required"] is True
    assert all(obj["sku"] is None for obj in state["objects"])
    assert all(vote == (.2,) * 5 for vote in inference._camera_evidence[("overhead", 10)])
