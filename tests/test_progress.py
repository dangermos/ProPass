"""The Training tab's progress endpoint only reads files the pipeline writes."""
import json
import os
import time

from api.progress import progress


def test_empty_project_reports_nothing_started(tmp_path):
    result = progress(tmp_path, 17)
    assert result["export"]["total"] == 0 and not result["export"]["running"]
    assert result["training"]["stages"] == [] and not result["training"]["active"]
    assert [r["expected"] for r in result["recordings"]] == [85, 85]
    assert not any(score["available"] for score in result["scores"])


def test_training_log_is_read_as_stages(tmp_path):
    logs = tmp_path / "artifacts" / "logs"
    logs.mkdir(parents=True)
    (logs / "train-v1.log").write_text('{"architecture": "yolo"}\nUnity synthetic crop splits\n'
                                       "      7/60      2.1G      0.5      0.4\n")
    training = progress(tmp_path, 17)["training"]
    states = [stage["state"] for stage in training["stages"]]
    assert states == ["done", "done", "running", "waiting"] and training["active"]
    assert (training["stages"][2]["epoch"], training["stages"][2]["epochs"]) == (7, 60)


def test_a_stale_log_is_not_shown_as_running(tmp_path):
    logs = tmp_path / "artifacts" / "logs"
    logs.mkdir(parents=True)
    log = logs / "train-v1.log"
    log.write_text("      7/60      2.1G      0.5      0.4\n")
    old = time.time() - 3600
    os.utime(log, (old, old))
    training = progress(tmp_path, 17)["training"]
    assert not training["active"] and training["stages"][0]["state"] == "stopped"


def test_recordings_and_scores_are_counted(tmp_path):
    for seed in range(3):
        run = tmp_path / "artifacts" / "benchmark" / "single" / f"seed_{seed:02d}"
        run.mkdir(parents=True)
        (run / "run.json").write_text("{}")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "benchmark-v2-dev.json").write_text(json.dumps({"summary": {"label": "dev", "passed": 70, "runs": 85}}))
    result = progress(tmp_path, 17)
    assert result["recordings"][0]["recorded"] == 3 and result["recordings"][1]["recorded"] == 0
    assert result["scores"][0]["passed"] == 70 and not result["scores"][1]["available"]


def test_a_score_older_than_the_weights_is_marked_stale(tmp_path):
    (tmp_path / "models").mkdir()
    score = tmp_path / "models" / "benchmark-v2-dev.json"
    score.write_text(json.dumps({"summary": {"label": "dev", "passed": 70, "runs": 85}}))
    old = time.time() - 3600
    os.utime(score, (old, old))
    (tmp_path / "models" / "classifier.pt").write_text("weights")
    assert progress(tmp_path, 17)["scores"][0]["stale"]
