"""Draw the printed packaging for every catalog product as Unity textures.

    .venv/bin/python scripts/prepare_products.py

All brands and products are invented, so everything here is generated and nothing is copied
from a real package. For each product in catalog.json this writes, into
unity/Assets/ProPass/Products/:
  <sku>_photo.png     the printed front panel: brand, product name, a simple icon, a pattern
  <sku>_top.png       the printed top, which is what the gate camera mostly sees
  <sku>_barcode.png   a crisp Code 128 label encoding "SKU=<barcode>"
Lumber has no packaging. Then rebuild the scene: ProPass → Build checkout scene.
"""
import json
import math
from pathlib import Path

import zxingcpp
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "unity" / "Assets" / "ProPass" / "Products"
PX = 1400       # pixels per meter of package face


def font(size, bold=True):
    for name in ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f"/usr/share/fonts/truetype/{'dejavu' if 'DejaVu' in name else 'liberation'}/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def rgb(color, scale=1.0):
    return tuple(max(0, min(255, int(c * 255 * scale))) for c in color)


def fit(draw, text, width, start):
    """The largest font, at most `start` pixels, that fits `text` in `width`."""
    size = start
    while size > 12 and draw.textlength(text, font=font(size)) > width:
        size -= 2
    return font(size)


def pattern(draw, kind, box, color):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    step = max(18, w // 14)
    if kind == "diagonal":
        for x in range(x0 - h, x1, step * 2):
            draw.polygon([(x, y1), (x + step, y1), (x + step + h, y0), (x + h, y0)], fill=color)
    elif kind == "band":
        draw.rectangle((x0, y0 + h * .55, x1, y0 + h * .8), fill=color)
    elif kind == "ticks":
        for i, x in enumerate(range(x0, x1, step)):
            draw.rectangle((x, y1 - (h * .5 if i % 5 == 0 else h * .25), x + step * .18, y1), fill=color)
    elif kind == "dots":
        for row, y in enumerate(range(y0 + step // 2, y1, step)):
            for x in range(x0 + (step // 2 if row % 2 else 0), x1, step):
                draw.ellipse((x - step * .2, y - step * .2, x + step * .2, y + step * .2), fill=color)
    elif kind == "chevron":
        for y in range(y0, y1 + step, step * 2):
            for x in range(x0, x1, step * 2):
                draw.polygon([(x, y), (x + step, y - step), (x + step * 2, y), (x + step * 2, y + step * .5),
                              (x + step, y - step * .5), (x, y + step * .5)], fill=color)
    elif kind == "hazard":
        for x in range(x0 - h, x1, step * 3):
            draw.polygon([(x, y1), (x + step * 1.5, y1), (x + step * 1.5 + h * .3, y1 - h * .3), (x + h * .3, y1 - h * .3)], fill=color)
    elif kind == "wave":
        for y in range(y0 + step, y1, step * 2):
            points = [(x, y + math.sin(x / step * 1.3) * step * .5) for x in range(x0, x1 + 8, 8)]
            draw.line(points, fill=color, width=max(6, step // 4))
    elif kind == "rays":
        cx, cy = x0 + w * .5, y0 + h * .45
        for k in range(16):
            a0, a1 = k * math.pi / 8, k * math.pi / 8 + math.pi / 22
            draw.polygon([(cx, cy), (cx + math.cos(a0) * w, cy + math.sin(a0) * w), (cx + math.cos(a1) * w, cy + math.sin(a1) * w)], fill=color)
    elif kind == "blocks":
        for row, y in enumerate(range(y0, y1, step)):
            for x in range(x0 - (step if row % 2 else 0), x1, step * 2):
                draw.rectangle((x + 3, y + 3, x + step * 2 - 3, y + step - 3), outline=color, width=max(3, step // 10))


def icon(draw, kind, cx, cy, r, color, ground):
    """A plain geometric emblem. It says what family the product is in, nothing more."""
    def ring(scale, fill):
        draw.ellipse((cx - r * scale, cy - r * scale, cx + r * scale, cy + r * scale), fill=fill)
    if kind in ("ring", "blade", "sun"):
        if kind != "ring":
            for k in range(12 if kind == "blade" else 8):
                a = k * 2 * math.pi / (12 if kind == "blade" else 8)
                b = a + (.28 if kind == "blade" else .2)
                draw.polygon([(cx + math.cos(a) * r * .7, cy + math.sin(a) * r * .7), (cx + math.cos((a + b) / 2) * r * 1.05, cy + math.sin((a + b) / 2) * r * 1.05),
                              (cx + math.cos(b) * r * .7, cy + math.sin(b) * r * .7)], fill=color)
        ring(.78, color); ring(.42, ground); ring(.14, color)
    elif kind == "drill":
        draw.rounded_rectangle((cx - r, cy - r * .5, cx + r * .35, cy), r * .12, fill=color)
        draw.rectangle((cx + r * .35, cy - r * .33, cx + r, cy - r * .17), fill=color)
        draw.polygon([(cx - r * .7, cy), (cx - r * .25, cy), (cx - r * .4, cy + r * .8), (cx - r * .85, cy + r * .8)], fill=color)
    elif kind == "bolt":
        draw.polygon([(cx + r * .1, cy - r), (cx - r * .55, cy + r * .1), (cx - r * .05, cy + r * .1), (cx - r * .2, cy + r),
                      (cx + r * .55, cy - r * .15), (cx + r * .05, cy - r * .15)], fill=color)
    elif kind == "screw":
        draw.rectangle((cx - r * .6, cy - r, cx + r * .6, cy - r * .7), fill=color)
        draw.polygon([(cx - r * .22, cy - r * .7), (cx + r * .22, cy - r * .7), (cx, cy + r)], fill=color)
        for k in range(4):
            y = cy - r * .5 + k * r * .32
            draw.line((cx - r * .32, y, cx + r * .32, y + r * .14), fill=ground, width=max(4, int(r * .07)))
    elif kind == "hand":
        draw.rounded_rectangle((cx - r * .55, cy - r * .1, cx + r * .55, cy + r), r * .2, fill=color)
        for k in range(4):
            x = cx - r * .55 + k * r * .29
            draw.rounded_rectangle((x, cy - r * (.95 if k in (1, 2) else .75), x + r * .24, cy + r * .1), r * .1, fill=color)
    elif kind == "hammer":
        draw.rectangle((cx - r * .9, cy - r * .9, cx + r * .5, cy - r * .4), fill=color)
        draw.rectangle((cx - r * .15, cy - r * .4, cx + r * .1, cy + r), fill=color)
    elif kind == "drop":
        draw.polygon([(cx, cy - r), (cx - r * .62, cy + r * .2), (cx + r * .62, cy + r * .2)], fill=color)
        draw.ellipse((cx - r * .65, cy - r * .3, cx + r * .65, cy + r), fill=color)
    elif kind == "trowel":
        draw.polygon([(cx - r, cy + r * .1), (cx + r * .3, cy - r * .7), (cx + r * .3, cy + r * .9)], fill=color)
        draw.rectangle((cx + r * .3, cy - r * .05, cx + r, cy + r * .25), fill=color)
    elif kind == "block":
        for dx, dy in ((-1, -.9), (0, -.9), (-.5, -.25), (.5, -.25), (-1, .4), (0, .4)):
            draw.rectangle((cx + dx * r * .9 + 4, cy + dy * r + 4, cx + (dx + 1) * r * .9 - 4, cy + (dy + .6) * r - 4), fill=color)
    elif kind == "tube":
        draw.rounded_rectangle((cx - r * .3, cy - r * .35, cx + r * .3, cy + r), r * .12, fill=color)
        draw.polygon([(cx - r * .14, cy - r * .35), (cx + r * .14, cy - r * .35), (cx + r * .04, cy - r), (cx - r * .04, cy - r)], fill=color)
    elif kind == "shield":
        draw.polygon([(cx - r * .8, cy - r * .8), (cx + r * .8, cy - r * .8), (cx + r * .8, cy + r * .1), (cx, cy + r), (cx - r * .8, cy + r * .1)], fill=color)
        draw.line((cx - r * .35, cy, cx - r * .05, cy + r * .3, cx + r * .4, cy - r * .35), fill=ground, width=max(8, int(r * .16)))


def panel(product, width_m, height_m, top=False):
    """One printed face. The front carries everything; the top repeats brand, name and pattern, larger."""
    w, h = max(64, int(width_m * PX)), max(64, int(height_m * PX))
    base, accent = rgb(product["color"]), rgb(product["accent"])
    dark = sum(product["color"]) < 1.4
    ink = (250, 250, 248) if dark else (16, 18, 22)
    image = Image.new("RGB", (w, h), base)
    draw = ImageDraw.Draw(image)
    pattern(draw, product["pattern"], (0, int(h * (.0 if top else .5)), w, h), rgb(product["color"], 1.25 if dark else .82))
    # Brand bar across the top edge.
    bar = int(h * (.24 if top else .2))
    draw.rectangle((0, 0, w, bar), fill=accent)
    bar_ink = (16, 18, 22) if sum(product["accent"]) > 1.6 else (250, 250, 248)
    brand = fit(draw, product["brand"], w * .86, int(bar * .62))
    draw.text((w * .06, bar * .5), product["brand"], font=brand, fill=bar_ink, anchor="lm")
    if top:
        name = fit(draw, product["label"], w * .9, int(h * .26))
        draw.text((w * .5, bar + (h - bar) * .5), product["label"], font=name, fill=ink, anchor="mm", stroke_width=max(2, h // 90), stroke_fill=base)
        return image
    if w < 560:
        # A narrow face (a pail, a tall box): name on top, emblem underneath.
        name = fit(draw, product["label"], w * .88, int(h * .1))
        draw.text((w * .5, bar + (h - bar) * .16), product["label"], font=name, fill=ink, anchor="mm")
        icon(draw, product["icon"], w * .5, bar + (h - bar) * .58, min(w * .3, (h - bar) * .26), accent if accent != base else ink, base)
        draw.rectangle((0, h - max(6, h // 40), w, h), fill=accent)
        return image
    radius = min(w * .2, h * .22)
    icon(draw, product["icon"], w * .76, bar + (h - bar) * .36, radius, accent if accent != base else ink, base)
    name = fit(draw, product["label"], w * .56, int(h * .13))
    draw.text((w * .06, bar + (h - bar) * .22), product["label"], font=name, fill=ink, anchor="lm")
    small = font(max(14, int(h * .05)), bold=False)
    draw.text((w * .06, bar + (h - bar) * .42), product["name"], font=fit(draw, product["name"], w * .56, max(14, int(h * .055))), fill=ink, anchor="lm")
    draw.text((w * .06, bar + (h - bar) * .56), "Demo product · not for sale", font=small, fill=ink, anchor="lm")
    draw.rectangle((0, h - max(6, h // 40), w, h), fill=accent)
    return image


def barcode_label(text):
    """A white shelf-tag style label: bars with a quiet zone, and the text underneath."""
    bars = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.Code128).to_image(scale=6)
    bars = Image.fromarray(bars).convert("L")
    bars = bars.resize((bars.width, 220), Image.Resampling.NEAREST)
    canvas = Image.new("L", (bars.width + 120, 330), 255)
    canvas.paste(bars, (60, 30))
    draw = ImageDraw.Draw(canvas)
    letters = font(42)
    draw.text(((canvas.width - draw.textlength(text, font=letters)) / 2, 262), text, fill=0, font=letters)
    return canvas.convert("RGB")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT.glob("*.png"):
        old.unlink()
    for product in json.loads((ROOT / "catalog.json").read_text())["products"]:
        if product["shape"] == "board":
            print(f"{product['sku']}: lumber, no packaging")
            continue
        width, height, depth = product["size"]
        drum = product["shape"] == "drum"
        # These proportions mirror ProPassSceneBuilder.Product.
        face = width * (.62 if drum else .94)
        label_height = min(face, .34) * 330 / 1110
        panel(product, face, height * .96 - label_height - .014).save(OUTPUT / f"{product['sku']}_photo.png")
        panel(product, width * (.7 if drum else .94), depth * (.7 if drum else .94), top=True).save(OUTPUT / f"{product['sku']}_top.png")
        barcode_label(f"SKU={product['barcode']}").save(OUTPUT / f"{product['sku']}_barcode.png")
        print(f"{product['sku']}: {product['brand']} {product['label']}")
    # The unenrolled gray package carries a barcode that is not in the catalog, and no print.
    barcode_label("SKU=0000000000").save(OUTPUT / "UNKNOWN_barcode.png")


if __name__ == "__main__":
    main()
