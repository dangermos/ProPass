from training.benchmark import iou, match


def test_iou_of_identical_and_disjoint_boxes():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0


def test_matching_is_one_to_one_and_prefers_best_overlap():
    truth = [{"physical_id": "a", "bbox": [0, 0, 10, 10]}, {"physical_id": "b", "bbox": [8, 0, 18, 10]}]
    detections = [{"object_id": "x", "bbox": [7, 0, 17, 10]}, {"object_id": "y", "bbox": [0, 0, 9, 10]}]
    pairs = {t["physical_id"]: d["object_id"] for t, d in match(truth, detections)}
    assert pairs == {"a": "y", "b": "x"}


def test_low_overlap_and_missing_boxes_are_not_matched():
    truth = [{"physical_id": "a", "bbox": [0, 0, 10, 10]}, {"physical_id": "hidden", "bbox": []}]
    assert match(truth, [{"object_id": "x", "bbox": [9, 9, 20, 20]}]) == []
