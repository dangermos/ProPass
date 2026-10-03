"""Deterministic event tests isolate application logic from learned prediction.

These injected observations do not represent model accuracy measurements.
Actual synthetic holdout metrics are recorded separately in models/manifest.json.
"""
import pytest

from vision.ledger import LedgerConfig, Observation, PhysicalLedger


SKUS = ["PEX-001", "PEX-002", "PEX-003", "PEX-004", "PEX-005"]


def obs(track_id, y, sku=0, x=300, embedding=(1.0, 0.0), unknown=False):
    probabilities = [0.01]*5
    probabilities[sku] = 0.96
    return Observation(track_id, (x-35,y-25,x+35,y+25), 0.95,
                       tuple(probabilities), embedding, 1.0, unknown)


def ledger():
    config = LedgerConfig(dwell_seconds=0.08,evidence_interval=0.08)
    result = PhysicalLedger(SKUS, config)
    result.reset("test-run")
    return result


def frame(engine, number, observations):
    return engine.update(observations, number, number*0.1, "test-run", (1000,1000))


def cross(engine, start=0, track=1, x=300, unknown=False):
    events = []
    for offset,y in enumerate([800,800,600,500,300,300,300]):
        result = frame(engine,start+offset,[obs(track,y,x=x,unknown=unknown)])
        events.extend(result["events"])
    return result,events


def test_one_physical_unit_seen_in_one_hundred_frames_is_added_once():
    engine = ledger()
    result,events = cross(engine)
    for number in range(7,100):
        result = frame(engine,number,[obs(1,300)])
        events.extend(result["events"])
    assert result["metrics"]["cart_units"] == 1
    assert sum(e["type"]=="ITEM_ADDED" for e in events) == 1
    assert len({e["event_id"] for e in events}) == len(events)


def test_two_simultaneous_identical_products_remain_two_physical_units():
    engine = ledger()
    events = []
    for number,y in enumerate([800,800,600,500,300,300,300]):
        result = frame(engine,number,[obs(1,y,x=300),obs(2,y,x=450)])
        events.extend(result["events"])
    assert result["metrics"]["cart_units"] == 2
    assert len({o["object_id"] for o in result["objects"]}) == 2
    assert sum(e["type"]=="ITEM_ADDED" for e in events) == 2


def test_short_gap_and_new_tracker_id_reuses_canonical_object():
    engine = ledger()
    result,events = cross(engine)
    old_id = result["objects"][0]["object_id"]
    frame(engine,7,[])
    frame(engine,8,[])
    result = frame(engine,9,[obs(17,300)])
    assert result["detections"][0]["object_id"] == old_id
    assert len(result["objects"]) == 1
    assert result["metrics"]["cart_units"] == 1
    assert all(e["type"]!="ITEM_ADDED" for e in result["events"])


def test_lost_visibility_does_not_remove_cart_membership():
    engine = ledger()
    cross(engine)
    result = frame(engine,20,[])
    assert result["metrics"]["cart_units"] == 1
    assert result["objects"][0]["visible"] is False
    assert all(e["type"]!="ITEM_REMOVED" for e in result["events"])


def test_entered_product_lost_before_commit_requires_completeness_review():
    engine = ledger()
    for number,y in enumerate([800,800,600,500]):
        frame(engine,number,[obs(1,y)])
    # While it could still be hidden behind an occluder, checkout is blocked as pending.
    hidden = frame(engine,24,[])
    assert hidden["review_required"] is True and hidden["objects"][0]["review_reason"] is None
    # After the occlusion window it becomes an explicit completeness review.
    result = frame(engine,70,[])
    assert result["metrics"]["cart_units"] == 0
    assert result["review_required"] is True
    assert "disappeared before" in result["objects"][0]["review_reason"]


def test_brief_precommit_occlusion_recovers_without_completeness_review():
    engine = ledger()
    for number,y in enumerate([800,800,600,500]):
        frame(engine,number,[obs(1,y)])
    frame(engine,4,[])
    frame(engine,5,[])
    result = frame(engine,6,[obs(17,480)])
    assert result["review_required"] is True  # pending, not a hard identity failure
    assert result["objects"][0]["review_reason"] is None
    assert len(result["objects"]) == 1


def test_visible_unfinished_known_merchandise_blocks_partial_cart_preparation():
    engine = ledger()
    for number,y in enumerate([800,800,600,500]):
        result = frame(engine,number,[obs(1,y)])
    assert result["objects"][0]["sku"] == "PEX-001"
    assert result["review_required"] is True
    assert result["metrics"]["pending_objects"] == 1
    assert result["objects"][0]["review_reason"] is None
    assert not any(e["type"]=="REVIEW_REQUIRED" for e in result["events"])


def test_observed_reverse_removal_then_disappearance_does_not_require_review():
    engine = ledger()
    cross(engine)
    for number,y in enumerate([500,650,800,800,800],start=7):
        frame(engine,number,[obs(1,y)])
    result = frame(engine,35,[])
    assert result["review_required"] is False
    assert result["metrics"]["cart_units"] == 0


def test_reverse_observed_crossing_removes_then_readd_uses_same_identity():
    engine = ledger()
    _,events = cross(engine)
    for number,y in enumerate([500,650,800,800,800], start=7):
        result = frame(engine,number,[obs(1,y)])
        events.extend(result["events"])
    assert result["metrics"]["cart_units"] == 0
    assert sum(e["type"]=="ITEM_REMOVED" for e in events) == 1
    for number,y in enumerate([600,500,300,300,300],start=12):
        result = frame(engine,number,[obs(1,y)])
        events.extend(result["events"])
    assert result["metrics"]["cart_units"] == 1
    assert sum(e["type"]=="ITEM_ADDED" for e in events) == 2
    assert len(result["objects"]) == 1


