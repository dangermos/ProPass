"""Joining camera aliases cannot silently reconcile two established purchases.

These deterministic observation adapters exercise process_frames and the real
ledger together, without a detector checkpoint or GPU.
"""
from types import SimpleNamespace

from vision import geometry
from vision.engine import CameraObservation, VisionEngine
from vision.ledger import LedgerConfig, PhysicalLedger


SKUS = [f"PEX-00{index + 1}" for index in range(5)]
RUN = "fusion-merge"
IMAGE = SimpleNamespace(shape=(540, 960))


def engine():
    result = VisionEngine.__new__(VisionEngine)
    result.skus = SKUS
    result.camera_ids = ["lane", "overhead"]
    result.calibration = object()  # Only truthiness is needed by process_frames.
    result.fuse_radius = .45
    result._fused = {}
    result._next_fused = 1
    result.detectors = {"lane": object(), "overhead": object()}
    result.classifier = object()  # Bypass checkpoint loading via ready interface.
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


def box(camera, track, x, z):
    return CameraObservation(camera, track, (100, 100, 160, 145), .95,
                             (.96, .01, .01, .01, .01), (1., 0.), 1.,
                             False, True, (x, z))


def frame(inference, number, observations):
    inference._observe = lambda camera, image: observations[camera]
    return inference.process_frames({camera: IMAGE for camera in observations},
                                    number, number * .2, RUN)


def separated(inference, z_values):
    for number, z in enumerate(z_values):
        state = frame(inference, number, {
            "lane": [box("lane", 1, -.5, z)],
            "overhead": [box("overhead", 10, .5, z)],
        })
    return state


def test_joining_two_established_cart_members_requires_review_without_rewriting_membership():
    inference = engine()
    before = separated(inference, [-3.4, -3.4, -2.6, -1., 1., 2.3, 2.3, 2.3])
    assert before["metrics"]["cart_units"] == 2
    assert before["review_required"] is False
    original_ids = {obj["object_id"] for obj in before["objects"]}
    state = frame(inference, 8, {
        "lane": [box("lane", 1, -.05, 2.3)],
        "overhead": [box("overhead", 10, .05, 2.3)],
    })
    assert state["review_required"] is True
    assert any(event["type"] == "REVIEW_REQUIRED" for event in state["events"])
    assert any(obj["review_reason"] for obj in state["objects"] if obj["object_id"] in original_ids)
    # Geometry disagreement is not evidence for removing a purchased unit.
    assert state["metrics"]["cart_units"] == 2
    assert all(obj["membership"] for obj in state["objects"] if obj["object_id"] in original_ids)
    assert not any(event["type"] == "ITEM_REMOVED" for event in state["events"])


def test_joining_distinct_approaching_objects_requires_identity_review_before_charge():
    inference = engine()
    before = separated(inference, [-3.4, -3.4, -3.4])
    assert len(before["objects"]) == 2
    assert all(obj["sku"] == SKUS[0] for obj in before["objects"])
    assert before["metrics"]["cart_units"] == 0
    state = frame(inference, 3, {
        "lane": [box("lane", 1, -.05, -3.4)],
        "overhead": [box("overhead", 10, .05, -3.4)],
    })
    assert state["review_required"] is True
    assert any(event["type"] == "REVIEW_REQUIRED" for event in state["events"])
    assert state["metrics"]["cart_units"] == 0
    assert not any(event["type"] == "ITEM_ADDED" for event in state["events"])


def test_reconciled_aliases_for_one_canonical_purchase_do_not_create_false_merge_review():
    inference = engine()
    for number, z in enumerate([-3.4, -3.4, -2.6, -1., 1., 2.3, 2.3, 2.3]):
        state = frame(inference, number, {"lane": [box("lane", 1, 0., z)]})
    original = state["objects"][0]["object_id"]
    # A new camera-local/fused track reattaches to the same canonical object.
    state = frame(inference, 8, {"overhead": [box("overhead", 10, .02, 2.3)]})
    assert len(set(inference._fused.values())) == 2
    assert len(state["objects"]) == 1
    assert state["objects"][0]["object_id"] == original
    state = frame(inference, 9, {
        "lane": [box("lane", 1, 0., 2.3)],
        "overhead": [box("overhead", 10, .02, 2.3)],
    })
    assert state["review_required"] is False
    assert state["metrics"]["cart_units"] == 1
    assert len(state["objects"]) == 1
    assert state["objects"][0]["object_id"] == original
    assert not any(event["type"] in {"REVIEW_REQUIRED", "ITEM_ADDED", "ITEM_REMOVED"}
                   for event in state["events"])


def test_outside_primary_alias_cannot_hide_review_for_a_lost_purchased_secondary():
    inference = engine()
    for number, z in enumerate([-3.4, -3.4, -2.6, -1., 1., 2.3, 2.3, 2.3]):
        state = frame(inference, number, {
            # This outside object gets the smaller fused ID and wins alias choice.
            "lane": [box("lane", 1, 2.4, 2.3)],
            "overhead": [box("overhead", 10, 0., z)],
        })
    assert state["metrics"]["cart_units"] == 1
    assert state["review_required"] is False
    member = next(obj["object_id"] for obj in state["objects"] if obj["membership"])
    outside = next(obj["object_id"] for obj in state["objects"] if obj["zone"] == "OUTSIDE")
    state = frame(inference, 8, {
        "lane": [box("lane", 1, 1.95, 2.3)],
        "overhead": [box("overhead", 10, 1.8, 2.3)],
    })
    # Both new projections and their fused center are outside. Review must reach
    # the old purchased canonical object, rather than only the winning alias.
    assert state["review_required"] is True
    assert next(obj for obj in state["objects"] if obj["object_id"] == member)["review_reason"]
    assert any(event["type"] == "REVIEW_REQUIRED" and event["object_id"] == member
               for event in state["events"])
    assert state["metrics"]["cart_units"] == 1
    assert next(obj for obj in state["objects"] if obj["object_id"] == member)["membership"] is True
    assert next(obj for obj in state["objects"] if obj["object_id"] == outside)["membership"] is False


def test_joining_two_entirely_outside_canonical_objects_does_not_block_unrelated_cart():
    inference = engine()
    for number, z in enumerate([-3.4, -3.4, -2.6, -1., 1., 2.3, 2.3, 2.3]):
        state = frame(inference, number, {
            "lane": [box("lane", 1, 0., z), box("lane", 2, 3., 2.3)],
            "overhead": [box("overhead", 10, .02, z), box("overhead", 20, 4., 2.3)],
        })
    assert state["metrics"]["cart_units"] == 1
    assert state["review_required"] is False
    outside_ids = {obj["object_id"] for obj in state["objects"] if obj["zone"] == "OUTSIDE"}
    assert len(outside_ids) == 2
    state = frame(inference, 8, {
        "lane": [box("lane", 1, 0., 2.3), box("lane", 2, 3.4, 2.3)],
        "overhead": [box("overhead", 10, .02, 2.3), box("overhead", 20, 3.5, 2.3)],
    })
    assert state["review_required"] is False
    assert state["metrics"]["cart_units"] == 1
    assert state["metrics"]["pending_objects"] == 0
    assert all(obj["review_reason"] is None for obj in state["objects"] if obj["object_id"] in outside_ids)
    assert not any(event["type"] in {"REVIEW_REQUIRED", "ITEM_ADDED", "ITEM_REMOVED"}
                   for event in state["events"])
