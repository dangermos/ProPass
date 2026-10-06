"""Class-conditioned cosine rejection with legacy or multi-view prototypes.

These features describe a SKU's appearance distribution, not a unique physical
object. Construction never uses live simulation labels or evaluation footage.
"""
from __future__ import annotations

import torch
from torch.nn import functional as F


def prototype_distance(features, predictions, prototypes, bank=None):
    """Nearest cosine distance inside each predicted class.

    features is N×D, predictions is N, and prototypes may be C×D (legacy) or
    C×K×D. An optional C×K×D bank takes precedence. Without either reference,
    the distance gate is disabled (zero distances). Invalid/zero feature
    vectors fail closed with infinite distances.
    """
    if features.ndim != 2:
        raise ValueError("Features must have shape N×D")
    if predictions.ndim != 1 or len(predictions) != len(features):
        raise ValueError("Predictions must have shape N matching the features")
    if predictions.dtype not in (torch.int8, torch.int16, torch.int32, torch.int64, torch.uint8):
        raise ValueError("Predictions must be integer class indices")
    reference = bank if bank is not None else prototypes
    if reference is None:
        return features.new_zeros(len(features))
    if reference.ndim not in (2, 3) or reference.shape[-1] != features.shape[-1]:
        raise ValueError("Prototypes must have shape C×D or C×K×D matching features")
    if reference.shape[0] == 0 or (reference.ndim == 3 and reference.shape[1] == 0):
        raise ValueError("Prototype classes and cluster banks must be nonempty")
    indices = predictions.to(device=features.device, dtype=torch.long)
    if len(indices) and (int(indices.min()) < 0 or int(indices.max()) >= reference.shape[0]):
        raise ValueError("Predicted class is outside the prototype class range")
    selected = reference.to(device=features.device, dtype=features.dtype)[indices]
    if selected.ndim == 2:
        selected = selected[:, None, :]
    good_features = torch.isfinite(features).all(1) & (features.norm(dim=1) > 0)
    good_prototypes = torch.isfinite(selected).all(2) & (selected.norm(dim=2) > 0)
    normalized = F.normalize(torch.nan_to_num(features), dim=1)
    centers = F.normalize(torch.nan_to_num(selected), dim=2)
    similarities = (normalized[:, None, :] * centers).sum(2)
    similarities = similarities.masked_fill(~good_prototypes, -torch.inf)
    distances = (1 - similarities.max(1).values).clamp(min=0)
    return distances.masked_fill(~good_features, torch.inf)


def cosine_cluster_bank(features, labels, class_count, clusters=8, max_iterations=30):
    """Deterministic spherical k-means, independently within each class.

    Stable input order is required (calibration uses ImageFolder order).
    Construction uses CPU float32. The first center is closest to the class
    mean; later centers are farthest from existing centers. Empty clusters
    retain their preceding center. Classes with fewer than K examples repeat
    an existing center to keep one rectangular C×K×D bank.
    """
    if features.ndim != 2 or len(features) != len(labels) or labels.ndim != 1:
        raise ValueError("Features N×D and labels N must match")
    if class_count < 1 or clusters < 1 or max_iterations < 1:
        raise ValueError("Class count, cluster count and iteration limit must be positive")
    features = features.detach().to(device="cpu", dtype=torch.float32)
    labels = labels.detach().to(device="cpu", dtype=torch.long)
    if not torch.isfinite(features).all() or (features.norm(dim=1) == 0).any():
        raise ValueError("Training features must be finite and nonzero")
    if len(labels) and (int(labels.min()) < 0 or int(labels.max()) >= class_count):
        raise ValueError("Training labels are outside the class range")
    features = F.normalize(features, dim=1)
    banks, details = [], []
    for class_id in range(class_count):
        samples = features[labels == class_id]
        if not len(samples):
            raise ValueError(f"Class {class_id} has no training features")
        active = min(clusters, len(samples))
        mean = F.normalize(samples.mean(0), dim=0)
        first = int((samples @ mean).argmax())
        chosen = [first]
        nearest = samples @ samples[first]
        while len(chosen) < active:
            candidates = nearest.clone()
            candidates[chosen] = torch.inf
            index = int(candidates.argmin())
            chosen.append(index)
            nearest = torch.maximum(nearest, samples @ samples[index])
        centers = samples[chosen].clone()
        previous = None
        iterations = 0
        for _ in range(max_iterations):
            assignments = (samples @ centers.T).argmax(1)
            iterations += 1
            if previous is not None and torch.equal(assignments, previous):
                break
            previous = assignments.clone()
            updated = centers.clone()
            for cluster in range(active):
                members = samples[assignments == cluster]
                if len(members):
                    center = members.mean(0)
                    if center.norm() > 0:
                        updated[cluster] = F.normalize(center, dim=0)
            centers = updated
        if active < clusters:
            centers = torch.cat((centers, centers[:1].repeat(clusters-active, 1)))
        banks.append(centers)
        details.append({"class_index": class_id, "samples": len(samples),
                        "active_clusters": active, "iterations": iterations})
    return torch.stack(banks), details
