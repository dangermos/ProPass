"""Deterministic multi-camera identity/event contracts, independent of GPU models.

The synthetic observations below measure association correctness only. They do
not claim detector, classifier, or synthetic-to-real accuracy.
"""
from dataclasses import replace

import pytest

from vision import geometry
from vision.engine import CameraObservation, VisionEngine
from vision.ledger import LedgerConfig, Observation, PhysicalLedger


SKUS = [f"PEX-00{i + 1}" for i in range(5)]
RUN_ID = "fusion-test"


@pytest.fixture
def engine():
    # Deliberately bypass initialization: these tests never deserialize models.
    result = VisionEngine.__new__(VisionEngine)
    result.skus = SKUS
    result.fuse_radius = 0.45
    result._fused = {}
    result._next_fused = 1
    return result


def seen(camera, track, x=0.0, z=0.0, sku=0, quality=1.0, unknown=False, full_view=True):
    probabilities = [0.01] * len(SKUS)
    probabilities[sku] = 0.96
    embedding = tuple(float(index == sku) for index in range(len(SKUS)))
    return CameraObservation(camera, track, (100, 100, 160, 145), 0.95,
                             tuple(probabilities), embedding, quality, unknown, full_view, (x, z))


def group_keys(members):
    return {frozenset((item.camera, item.track_id) for item in group) for group in members}


def test_one_physical_box_seen_by_two_cameras_becomes_one_observation(engine):
    observations, members = engine._fuse([seen("lane", 1, x=0.02), seen("overhead", 10, x=-0.02)])
    assert len(observations) == 1
    assert group_keys(members) == {frozenset({("lane", 1), ("overhead", 10)})}
    center = observations[0].center
    assert geometry.from_map(center[0] / geometry.MAP_SIZE,
                             center[1] / geometry.MAP_SIZE) == pytest.approx((0, 0))
    assert observations[0].sized is False


def test_nearby_boxes_in_the_same_camera_never_merge(engine):
    observations, members = engine._fuse([seen("lane", 1, x=-0.1), seen("lane", 2, x=0.1)])
    assert len(observations) == 2
    assert len({observation.track_id for observation in observations}) == 2
    assert all(len(group) == 1 for group in members)


def test_visibility_loss_in_one_camera_preserves_fused_identity(engine):
    paired, _ = engine._fuse([seen("lane", 1), seen("overhead", 10)])
    overhead, _ = engine._fuse([seen("overhead", 10, z=0.1)])
    recovered, _ = engine._fuse([seen("lane", 1, z=0.2), seen("overhead", 10, z=0.2)])
    lane, _ = engine._fuse([seen("lane", 1, z=0.3)])
    assert {group[0].track_id for group in (paired, overhead, recovered, lane)} == {paired[0].track_id}


def test_reconciled_camera_alias_does_not_resurrect_its_previous_fused_id(engine):
    lane, _ = engine._fuse([seen("lane", 1)])
    overhead, _ = engine._fuse([seen("overhead", 10)])
    assert lane[0].track_id != overhead[0].track_id
    paired, _ = engine._fuse([seen("lane", 1), seen("overhead", 10)])
    overhead_only, _ = engine._fuse([seen("overhead", 10)])
    assert len(paired) == 1
    assert overhead_only[0].track_id == paired[0].track_id


def test_identical_nearby_units_match_one_to_one_across_cameras(engine):
    observations, members = engine._fuse([
        seen("lane", 1, x=-0.18), seen("lane", 2, x=0.18),
        seen("overhead", 10, x=-0.15), seen("overhead", 20, x=0.15),
    ])
    assert len(observations) == 2
    assert len({observation.track_id for observation in observations}) == 2
    assert group_keys(members) == {
        frozenset({("lane", 1), ("overhead", 10)}),
        frozenset({("lane", 2), ("overhead", 20)}),
    }


def test_high_confidence_different_skus_do_not_merge_just_because_they_are_close(engine):
    observations, members = engine._fuse([seen("lane", 1, sku=0), seen("overhead", 10, x=0.2, sku=1)])
    assert len(observations) == 2
    assert all(len(group) == 1 for group in members)


def test_unknown_view_can_support_position_without_overriding_clear_sku(engine):
    observations, _ = engine._fuse([
        seen("lane", 1, sku=0, quality=0.7),
        seen("overhead", 10, x=0.05, sku=4, quality=1.0, unknown=True),
    ])
    assert len(observations) == 1
    assert observations[0].unknown is False
    assert observations[0].probabilities[0] == pytest.approx(0.96)
    assert observations[0].embedding == (1, 0, 0, 0, 0)
    cx, cy = observations[0].center
    assert geometry.from_map(cx / geometry.MAP_SIZE, cy / geometry.MAP_SIZE) == pytest.approx((0, 0))


