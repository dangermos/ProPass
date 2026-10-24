"""Write the measured numbers where people read them, straight from the reports.

    .venv/bin/python scripts/publish_results.py

Reads models/benchmark-dev.json, models/benchmark-test.json and the model manifests, then writes
  web/public/results.json   the numbers the project site shows
  README.md                 from docs/templates/README.tpl.md
so the site and the README cannot drift from the data. Run it after scripts/round.sh test.
"""
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def split(path):
    report = json.loads(path.read_text())
    runs = report["runs"]
    extra = [r for r in runs if not r["passed"] and r["review_required"]]
    reasons = Counter(reason for r in extra for reason in set(r.get("review_reasons", [])))
    scenes = Counter()
    for r in runs:
        scenes[r["scenario"]] += r["passed"]
    barcode = sum(r["sku_sources"].get("barcode", 0) for r in runs)
    charged = sum(sum(r["sku_sources"].values()) for r in runs)
    return {"runs": len(runs), "seeds": report["summary"]["seeds"], "passed": sum(r["passed"] for r in runs),
            "auto": sum(r["passed"] and not r["review_required"] for r in runs),
            "held": sum(r["passed"] and r["review_required"] for r in runs),
            "extra": len(extra), "extra_incomplete": sum(not r["exact_cart"] for r in extra),
            "wrong": sum(not r["exact_cart"] and not r["review_required"] for r in runs),
            "missed": sum(r["missed_items"] for r in runs), "false_adds": sum(r["false_adds"] for r in runs),
            "barcode": barcode, "charged": charged, "scenes": dict(scenes), "top_reasons": reasons.most_common(3)}


def models():
    out = {}
    for camera, path in (("lane", ROOT / "models/manifest.json"), ("overhead", ROOT / "models/overhead/manifest.json")):
        m = json.loads(path.read_text())
        out[camera] = {"map50": round(m["detector"]["test"]["map50"], 3), "map50_95": round(m["detector"]["test"]["map50_95"], 3),
                       "accuracy": round(m["classifier"]["test"]["accuracy"], 3), "crops": m["classifier"]["test"]["total"],
                       "train_scenes": m["detector"].get("train_images")}
    return out


def weak_spots(test):
    """The README's short list of what still fails, from the held-out report."""
    low = min(test["scenes"].values())
    names = [f"**{scene}**" for scene, passed in test["scenes"].items() if passed == low]
    per_scene = len(test["seeds"])
    wrong = ("None of the held-out carts closed with a wrong or missing item" if not test["wrong"]
             else f"{test['wrong']} held-out cart(s) closed with a wrong or missing item")
    return [f"- **Weakest scenes:** {' and '.join(names) if len(names) < 3 else ', '.join(names)} pass {low} of {per_scene} held-out runs"
            f"{' each' if len(names) > 1 else ''}. The reasons per scene are in [docs/benchmark.md](docs/benchmark.md#-why-runs-fail).",
            f"- **Cautious hand-offs:** when the lane isn't sure, it sends the cart to an associate rather than risk a wrong charge. "
            f"{test['extra']} of {test['runs']} held-out carts went to one as a precaution, and {test['extra'] - test['extra_incomplete']} of those were already right.",
            f"- **Wrong charges:** {wrong}, but {test['runs']} runs cannot rule out a small rate. Earlier rounds did close wrong carts: "
            "one held-out lumber cart one board short, and development runs before two bug fixes ([project log](docs/pro-express-v2.md)).",
            "- **Next steps:** fewer precautionary hand-offs, then stacked and hidden packages; see [docs/roadmap.md](docs/roadmap.md)."]


