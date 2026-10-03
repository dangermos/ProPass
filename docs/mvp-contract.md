# ProPass first MVP contract

This is a simulation-only checkout prototype. Product names/prices are fictional demo catalog entries. No payment or external customer system is connected. Unity ground truth is an offline training/evaluation input only. Runtime recognition receives rendered RGB pixels, frame number, capture timestamp, and run ID.

## Components

Unity 6.6 URP simulation → JPEG POST → Python vision engine → physical-object/event engine → persisted demo cart → React dashboard. The API runs on localhost:8000. React uses a proxy or same-origin production assets. SQLite is the immediate persistence default; PostgreSQL is the supported optional deployment target. No infrastructure is required to view a staged replay.

## Stable interfaces

- `GET /api/health`: readiness, vision mode/checkpoint availability, latest frame age.
- `POST /api/frames?frame_id=42&timestamp=2.5&run_id=<uuid>`: raw JPEG (`image/jpeg`). Respond with latest snapshot or compact acknowledgement. Bounded/latest-frame processing must not accumulate an unbounded queue. No ground-truth detections, identities, or SKU labels are accepted.
- `GET /api/snapshot`: complete UI state; `GET /api/frame`: latest JPEG; `WS /api/ws`: snapshot updates.
- `GET /api/simulator/control`: `{scenario, run_id, paused}` polled by Unity. Scenario values: `single`, `duplicate`, `mixed`, `occlusion`, `remove`, `unknown`.
- `POST /api/scenario`: `{scenario}` resets the unconfirmed demo session and returns a new run_id. Confirmed receipts are retained.
- `POST /api/session`: `{customer_name}` binds an explicitly simulated account; returns session/cart. No claims of real QR authentication in this first UI.
- `POST /api/cart/prepare`: pause simulator capture, drain accepted frames, return prepared cart version or pending response; must reject unresolved evidence. `POST /api/cart/confirm`: `{version, idempotency_key}` writes immutable simulated receipt. Returns same receipt on retry, rejects stale version.
- `POST /api/cart/reset`: resets unconfirmed session and generates new run ID; no deletion of confirmed receipt history.

The vision package exposes `VisionEngine(catalog_path, models_dir, config_path=None)`, `process_frame(image_bgr, frame_id, timestamp, run_id) -> dict`, `reset(run_id)`, and `status() -> dict`. Output keys: `frame_id`, `timestamp`, `run_id`, `detections`, `objects`, `events`, `review_required`, `metrics`.

Detection/object fields: `bbox: [x1,y1,x2,y2]` in input pixels, `track_id`, `object_id` (canonical), `sku` (nullable), `confidence`, `state`, `zone`, `visible`. Event fields: stable `event_id`, `object_id`, `sku`, `type` (`TRACK_CREATED`, `SKU_RESOLVED`, `ITEM_ADDED`, `ITEM_REMOVED`, `REVIEW_REQUIRED`), `timestamp`, optional `reason`. Membership changes arise only from ITEM_ADDED/REMOVED and are keyed by canonical object. Persistent track IDs are not SKU IDs.

Default image coordinates: x across the lane, approach at image bottom, commit at image top. Initial boundaries y=0.65 and y=0.40, configurable after camera calibration. Products move from high y to low y; reverse movement removes only after observed return to approach. Lost tracks alone never remove products.

## Catalog

`catalog.json` contains `{products: [...]}` with five entries and 0-based class indices. Each has `sku`, `name`, `price` (USD demo), `class_index`, `color` (RGB visual branding only). Two distinct physical instances of the same SKU must share appearance.

## Verification

Actual learned detection and classification on held-out synthetic scenes, multiplicity and reversible events, duplicate-delivery idempotency, confirmation race tests, and live Unity frame advancement are required. Synthetic success does not establish transfer to real cameras. Legacy SynthDet is a reference; this existing Unity 6 project uses a small custom image/mask label exporter rather than downgrading its Editor.

## Growth

Retain camera/replay adapters and checkpoints/manifests. Next: real phone-video transfer evaluation, QR session binding, tighter calibration, broader SKU set, complementary cameras. Any ambiguity beyond the observed operating conditions is reviewable instead of guessed.
