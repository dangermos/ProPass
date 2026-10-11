"""Barcode decoding and attaching reads to tracked boxes (no GPU models involved)."""
import numpy as np
import pytest
import zxingcpp

from vision import geometry
from vision.engine import VisionEngine
from vision.ledger import Observation


class FlatCamera:
    """A stand-in calibration: image pixels map straight to meters on the lane map."""
    position = [0.0, 2.3, 1.9]

    def to_world(self, x, y, width, height):
        return x / width * 4 - 2, y / height * 4 - 2


@pytest.fixture
def engine():
    result = VisionEngine.__new__(VisionEngine)
    result.fuse_radius = 0.45
    result.barcode_to_sku = {"1015765383": "PEX-002"}
    result.calibration = type("Calibration", (), {"cameras": {"scan": FlatCamera()}})()
    return result


def frame_with(text):
    bars = np.array(zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.Code128).to_image(scale=3))
    bars = np.repeat(bars, 30, axis=0)[:120]
    image = np.full((400, 1200, 3), 255, np.uint8)
    image[140:140 + bars.shape[0], 200:200 + bars.shape[1]] = bars[:, :, None]
    return image


def at(track, x, z):
    u, v = geometry.to_map(x, z)
    cx, cy = u * geometry.MAP_SIZE, v * geometry.MAP_SIZE
    return Observation(track, (cx - 20, cy - 20, cx + 20, cy + 20), 0.9, (0.2,) * 5)


def test_store_label_is_decoded_and_mapped_to_its_catalog_sku(engine):
    found = engine._read_barcodes({"scan": frame_with("SKU=1015765383")})
    assert [(b["text"], b["sku"], b["camera"]) for b in found] == [("SKU=1015765383", "PEX-002", "scan")]
    assert len(found[0]["corners"]) == 4


def test_label_not_in_the_catalog_is_reported_as_unlisted(engine):
    found = engine._read_barcodes({"scan": frame_with("SKU=0000000000")})
    assert found[0]["sku"] == "unlisted:0000000000"


def test_text_that_is_not_a_store_label_is_ignored(engine):
    assert engine._read_barcodes({"scan": frame_with("HELLO-12345")}) == []


def test_a_read_goes_to_the_nearest_tracked_box_only(engine):
    read = {"sku": "PEX-002", "world": (0.5, 1.0), "track_id": None}
    near, far = at(1, 0.45, 1.3), at(2, -0.6, 1.0)
    attached = engine._attach_barcodes([far, near], [read])
    assert [o.barcode for o in attached] == [None, "PEX-002"]
    assert read["track_id"] == 1


def test_a_cart_label_goes_to_the_box_behind_it_not_the_neighbor_it_lands_on(engine):
    # Measured on the flat cart: the back box's label projects 0.34 m toward the scan camera,
    # 0.10 m from the middle box's center.
    read = {"sku": "PEX-005", "camera": "scan", "world": (0.0, 0.43), "track_id": None}
    middle, back = at(3, 0.0, 0.53), at(2, 0.0, 0.09)
    attached = engine._attach_barcodes([middle, back], [read])
    assert [o.barcode for o in attached] == [None, "PEX-005"]
    assert read["track_id"] == 2


def test_a_read_with_no_box_nearby_is_not_attached(engine):
    attached = engine._attach_barcodes([at(1, 1.4, -3.0)], [{"sku": "PEX-002", "world": (0.0, 1.0), "track_id": None}])
    assert attached[0].barcode is None
