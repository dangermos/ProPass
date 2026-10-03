"""Camera calibration: image pixels ↔ lane coordinates on the carry-height plane.

vision/cameras.json is exported from Unity (ProPass → Export camera calibration). It holds
only geometry: point pairs between the plane (world x, z in meters) and each camera's image.
A homography per camera places every detection in shared lane coordinates, so zones are
physical lines and two cameras can agree on which box is which.

The ledger keeps working in normalized "frame" coordinates. In world mode that frame is a
top-down map of the lane: u grows with x, v grows toward the entry (like the lane camera,
where the entry is at the bottom of the image).
"""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path

# Extent of the top-down map, in meters. Wide enough for the next aisles and the entry.
X_MIN, X_MAX, Z_MIN, Z_MAX = -5.0, 5.0, -7.0, 7.0
MAP_SIZE = 1000          # the ledger's virtual frame is MAP_SIZE × MAP_SIZE
LANE_MARGIN_M = 0.1      # tolerance added to the lane half-width
ENTRY_EDGE_Z = -4.2      # behind this line an item is at the entry edge of coverage


def to_map(x: float, z: float) -> tuple[float, float]:
    """World meters → normalized map coordinates (u, v)."""
    return (x - X_MIN) / (X_MAX - X_MIN), (Z_MAX - z) / (Z_MAX - Z_MIN)


def from_map(u: float, v: float) -> tuple[float, float]:
    return X_MIN + u * (X_MAX - X_MIN), Z_MAX - v * (Z_MAX - Z_MIN)


@dataclass
class Camera:
    id: str
    width: int
    height: int
    image_to_plane: object          # 3×3 homography, normalized image → world (x, z)
    footprint: list[list[float]]
    position: list[float]

    def to_world(self, x_px: float, y_px: float, width: int, height: int) -> tuple[float, float]:
        import numpy as np
        p = self.image_to_plane @ np.array([x_px / width, y_px / height, 1.0])
        return float(p[0] / p[2]), float(p[1] / p[2])


class Calibration:
    def __init__(self, path):
        import cv2
        import numpy as np
        data = json.loads(Path(path).read_text())
        self.lane = data["lane"]
        self.plane_height = data.get("plane_height", 0.9)
        self.cameras: dict[str, Camera] = {}
        for cam in data["cameras"]:
            pairs = np.array(cam["plane_to_image"], dtype=np.float64)
            homography, _ = cv2.findHomography(pairs[:, 2:4], pairs[:, 0:2])
            self.cameras[cam["id"]] = Camera(cam["id"], cam["width"], cam["height"], homography,
                                             cam["footprint"], cam["position"])

    def ledger_overrides(self) -> dict:
        """Zones and lane outline expressed in map coordinates."""
        half = self.lane["half_width"] + LANE_MARGIN_M
        left, _ = to_map(-half, 0)
        right, _ = to_map(half, 0)
        return {"approach_y": to_map(0, self.lane["approach_z"])[1],
                "commit_y": to_map(0, self.lane["commit_z"])[1],
                "lane_polygon": ((left, 0.0), (right, 0.0), (right, 1.0), (left, 1.0))}

    def describe(self) -> dict:
        """Geometry for the dashboard's coverage map."""
        return {"bounds": {"x": [X_MIN, X_MAX], "z": [Z_MIN, Z_MAX]}, "lane": self.lane,
                "cameras": [{"id": c.id, "position": c.position, "footprint": c.footprint}
                            for c in self.cameras.values()]}
