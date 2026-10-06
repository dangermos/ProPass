# 🏗️ Architecture

ProPass is four small parts with one strict boundary between them: **Unity owns the physical world, and everything after the cameras has to infer it from pixels.** Synchronized lane and overhead views feed one physical ledger and one cart. Fixed camera calibration supplies geometry; live product transforms and labels never enter inference.

```mermaid
flowchart LR
    subgraph SIM["🎮 Simulation · Unity 6.6 URP"]
        direction TB
        S1[Scenario script<br/>spawns + moves products]
        S2[Lane + overhead RGB cameras<br/>one synchronized capture instant]
        S1 --> S2
    end
    subgraph API["⚙️ Backend · FastAPI"]
        direction TB
        A1[Frame ingress + grouping<br/>camera, frame, timing + run checks]
        A2[Bounded capture-group queue<br/>max 2, drop oldest whole group]
        A3[Single inference worker]
        A4[(SQLite / Postgres<br/>sessions, items,<br/>events, receipts)]
        A1 --> A2 --> A3 --> A4
    end
    subgraph VIS["👁️ Vision · PyTorch"]
        direction TB
        V1[YOLO26n per camera<br/>merchandise · person · cart]
        V2[BoT-SORT per camera<br/>camera-local track IDs]
        V3[Shared EfficientNet-B0<br/>SKU + reject]
        V5[Carry-plane homographies<br/>cross-camera fusion]
        V4[One physical ledger<br/>identity, zones, events]
        V1 --> V2 --> V5 --> V4
        V1 --> V3 --> V5
    end
    subgraph WEB["🖥️ Dashboard · React"]
        W0[Title screen<br/>scenario picker]
        W1[Live lane · Decisions ·<br/>Models · Benchmark tabs]
        W2[Cart, review + confirm]
    end
    S2 -- "JPEG + camera_id + shared frame_id/time/run_id" --> A1
    A3 <--> VIS
    A4 -- "WebSocket snapshots" --> WEB
    W2 -- "scenario / prepare / confirm" --> A1
    A1 -. "control poll: scenario, run_id, paused" .-> S1
    SIM -. "offline only: masks + labels" .-> T[🧪 Training + evaluation]

    style SIM fill:#ffe9df,stroke:#ff7a3d,color:#4a1800
    style API fill:#e0fbf6,stroke:#38d6bf,color:#00382f
    style VIS fill:#e6efff,stroke:#6aa8ff,color:#0b2a5c
    style WEB fill:#fff1e0,stroke:#ffbb71,color:#4a2c00
    style T fill:#f1e9ff,stroke:#bd9aff,color:#2c1660
```

| Part | Folder | Owns | Talks to |
|---|---|---|---|
| 🎮 Simulation | `unity/Assets/ProPass` | Scene, products, scripted scenarios, two cameras, dataset/calibration export | API over HTTP (JPEGs out, control polled in) |
| ⚙️ Backend | `api/` | Validation, queueing, run lifecycle, persistence, the confirmation barrier | Vision in-process, dashboard over HTTP and WebSocket |
| 👁️ Vision | `vision/` | Per-camera detection/tracking, shared classification, calibration/fusion, physical identity, zone events | Called once per capture group by the backend worker |
| 🖥️ Dashboard | `web/` | Displaying state, choosing scenarios, review and confirm | Backend only |

How a frame moves through these parts is covered in [pipeline.md](pipeline.md). Vision internals are in [vision.md](vision.md).

Each capture group's images share `(run_id, frame_id, timestamp)` and have distinct `camera_id` values. The backend keeps one pending group and queues it when all configured views arrive. A newer frame, or checkout preparation, flushes an incomplete group with its available images. Missing cameras never borrow an older image. `process_frames` performs one ledger update for the group; per-camera JPEGs and detections remain separate for correctly aligned dashboard overlays.

## 🧠 Key design decisions

| Decision | Why |
|---|---|
| **The detector finds "merchandise", not SKUs** | SKU and identity are separate questions. A two-box test only works if "what is it" stays independent of "which physical box is it". The detector also learns *person* and *cart*, so shoppers, hands and flatbeds stop being mistaken for products. |
| **Lane-aware zones** | Zones are bounded by a lane polygon, so a product carried in the next aisle is tracked but never charged. |
| **Calibrated fusion before one ledger** | Image-box centers project onto a 0.9 m carry plane, giving cameras common `(x, z)` coordinates and physical zone markers. New pairs reject strong SKU disagreement; established pairs require sustained camera-local disagreement before splitting. Weak views cannot dilute a strong view's evidence or position. |
| **Canonical object IDs instead of tracker IDs** | Tracker IDs break whenever something is occluded. The ledger re-attaches fragments using motion, appearance and SKU gates, so the cart counts **physical units**, not detections. |
| **Review both prior units on a conflicting camera join** | A fusion alias change is not proof that two established ledger objects are one product. `conflicting_tracks` identifies those prior units, and the ledger reviews both lane-relevant identities rather than silently hiding one. |
| **The cart changes only on observed zone crossings** | Seeing an item doesn't mean buying it. An item is added only when it's observed moving APPROACH → COMMIT, and removed only when it's observed going back. A lost track never removes anything. |
| **Uncertainty blocks checkout instead of guessing** | Unknown products, ambiguous re-identification, or an item still mid-lane all trigger review. A wrong receipt costs more than a pause. |
| **Bounded queue that drops the oldest whole capture group** | A live demo should stay current without mixing camera images from different instants. The drops and incomplete groups are counted and shown. |
| **One process, one worker** | Inference, sequencing and the simulator session share state under one lock. That's simple and correct for one lane. Scaling out is covered below. |