def main():
    dev, test, nets = split(ROOT / "models/benchmark-dev.json"), split(ROOT / "models/benchmark-test.json"), models()
    tests = re.search(r"(\d+) passed", subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "pytest", "-q", "tests"], cwd=ROOT,
                                                       capture_output=True, text=True).stdout)
    catalog = json.loads((ROOT / "catalog.json").read_text())["products"]
    results = {"dev": dev, "test": test, "models": nets, "tests": int(tests.group(1)) if tests else None, "products": len(catalog)}
    (ROOT / "web/public/results.json").write_text(json.dumps(results, indent=1))

    notes = [f"- **{test['auto']} of 85 held-out carts closed with nobody stepping in, and all {test['held']} carts that needed a person were sent to one.**"]
    notes.append(f"- **{'No cart' if not test['wrong'] else str(test['wrong']) + ' cart(s)'} closed with a wrong or missing item**"
                 + (" on the held-out runs." if not test["wrong"] else " on the held-out runs: that is the worst kind of error and it is listed in docs/benchmark.md."))
    notes.append(f"- **{test['extra']} carts went to an associate as a precaution.** When the lane isn't sure, it hands the cart to a person rather than risk a wrong charge. "
                 f"{test['extra'] - test['extra_incomplete']} of them were already right. The other {test['extra_incomplete']} were incomplete or wrong "
                 f"({test['missed']} items the cameras lost, {test["false_adds"]} wrong line{"" if test["false_adds"] == 1 else "s"}), so closing them would have charged the wrong amount. "
                 "Most common reasons: " + "; ".join(f"{reason.lower()} ({count})" for reason, count in test["top_reasons"]) + ".")
    # The optional decision model, scored on development runs only (training/decision_eval.py).
    second = json.loads((ROOT / "models/decision-subq-dev.json").read_text())["summary"]
    alone = json.loads((ROOT / "models/decision-subq-only-dev.json").read_text())["summary"]["with_decision"]
    closed = second["with_decision"]["auto"] - second["rules"]["auto"]
    notes_decision = (f"**An optional second opinion.** A decision model ({second['model']}, SubQ's Decisions API) can review the carts the rules would hand off "
                      "for a soft reason. Locked tools, unknown barcodes and barcode mismatches never reach it, and a failed call keeps the rules' decision. "
                      f"On development runs it closed {closed} of the {second['model_calls']} carts it was asked about "
                      f"({second['rules']['passed']} → {second['with_decision']['passed']} runs passed, "
                      f"{second['with_decision']['wrong_close']} wrong closes). Deciding every cart on its own, without the rules, it passed {alone['passed']}. "
                      "It is off by default and has not been scored on held-out runs. Code: [vision/decision.py](vision/decision.py); "
                      "scoring: [training/decision_eval.py](training/decision_eval.py).")
    fill = {"TESTS": results["tests"], "DECISION_NOTE": notes_decision, "RESULT_NOTES": "\n".join(notes), "WEAK_SPOTS": "\n".join(weak_spots(test)),
            "LANE_MAP": nets["lane"]["map50_95"], "LANE_ACC": f"{nets['lane']['accuracy']:.1%}",
            "OVER_MAP": nets["overhead"]["map50_95"], "OVER_ACC": f"{nets['overhead']['accuracy']:.1%}"}
    for name, s in (("DEV", dev), ("TEST", test)):
        fill.update({f"{name}_PASS": s["passed"], f"{name}_AUTO": s["auto"], f"{name}_HELD": s["held"], f"{name}_EXTRA": s["extra"],
                     f"{name}_WRONG": s["wrong"], f"{name}_MISSED": s["missed"], f"{name}_FALSE": s["false_adds"],
                     f"{name}_BARCODE": f"{s['barcode']} of {s['charged']}"})
    text = (ROOT / "docs/templates/README.tpl.md").read_text()
    for key, value in fill.items():
        text = text.replace(f"@{key}@", str(value))
    left = re.findall(r"@[A-Z_]+@", text)
    if left:
        raise SystemExit(f"Unfilled README fields: {left}")
    (ROOT / "README.md").write_text(text)
    print(json.dumps({k: results[k] for k in ("tests", "products")} | {"dev": dev["passed"], "test": test["passed"], "auto": test["auto"], "wrong": test["wrong"]}))


if __name__ == "__main__":
    main()
