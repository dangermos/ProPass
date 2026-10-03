"""Physical merchandise identity and observed checkout transitions.

This module deliberately has no image/ML dependency. Detector tracker IDs are
observations, never purchase IDs; the canonical ledger owns cart membership.
Unity ground truth is neither an argument nor a runtime data source.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import hypot, sqrt
from typing import Sequence
import uuid


@dataclass(frozen=True)
class Observation:
    track_id: int
    bbox: tuple[float, float, float, float]
    detector_confidence: float
    probabilities: tuple[float, ...]
    embedding: tuple[float, ...] = ()
    quality: float = 1.0
    unknown: bool = False

    @property
    def center(self):
        return ((self.bbox[0] + self.bbox[2]) / 2,
                (self.bbox[1] + self.bbox[3]) / 2)


@dataclass
class LedgerConfig:
    approach_y: float = 0.65
    commit_y: float = 0.40
    hysteresis: float = 0.025
    dwell_seconds: float = 0.12
    evidence_interval: float = 0.12
    minimum_views: int = 3
    evidence_window: int = 8
    sku_threshold: float = 0.85
    sku_margin: float = 0.20
    minimum_quality: float = 0.25
    reattach_seconds: float = 1.8
    reattach_distance: float = 0.15
    reattach_appearance: float = 0.20
    reattach_margin: float = 0.08
    unknown_timeout: float = 0.5
    # Normalized image polygon of the lane at carrying height. Objects whose
    # center is outside it (e.g. a shopper in the next aisle) are tracked but
    # can never become pending, purchased or a reason for review.
    lane_polygon: tuple[tuple[float, float], ...] | None = None
    lane_margin: float = 0.015
    # Longer gaps (a flatbed or shopper hiding an item) may still re-attach to
    # a lost object when the reappearance fits its motion. The position gate
    # widens by occlusion_gate_growth (normalized image units) per extra second.
    occlusion_seconds: float = 6.0
    occlusion_gate_growth: float = 0.05
    # A track that reappears half-hidden may fail the gates on its first frame.
    # For this long after it starts, a young object can still be merged back
    # into the lost object it turns out to be.
    late_merge_seconds: float = 1.5


@dataclass
class PhysicalObject:
    object_id: str
    track_id: int
    bbox: tuple[float, float, float, float]
    first_seen: float
    last_seen: float
    previous_center: tuple[float, float]
    velocity: tuple[float, float] = (0.0, 0.0)
    embedding: tuple[float, ...] = ()
    probabilities: deque = field(default_factory=deque)
    last_evidence: float = -1e9
    sku: str | None = None
    confidence: float = 0.0
    visible: bool = True
    state: str = "TRACKED"
    zone: str = "MIDDLE"
    candidate_zone: str = "MIDDLE"
    candidate_since: float = 0.0
    approach_observed: bool = False
    committed: bool = False
    membership: bool = False
    review_reason: str | None = None
    ambiguous_identity: bool = False
    sequence: int = 0
    # Appearance memory from clear views only, so a crop taken while something
    # slides in front of the box doesn't become the object's identity.
    gallery: deque = field(default_factory=lambda: deque(maxlen=8))
    reference_area: float = 0.0
    last_gallery: float = -1e9
    full_view_seen: bool = False      # ever seen without touching the image border
    accepted_confidence: float | None = None   # averaged SKU probability when the SKU was accepted


def inside_polygon(x: float, y: float, polygon) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def segment_distance(point, start, end, width, height) -> float:
    """Normalized distance from point to the segment start→end."""
    px, py = point[0]/width, point[1]/height
    ax, ay, bx, by = start[0]/width, start[1]/height, end[0]/width, end[1]/height
    dx, dy = bx-ax, by-ay
    length = dx*dx + dy*dy
    u = 0.0 if length == 0 else max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / length))
    return hypot(px-(ax+u*dx), py-(ay+u*dy))


def cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    denom = sqrt(sum(x*x for x in a) * sum(y*y for y in b))
    return 1.0 - sum(x*y for x, y in zip(a, b)) / denom if denom else 1.0


class PhysicalLedger:
    def __init__(self, skus: list[str], config: LedgerConfig | None = None):
        self.skus = skus
        self.config = config or LedgerConfig()
        self.reset("unstarted")

    def reset(self, run_id: str):
        self.run_id = run_id
        self.objects: dict[str, PhysicalObject] = {}
        self.track_to_object: dict[int, str] = {}
        self.last_frame_id = -1
        self.last_timestamp = -1.0
        self.counter = 0
        self._events: list[dict] = []
        self._last_output: dict | None = None

    def _emit(self, obj: PhysicalObject, event_type: str, timestamp: float,
              reason: str | None = None):
        obj.sequence += 1
        identity = f"{self.run_id}:{obj.object_id}:{obj.sequence}:{event_type}"
        event = {"event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, identity)),
                 "object_id": obj.object_id, "sku": obj.sku,
                 "type": event_type, "timestamp": timestamp}
        if reason:
            event["reason"] = reason
        self._events.append(event)

    def _review(self, obj: PhysicalObject, timestamp: float, reason: str):
        if obj.review_reason != reason:
            obj.review_reason = reason
            self._emit(obj, "REVIEW_REQUIRED", timestamp, reason)

    def _zone(self, x: float, y: float, was_outside: bool = False) -> str:
        if self.config.lane_polygon:
            polygon = list(self.config.lane_polygon)
            # Hysteresis: coming back in from outside needs a clear margin, so a box
            # riding the lane edge doesn't flicker in and out.
            margin = self.config.lane_margin if was_outside else 0.0
            if not all(inside_polygon(x + dx, y, polygon) for dx in {-margin, margin}):
                return "OUTSIDE"
        if y >= self.config.approach_y + self.config.hysteresis:
            return "APPROACH"
        if y <= self.config.commit_y - self.config.hysteresis:
            return "COMMIT"
        return "MIDDLE"

    def _match_cost(self, obj: PhysicalObject, obs: Observation, timestamp: float,
                    width: int, height: int) -> float | None:
        gap = timestamp - obj.last_seen
        if not (0 < gap <= self.config.occlusion_seconds):
            return None
        long_gap = gap > self.config.reattach_seconds
        # Extrapolate only a short distance; handheld merchandise is not rigidly
        # moving, and a long motion prediction should not become false evidence.
        horizon = gap if long_gap else min(gap, 0.4)
        predicted = (obj.previous_center[0] + obj.velocity[0] * horizon,
                     obj.previous_center[1] + obj.velocity[1] * horizon)
        # A held object can slow down or stop while hidden, so it may be anywhere
        # between its last observed location and its motion prediction.
        distance = segment_distance(obs.center, obj.previous_center, predicted, width, height)
        appearance = min((cosine_distance(e, obs.embedding) for e, _ in obj.gallery),
                         default=cosine_distance(obj.embedding, obs.embedding))
        gate = self.config.reattach_distance
        if long_gap:
            gate += self.config.occlusion_gate_growth * (gap - self.config.reattach_seconds)
        if distance > gate:
            return None
        if appearance > self.config.reattach_appearance:
            # Something emerging from behind an occluder is often half-visible, so its
            # crop looks different. After a long gap, motion plus "not confidently a
            # different SKU" (checked below) is enough; ties still go to review.
            if not long_gap:
                return None
            appearance = min(appearance, 1.0)
        old_area = max(1.0, obj.gallery[-1][1] if obj.gallery else (obj.bbox[2]-obj.bbox[0])*(obj.bbox[3]-obj.bbox[1]))
        new_area = max(1.0, (obs.bbox[2]-obs.bbox[0])*(obs.bbox[3]-obs.bbox[1]))
        if not 0.45 <= new_area/old_area <= 2.2:
            return None
        if obj.sku and obs.probabilities:
            index = self.skus.index(obj.sku)
            if max(obs.probabilities) >= 0.85 and obs.probabilities[index] < 0.2:
                return None
        return 0.7 * distance + 0.3 * appearance

    def _new(self, obs: Observation, timestamp: float, ambiguous: bool = False):
        self.counter += 1
        obj_id = f"{self.run_id[:8]}-obj-{self.counter:04d}"
        obj = PhysicalObject(obj_id, obs.track_id, obs.bbox, timestamp, timestamp,
                             obs.center, embedding=obs.embedding,
                             ambiguous_identity=ambiguous)
        obj.probabilities = deque(maxlen=self.config.evidence_window)
        self.objects[obj_id] = obj
        self.track_to_object[obs.track_id] = obj_id
        self._emit(obj, "TRACK_CREATED", timestamp)
        if ambiguous:
            self._review(obj, timestamp, "Ambiguous tracker fragmentation: physical identity needs review")
        return obj

    def _recognize(self, obj: PhysicalObject, obs: Observation, timestamp: float):
        if (obs.quality < self.config.minimum_quality or not obs.probabilities or
                timestamp - obj.last_evidence < self.config.evidence_interval):
            return
        if len(obs.probabilities) != len(self.skus):
            raise ValueError("SKU probability vector does not match catalog")
        evidence = (tuple(1.0/len(self.skus) for _ in self.skus)
                    if obs.unknown else obs.probabilities)
        obj.probabilities.append(evidence)
        obj.last_evidence = timestamp
        averaged = [sum(p[i] for p in obj.probabilities)/len(obj.probabilities)
                    for i in range(len(self.skus))]
        ranking = sorted(range(len(averaged)), key=averaged.__getitem__, reverse=True)
        top, second = ranking[0], ranking[1] if len(ranking) > 1 else ranking[0]
        obj.confidence = averaged[top]
        enough = len(obj.probabilities) >= self.config.minimum_views
        confident = (averaged[top] >= self.config.sku_threshold and
                     averaged[top]-averaged[second] >= self.config.sku_margin)
        candidate_sku = self.skus[top]
        if enough and confident:
            if obj.sku is None:
                obj.sku = candidate_sku
                obj.accepted_confidence = averaged[top]
                if not obj.ambiguous_identity:
                    obj.review_reason = None
                self._emit(obj, "SKU_RESOLVED", timestamp)
            elif obj.sku != candidate_sku:
                # Never silently rewrite the SKU of a cart member. A class flip
                # can be caused by an ID switch, so it is an explicit review.
                self._review(obj, timestamp, "Conflicting SKU evidence on the same physical object")

    def _update(self, obj: PhysicalObject, obs: Observation, timestamp: float,
                width: int, height: int):
        dt = timestamp - obj.last_seen
        if dt > 0:
            # Smoothed so a long-gap prediction isn't driven by one noisy frame.
            raw = ((obs.center[0]-obj.previous_center[0])/dt,
                   (obs.center[1]-obj.previous_center[1])/dt)
            obj.velocity = (0.6*obj.velocity[0] + 0.4*raw[0], 0.6*obj.velocity[1] + 0.4*raw[1])
        obj.previous_center = obs.center
        obj.last_seen = timestamp
        obj.visible = True
        obj.track_id = obs.track_id
        obj.bbox = obs.bbox
        if obs.embedding:
            obj.embedding = obs.embedding
        if obs.bbox[0] > 3 and obs.bbox[1] > 3 and obs.bbox[2] < width-3 and obs.bbox[3] < height-3:
            obj.full_view_seen = True
        area = (obs.bbox[2]-obs.bbox[0])*(obs.bbox[3]-obs.bbox[1])
        # Decaying peak area: tolerates shrinking with distance, flags sudden occlusion.
        obj.reference_area = max(area, obj.reference_area*0.97)
        if (obs.embedding and not obs.unknown and obs.quality >= self.config.minimum_quality
                and area >= 0.75*obj.reference_area
                and timestamp - obj.last_gallery >= self.config.evidence_interval):
            obj.gallery.append((obs.embedding, area))
            obj.last_gallery = timestamp
        self._recognize(obj, obs, timestamp)
        observed_zone = self._zone(obs.center[0]/width, obs.center[1]/height, obj.zone == "OUTSIDE")
        if observed_zone != obj.candidate_zone:
            obj.candidate_zone = observed_zone
            obj.candidate_since = timestamp
        if timestamp - obj.candidate_since >= self.config.dwell_seconds:
            obj.zone = observed_zone
            if observed_zone == "APPROACH":
                obj.approach_observed = True
                obj.committed = False
                if obj.membership:
                    obj.membership = False
                    obj.state = "REMOVED"
                    self._emit(obj, "ITEM_REMOVED", timestamp)
                elif obj.state != "REMOVED":
                    obj.state = "ENTERING"
            elif observed_zone == "COMMIT":
                if obj.approach_observed:
                    obj.committed = True
                elif not obj.membership:
                    self._review(obj, timestamp, "Product first observed beyond checkout boundary")
            elif observed_zone == "OUTSIDE":
                if not obj.membership and not obj.approach_observed and obj.state != "REMOVED":
                    obj.state = "OUTSIDE"
            else:
                if not obj.membership and obj.state != "REMOVED":
                    obj.state = "TRACKED"
        if obj.committed and not obj.membership:
            if obj.sku and not obj.review_reason:
                obj.membership = True
                obj.state = "ADDED"
                self._emit(obj, "ITEM_ADDED", timestamp)
            elif timestamp - obj.first_seen >= self.config.unknown_timeout:
                self._review(obj, timestamp, "Checkout crossing lacks accepted SKU evidence")

    def update(self, observations: list[Observation], frame_id: int, timestamp: float,
               run_id: str, image_size: tuple[int, int]) -> dict:
        if run_id != self.run_id:
            raise ValueError("Run ID mismatch: reset must precede a new run")
        if frame_id <= self.last_frame_id:
            # Retries never repeat an event. Returning current state also avoids
            # replacing a newer UI frame with an older frame's evidence.
            if self._last_output:
                return {**self._last_output, "events": [], "duplicate_frame": True}
            raise ValueError("Frame ID must increase")
        if timestamp < self.last_timestamp:
            raise ValueError("Capture timestamps must be monotonic")
        width, height = image_size
        if width <= 0 or height <= 0:
            raise ValueError("Image dimensions must be positive")
        if len({obs.track_id for obs in observations}) != len(observations):
            raise ValueError("A tracker ID may occur only once in a frame")
        self._events = []
        for obj in self.objects.values():
            obj.visible = False
        claimed: set[str] = set()
        assigned: dict[int, PhysicalObject] = {}
        new: list[Observation] = []
        for obs in observations:
            obj_id = self.track_to_object.get(obs.track_id)
            if obj_id and obj_id not in claimed:
                obj = self.objects[obj_id]
                # IDs are only trusted over bounded gaps. ByteTrack is reset per
                # run, but a distant/old reuse must not inherit purchase identity.
                gap = timestamp-obj.last_seen
                if gap <= self.config.reattach_seconds:
                    assigned[obs.track_id] = obj
                    claimed.add(obj_id)
                    continue
                self.track_to_object.pop(obs.track_id, None)
            new.append(obs)
        # Reattach fragments only to LOST objects. Every old object and new
        # observation can participate once; simultaneous identical units cannot
        # be collapsed by a per-SKU deduplication shortcut.
        candidate_map = {}
        for obs in new:
            candidates = []
            for obj_id, obj in self.objects.items():
                if obj_id in claimed:
                    continue
                cost = self._match_cost(obj, obs, timestamp, width, height)
                if cost is not None:
                    candidates.append((cost, obj_id))
            candidate_map[obs.track_id] = sorted(candidates)
        for obs in sorted(new, key=lambda o: candidate_map[o.track_id][0][0]
                          if candidate_map[o.track_id] else 1e9):
            candidates = [(cost, oid) for cost, oid in candidate_map[obs.track_id]
                          if oid not in claimed]
            ambiguous = len(candidates) > 1 and candidates[1][0]-candidates[0][0] < self.config.reattach_margin
            if candidates and not ambiguous:
                obj = self.objects[candidates[0][1]]
                self.track_to_object.pop(obj.track_id, None)
                self.track_to_object[obs.track_id] = obj.object_id
            else:
                obj = self._new(obs, timestamp, ambiguous)
                if ambiguous:
                    for _, oid in candidates:
                        self.objects[oid].ambiguous_identity = True
                        self._review(self.objects[oid], timestamp,
                                     "Multiple lost identical products match a reappearing observation")
            assigned[obs.track_id] = obj
            claimed.add(obj.object_id)
        self._late_merge(observations, assigned, claimed, timestamp, width, height)
        detections = []
        for obs in observations:
            obj = assigned[obs.track_id]
            self._update(obj, obs, timestamp, width, height)
            detections.append(self._serialize(obj) | {"detector_confidence": obs.detector_confidence})
        for obj in self.objects.values():
            lost_for = timestamp - obj.last_seen
            if not obj.visible and not obj.membership and obj.state not in ("REMOVED", "OUTSIDE"):
                if obj.sku is None and not obj.full_view_seen and lost_for > self.config.reattach_seconds:
                    # Only ever seen cut off by the frame edge, then superseded: a fragment.
                    obj.state = "FRAGMENT"
                elif obj.zone == "APPROACH" and obj.bbox[3] >= height-3 and lost_for > 0.5:
                    # Left back out through the entry edge of the frame.
                    obj.state = "LEFT"
            if obj.state in ("FRAGMENT", "LEFT"):
                continue
            if (not obj.visible and obj.committed and obj.sku is None and
                    timestamp-obj.first_seen >= self.config.unknown_timeout):
                self._review(obj, timestamp, "Unresolved product disappeared after a checkout crossing")
            if (not obj.visible and obj.approach_observed and not obj.committed and
                    not obj.membership and obj.state != "REMOVED" and
                    timestamp-obj.last_seen > self.config.occlusion_seconds):
                self._review(obj, timestamp,
                             "Entered merchandise disappeared before an observed checkout or reverse removal")
        # Pending evidence blocks cart preparation even before it is a hard
        # failure. Freezing a partly traversed lane must not omit a known item.
        pending = [obj for obj in self.objects.values()
                   if not obj.membership and obj.state not in ("REMOVED", "OUTSIDE", "LEFT", "FRAGMENT") and
                   (obj.visible or obj.approach_observed)]
        review = bool(pending) or any(obj.review_reason for obj in self.objects.values())
        output = {"frame_id": frame_id, "timestamp": timestamp, "run_id": run_id,
                  "detections": detections,
                  "objects": [self._serialize(obj) for obj in self.objects.values()],
                  "events": self._events.copy(), "review_required": review,
                  "metrics": {"visible_objects": len(observations),
                              "physical_objects": len(self.objects),
                              "cart_units": sum(obj.membership for obj in self.objects.values()),
                              "pending_objects": len(pending),
                              "review_objects": sum(bool(obj.review_reason) for obj in self.objects.values())}}
        self.last_frame_id = frame_id
        self.last_timestamp = timestamp
        self._last_output = output
        return output

    def _late_merge(self, observations, assigned, claimed, timestamp, width, height):
        for obs in observations:
            young = assigned[obs.track_id]
            if (timestamp - young.first_seen > self.config.late_merge_seconds or young.membership
                    or young.committed or young.ambiguous_identity):
                continue
            candidates = sorted(
                (cost, oid) for oid, lost in self.objects.items()
                if oid not in claimed and oid != young.object_id and lost.last_seen < young.first_seen
                for cost in [self._match_cost(lost, obs, timestamp, width, height)] if cost is not None)
            if not candidates or (len(candidates) > 1 and
                                  candidates[1][0] - candidates[0][0] < self.config.reattach_margin):
                continue
            lost = self.objects[candidates[0][1]]
            # The young fragment was the lost object all along: drop it, keep the original identity.
            del self.objects[young.object_id]
            claimed.discard(young.object_id)
            self.track_to_object[obs.track_id] = lost.object_id
            claimed.add(lost.object_id)
            assigned[obs.track_id] = lost

    @staticmethod
    def _serialize(obj: PhysicalObject):
        return {"bbox": list(obj.bbox), "track_id": obj.track_id,
                "object_id": obj.object_id, "sku": obj.sku,
                "confidence": obj.confidence,
                "accepted_confidence": obj.accepted_confidence, "state": obj.state,
                "zone": obj.zone, "visible": obj.visible,
                "membership": obj.membership, "review_reason": obj.review_reason}
