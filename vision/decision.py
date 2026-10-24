"""Whether a finished cart closes on its own or goes to an associate.

The rules decision is the ledger's own: any review reason or item still in the lane
hands the cart off. Many of those hand-offs are precautionary (a tracking flicker on a
box that is already charged), so an optional decision model can look at the per-item
evidence and close those carts instead.

Two decision models are supported: SubQ, a general LLM with an OpenAI-style chat API
(https://api.subq.ai, key in SUBQ_API_KEY), asked for a JSON verdict; and Jev, TypeSafe's
System One decision model (https://docs.typesafe.ai, key in TYPESAFE_API_KEY), asked one
typed Choice question. Either is off unless asked for, and only ever consulted about soft flags: a locked item, an
unknown product, a barcode that disagrees with the product, or an item that crossed
checkout without a SKU always goes to an associate, whatever the model says. If the call
fails for any reason the rules decision stands.

    python -m training.decision_eval --decision subq      # reads SUBQ_API_KEY from the env or .env
"""
from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

CLOSE, HAND_OFF = "close", "needs_associate"
PROVIDERS = {
    # name: (default base URL, default model, API key variable)
    "subq": ("https://api.subq.ai/v1", "subq-preview", "SUBQ_API_KEY"),
    "jev": ("https://api.typesafe.ai/v1", "jev-latest", "TYPESAFE_API_KEY"),
}
ROOT = Path(__file__).resolve().parents[1]

# Reasons no model may override: what the customer is taking out is not known or not allowed.
HARD_REASONS = (
    "Restricted item: an associate must release it",
    "Barcode is not in the catalog",
    "Barcode disagrees with how the product looks",
    "Barcode disagrees with the product already recorded",
    "Checkout crossing lacks accepted SKU evidence",
    "Unresolved product disappeared after a checkout crossing",
)


@dataclass
class Decision:
    decision: str                      # CLOSE or HAND_OFF
    reason: str
    source: str                        # "rules", the provider's name, or "rules (<provider> unavailable: ...)"
    probability: float | None = None   # the model's probability that the cart can close
    confidence: float | None = None
    flagged: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"decision": self.decision, "reason": self.reason, "source": self.source,
                "probability": self.probability, "confidence": self.confidence, "flagged": self.flagged}


def flagged_items(evidence: dict) -> list[dict]:
    return [item for item in evidence["items"] if item["review_reason"]]


def hard_reasons(evidence: dict) -> list[str]:
    """Why this cart must go to an associate no matter what a decision model says."""
    found = []
    for item in evidence["items"]:
        if item["restricted"]:
            found.append(HARD_REASONS[0])
        if item["review_reason"] in HARD_REASONS:
            found.append(item["review_reason"])
        if item["crossed_checkout"] and not item["sku"] and not item["in_cart"]:
            found.append("Item crossed checkout without being identified")
    return sorted(set(found))


def rules_decision(evidence: dict) -> Decision:
    flags = flagged_items(evidence)
    if not evidence["review_required"] and not flags:
        return Decision(CLOSE, "Every item in the lane is charged", "rules")
    reasons = sorted({item["review_reason"] for item in flags})
    if evidence["in_progress"]:
        reasons.append(f"{evidence['in_progress']} item(s) still in the lane")
    return Decision(HAND_OFF, "; ".join(reasons) or "Review required", "rules", flagged=reasons)


def decision_state(evidence: dict, names: dict[str, str]) -> dict:
    """What the decision model sees: the charged cart and each item that stopped the cart closing.
    Facts are precomputed in plain words so the model doesn't have to infer them."""
    cart = [item for item in evidence["items"] if item["in_cart"]]
    charged = Counter(item["sku"] for item in cart)

    def describe(item: dict) -> dict:
        product = names.get(item["sku"], item["sku"]) if item["sku"] else "not identified"
        return {
            "product": product,
            "identified_by": {"barcode": "barcode label", "visual": "appearance"}.get(item["sku_source"] or "", "nothing"),
            "barcode_reads": item["barcode_reads"],
            "appearance_confidence": item["accepted_confidence"] if item["accepted_confidence"] is not None else item["confidence"],
            "camera_views_used": item["views"],
            "seconds_tracked": item["seen_seconds"],
            "ever_seen_whole": item["seen_whole"],
            "entered_the_lane": item["entered_lane"],
            "crossed_checkout": item["crossed_checkout"],
            "visible_at_end": item["visible_now"],
            "where_last_seen": {"APPROACH": "lane entrance", "MIDDLE": "middle of the lane",
                                "COMMIT": "past checkout", "OUTSIDE": "outside the lane"}.get(item["zone"], item["zone"]),
            "same_product_already_charged": charged.get(item["sku"], 0) if item["sku"] else 0,
            "identity_uncertain": item["ambiguous_identity"],
        }
    pending = [item for item in evidence["items"]
               if not item["in_cart"] and not item["review_reason"] and item["visible_now"] and item["entered_lane"]]
    return {
        "situation": "Self-checkout lane. Cameras track products in a cart as it rolls through; a product is "
                     "charged when it crosses the checkout line. The tracker flagged the items below instead of "
                     "closing the cart. Closing means the customer pays for the charged cart only.",
        "charged_cart": [{"product": names.get(item["sku"], item["sku"]),
                          "identified_by": item["sku_source"], "rating": item["rating"]} for item in cart],
        "flagged_items": [describe(item) | {"flag": item["review_reason"]} for item in flagged_items(evidence)],
        "items_still_in_lane_not_charged": [describe(item) for item in pending],
    }


INSTRUCTIONS = ("Can this cart close with only the charged items, or must an associate check it? "
                "Close only when every flagged item is clearly a tracking artifact.")