def test_duplicate_frame_delivery_does_not_repeat_events():
    engine = ledger()
    result,_ = cross(engine)
    duplicate = frame(engine,6,[obs(1,300)])
    assert duplicate["events"] == []
    assert duplicate["duplicate_frame"] is True
    assert duplicate["metrics"]["cart_units"] == result["metrics"]["cart_units"]


def test_unseen_unknown_product_crossing_requires_review_and_no_add():
    engine = ledger()
    result,events = cross(engine,unknown=True)
    assert result["review_required"] is True
    assert result["objects"][0]["sku"] is None
    assert result["metrics"]["cart_units"] == 0
    assert any(e["type"]=="REVIEW_REQUIRED" for e in events)
    assert not any(e["type"]=="ITEM_ADDED" for e in events)


def test_pending_sku_can_resolve_later_without_counting_the_crossing_twice():
    engine = ledger()
    result,events = cross(engine,unknown=True)
    assert result["review_required"] is True
    for number in range(7,25):
        result = frame(engine,number,[obs(1,300)])
        events.extend(result["events"])
    assert result["review_required"] is False
    assert result["metrics"]["cart_units"] == 1
    assert len(result["objects"]) == 1
    assert sum(e["type"]=="ITEM_ADDED" for e in events) == 1
    assert sum(e["type"]=="SKU_RESOLVED" for e in events) == 1


def test_small_boundary_jitter_does_not_create_add_remove_events():
    engine = ledger()
    events = []
    for number,y in enumerate([800,800,600,500,385,410,390,405,385,410]):
        result = frame(engine,number,[obs(1,y)])
        events.extend(result["events"])
    assert result["metrics"]["cart_units"] == 0
    assert not any(e["type"] in {"ITEM_ADDED","ITEM_REMOVED"} for e in events)


def test_initial_visibility_after_boundary_is_not_an_automatic_purchase():
    engine = ledger()
    events = []
    for number in range(5):
        result = frame(engine,number,[obs(1,300)])
        events.extend(result["events"])
    assert result["review_required"] is True
    assert result["metrics"]["cart_units"] == 0


def test_ambiguous_identical_fragment_recovery_is_reviewed_not_merged():
    engine = ledger()
    for number,y in enumerate([800,800,600,500,300,300,300]):
        frame(engine,number,[obs(1,y,x=300),obs(2,y,x=450)])
    frame(engine,7,[])
    result = frame(engine,8,[obs(99,300,x=375)])
    assert result["review_required"] is True
    assert result["metrics"]["cart_units"] == 2
    assert len(result["objects"]) == 3
    assert result["detections"][0]["membership"] is False


def test_same_tracker_id_cannot_occur_twice_in_one_frame():
    engine = ledger()
    with pytest.raises(ValueError,match="only once"):
        frame(engine,0,[obs(1,800,x=300),obs(1,800,x=500)])


def test_nonmonotonic_timestamp_and_wrong_run_are_rejected():
    engine = ledger()
    frame(engine,1,[obs(1,800)])
    with pytest.raises(ValueError,match="monotonic"):
        engine.update([obs(1,800)],2,0,"test-run",(1000,1000))
    with pytest.raises(ValueError,match="Run ID"):
        engine.update([obs(1,800)],2,0.2,"different-run",(1000,1000))


def test_conflicting_sku_does_not_silently_change_existing_purchase():
    engine = ledger()
    cross(engine)
    events = []
    for number in range(7,22):
        result = frame(engine,number,[obs(1,300,sku=1)])
        events.extend(result["events"])
    assert result["review_required"] is True
    assert result["objects"][0]["sku"] == "PEX-001"
    assert result["metrics"]["cart_units"] == 1
    assert all(e["type"]!="SKU_RESOLVED" for e in events)


def test_product_carried_outside_the_lane_is_never_charged_or_pending():
    config = LedgerConfig(dwell_seconds=0.08, evidence_interval=0.08,
                          lane_polygon=((0.2, 0.0), (0.6, 0.0), (0.6, 1.0), (0.2, 1.0)))
    engine = PhysicalLedger(SKUS, config)
    engine.reset("test-run")
    result, events = cross(engine, x=850)   # next aisle, crosses both zone rows
    assert result["metrics"]["cart_units"] == 0
    assert not result["review_required"]
    assert "ITEM_ADDED" not in {e["type"] for e in events}
    inside, _ = cross(engine, start=20, track=2, x=400)
    assert inside["metrics"]["cart_units"] == 1


def test_long_occlusion_reattaches_when_reappearance_fits_motion():
    engine = ledger()
    for number,y in enumerate([800,780,760,740,720,700,680,660,640,620]):
        frame(engine,number,[obs(1,y)])
    # Hidden for 3.5 s (longer than the short re-attach window), then seen further along.
    events = []
    for number,y in enumerate([450,430,410,390,370,350,330,310],start=45):
        events += frame(engine,number,[obs(7,y)])["events"]
    result = frame(engine,60,[obs(7,300)])
    assert len(result["objects"]) == 1
    assert result["metrics"]["cart_units"] == 1
    assert not result["review_required"]
