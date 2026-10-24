"""The optional checkout decision layer: rules first, hard reasons never overridden, rules on failure."""
import urllib.error

import pytest

from training.decision_eval import outcome, tally
from vision.decision import CLOSE, HAND_OFF, ModelDecider, call_systemone, decision_state, rules_decision
from vision.ledger import Observation, PhysicalLedger

NAMES = {"PEX-001": "Drill", "PEX-002": "Driver"}


def item(**overrides):
    base = {"object_id": "o1", "sku": "PEX-001", "sku_source": "barcode", "barcode_reads": 2, "rating": "verified",
            "accepted_confidence": 1.0, "confidence": 0.97, "views": 8, "state": "ADDED", "zone": "COMMIT",
            "in_cart": True, "visible_now": False, "entered_lane": True, "crossed_checkout": True,
            "seen_seconds": 4.0, "seen_whole": True, "ambiguous_identity": False, "restricted": False,
            "review_reason": None}
    return base | overrides


def evidence(*items, review=True, in_progress=0):
    return {"run_id": "r", "timestamp": 9.0, "review_required": review, "in_progress": in_progress, "items": list(items)}


SOFT = item(object_id="o2", sku="PEX-001", sku_source="visual", in_cart=False, crossed_checkout=False,
            state="ENTERING", zone="APPROACH", seen_seconds=0.4, seen_whole=False,
            review_reason="Entered merchandise disappeared before an observed checkout or reverse removal")


class Recorder:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.states = answer, error, []

    def __call__(self, state, api_key, model, base_url):
        self.states.append(state)
        if self.error:
            raise self.error
        return self.answer


def decider(call, key="test-key"):
    return ModelDecider("subq", api_key=key, names=NAMES, call=call)


def test_clean_cart_closes_without_a_model_call():
    call = Recorder()
    made = decider(call).decide(evidence(item(), review=False))
    assert made.decision == CLOSE and made.source == "rules" and not call.states


def test_model_can_close_a_soft_flag():
    call = Recorder({"choice": CLOSE, "probability": 0.93, "confidence": 0.9})
    made = decider(call).decide(evidence(item(), SOFT))
    assert made.decision == CLOSE and made.source == "subq" and made.probability == 0.93
    state = call.states[0]
    assert state["flagged_items"][0]["same_product_already_charged"] == 1
    assert state["charged_cart"] == [{"product": "Drill", "identified_by": "barcode", "rating": "verified"}]


def test_low_probability_close_still_hands_off():
    call = Recorder({"choice": CLOSE, "probability": 0.6, "confidence": None})
    assert decider(call).decide(evidence(item(), SOFT)).decision == HAND_OFF


@pytest.mark.parametrize("hard", [
    item(object_id="o3", sku="PEX-002", restricted=True, in_cart=False,
         review_reason="Restricted item: an associate must release it"),
    item(object_id="o3", sku=None, sku_source=None, in_cart=False, review_reason="Barcode is not in the catalog"),
    item(object_id="o3", sku="PEX-002", in_cart=False, review_reason="Barcode disagrees with how the product looks"),
    item(object_id="o3", sku=None, sku_source=None, in_cart=False, crossed_checkout=True,
         review_reason="Product first observed beyond checkout boundary"),
])
def test_hard_reasons_are_never_sent_to_the_model(hard):
    call = Recorder({"choice": CLOSE, "probability": 1.0, "confidence": None})
    made = decider(call).decide(evidence(item(), SOFT, hard))
    assert made.decision == HAND_OFF and made.source == "rules" and not call.states


@pytest.mark.parametrize("error", [urllib.error.URLError("down"), TimeoutError(), ValueError("bad json"), KeyError("answers")])
def test_failures_fall_back_to_the_rules(error):
    made = decider(Recorder(error=error)).decide(evidence(item(), SOFT))
    assert made.decision == HAND_OFF and made.source.startswith("rules (subq unavailable")


def test_no_key_falls_back_to_the_rules(monkeypatch):
    monkeypatch.delenv("SUBQ_API_KEY", raising=False)
    call = Recorder()
    made = ModelDecider("subq", api_key="", names=NAMES, call=call).decide(evidence(item(), SOFT))
    assert made.decision == HAND_OFF and not call.states


def test_systemone_request_and_answer(monkeypatch):
    reply = {"answers": {"checkout": {"type": "choice", "choice": "close", "confidence": 0.8,
                                      "probabilities": {"close": 0.9, "needs_associate": 0.1}}}}
    sent = {}

    def fake_post(url, body, api_key, timeout):
        sent.update(url=url, body=body)
        return reply
    monkeypatch.setattr("vision.decision._post", fake_post)
    answer = call_systemone({"x": 1}, "k", "subq-snap-1.1", "https://api.subq.ai/v1")
    assert answer == {"choice": CLOSE, "probability": 0.9, "confidence": 0.8}
    assert sent["url"] == "https://api.subq.ai/v1/systemone" and sent["body"]["model"] == "subq-snap-1.1"
    assert sent["body"]["state"] == {"x": 1} and set(sent["body"]["questions"]["checkout"]["criteria"]) == {CLOSE, HAND_OFF}


def test_unexpected_answer_is_an_error(monkeypatch):
    monkeypatch.setattr("vision.decision._post", lambda *a: {"answers": {"checkout": {"type": "noul", "noul": 0.5}}})
    with pytest.raises(ValueError):
        call_systemone({}, "k", "m", "u")


def test_rules_decision_matches_the_ledger_flag():
    assert rules_decision(evidence(item(), SOFT)).decision == HAND_OFF
    assert rules_decision(evidence(item(), review=True, in_progress=1)).decision == HAND_OFF


def test_ledger_evidence_reports_the_final_state():
    ledger = PhysicalLedger(["PEX-001", "PEX-002"])
    ledger.reset("run-1")
    probabilities = (0.99, 0.01)
    for frame, y in enumerate([0.9, 0.85, 0.8, 0.75, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]):
        bbox = (300.0, y * 480 - 20, 340.0, y * 480 + 20)
        ledger.update([Observation(1, bbox, 0.9, probabilities)], frame, frame * 0.2, "run-1", (640, 480))
    found = ledger.evidence()
    assert found["review_required"] is False and len(found["items"]) == 1
    assert found["items"][0]["in_cart"] and found["items"][0]["sku"] == "PEX-001"
    assert decision_state(found, NAMES)["charged_cart"][0]["product"] == "Drill"


def test_outcomes_count_a_closed_incomplete_cart_as_wrong():
    right = {"expected_review": False, "exact_cart": True}
    short = {"expected_review": False, "exact_cart": False}
    locked = {"expected_review": True, "exact_cart": True}
    assert outcome(right, CLOSE) == "auto" and outcome(short, CLOSE) == "wrong_close"
    assert outcome(locked, CLOSE) == "wrong_close" and outcome(locked, HAND_OFF) == "handoff"
    counts = tally([right, short, locked], [{"decision": HAND_OFF}] * 3)
    assert counts["precaution"] == 2 and counts["precaution_cart_right"] == 1 and counts["passed"] == 1


def test_model_only_experiment_skips_the_rules_and_the_guard():
    call = Recorder({"choice": CLOSE, "probability": 0.95, "confidence": 0.9})
    hard = item(object_id="o3", sku="PEX-002", restricted=True, in_cart=False,
                review_reason="Restricted item: an associate must release it")
    assert decider(call).decide(evidence(item(), hard)).decision == HAND_OFF and not call.states
    assert decider(call).decide(evidence(item(), hard), model_only=True).decision == CLOSE
    assert decider(call).decide(evidence(item(), review=False), model_only=True).source == "subq"
