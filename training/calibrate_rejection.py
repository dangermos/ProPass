"""Build train-only SKU appearance banks; calibrate on known validation crops.

EfficientNet weights and class predictions stay frozen. No test crop or benchmark
recording is opened. Previous checkpoints and reports remain recoverable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserve(directory, names):
    directory.mkdir(exist_ok=True)
    for name in names:
        source = ROOT / "models" / name
        destination = directory / name
        if source.exists() and not destination.exists():
            shutil.copy2(source, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clusters", type=int, default=8)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    import torch
    from torch import nn
    from torch.utils.data import DataLoader
    from torchvision.datasets import ImageFolder
    from torchvision.models import efficientnet_b0
    from vision.rejection import cosine_cluster_bank, prototype_distance
    from vision.transforms import classifier_transform

    started = time.perf_counter()
    torch.manual_seed(42)
    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)
    device = ("cuda:0" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    checkpoint_path = ROOT / "models/classifier.pt"
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    source_hash = digest(checkpoint_path)
    backup_names = ("classifier.pt", "manifest.json", "rejection-calibration.json")
    preserve(ROOT / "models/v3-original", backup_names)
    preserve(ROOT / "models/v3-calibrated-mean", backup_names)

    labels = checkpoint.get("class_labels", checkpoint["skus"])
    network = efficientnet_b0(weights=None)
    network.classifier[1] = nn.Linear(network.classifier[1].in_features, len(labels))
    network.load_state_dict(checkpoint["state_dict"])
    network.to(device).eval()
    for parameter in network.parameters():
        parameter.requires_grad = False
    temperature = float(checkpoint.get("temperature", 1.0))
    datasets = {split: ImageFolder(ROOT / "training/data/crops" / split,
                                 transform=classifier_transform(False))
                for split in ("train", "val")}
    if any(dataset.classes != labels for dataset in datasets.values()):
        raise ValueError("Training/validation class order must match the classifier")

    def extract(split):
        features, targets, predicted = [], [], []
        with torch.inference_mode():
            for images, target in DataLoader(datasets[split], batch_size=args.batch,
                                            shuffle=False, num_workers=0):
                pooled = network.avgpool(network.features(images.to(device))).flatten(1)
                features.append(nn.functional.normalize(pooled, dim=1).cpu())
                targets.append(target)
                predicted.append((network.classifier(pooled)/temperature).argmax(1).cpu())
        print(json.dumps({"stage": split, "samples": len(datasets[split]), "device": device}), flush=True)
        return torch.cat(features), torch.cat(targets), torch.cat(predicted)

    training_features, training_labels, _ = extract("train")
    bank, clusters = cosine_cluster_bank(training_features, training_labels, len(labels),
                                         args.clusters, args.iterations)
    features, target, predicted = extract("val")
    known = target < len(checkpoint["skus"])
    old_prototypes = checkpoint.get("prototypes")
    old_bank = checkpoint.get("prototype_bank")
    old_threshold = float(checkpoint["max_prototype_distance"])
    before = prototype_distance(features, target, old_prototypes, old_bank)
    after = prototype_distance(features, target, old_prototypes, bank)
    quantile = float(torch.quantile(after[known], .99))
    threshold = min(.95, max(.08, quantile+.05))
    runtime_before = prototype_distance(features, predicted, old_prototypes, old_bank)
    runtime_after = prototype_distance(features, predicted, old_prototypes, bank)
    unknown_head = predicted >= len(checkpoint["skus"])
    per_class = []
    for index, label in enumerate(labels):
        mask = target == index
        per_class.append({"class": label, "samples": int(mask.sum()),
                          "distance_q99_before": float(torch.quantile(before[mask], .99)),
                          "distance_q99_after": float(torch.quantile(after[mask], .99)),
                          "distance_rejections_before": int((before[mask]>old_threshold).sum()),
                          "distance_rejections_after": int((after[mask]>threshold).sum()),
                          "head_correct": int((predicted[mask]==target[mask]).sum())})

    # Retain legacy means as a stable reference for older reports/checkpoints.
    checkpoint["prototype_bank"] = bank
    checkpoint["max_prototype_distance"] = threshold
    checkpoint["rejection_calibration"] = {
        "method": "class-conditioned spherical k-means feature bank", "training_split": "train",
        "calibration_split": "val", "known_quantile": .99, "margin": .05,
        "known_samples": int(known.sum()), "clusters_per_class": args.clusters,
        "quantile_uses": "labeled class distance for known validation crops"}
    temporary = checkpoint_path.with_suffix(".calibrated.pt")
    torch.save(checkpoint, temporary)
    temporary.replace(checkpoint_path)
    new_hash = digest(checkpoint_path)
    report = {
        "method": "class-conditioned spherical k-means feature bank", "source_sha256": source_hash,
        "sha256": new_hash, "bank_sha256": hashlib.sha256(bank.contiguous().numpy().tobytes()).hexdigest(),
        "split": "training bank; known validation threshold", "training_samples": len(training_labels),
        "training_split": "training/data/crops/train", "calibration_split": "training/data/crops/val",
        "prototype_bank_shape": list(bank.shape), "clusters_per_class": args.clusters,
        "clustering_max_iterations": args.iterations, "clustering": clusters,
        "initialization": "stable class-mean first center, then farthest cosine centers; no randomness",
        "source_threshold": old_threshold, "threshold": threshold, "known_distance_q99": quantile,
        "quantile": .99, "margin": .05, "quantile_uses": "known labeled-class validation distances",
        "known_samples": int(known.sum()),
        "known_distance_rejections_before": int((before[known]>old_threshold).sum()),
        "known_distance_rejections_after": int((after[known]>threshold).sum()),
        "known_runtime_distance_rejections_before": int((runtime_before[known]>old_threshold).sum()),
        "known_runtime_distance_rejections_after": int((runtime_after[known]>threshold).sum()),
        "known_runtime_head_or_distance_rejections_before": int((unknown_head[known]|(runtime_before[known]>old_threshold)).sum()),
        "known_runtime_head_or_distance_rejections_after": int((unknown_head[known]|(runtime_after[known]>threshold)).sum()),
        "known_head_correct": int((predicted[known]==target[known]).sum()),
        "unknown_samples": int((~known).sum()),
        "unknown_head_rejections": int(unknown_head[~known].sum()),
        "unknown_head_or_distance_rejections_after": int((unknown_head[~known]|(runtime_after[~known]>threshold)).sum()),
        "per_class": per_class, "benchmark_or_test_used": False,
        "classifier_weights_changed": False, "temperature_changed": False,
        "confidence_or_sku_vote_thresholds_changed": False, "device": device,
        "seconds": round(time.perf_counter()-started, 3),
        "backups": ["models/v3-original", "models/v3-calibrated-mean"],
        "limitations": "Unknown validation covers one synthetic gray package family only; real-camera transfer unmeasured"}
    (ROOT / "models/rejection-calibration.json").write_text(json.dumps(report, indent=2)+"\n")
    manifest_path = ROOT / "models/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    classifier = manifest["classifier"]
    for name in ("test_accepted", "test_accepted_correct"):
        if name in classifier:
            classifier[f"initial_threshold_{name}"] = classifier.pop(name)
    classifier.update(sha256=new_hash, maximum_prototype_distance=threshold,
                      prototype_bank_shape=list(bank.shape), rejection_calibration=report)
    manifest_path.write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