def test_tracker_id_replacement_in_one_camera_inherits_other_cameras_identity(engine):
    original, _ = engine._fuse([seen("lane", 1), seen("overhead", 10)])
    replacement, _ = engine._fuse([seen("lane", 99, z=0.1), seen("overhead", 10, z=0.1)])
    lane_only, _ = engine._fuse([seen("lane", 99, z=0.2)])
    assert replacement[0].track_id == original[0].track_id == lane_only[0].track_id


def test_established_pairs_survive_crossing_projection_noise(engine):
    _, first_members = engine._fuse([
        seen("lane", 1, x=-0.3), seen("lane", 2, x=0.3),
        seen("overhead", 10, x=-0.32), seen("overhead", 20, x=0.32),
    ])
    # Centers disagree by 15 cm near the crossing. Nearest-only pairing swaps
    # cameras here; the independently stable tracker histories resolve the tie.
    observations, members = engine._fuse([
        seen("lane", 1, x=-0.08), seen("lane", 2, x=0.08),
        seen("overhead", 10, x=0.07), seen("overhead", 20, x=-0.07),
    ])
    assert len(observations) == 2
    assert group_keys(members) == group_keys(first_members)


def test_out_of_gate_true_pair_does_not_merge_two_established_objects(engine):
    engine._fuse([
        seen("lane", 1, x=-0.6), seen("lane", 2, x=0.6),
        seen("overhead", 10, x=-0.62), seen("overhead", 20, x=0.62),
    ])
    # A height/projection error pushes the established pairs outside the
    # geometry gate. Swapping their partners would merge two known identities.
    _, members = engine._fuse([
        seen("lane", 1, x=-0.3), seen("lane", 2, x=0.3),
        seen("overhead", 10, x=0.3), seen("overhead", 20, x=-0.3),
    ])
    assert frozenset({("lane", 1), ("overhead", 20)}) not in group_keys(members)
    assert frozenset({("lane", 2), ("overhead", 10)}) not in group_keys(members)


def make_ledger():
    calibration = geometry.Calibration("vision/cameras.json")
    config = LedgerConfig(**calibration.ledger_overrides(), dwell_seconds=0.08,
                          evidence_interval=0.08, reattach_distance=0.06)
    result = PhysicalLedger(SKUS, config)
    result.reset(RUN_ID)
    return result


def map_observation(track, x=0, z=-3, full_view=True, at_entry_edge=False, sized=False,
                    unknown=False, half=20):
    u, v = geometry.to_map(x, z)
    cx, cy = u * geometry.MAP_SIZE, v * geometry.MAP_SIZE
    return Observation(track, (cx - half, cy - half, cx + half, cy + half), 0.95,
                       (0.96, 0.01, 0.01, 0.01, 0.01), (1, 0, 0, 0, 0), 1.0, unknown,
                       full_view=full_view, at_entry_edge=at_entry_edge, sized=sized)


def update(ledger, frame, timestamp, observations):
    return ledger.update(observations, frame, timestamp, RUN_ID,
                         (geometry.MAP_SIZE, geometry.MAP_SIZE))


def test_two_camera_crossing_adds_one_unit_even_after_lane_disappears(engine):
    ledger = make_ledger()
    events = []
    for number, z in enumerate([-3.4, -3.4, -2.6, -1.0, 1.0, 2.3, 2.3, 2.3]):
        boxes = [seen("overhead", 10, z=z)]
        if number < 4:
            boxes.append(seen("lane", 1, z=z))
        fused, _ = engine._fuse(boxes)
        result = update(ledger, number, number * 0.2, fused)
        events.extend(result["events"])
    assert result["metrics"]["cart_units"] == 1
    assert len(result["objects"]) == 1
    assert result["review_required"] is False
    assert sum(event["type"] == "ITEM_ADDED" for event in events) == 1