## 🔄 Physical item lifecycle

```mermaid
stateDiagram-v2
    direction LR
    [*] --> Acquired: RGB detection
    Acquired --> Entering: stable in APPROACH
    Entering --> Tracked: SKU accepted over several views
    Tracked --> Added: observed forward crossing into COMMIT
    Added --> Removed: observed reverse crossing to APPROACH
    Removed --> Added: crosses forward again
    Added --> Purchased: prepared cart version confirmed
    Entering --> Review: disappears unresolved
    Tracked --> Review: ambiguous / unknown at commit
    Review --> Tracked: evidence resolves

    classDef good fill:#d9f7e8,stroke:#2ea043,color:#0b3d1d
    classDef warn fill:#fff1e0,stroke:#ffbb71,color:#4a2c00
    classDef bad fill:#ffe1e5,stroke:#ff8293,color:#5c0a17
    class Added,Purchased good
    class Entering,Tracked warn
    class Review,Removed bad
```

*Purchased* is a receipt-level state that only the backend sets. The vision side exposes entering, tracked, added, removed and the review reason.

## 🛡️ The confirmation barrier

Checking out has to be correct even when frames are still in flight. Here's what happens:

```mermaid
sequenceDiagram
    participant R as Dashboard
    participant A as API
    participant U as Unity
    R->>A: POST /api/cart/prepare
    A->>A: paused = true, status PREPARING
    A->>A: flush last incomplete camera group
    U->>A: next poll sees paused, capture stops
    A->>A: drain accepted groups (up to 30 s, otherwise 202 pending)
    alt any review flag or unresolved SKU
        A-->>R: 409 needs review
    else clean
        A->>A: freeze version + last frame_id, status REVIEWING
        A-->>R: prepared cart
        R->>A: POST /api/cart/confirm {version, idempotency_key}
        A->>A: version, run and review checks, then write receipt
        A-->>R: immutable receipt (same receipt on retry)
    end
```

These rules make it safe:
- New evidence that changes the cart after preparation **invalidates** the prepared version. Confirmation then fails with a 409, and the cart has to be prepared again.
- Uniqueness constraints on `(run_id, event_id)` and `(session_id, object_id)` mean replayed events can't double-count.
- Each cart gets one receipt. Retrying with the same key returns it, and a different key is rejected.
- Resetting the scenario creates a new session and `run_id`. Confirmed receipts are kept.

## 🗄️ Data model

```mermaid
erDiagram
    CHECKOUT_SESSION ||--|| CART : has
    CHECKOUT_SESSION ||--o{ PHYSICAL_ITEM : tracks
    CHECKOUT_SESSION ||--o{ CHECKOUT_EVENT : logs
    CART ||--o| RECEIPT : "confirmed as"
    CHECKOUT_SESSION {
        string id PK
        string run_id UK
        string scenario
        string customer_name
        string status
    }
    CART {
        string id PK
        int version
        string status
        int prepared_version
        int prepared_frame_id
    }
    PHYSICAL_ITEM {
        string object_id "unique per session"
        string sku
        bool active
    }
    CHECKOUT_EVENT {
        string event_id "unique per run"
        string event_type
        string object_id
        float timestamp
    }
    RECEIPT {
        string id PK
        string idempotency_key
        int confirmed_version
        json lines
        float total
    }
```

Cart lines aren't stored. They're computed from the **active physical items** grouped by SKU, so two drill kits are two rows that roll up to quantity 2. The product catalog, vision settings and fixed camera calibration are config files ([catalog.json](../catalog.json), [vision/config.json](../vision/config.json) and [vision/cameras.json](../vision/cameras.json)), not tables. Camera-local tracker IDs and image boxes are evidence; the persisted physical item is keyed by canonical object identity.

SQLite is the default. The same SQLAlchemy schema runs on PostgreSQL:

```bash
docker compose up -d postgres
export PROPASS_DATABASE_URL=postgresql+psycopg://propass:propass_local_demo@127.0.0.1:5433/propass
```

## 📏 Scope and honest limits

| Modeled ✅ | Not modeled yet ⏳ |
|---|---|
| One lane, two cameras, one customer session | Multiple customers, and deciding which person owns which item |
| Five visually distinct fictional products, plus one unknown | Look-alike SKUs and real packaging |
| Brief/prolonged lane-view occlusion, identical units, reverse removal | Arbitrary simultaneous occlusion of both views and reliable identity of completely hidden items |
| A simulated account picker | Real authentication (a QR trip token is planned) and payment |
| Synthetic evaluation | Transfer to a real camera |

**Before any real financial use**, the project would need integer currency, real auth, an adjustment and audit workflow, durable worker recovery and payment integration. The float prices are fine for a demo only.

**Scaling to many lanes** would mean partitioning inference and ordered events by lane/session, synchronizing each lane's camera producers, giving ingress durable offsets, and adding a broker once several producers require it. Each lane still needs one coherent physical ledger. None of that is needed for this local prototype.

**Simulation versus reality.** Synthetic data gives exact labels and rare cases for free. Scene-level splits stop frames from leaking between train and test. But held-out *assets*, stores and real cameras haven't been tested. The next rigorous experiment is synthetic-only vs real-only vs mixed fine-tuning, scored on a held-out real recording. It would report exact-cart rate, false adds and removes, identity switches, review rate and latency.
