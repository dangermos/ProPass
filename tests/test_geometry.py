"""Calibration contracts at the exported carry-height plane; no model loading."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from vision.geometry import Calibration, Camera, from_map, to_map


CALIBRATION_PATH = Path(__file__).parents[1] / "vision" / "cameras.json"


@pytest.fixture
def calibration():
    return Calibration(CALIBRATION_PATH)


@pytest.mark.parametrize("x,z", [(-5, -7), (5, 7), (0, 0), (-1.6, -2), (1.6, 1.6)])
def test_world_map_round_trip_preserves_meters_and_forward_direction(x, z):
    assert from_map(*to_map(x, z)) == pytest.approx((x, z))
    assert to_map(x, z + 0.1)[1] < to_map(x, z)[1]


def test_exported_camera_point_pairs_project_to_the_carry_height_plane(calibration):
    exported = json.loads(CALIBRATION_PATH.read_text())
    assert calibration.plane_height == pytest.approx(0.9)
    assert set(calibration.cameras) == {"lane", "overhead"}
    for camera_data in exported["cameras"]:
        camera = calibration.cameras[camera_data["id"]]
        for x, z, u, v in camera_data["plane_to_image"]:
            assert camera.to_world(u * camera.width, v * camera.height,
                                   camera.width, camera.height) == pytest.approx((x, z), abs=2e-4)


@pytest.mark.parametrize("camera_id", ["lane", "overhead"])
@pytest.mark.parametrize("x,z", [(-1.2, -2.25), (0, 0), (1.2, 2.25)])
def test_camera_homography_round_trip_is_resolution_independent(calibration, camera_id, x, z):
    camera = calibration.cameras[camera_id]
    projected = np.linalg.inv(camera.image_to_plane) @ np.array([x, z, 1.0])
    u, v = projected[:2] / projected[2]
    assert camera.to_world(u * 1920, v * 1080, 1920, 1080) == pytest.approx((x, z))
    assert camera.to_world(u * 320, v * 180, 320, 180) == pytest.approx((x, z))


def test_overhead_image_right_is_world_forward_and_image_down_is_world_right(calibration):
    overhead = calibration.cameras["overhead"]
    x, z = overhead.to_world(480, 270, 960, 540)
    assert (x, z) == pytest.approx((0, 0), abs=1e-4)
    assert overhead.to_world(580, 270, 960, 540)[1] > z
    assert overhead.to_world(480, 370, 960, 540)[0] > x


def test_lane_zones_are_physical_lines_on_the_map(calibration):
    overrides = calibration.ledger_overrides()
    assert from_map(0.5, overrides["approach_y"])[1] == pytest.approx(-2)
    assert from_map(0.5, overrides["commit_y"])[1] == pytest.approx(1.6)
    polygon = overrides["lane_polygon"]
    assert from_map(polygon[0][0], 0.5)[0] == pytest.approx(-1.7)
    assert from_map(polygon[1][0], 0.5)[0] == pytest.approx(1.7)


def write_calibration(tmp_path, change):
    data = deepcopy(json.loads(CALIBRATION_PATH.read_text()))
    change(data)
    path = tmp_path / "cameras.json"
    path.write_text(json.dumps(data))
    return path


def test_duplicate_camera_ids_do_not_silently_overwrite_calibration(tmp_path):
    path = write_calibration(tmp_path, lambda data: data["cameras"].append(deepcopy(data["cameras"][0])))
    with pytest.raises(ValueError, match="Duplicate.*camera ID"):
        Calibration(path)


@pytest.mark.parametrize("dimension", ["width", "height"])
def test_invalid_calibration_resolution_is_rejected(tmp_path, dimension):
    path = write_calibration(tmp_path, lambda data: data["cameras"][0].update({dimension: 0}))
    with pytest.raises(ValueError, match="dimensions must be positive"):
        Calibration(path)


def test_nonfinite_calibration_resolution_is_rejected(tmp_path):
    path = write_calibration(tmp_path, lambda data: data["cameras"][0].update({"width": float("inf")}))
    with pytest.raises(ValueError, match="dimensions must be finite"):
        Calibration(path)


def test_insufficient_point_pairs_are_rejected(tmp_path):
    path = write_calibration(tmp_path, lambda data: data["cameras"][0].update(
        {"plane_to_image": data["cameras"][0]["plane_to_image"][:3]}))
    with pytest.raises(ValueError, match="at least four"):
        Calibration(path)


def test_collinear_calibration_is_rejected(tmp_path):
    path = write_calibration(tmp_path, lambda data: data["cameras"][0].update(
        {"plane_to_image": [[i, 0, i / 10, 0.5] for i in range(4)]}))
    with pytest.raises(ValueError, match="degenerate|cannot define"):
        Calibration(path)


def test_nonfinite_point_pairs_are_rejected(tmp_path):
    def corrupt(data):
        data["cameras"][0]["plane_to_image"][0][2] = float("nan")
    with pytest.raises(ValueError, match="must be finite"):
        Calibration(write_calibration(tmp_path, corrupt))


def test_empty_camera_calibration_is_rejected(tmp_path):
    path = write_calibration(tmp_path, lambda data: data.update({"cameras": []}))
    with pytest.raises(ValueError, match="at least one camera"):
        Calibration(path)


@pytest.mark.parametrize("width,height", [(0, 540), (960, 0), (-1, 540)])
def test_projecting_with_invalid_frame_dimensions_is_rejected(calibration, width, height):
    with pytest.raises(ValueError, match="dimensions must be positive"):
        calibration.cameras["lane"].to_world(100, 100, width, height)


def test_horizon_points_fail_explicitly_instead_of_creating_infinite_tracks():
    camera = Camera("test", 100, 100, np.array([[1, 0, 0], [0, 1, 0], [1, 0, -0.5]]), [], [])
    with pytest.raises(ValueError, match="cannot project"):
        camera.to_world(50, 30, 100, 100)


def test_nonfinite_image_coordinates_are_rejected(calibration):
    with pytest.raises(ValueError, match="must be finite"):
        calibration.cameras["lane"].to_world(float("nan"), 100, 960, 540)
