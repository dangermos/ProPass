"""World-coordinate identity recovery contracts, with no models or GPU inputs.

Changing viewpoint can change a product crop's embedding. Calibrated position
plus the same strong SKU may recover identity conservatively; neither SKU-wide
deduplication nor unrelated aisle uncertainty may rewrite a completed cart.
"""
from dataclasses import replace

import pytest

from vision import geometry
from vision.engine import CameraObservation, VisionEngine
from vision.ledger import LedgerConfig, Observation, PhysicalLedger

SKUS = [f"PEX-00{index + 1}" for index in range(5)]
RUN = "world-recovery"


def ledger():
    left, _ = geometry.to_map(-1.7, 0)
    right, _ = geometry.to_map(1.7, 0)
    config = LedgerConfig(
        approach_y=geometry.to_map(0, -2)[1],
        commit_y=geometry.to_map(0, 1.6)[1],
        lane_polygon=((left, 0), (right, 0), (right, 1), (left, 1)),
        hysteresis=.015, lane_margin=.01, dwell_seconds=.08,
        evidence_interval=.08, reattach_distance=.06, reattach_margin=.03,
        occlusion_gate_growth=.02,
    )
    result = PhysicalLedger(SKUS, config)
    result.reset(RUN)
    return result


def observation(track, x=0, z=2.3, sku=0, embedding=(1., 0.),
                unknown=False, confidence=.96):
    u, v = geometry.to_map(x, z)
    cx, cy = u * geometry.MAP_SIZE, v * geometry.MAP_SIZE
    probabilities = [.01] * len(SKUS)
    probabilities[sku] = confidence
    return Observation(track, (cx - 20, cy - 20, cx + 20, cy + 20), .95,
                       tuple(probabilities), embedding, 1., unknown,
                       full_view=True, at_entry_edge=False, sized=False)


def update(engine, number, observations):
    return engine.update(observations, number, number * .2, RUN,
                         (geometry.MAP_SIZE, geometry.MAP_SIZE))


def cross(engine, xs=(0.,)):
    events = []
    for number, z in enumerate([-3.4, -3.4, -2.6, -1., 1., 2.3, 2.3, 2.3]):
        state = update(engine, number, [observation(index + 1, x=x, z=z)
                                        for index, x in enumerate(xs)])
        events.extend(state["events"])
    assert state["metrics"]["cart_units"] == len(xs)
    assert state["review_required"] is False
    return state, events


def test_nearby_world_recovery_with_same_strong_sku_tolerates_viewpoint_embedding_change():
    engine = ledger()
    previous, _ = cross(engine)
    canonical = previous["objects"][0]["object_id"]
    update(engine, 8, [])
    state = update(engine, 9, [observation(99, x=.05, z=2.32, embedding=(0., 1.))])
    assert state["detections"][0]["object_id"] == canonical
    assert len(state["objects"]) == 1
    assert state["metrics"]["cart_units"] == 1
    assert state["review_required"] is False
    assert not any(event["type"] in {"ITEM_ADDED", "ITEM_REMOVED"} for event in state["events"])


def test_strong_contradictory_sku_cannot_inherit_world_purchase_identity():
    engine = ledger()
    previous, _ = cross(engine)
    canonical = previous["objects"][0]["object_id"]
    update(engine, 8, [])
    # Even a visually similar crop at the same location cannot override the SKU veto.
    state = update(engine, 9, [observation(99, x=.02, sku=1)])
    assert state["detections"][0]["object_id"] != canonical
    assert len(state["objects"]) == 2
    assert state["metrics"]["cart_units"] == 1
    assert state["review_required"] is True
    original = next(obj for obj in state["objects"] if obj["object_id"] == canonical)
    assert original["sku"] == SKUS[0] and original["membership"] is True


def test_same_sku_competing_lost_world_units_trigger_identity_ambiguity():
    engine = ledger()
    previous, _ = cross(engine, xs=(-.18, .18))
    originals = {obj["object_id"] for obj in previous["objects"]}
    update(engine, 8, [])
    state = update(engine, 9, [observation(99, x=0., embedding=(0., 1.))])
    assert state["review_required"] is True
    assert state["metrics"]["cart_units"] == 2
    assert state["detections"][0]["object_id"] not in originals
    assert all(obj["review_reason"] for obj in state["objects"] if obj["object_id"] in originals)
    assert any(event["type"] == "REVIEW_REQUIRED" for event in state["events"])


@pytest.mark.parametrize("replacement", [
    observation(99, embedding=(0., 1.), unknown=True),
    observation(99, embedding=(0., 1.), confidence=.55),
    replace(observation(99, embedding=(0., 1.)), sized=True),
])
def test_world_fallback_requires_strong_enrolled_evidence_and_never_changes_image_gates(replacement):
    engine = ledger()
    previous, _ = cross(engine)
    canonical = previous["objects"][0]["object_id"]
    update(engine, 8, [])
    state = update(engine, 9, [replacement])
    assert state["detections"][0]["object_id"] != canonical
    assert state["metrics"]["cart_units"] == 1
    assert state["review_required"] is True


def test_world_recovery_still_obeys_spatial_gate_when_same_sku_is_far_away():
    engine = ledger()
    previous, _ = cross(engine)
    canonical = previous["objects"][0]["object_id"]
    update(engine, 8, [])
    state = update(engine, 9, [observation(99, x=1.3, embedding=(0., 1.))])
    assert state["detections"][0]["object_id"] != canonical
    assert len(state["objects"]) == 2
    assert state["metrics"]["cart_units"] == 1
    assert state["review_required"] is True


def camera(camera_id, track, x, z):
    return CameraObservation(camera_id, track, (100, 100, 160, 145), .95,
                             (.96, .01, .01, .01, .01), (1., 0.), 1.,
                             False, True, (x, z))


def fusion():
    # Bypass checkpoint loading: only deterministic geometric association is tested.
    result = VisionEngine.__new__(VisionEngine)
    result.skus = SKUS
    result.fuse_radius = .45
    result._fused = {}
    result._next_fused = 1
    return result

def test_projection_ambiguity_on_a_lane_purchase_still_requires_review_after_it_moves_outside():
    engine = ledger()
    previous, _ = cross(engine)
    canonical = previous["objects"][0]["object_id"]
    state = update(engine, 8, [replace(observation(1, x=2.5), ambiguous_identity=True)])
    assert state["review_required"] is True
    assert state["metrics"]["cart_units"] == 1
    assert state["objects"][0]["object_id"] == canonical
    assert state["objects"][0]["review_reason"]
