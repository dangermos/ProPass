"""Score a checkout decision layer against the rules, on recorded evidence.

The evidence comes from one benchmark pass (`training.benchmark --evidence`), so the vision
models run once and each decision model is scored offline from the same final ledger state:

    .venv/bin/python -m training.benchmark --root artifacts/benchmark --label dev \
        --output models/benchmark-dev-decision.json --workers 4 --evidence models/decision-evidence-dev.json
    .venv/bin/python -m training.decision_eval --decision subq

Development runs only. The held-out runs are scored once, by request, and are refused here
unless --allow-held-out is given.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vision.decision import CLOSE, PROVIDERS, ModelDecider, rules_decision

ROOT = Path(__file__).resolve().parents[1]


def outcome(run: dict, decision: str) -> str:
    """auto (closed, right), handoff (correctly sent), precaution (sent, not needed), wrong_close."""
    needed = run["expected_review"] or not run["exact_cart"]
    if decision == CLOSE:
        return "wrong_close" if needed else "auto"
    return "handoff" if run["expected_review"] else "precaution"


def tally(runs: list[dict], decisions: list[dict]) -> dict:
    counts = {"auto": 0, "handoff": 0, "precaution": 0, "precaution_cart_right": 0, "wrong_close": 0}
    for run, decision in zip(runs, decisions, strict=True):
        kind = outcome(run, decision["decision"])
        counts[kind] += 1
        if kind == "precaution" and run["exact_cart"]:
            counts["precaution_cart_right"] += 1
    counts["passed"] = counts["auto"] + sum(1 for run, d in zip(runs, decisions, strict=True)
                                            if outcome(run, d["decision"]) == "handoff" and run["exact_cart"])
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--evidence", type=Path, default=ROOT / "models" / "decision-evidence-dev.json")
    parser.add_argument("--decision", choices=["rules", *PROVIDERS], default="rules")
    parser.add_argument("--threshold", type=float, default=0.8, help="the model's probability needed to close")
    parser.add_argument("--output", type=Path, help="default: models/decision-<decision>-dev.json")
    parser.add_argument("--allow-held-out", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.evidence.read_text())
    if "benchmark-test" in data["recording_root"] and not args.allow_held_out:
        raise SystemExit("These are held-out recordings, which are scored once on request. Use development runs.")
    runs = data["runs"]
    decider = None if args.decision == "rules" else ModelDecider(args.decision, threshold=args.threshold)
    decisions = []
    for run in runs:
        rules = rules_decision(run["evidence"])
        made = decider.decide(run["evidence"]) if decider else rules
        decisions.append(made.as_dict() | {"run_id": run["run_id"], "rules": rules.decision,
                                           "outcome": outcome(run, made.decision), "exact_cart": run["exact_cart"]})
        if made.source != "rules":
            print(f"{decisions[-1]['outcome']:<12} {run['run_id']:<20} {made.source:<10} p={made.probability}  {made.reason[:110]}")
    baseline = tally(runs, [{"decision": d["rules"]} for d in decisions])
    result = tally(runs, decisions)
    fallbacks = sum("unavailable" in d["source"] for d in decisions)
    summary = {"evidence": str(args.evidence), "label": data["label"], "runs": len(runs), "decision": args.decision,
               "threshold": args.threshold, "model": decider.model if decider else None,
               "rules": baseline, "with_decision": result, "fallbacks_to_rules": fallbacks,
               "model_calls": sum(d["source"] == args.decision for d in decisions) if decider else 0}
    output = args.output or ROOT / "models" / f"decision-{args.decision}-dev.json"
    output.write_text(json.dumps({"summary": summary, "decisions": decisions}, indent=1))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