def test_two_identical_physical_units_cross_both_cameras_and_are_added_twice(engine):
    ledger = make_ledger()
    events = []
    for number, z in enumerate([-3.4, -3.4, -2.6, -1.0, 1.0, 2.3, 2.3, 2.3]):
        fused, _ = engine._fuse([
            seen("lane", 1, x=-0.48, z=z), seen("lane", 2, x=0.48, z=z),
            seen("overhead", 10, x=-0.45, z=z), seen("overhead", 20, x=0.45, z=z),
        ])
        result = update(ledger, number, number * 0.2, fused)
        events.extend(result["events"])
    assert result["metrics"]["cart_units"] == 2
    assert len(result["objects"]) == 2
    assert result["review_required"] is False
    assert sum(event["type"] == "ITEM_ADDED" for event in events) == 2
    assert all(obj["sku"] == SKUS[0] for obj in result["objects"])


def test_both_camera_tracker_ids_replaced_after_short_gap_reuse_canonical_item(engine):
    ledger = make_ledger()
    for number, z in enumerate([-3.4, -3.4, -2.6, -1.0, 1.0, 2.3, 2.3, 2.3]):
        fused, _ = engine._fuse([seen("lane", 1, z=z), seen("overhead", 10, z=z)])
        result = update(ledger, number, number * 0.2, fused)
    original = result["objects"][0]["object_id"]
    update(ledger, 8, 1.6, [])
    fused, _ = engine._fuse([seen("lane", 99, z=2.3), seen("overhead", 100, z=2.3)])
    result = update(ledger, 9, 1.8, fused)
    assert result["detections"][0]["object_id"] == original
    assert result["metrics"]["cart_units"] == 1
    assert len(result["objects"]) == 1
    assert result["review_required"] is False
    assert not any(event["type"] == "ITEM_ADDED" for event in result["events"])


def test_one_established_object_split_by_projection_error_cannot_silently_count_twice(engine):
    ledger = make_ledger()
    for number in range(3):
        fused, _ = engine._fuse([seen("lane", 1, z=-3.4), seen("overhead", 10, z=-3.4)])
        update(ledger, number, number * 0.2, fused)
    for number, z in enumerate([-2.6, -2.6, -1.0, 1.0, 2.3, 2.3, 2.3], start=3):
        # Both tracker IDs previously belonged to one physical box. Incorrect
        # carry-plane projections now place them beyond the fusion radius.
        fused, _ = engine._fuse([seen("lane", 1, x=-0.3, z=z),
                                seen("overhead", 10, x=0.3, z=z)])
        result = update(ledger, number, number * 0.2, fused)
    assert result["metrics"]["cart_units"] == 1 or result["review_required"] is True


@pytest.mark.parametrize("full_view,expected_state,review", [
    (False, "FRAGMENT", False), (True, "ENTERING", True),
])
def test_map_full_view_flag_uses_camera_border_evidence(full_view, expected_state, review):
    ledger = make_ledger()
    observation = map_observation(1, full_view=full_view, unknown=True)
    update(ledger, 0, 0, [observation])
    update(ledger, 1, 0.2, [observation])
    result = update(ledger, 2, 2.5, [])
    assert result["objects"][0]["state"] == expected_state
    assert result["review_required"] is review


@pytest.mark.parametrize("at_entry_edge,expected_state,review", [
    (True, "LEFT", False), (False, "ENTERING", True),
])
def test_map_entry_edge_flag_is_independent_of_virtual_bbox_border(at_entry_edge, expected_state, review):
    ledger = make_ledger()
    observation = map_observation(1, z=-4.3, at_entry_edge=at_entry_edge)
    update(ledger, 0, 0, [observation])
    update(ledger, 1, 0.2, [observation])
    result = update(ledger, 2, 1.0, [])
    assert result["objects"][0]["state"] == expected_state
    assert result["review_required"] is review


def test_map_sized_false_ignores_virtual_marker_area_in_fragment_recovery():
    ledger = make_ledger()
    previous = map_observation(1, half=20)
    update(ledger, 0, 0, [previous])
    update(ledger, 1, 0.2, [previous])
    canonical = next(iter(ledger.objects.values()))
    tiny_marker = map_observation(99, z=-2.95, half=2)
    assert ledger._match_cost(canonical, tiny_marker, 0.4, 1000, 1000) is not None
    assert ledger._match_cost(canonical, replace(tiny_marker, sized=True), 0.4, 1000, 1000) is None


def test_fusion_preserves_explicit_camera_visibility_and_entry_flags(engine):
    fused, _ = engine._fuse([
        seen("lane", 1, z=-4.3, full_view=False),
        seen("overhead", 10, z=-4.3, full_view=True),
    ])
    assert fused[0].full_view is True
    assert fused[0].at_entry_edge is True
    assert fused[0].sized is False
