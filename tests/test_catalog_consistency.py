"""The catalog is written in two places (catalog.json for Python, ProPassCatalog.cs for Unity). They must agree."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROW = re.compile(r'new CatalogItem\("(?P<sku>[^"]+)",\s*"[^"]*",\s*"[^"]*",\s*(?P<index>-?\d+),\s*C\((?P<color>[^)]*)\),\s*S\((?P<size>[^)]*)\)(?:,\s*PackageShape\.(?P<shape>\w+))?')


def numbers(text):
    return [float(part.strip().rstrip("f")) for part in text.split(",")]


def unity_items():
    source = (ROOT / "unity/Assets/ProPass/Runtime/ProPassCatalog.cs").read_text()
    return {m["sku"]: m for m in ROW.finditer(source)}


def test_every_catalog_product_has_a_matching_unity_prefab_row():
    products = json.loads((ROOT / "catalog.json").read_text())["products"]
    unity = unity_items()
    assert set(unity) == {p["sku"] for p in products} | {"UNKNOWN"}
    for product in products:
        row = unity[product["sku"]]
        assert int(row["index"]) == product["class_index"], product["sku"]
        assert numbers(row["size"]) == product["size"], product["sku"]
        assert numbers(row["color"]) == product["color"], product["sku"]
        assert (row["shape"] or "Box").lower() == product["shape"], product["sku"]


def test_class_indices_are_unique_and_barcodes_are_invented():
    products = json.loads((ROOT / "catalog.json").read_text())["products"]
    assert sorted(p["class_index"] for p in products) == list(range(len(products)))
    barcodes = [p["barcode"] for p in products if p.get("barcode")]
    assert len(set(barcodes)) == len(barcodes)
    # 99... is this project's made-up range; a real store SKU must never be in the catalog.
    assert all(code.startswith("99") and len(code) == 10 for code in barcodes)
