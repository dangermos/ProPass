"""Turn the catalog and the owner-supplied product folder into Unity textures.

    .venv/bin/python scripts/prepare_products.py

For every catalog product this writes, into unity/Assets/ProPass/Products/ (git-ignored):
  <sku>_barcode.png   a crisp Code 128 label encoding "SKU=<barcode>"
  <sku>_photo.png     the product photo, when Barcodes/<barcode>.png (or .jpg) exists

A barcode image supplied in Barcodes/ is decoded and re-drawn at high resolution, so the
label on the box carries exactly the supplied content. Products without a supplied barcode
get one generated from the catalog. Then rebuild the scene: ProPass → Build checkout scene.
"""
import json
from pathlib import Path

import zxingcpp
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SUPPLIED = ROOT / "Barcodes"
OUTPUT = ROOT / "unity" / "Assets" / "ProPass" / "Products"


def payload(product):
    """What the label encodes: the supplied image's own content, else SKU=<catalog barcode>."""
    for suffix in (".gif", ".png", ".jpg"):
        path = SUPPLIED / f"{product['barcode']}_barcode{suffix}"
        path = path if path.exists() else SUPPLIED / f"{product['barcode']}{suffix}"
        if path.exists():
            read = zxingcpp.read_barcodes(Image.open(path).convert("L"))
            if read:
                return read[0].text
    return f"SKU={product['barcode']}"


def label(text):
    """A white shelf-tag style label: bars with a quiet zone, and the text underneath."""
    bars = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.Code128).to_image(scale=6)
    bars = Image.fromarray(bars).convert("L")
    bars = bars.resize((bars.width, 220), Image.Resampling.NEAREST)
    canvas = Image.new("L", (bars.width + 120, 330), 255)
    canvas.paste(bars, (60, 30))
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
    except OSError:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(canvas)
    width = draw.textlength(text, font=font)
    draw.text(((canvas.width - width) / 2, 262), text, fill=0, font=font)
    return canvas.convert("RGB")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for product in json.loads((ROOT / "catalog.json").read_text())["products"]:
        text = payload(product)
        label(text).save(OUTPUT / f"{product['sku']}_barcode.png")
        photo = next((SUPPLIED / f"{product['barcode']}{s}" for s in (".png", ".jpg", ".jpeg")
                      if (SUPPLIED / f"{product['barcode']}{s}").exists()), None)
        target = OUTPUT / f"{product['sku']}_photo.png"
        if photo:
            Image.open(photo).convert("RGB").save(target)
        elif target.exists():
            target.unlink()
        print(f"{product['sku']}: label {text!r}, photo {'yes' if photo else 'no (placeholder art)'}")
    # The unenrolled gray package carries a barcode that is not in the catalog.
    label("SKU=0000000000").save(OUTPUT / "UNKNOWN_barcode.png")


if __name__ == "__main__":
    main()
