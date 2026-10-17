"""Reproducible transfer-learning entrypoints; simulation GT is offline only.

Run from propass/: .venv/bin/python -m training.train detector
Then: .venv/bin/python -m training.train classifier
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR",str(ROOT/"training"/".ultralytics"))
os.environ.setdefault("TORCH_HOME",str(ROOT/"models"/"pretrained"))


# Each camera has its own model pair. The lane camera's lives in models/, any other
# camera's in models/<camera>/, which is where the engine looks for it.
MODEL_DIR = ROOT/"models"
CAMERA = None


def use_camera(camera):
    global MODEL_DIR, CAMERA
    CAMERA = camera
    MODEL_DIR = ROOT/"models" if camera in (None, "lane") else ROOT/"models"/camera
    MODEL_DIR.mkdir(parents=True, exist_ok=True)


def scenes(split):
    """Scene names rendered from the selected camera, or None for every scene."""
    if CAMERA is None:
        return None
    return {path.stem for path in (ROOT/"training"/"data"/"manifests"/split).glob("*.json")
            if json.loads(path.read_text()).get("camera", "lane") == CAMERA}


def manifest_update(key, data):
    path = MODEL_DIR/"manifest.json"
    existing = json.loads(path.read_text()) if path.exists() else {}
    existing[key] = data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


DETECTOR_CLASSES = ["merchandise", "person", "cart"]


def detector(args):
    from ultralytics import YOLO
    data_root = ROOT/"training"/"data"/"detection"
    data_root.mkdir(parents=True, exist_ok=True)
    yaml_path = data_root/"dataset.yaml"
    # Class order must match ProPassDatasetExporter.ClassNames; the engine tracks class 0 only.
    names = "".join(f"  {i}: {n}\n" for i, n in enumerate(DETECTOR_CLASSES))
    splits = {}
    for split in ("train", "val", "test"):
        wanted = scenes(split)
        if wanted is None:
            splits[split] = f"images/{split}"
        else:
            # A list file restricts the split to one camera's scenes; labels are found beside the images.
            listing = data_root/f"{split}-{CAMERA}.txt"
            listing.write_text("".join(f"{data_root}/images/{split}/{stem}.jpg\n" for stem in sorted(wanted)))
            splits[split] = listing.name
    yaml_path = data_root/(f"dataset-{CAMERA}.yaml" if CAMERA else "dataset.yaml")
    yaml_path.write_text(f"path: {data_root}\ntrain: {splits['train']}\nval: {splits['val']}\ntest: {splits['test']}\nnames:\n{names}")
    started = time.time()
    pretrained = ROOT/"models"/"pretrained"/"yolo26n.pt"
    pretrained.parent.mkdir(parents=True,exist_ok=True)
    model = YOLO(str(pretrained))
    model.train(data=str(yaml_path), epochs=args.epochs, imgsz=args.imgsz,
                batch=args.batch, device=args.device, workers=2,
                project=str(ROOT/"training"/"runs"), name="merchandise",
                exist_ok=True, optimizer="AdamW", lr0=0.001, lrf=0.05,
                weight_decay=0.0005, warmup_epochs=2, patience=10,
                seed=42, deterministic=True, amp=True,
                degrees=8, translate=0.08, scale=0.2, fliplr=0.0,
                flipud=0.0, mosaic=0.15, close_mosaic=5,
                hsv_h=0.008, hsv_s=0.2, hsv_v=0.2,
                plots=True, verbose=False)
    best = ROOT/"training"/"runs"/"merchandise"/"weights"/"best.pt"
    destination = MODEL_DIR/"detector.pt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, destination)
    evaluation = YOLO(str(destination)).val(data=str(yaml_path), split="test",
        imgsz=args.imgsz, batch=args.batch, device=args.device,
        project=str(ROOT/"training"/"runs"), name="detector-test", exist_ok=True)
    report = {"checkpoint": "YOLO26n COCO pretrained", "architecture": "merchandise + person + cart (occluder-aware)",
              "seconds": time.time()-started, "sha256": digest(destination),
              "epochs_requested": args.epochs, "batch": args.batch,
              "image_size": args.imgsz, "device": args.device,
              "classes": DETECTOR_CLASSES,
              "test": {"map50": float(evaluation.box.map50),
                       "map50_95": float(evaluation.box.map),
                       "precision": float(evaluation.box.mp),
                       "recall": float(evaluation.box.mr)},
              "dataset": "Unity synthetic scene splits; no real-camera transfer claim",
              "train_images": len(list((data_root/"images"/"train").glob("*"))),
              "val_images": len(list((data_root/"images"/"val").glob("*"))),
              "test_images": len(list((data_root/"images"/"test").glob("*")))}
    manifest_update("detector", report)
    print(json.dumps(report, indent=2), flush=True)


def classifier(args):
    import torch
    from torch import nn
    from torch.utils.data import DataLoader
    from torchvision.datasets import ImageFolder
    from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0

    from vision.transforms import classifier_transform
    torch.manual_seed(42)
    torch.set_num_threads(4)
    device = torch.device(args.device)
    started = time.time()
    root = ROOT/"training"/"data"/"crops"
    def crops(split, training):
        dataset = ImageFolder(root/split, transform=classifier_transform(training))
        wanted = scenes(split)
        if wanted is not None:
            # Crop files are named <scene>_<index>.jpg; keep the selected camera's scenes.
            dataset.samples = [s for s in dataset.samples if Path(s[0]).stem.rsplit("_", 1)[0] in wanted]
            dataset.imgs, dataset.targets = dataset.samples, [target for _, target in dataset.samples]
        return dataset
    data = {split: crops(split, split=="train") for split in ("train", "val", "test")}
    skus = [p["sku"] for p in sorted(json.loads((ROOT/"catalog.json").read_text())["products"],
                                    key=lambda p: p["class_index"])]
    class_labels = skus+["ZZZ-UNKNOWN"] if (root/"train"/"ZZZ-UNKNOWN").exists() else skus
    if data["train"].classes != class_labels or any(d.classes != class_labels for d in data.values()):
        raise ValueError(f"Crop folders must exactly match class order {class_labels}")
    loaders = {split: DataLoader(dataset, batch_size=args.batch,
                                 shuffle=split=="train", num_workers=2,
                                 pin_memory=device.type=="cuda") for split,dataset in data.items()}
    network = efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1)
    network.classifier[1] = nn.Linear(network.classifier[1].in_features, len(class_labels))
    network.to(device)
    for parameter in network.features.parameters():
        parameter.requires_grad = False
    optimizer = torch.optim.AdamW(network.classifier.parameters(), lr=0.001, weight_decay=0.0001)
    scaler = torch.amp.GradScaler(device.type, enabled=device.type=="cuda")
    counts = torch.bincount(torch.tensor(data["train"].targets),minlength=len(class_labels)).float()
    class_weights = (counts.mean()/counts.clamp_min(1)).sqrt().clamp(0.5,3.0).to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.02,weight=class_weights)
    best_accuracy = -1.0
    best_state = None
    history = []

    def evaluate(loader, collect=False):
        network.eval()
        correct, total, losses = 0, 0, 0.0
        logits_all, labels_all, embeddings_all = [], [], []
        with torch.inference_mode():
            for images, labels in loader:
                images, labels = images.to(device), labels.to(device)
                features = network.avgpool(network.features(images)).flatten(1)
                logits = network.classifier(features)
                correct += int((logits.argmax(1)==labels).sum())
                total += len(labels)
                losses += float(criterion(logits,labels))*len(labels)
                if collect:
                    logits_all.append(logits.cpu())
                    labels_all.append(labels.cpu())
                    embeddings_all.append(nn.functional.normalize(features,dim=1).cpu())
        metrics = {"correct": correct, "total": total, "accuracy": correct/max(total,1),
                   "loss": losses/max(total,1)}
        if collect:
            return metrics, torch.cat(logits_all), torch.cat(labels_all), torch.cat(embeddings_all)
        return metrics

    for epoch in range(args.epochs):
        if epoch == args.head_epochs:
            # Fine-tune the last two feature stages, keeping earlier ImageNet
            # representations and BatchNorm running statistics stable.
            for stage in list(network.features.children())[-2:]:
                for parameter in stage.parameters():
                    parameter.requires_grad = True
            optimizer = torch.optim.AdamW([
                {"params": [p for p in network.features.parameters() if p.requires_grad], "lr":0.0001},
                {"params": network.classifier.parameters(), "lr":0.0003}], weight_decay=0.0001)
        network.train()
        for module in network.modules():
            if isinstance(module, nn.BatchNorm2d):
                module.eval()
        if epoch < args.head_epochs:
            network.features.eval()
        total_loss, count = 0.0, 0
        for images, labels in loaders["train"]:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device.type, enabled=device.type=="cuda"):
                logits = network(images)
                loss = criterion(logits, labels)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total_loss += float(loss.detach())*len(labels)
            count += len(labels)
        val = evaluate(loaders["val"])
        record = {"epoch":epoch+1, "train_loss":total_loss/count, "val":val}
        history.append(record)
        print(json.dumps(record), flush=True)
        if val["accuracy"] > best_accuracy or (val["accuracy"] == best_accuracy and
           (best_state is None or val["loss"] < min(h["val"]["loss"] for h in history[:-1]))):
            best_accuracy = val["accuracy"]
            best_state = {k:v.detach().cpu().clone() for k,v in network.state_dict().items()}
    network.load_state_dict(best_state)
    val_metrics, val_logits, val_labels, val_embeddings = evaluate(loaders["val"], True)
    # Temperature calibration uses validation logits only, never the holdout.
    temperature_parameter = torch.tensor(0.0, requires_grad=True)
    temp_optimizer = torch.optim.LBFGS([temperature_parameter], lr=0.1, max_iter=40)
    def closure():
        temp_optimizer.zero_grad()
        loss = nn.functional.cross_entropy(val_logits/temperature_parameter.exp().clamp(0.5,5), val_labels)
        loss.backward()
        return loss
    temp_optimizer.step(closure)
    temperature = float(temperature_parameter.exp().clamp(0.5,5).detach())
    # Train-only feature prototypes provide a second rejection signal. They are
    # class appearance summaries, explicitly not unique physical-object IDs.
    prototype_data = crops("train", False)
    prototype_loader = DataLoader(prototype_data,batch_size=args.batch,num_workers=2)
    _,_,train_labels,train_embeddings = evaluate(prototype_loader, True)
    prototypes = torch.stack([nn.functional.normalize(train_embeddings[train_labels==i].mean(0),dim=0)
                              for i in range(len(class_labels))])
    val_distance = 1-(val_embeddings*prototypes[val_labels]).sum(1)
    # The two camera views make each SKU's feature distribution multimodal.
    # A fixed 0.45 cap over-rejects valid views; calibrate from known validation
    # examples instead, independently of the explicit unknown classifier head.
    known_distance = val_distance[val_labels < len(skus)]
    max_distance = min(0.95,max(0.08,float(torch.quantile(known_distance,0.99))+0.05))
    test_metrics,test_logits,test_labels,test_embeddings = evaluate(loaders["test"],True)
    confusion = torch.zeros(len(class_labels),len(class_labels),dtype=torch.int64)
    for label,pred in zip(test_labels,test_logits.argmax(1), strict=False):
        confusion[label,pred] += 1
    probabilities = (test_logits/temperature).softmax(1)
    test_distance = 1-(test_embeddings*prototypes[probabilities.argmax(1)]).sum(1)
    max_prob = probabilities.max(1).values
    margins = probabilities.topk(2,dim=1).values
    accepted = ((max_prob>=0.85)&(margins[:,0]-margins[:,1]>=0.2)&
                (test_distance<=max_distance)&(probabilities.argmax(1)<len(skus)))
    destination = MODEL_DIR/"classifier.pt"
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary = destination.with_suffix(".tmp.pt")
    torch.save({"state_dict":best_state, "skus":skus, "class_labels":class_labels,"temperature":temperature,
                "prototypes":prototypes, "max_prototype_distance":max_distance,
                "architecture":"efficientnet_b0", "training_seed":42},temporary)
    temporary.replace(destination)
    report = {"checkpoint":"torchvision EfficientNet_B0_Weights.IMAGENET1K_V1",
              "seconds":time.time()-started,"sha256":digest(destination),
              "epochs":args.epochs,"head_epochs":args.head_epochs,"batch":args.batch,
              "device":args.device,"crop_size":224,"temperature":temperature,
              "maximum_prototype_distance":max_distance,
              "dataset_sizes":{split:len(d) for split,d in data.items()},
              "val":val_metrics,"test":test_metrics,"test_confusion":confusion.tolist(),
              "class_labels":class_labels,
              "test_accepted":int(accepted.sum()),
              "test_accepted_correct":int(((probabilities.argmax(1)==test_labels)&accepted).sum()),
              "unknown_rejection":"Training-set outlier exposure (unenrolled gray package), validation-calibrated feature distance and confidence; broader unknown performance unverified",
              "history":history,"dataset":"Unity synthetic crop splits; no real-camera transfer claim"}
    manifest_update("classifier",report)
    print(json.dumps(report,indent=2),flush=True)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command",required=True)
    detect = commands.add_parser("detector")
    detect.add_argument("--epochs",type=int,default=35)
    detect.add_argument("--batch",type=int,default=8)
    detect.add_argument("--imgsz",type=int,default=640)
    detect.add_argument("--device",default="0")
    detect.add_argument("--camera",help="train on one camera's scenes and save to that camera's model folder")
    classify = commands.add_parser("classifier")
    classify.add_argument("--epochs",type=int,default=12)
    classify.add_argument("--head-epochs",type=int,default=4)
    classify.add_argument("--batch",type=int,default=32)
    classify.add_argument("--device",default="cuda:0")
    classify.add_argument("--camera",help="train on one camera's scenes and save to that camera's model folder")
    args = parser.parse_args()
    use_camera(args.camera)
    detector(args) if args.command=="detector" else classifier(args)


if __name__ == "__main__":
    main()
