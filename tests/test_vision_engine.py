import json

from vision.engine import VisionEngine


def test_missing_checkpoints_are_explicitly_not_ready(tmp_path):
    catalog = tmp_path/"catalog.json"
    catalog.write_text(json.dumps({"products":[{"sku":f"PEX-00{i+1}","class_index":i}
                                              for i in range(5)]}))
    engine = VisionEngine(catalog,tmp_path/"models")
    assert engine.status()["ready"] is False
    assert engine.status()["mode"] == "awaiting_checkpoints"
    assert engine.status()["ground_truth_runtime"] is False
    assert "no simulated predictions" in engine.status()["error"]

