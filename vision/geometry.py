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
from math import isfinite
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
        if width <= 0 or height <= 0:
            raise ValueError("Image dimensions must be positive")
        if not all(isfinite(value) for value in (x_px, y_px, width, height)):
            raise ValueError("Image coordinates and dimensions must be finite")
        p = self.image_to_plane @ np.array([x_px / width, y_px / height, 1.0])
        if not np.isfinite(p).all() or abs(p[2]) < 1e-12:
            raise ValueError(f"Camera {self.id!r} cannot project this image point onto the carry plane")
        return float(p[0] / p[2]), float(p[1] / p[2])


class Calibration:
    def __init__(self, path):
        import cv2
        import numpy as np
        data = json.loads(Path(path).read_text())
        self.lane = data["lane"]
        self.plane_height = data.get("plane_height", 0.9)
        if not isfinite(self.plane_height):
            raise ValueError("Calibration plane_height must be finite")
        self.cameras: dict[str, Camera] = {}
        for cam in data["cameras"]:
            camera_id = cam["id"]
            if camera_id in self.cameras:
                raise ValueError(f"Duplicate calibration camera ID: {camera_id!r}")
            if not all(isfinite(cam[field]) for field in ("width", "height")):
                raise ValueError(f"Camera {camera_id!r} dimensions must be finite")
            if cam["width"] <= 0 or cam["height"] <= 0:
                raise ValueError(f"Camera {camera_id!r} dimensions must be positive")
            pairs = np.array(cam["plane_to_image"], dtype=np.float64)
            if pairs.ndim != 2 or pairs.shape[1] != 4 or pairs.shape[0] < 4:
                raise ValueError(f"Camera {camera_id!r} requires at least four [x, z, u, v] calibration pairs")
            if not np.isfinite(pairs).all():
                raise ValueError(f"Camera {camera_id!r} calibration pairs must be finite")
            try:
                homography, _ = cv2.findHomography(pairs[:, 2:4], pairs[:, 0:2])
            except cv2.error as exc:
                raise ValueError(f"Camera {camera_id!r} calibration cannot define a homography") from exc
            if (homography is None or not np.isfinite(homography).all()
                    or np.linalg.matrix_rank(homography) != 3):
                raise ValueError(f"Camera {camera_id!r} calibration is degenerate")
            self.cameras[camera_id] = Camera(camera_id, cam["width"], cam["height"], homography,
                                             cam["footprint"], cam["position"])
        if not self.cameras:
            raise ValueError("Calibration must include at least one camera")

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
