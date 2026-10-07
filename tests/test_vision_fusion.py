"""Multi-camera fusion contracts, independent of GPU models.

The lane camera is primary and other cameras assist. These synthetic observations check
association only. They say nothing about detector or classifier accuracy.
"""
import pytest

from vision import geometry
from vision.engine import CameraObservation, VisionEngine
from vision.ledger import LedgerConfig, PhysicalLedger

SKUS = [f"PEX-00{i + 1}" for i in range(5)]
RUN_ID = "fusion-test"


@pytest.fixture
def engine():
    # Deliberately bypass initialization: these tests never deserialize models.
    result = VisionEngine.__new__(VisionEngine)
    result.skus = SKUS
    result.camera_ids = ["lane", "overhead"]
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


def world(observation):
    u, v = (c / geometry.MAP_SIZE for c in observation.center)
    return geometry.from_map(u, v)


def test_one_box_seen_by_both_cameras_is_one_observation_at_the_overhead_position(engine):
    observations, members = engine._fuse([seen("lane", 1, x=0.05, z=0.3), seen("overhead", 10, x=0.0, z=0.0)])
    assert len(observations) == 1 and len(members[0]) == 2
    assert world(observations[0]) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert observations[0].sized is False


def test_two_boxes_in_the_same_camera_never_merge(engine):
    observations, _ = engine._fuse([seen("lane", 1, x=-0.1), seen("lane", 2, x=0.1)])
    assert len({o.track_id for o in observations}) == 2


def test_overhead_alone_never_starts_an_object(engine):
    observations, _ = engine._fuse([seen("overhead", 10)])
    assert observations == []


def test_overhead_keeps_the_identity_while_the_lane_camera_is_blocked(engine):
    first, _ = engine._fuse([seen("lane", 1), seen("overhead", 10)])
    hidden, _ = engine._fuse([seen("overhead", 10, z=0.5)])
    back, _ = engine._fuse([seen("lane", 7, z=1.0), seen("overhead", 10, z=1.0)])   # new lane tracker id
    assert first[0].track_id == hidden[0].track_id == back[0].track_id
    assert len(hidden) == len(back) == 1


def test_identical_side_by_side_units_pair_one_to_one(engine):
    observations, members = engine._fuse([seen("lane", 1, x=-0.5), seen("lane", 2, x=0.5),
                                          seen("overhead", 10, x=0.5), seen("overhead", 11, x=-0.5)])
    assert len(observations) == 2 and all(len(group) == 2 for group in members)
    pairs = {frozenset(o.track_id for o in group) for group in members}
    assert pairs == {frozenset({1, 11}), frozenset({2, 10})}


def test_confidently_different_skus_do_not_merge(engine):
    observations, members = engine._fuse([seen("lane", 1, sku=0), seen("overhead", 10, sku=3)])
    assert len(observations) == 1 and len(members[0]) == 1      # the overhead box stays out


def test_height_shift_is_learned_and_applied_when_only_the_lane_camera_sees_the_box(engine):
    for _ in range(12):     # a box carried high: the lane camera places it 0.5 m too far along z
        engine._fuse([seen("lane", 1, z=0.5), seen("overhead", 10, z=0.0)])
    alone, _ = engine._fuse([seen("lane", 1, z=1.5)])
    assert world(alone[0])[1] == pytest.approx(1.0, abs=0.05)


def test_established_pair_wins_over_a_closer_stranger(engine):
    engine._fuse([seen("lane", 1, x=0.0), seen("overhead", 10, x=0.0), seen("lane", 2, x=0.9), seen("overhead", 11, x=0.9)])
    _, members = engine._fuse([seen("lane", 1, x=0.3), seen("overhead", 10, x=0.6), seen("lane", 2, x=0.7), seen("overhead", 11, x=1.0)])
    pairs = {frozenset(o.track_id for o in group) for group in members}
    assert pairs == {frozenset({1, 10}), frozenset({2, 11})}


def test_unknown_view_does_not_dilute_a_clear_sku(engine):
    observations, _ = engine._fuse([seen("lane", 1, sku=2), seen("overhead", 10, sku=4, unknown=True)])
    assert observations[0].unknown is False
    assert observations[0].probabilities[2] == pytest.approx(0.96)


def test_two_camera_crossing_adds_one_unit_even_while_the_lane_camera_is_blocked(engine):
    engine.calibration = None
    ledger = PhysicalLedger(SKUS, LedgerConfig(dwell_seconds=0.08, evidence_interval=0.08,
                                               approach_y=geometry.to_map(0, -2)[1], commit_y=geometry.to_map(0, 1.6)[1]))
    ledger.reset(RUN_ID)
    result = None
    for frame, z in enumerate([-3.5, -3.3, -3.0, -2.5, -1.5, -0.5, 0.5, 1.5, 2.2, 2.6, 2.8, 3.0]):
        views = [seen("overhead", 10, z=z)]
        if not 4 <= frame <= 8:                       # blocked mid-lane
            views.append(seen("lane", 1 if frame < 4 else 5, z=z))
        observations, _ = engine._fuse(views)
        result = ledger.update(observations, frame, frame * 0.2, RUN_ID, (geometry.MAP_SIZE, geometry.MAP_SIZE))
    assert result["metrics"]["cart_units"] == 1
    assert len(result["objects"]) == 1
    assert not result["review_required"]


def test_a_region_claimed_more_confidently_by_a_person_is_not_merchandise():
    from vision.engine import merchandise_only
    boxes = [(100, 100, 140, 140), (300, 300, 340, 340), (102, 101, 141, 143), (300, 302, 341, 340)]
    # A box, a second box, a person over the first box's region, a weaker copy of the second box.
    assert merchandise_only(boxes, [0, 0, 1, 0], [0.3, 0.9, 0.8, 0.6]) == [1]
    # A person box that merely overlaps a product (someone standing behind it) removes nothing.
    assert merchandise_only([(100, 100, 140, 140), (90, 40, 150, 200)], [0, 1], [0.6, 0.9]) == [0]
