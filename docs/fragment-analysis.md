# 🔎 Nested detector fragments: a conservative boundary

**Current behavior keeps unresolved merchandise evidence visible and requires review.** We do not erase a camera-local object merely because its box overlaps a larger detection. A duplicate crop and a partly exposed second package can look the same in RGB, and silently dropping the latter would undercount a receipt.

## 📏 Development observation

The development trace `artifacts/diagnostics/parked-02-calibrated.json` shows an extra overhead-camera track, ID **11**, alongside established ID **9**. At **11.125 s**:

| Measurement | Value |
|---|---:|
| Intersection ÷ smaller box area | **0.9937** |
| Smaller ÷ larger box area | **0.3622** |
| Intersection over union (IoU) | **0.3591** |
| Detector confidence, smaller / larger | **0.382 / 0.914** |
| Larger track first observed | **10.250 s** |

ID 11 appears in **18 observed frames** from **11.125–13.750 s**. Containment ranges from **0.8547–1.0000**, and its area is **0.3615–0.5368** of ID 9's. Both boxes remain present. The smaller crop is rejected as unknown in **12/18** observations; four later clear observations have SKU probability ≥ **0.85** for the same product as the larger box, at **11.875, 12.125, 12.875 and 13.000 s**.

This explains why ordinary IoU suppression misses the initial nested box: nearly all of the small box lies inside the large one, but the union is much larger. World-mode fusion then represents each box with an equal-size map marker, so the original containment evidence is no longer available to the ledger. In the separate development trace `duplicate-00.json`, no same-camera pair reaches 0.85 containment. That comparison is limited evidence, not a general guarantee about overlapping products.

The raw traces live under git-ignored `artifacts/`; they are not published dataset assets. The reproducible [development trace tool](../training/inspect_run.py) records RGB inference observations and rejects held-out benchmark paths. It does not supply product ground truth to inference. These measurements came from development recordings only; held-out recordings were not inspected or used to choose fragment rules.

## ⚠️ Why containment alone is insufficient

A small second product can be mostly hidden behind a larger one. Two identical units may move together, so matching SKU and motion also fail to prove that they are one physical item. A rejected crop may be a partial view of a known package **or** an actual unknown product. Global NMS thresholds, per-SKU deduplication and unconditional smaller-box suppression all risk losing such evidence.

When two units remain indistinguishable in every camera for the entire observation window, RGB alone cannot determine their count. The defensible result is review or a request for a separating view; a second camera helps only when it exposes independent evidence.

## 🧭 Future extension: temporal quarantine and count evidence

A candidate fragment policy belongs **before cross-camera fusion**, while real image-box sizes and camera-local histories still exist. It should retain a diagnostic record rather than delete detections:

1. Quarantine a newly born, substantially smaller contained track only when the larger track already has clear history and remains simultaneously visible. Existing independently observed tracks are never collapsed by this rule.
2. Retain the candidate's boxes, timestamps, SKU/reject evidence and provisional parent. Require persistent containment and coherent relative motion across several views; a low-confidence birth alone is insufficient.
3. Check the other camera's one-to-one associations for evidence of a distinct second object. Prior independent visibility, conflicting strong SKU evidence or a separate corroborated trajectory vetoes a fragment alias. Unresolved unknown evidence continues to block preparation.
4. Consider an alias only after repeated clear same-SKU evidence and no independent count evidence. Record the decision and its assumptions. If the candidate separates or a second view contradicts the alias, revoke it and require review; do not silently rewrite an existing receipt.

Tests would cover a nested detector artifact, two previously independent overlapping identical units, a newly exposed unknown unit, conflicting SKUs, cross-camera corroboration, candidate separation and reset/drain while a candidate remains unresolved. Thresholds and any new model would be selected on development data, then evaluated once on held-out recordings.

**This extension is not implemented.** The present system preserves conservative review behavior for the ambiguous extra track.