CRITERIA = {
    CLOSE: "Every flag is a tracking artifact, not a product leaving uncharged: a second track on a product "
           "that is already charged, a brief or partial sighting, or something that never crossed checkout. "
           "The charged cart is complete.",
    HAND_OFF: "A flagged or uncharged item could be a real product the customer is taking out without "
              "paying, or the charged cart could be wrong. An associate should look.",
}
QUESTION = {"type": "choice", "instructions": INSTRUCTIONS, "criteria": CRITERIA}


def _post(url: str, body: dict, api_key: str, timeout: float) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def call_jev(state: dict, api_key: str, model: str, base_url: str, timeout: float = 15.0) -> dict:
    """One System One request with one Choice question."""
    body = {"model": model, "state": state, "questions": {"checkout": QUESTION}}
    answer = _post(f"{base_url}/systemone", body, api_key, timeout)["answers"]["checkout"]
    if answer.get("type") != "choice" or answer.get("choice") not in (CLOSE, HAND_OFF):
        raise ValueError(f"Unexpected Jev answer: {answer}")
    return {"choice": answer["choice"], "probability": float(answer["probabilities"][CLOSE]),
            "confidence": answer.get("confidence"), "reason": None}


SYSTEM_PROMPT = (
    "You decide whether a self-checkout cart can close or must go to a store associate. "
    f"{INSTRUCTIONS}\n\n"
    f"{CLOSE}: {CRITERIA[CLOSE]}\n{HAND_OFF}: {CRITERIA[HAND_OFF]}\n\n"
    'Reply with JSON only: {"decision": "close" or "needs_associate", '
    '"probability_close": number from 0 to 1, "reason": one short sentence}.')


def call_subq(state: dict, api_key: str, model: str, base_url: str, timeout: float = 30.0) -> dict:
    """One OpenAI-style chat completion asking for a JSON verdict."""
    body = {"model": model, "temperature": 0, "max_tokens": 200,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": json.dumps(state, indent=1)}]}
    text = _post(f"{base_url}/chat/completions", body, api_key, timeout)["choices"][0]["message"]["content"]
    start, end = text.find("{"), text.rfind("}")
    verdict = json.loads(text[start:end + 1])
    if verdict.get("decision") not in (CLOSE, HAND_OFF):
        raise ValueError(f"Unexpected SubQ answer: {text[:200]}")
    probability = float(verdict.get("probability_close", 1.0 if verdict["decision"] == CLOSE else 0.0))
    return {"choice": verdict["decision"], "probability": probability, "confidence": None,
            "reason": str(verdict.get("reason", ""))[:200] or None}


CALLS: dict[str, Callable[..., dict]] = {"jev": call_jev, "subq": call_subq}


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Fill missing environment variables from propass/.env, so keys never go on a command line."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def catalog_names(catalog_path: Path = ROOT / "catalog.json") -> dict[str, str]:
    return {p["sku"]: p["name"] for p in json.loads(Path(catalog_path).read_text())["products"]}


class ModelDecider:
    """Rules first; the decision model only for carts the rules would hand off for soft reasons."""

    def __init__(self, provider: str = "subq", api_key: str | None = None, model: str | None = None,
                 base_url: str | None = None, threshold: float = 0.8, names: dict[str, str] | None = None,
                 call: Callable[..., dict] | None = None):
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown decision provider {provider!r}; use one of {sorted(PROVIDERS)}")
        default_url, default_model, key_name = PROVIDERS[provider]
        load_dotenv()
        prefix = provider.upper()
        self.provider = provider
        self.api_key = api_key if api_key is not None else os.environ.get(key_name)
        self.model = model or os.environ.get(f"{prefix}_MODEL") or default_model
        self.base_url = (base_url or os.environ.get(f"{prefix}_BASE_URL") or default_url).rstrip("/")
        self.threshold, self.call = threshold, call or CALLS[provider]
        self.names = names if names is not None else catalog_names()

    def decide(self, evidence: dict) -> Decision:
        rules = rules_decision(evidence)
        if rules.decision == CLOSE:
            return rules
        hard = hard_reasons(evidence)
        if hard:
            return Decision(HAND_OFF, "; ".join(hard), "rules", flagged=hard)
        if not self.api_key:
            return Decision(HAND_OFF, rules.reason, f"rules ({self.provider} unavailable: no API key)", flagged=rules.flagged)
        try:
            answer = self.call(decision_state(evidence, self.names), self.api_key, self.model, self.base_url)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:   # URLError and timeouts are OSErrors
            return Decision(HAND_OFF, rules.reason, f"rules ({self.provider} unavailable: {type(error).__name__})",
                            flagged=rules.flagged)
        probability, confidence = answer["probability"], answer["confidence"]
        note = f" ({answer['reason']})" if answer.get("reason") else ""
        if answer["choice"] == CLOSE and probability >= self.threshold:
            return Decision(CLOSE, f"{self.provider} judged the flags precautionary{note}: {rules.reason}",
                            self.provider, probability, confidence, rules.flagged)
        return Decision(HAND_OFF, f"{self.provider} kept the hand-off{note}: {rules.reason}",
                        self.provider, probability, confidence, rules.flagged)


def decider_from_config(config: dict) -> ModelDecider | None:
    """None (the rules decide) unless the config sets "decision": {"provider": "subq" or "jev"}."""
    settings = config.get("decision") or {}
    if not settings.get("provider"):
        return None
    return ModelDecider(settings["provider"], model=settings.get("model"), base_url=settings.get("base_url"),
                        threshold=settings.get("close_threshold", 0.8))
