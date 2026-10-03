# 🏗️ Architecture

ProPass is four small parts with one strict boundary between them: **Unity owns the physical world, and everything after the camera has to infer it from pixels.**

```mermaid
flowchart LR
    subgraph SIM["🎮 Simulation · Unity 6.6 URP"]
        direction TB
        S1[Scenario script<br/>spawns + moves products]
        S2[RGB checkout camera]
        S1 --> S2
    end
    subgraph API["⚙️ Backend · FastAPI"]
        direction TB
        A1[Frame ingress<br/>validation + run check]
        A2[Bounded queue<br/>max 2, drop oldest]
        A3[Single inference worker]
        A4[(SQLite / Postgres<br/>sessions, items,<br/>events, receipts)]
        A1 --> A2 --> A3 --> A4
    end
    subgraph VIS["👁️ Vision · PyTorch"]
        direction TB
        V1[YOLO26n detector<br/>class: merchandise]
        V2[ByteTrack<br/>short-lived track IDs]
        V3[EfficientNet-B0<br/>SKU + reject]
        V4[Physical ledger<br/>identity, zones, events]
        V1 --> V2 --> V4
        V1 --> V3 --> V4
    end
    subgraph WEB["🖥️ Dashboard · React"]
        W1[Camera canvas + overlays]
        W2[Cart, events, scenarios,<br/>review + confirm]
    end
    S2 -- "JPEG + frame_id/time/run_id" --> A1
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
| 🎮 Simulation | `unity/Assets/ProPass` | Scene, products, scripted scenarios, camera, dataset export | API over HTTP (frames out, control polled in) |
| ⚙️ Backend | `api/` | Validation, queueing, run lifecycle, persistence, the confirmation barrier | Vision in-process, dashboard over HTTP and WebSocket |
| 👁️ Vision | `vision/` | Detection, classification, tracking, physical identity, zone events | Called by the backend worker only |
| 🖥️ Dashboard | `web/` | Displaying state, choosing scenarios, review and confirm | Backend only |

How a frame moves through these parts is covered in [pipeline.md](pipeline.md). Vision internals are in [vision.md](vision.md).

## 🧠 Key design decisions

| Decision | Why |
|---|---|
| **The detector learns one class, "merchandise"** | SKU and identity are separate questions. A two-box test only works if "what is it" stays independent of "which physical box is it". |
| **Canonical object IDs instead of tracker IDs** | ByteTrack IDs break whenever something is occluded. The ledger re-attaches fragments using motion, appearance and SKU gates, so the cart counts **physical units**, not detections. |
| **The cart changes only on observed zone crossings** | Seeing an item doesn't mean buying it. An item is added only when it's observed moving APPROACH → COMMIT, and removed only when it's observed going back. A lost track never removes anything. |
| **Uncertainty blocks checkout instead of guessing** | Unknown products, ambiguous re-identification, or an item still mid-lane all trigger review. A wrong receipt costs more than a pause. |
| **Bounded queue that drops the oldest frame** | A live demo should stay current. The drops are counted and shown. |
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
    U->>A: next poll sees paused, capture stops
    A->>A: drain queue (wait up to 30 s, otherwise 202 pending)
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

Cart lines aren't stored. They're computed from the **active physical items** grouped by SKU, so two drill kits are two rows that roll up to quantity 2. The product catalog and camera thresholds are config files ([catalog.json](../catalog.json) and [vision/config.json](../vision/config.json)), not tables.

SQLite is the default. The same SQLAlchemy schema runs on PostgreSQL:

```bash
docker compose up -d postgres
export PROPASS_DATABASE_URL=postgresql+psycopg://propass:propass_local_demo@127.0.0.1:5433/propass
```

## 📏 Scope and honest limits

| Modeled ✅ | Not modeled yet ⏳ |
|---|---|
| One lane, one camera, one customer | Multiple customers, and deciding which person owns which item |
| Five visually distinct fictional products, plus one unknown | Look-alike SKUs and real packaging |
| Brief occlusion, identical units, reverse removal | Long full occlusion, stacked or hidden items |
| A simulated account picker | Real authentication (a QR trip token is planned) and payment |
| Synthetic evaluation | Transfer to a real camera |

**Before any real financial use**, the project would need integer currency, real auth, an adjustment and audit workflow, durable worker recovery and payment integration. The float prices are fine for a demo only.

**Scaling to many lanes** would mean partitioning inference and ordered events by camera, giving ingress durable offsets, and adding a broker only once there are several producers. None of that is needed for one lane.

**Simulation versus reality.** Synthetic data gives exact labels and rare cases for free. Scene-level splits stop frames from leaking between train and test. But held-out *assets*, stores and real cameras haven't been tested. The next rigorous experiment is synthetic-only vs real-only vs mixed fine-tuning, scored on a held-out real recording. It would report exact-cart rate, false adds and removes, identity switches, review rate and latency.
