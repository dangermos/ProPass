"""Offline outlier exposure from TRAIN/VAL manifests, never runtime metadata.

The reject class represents the synthetic unenrolled gray package. Training on
this example does not establish general rejection of arbitrary unseen products.
"""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    counts = {}
    for split in ("train","val","test"):
        output = ROOT/"training"/"data"/"crops"/split/"ZZZ-UNKNOWN"
        output.mkdir(parents=True,exist_ok=True)
        count = 0
        for path in sorted((ROOT/"training"/"data"/"manifests"/split).glob("*.json")):
            manifest = json.loads(path.read_text())
            image_path = ROOT/"training"/"data"/"detection"/"images"/split/(path.stem+".jpg")
            for index,obj in enumerate(manifest["objects"]):
                if obj["sku"]!="UNKNOWN":
                    continue
                with Image.open(image_path) as image:
                    image.crop(obj["bbox"]).save(output/f"{path.stem}_{index}.jpg",quality=95)
                count += 1
        counts[split] = count
    print(json.dumps(counts))


if __name__=="__main__":
    main()
