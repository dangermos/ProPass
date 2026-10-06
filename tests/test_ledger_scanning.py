"""Barcode evidence, ratings, restricted items and the associate hand-off list.

Synthetic observations only: these check ledger rules, not barcode-reader accuracy.
"""
from dataclasses import replace

from vision.ledger import LedgerConfig, Observation, PhysicalLedger

SKUS = ["PEX-001", "PEX-002", "PEX-003", "PEX-004", "PEX-005"]
RUN = "scan-test"


def ledger(**config):
    result = PhysicalLedger(SKUS, LedgerConfig(dwell_seconds=0.08, evidence_interval=0.08, **config))
    result.reset(RUN)
    return result


def obs(track, y, sku=0, confidence=0.96, unknown=False, barcode=None, x=300):
    probabilities = [(1 - confidence) / 4] * 5
    probabilities[sku] = confidence
    return Observation(track, (x - 35, y - 25, x + 35, y + 25), 0.95, tuple(probabilities),
                       (1.0, 0.0), 1.0, unknown, barcode=barcode)


def cross(engine, make, start=0):
    result = None
    for offset, y in enumerate([800, 800, 600, 500, 300, 300, 300]):
        result = engine.update([make(y)], start + offset, (start + offset) * 0.1, RUN, (1000, 1000))
    return result


def item(result, index=0):
    return result["objects"][index]


def test_a_barcode_read_resolves_the_sku_at_once_and_rates_it_verified():
    engine = ledger()
    first = engine.update([obs(1, 800, unknown=True, barcode="PEX-003")], 0, 0.0, RUN, (1000, 1000))
    assert item(first)["sku"] == "PEX-003" and item(first)["sku_source"] == "barcode"
    result = cross(engine, lambda y: obs(1, y, unknown=True, barcode="PEX-003"), start=1)
    assert result["metrics"]["cart_units"] == 1
    assert item(result)["rating"] == "verified"
    assert result["assist"] == [] and not result["review_required"]


def test_visual_recognition_is_rated_high_or_medium_by_confidence():
    high = cross(ledger(), lambda y: obs(1, y, confidence=0.98))
    medium = cross(ledger(), lambda y: obs(1, y, confidence=0.90))
    assert item(high)["rating"] == "high" and item(high)["sku_source"] == "visual"
    assert item(medium)["rating"] == "medium"
    assert medium["metrics"]["cart_units"] == 1


def test_barcode_outranks_a_visual_guess_made_before_the_item_is_in_the_cart():
    engine = ledger()
    for frame in range(4):      # recognized by look as PEX-001 while still approaching
        engine.update([obs(1, 800, sku=0)], frame, frame * 0.1, RUN, (1000, 1000))
    result = engine.update([obs(1, 800, sku=0, barcode="PEX-004")], 4, 0.4, RUN, (1000, 1000))
    assert item(result)["sku"] == "PEX-004" and item(result)["rating"] == "high"    # one read so far
    again = engine.update([obs(1, 800, sku=0, barcode="PEX-004")], 5, 0.5, RUN, (1000, 1000))
    assert item(again)["rating"] == "verified" and not again["assist"]


def test_barcode_that_contradicts_a_cart_member_goes_to_an_associate():
    engine = ledger()
    cross(engine, lambda y: obs(1, y, sku=0))
    result = engine.update([obs(1, 300, sku=0, barcode="PEX-002")], 20, 2.0, RUN, (1000, 1000))
    assert item(result)["sku"] == "PEX-001" and item(result)["membership"] is True
    assert result["assist"][0]["reason"].startswith("Barcode disagrees")
    assert item(result)["rating"] == "needs_associate"


def test_unknown_barcode_is_not_charged_and_is_handed_to_an_associate():
    result = cross(ledger(), lambda y: obs(1, y, unknown=True, barcode="9999999999"))
    assert result["metrics"]["cart_units"] == 0
    assert [a["reason"] for a in result["assist"]] == ["Barcode is not in the catalog"]


def test_restricted_item_is_never_added_and_is_routed_to_an_associate():
    engine = ledger(restricted_skus=("PEX-002",))
    result = cross(engine, lambda y: obs(1, y, sku=1, barcode="PEX-002"))
    assert result["metrics"]["cart_units"] == 0
    assert result["assist"] == [{"object_id": item(result)["object_id"], "sku": "PEX-002",
                                 "reason": "Restricted item: an associate must release it", "restricted": True}]


def test_scanned_items_are_kept_when_another_item_needs_an_associate():
    engine = ledger()
    result = None
    for frame, y in enumerate([800, 800, 600, 500, 300, 300, 300, 300, 300, 300]):
        result = engine.update([obs(1, y, barcode="PEX-001", x=300), obs(2, y, unknown=True, x=600)],
                               frame, frame * 0.1, RUN, (1000, 1000))
    assert result["metrics"]["cart_units"] == 1          # the scanned one stays in the cart
    assert len(result["assist"]) == 1 and result["assist"][0]["sku"] is None
    assert result["in_progress"] == 0


def test_item_still_walking_through_is_in_progress_not_an_associate_case():
    engine = ledger()
    result = None
    for frame, y in enumerate([800, 800, 700, 600]):
        result = engine.update([obs(1, y, barcode="PEX-001")], frame, frame * 0.1, RUN, (1000, 1000))
    assert result["in_progress"] == 1 and result["assist"] == []
    assert result["review_required"] is True
