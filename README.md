# NorthBridge Production Counter (FSE 01)

A correct, production-grade modular monolith for event processing and production tracking. The system integrates a high-performance **FastAPI** backend, a native **PostgreSQL** persistence layer with raw SQL transactions and advisory locks, an in-process **MQTT 2.x worker** communicating with remote challenge brokers, and a responsive **React + Vite + TypeScript** dashboard.

---

## 1. Architectural Highlights

* **Modular Monolith**: Clean layer separation (`routes` → `service` → `repository`) with explicit transactional boundaries and zero cross-module coupling.
* **Pure Business Logic Core**: All production COUNT and VOID rules are consolidated exclusively inside `src/modules/events/service.py`. REST ingestion and MQTT challenge workers share this identical domain pipeline.
* **Deterministic Concurrency Control**: Eliminates race conditions between simultaneous `COUNT` and `VOID` events using PostgreSQL transaction-level advisory locks (`pg_advisory_xact_lock`).
* **Strict Idempotency**:
  * Event-level: Exact re-submissions return `DUPLICATE` without double-counting; conflicting payloads under the same key return `CONFLICT` while preserving original data.
  * MQTT challenge-level: Canonical JSON SHA-256 digests ensure repeated challenges return pre-computed responses without reprocessing.
* **Durable State Metrics**: All summary totals, pending queues, exceptions, and rejected metrics are computed directly via optimized SQL on durable tables—no vulnerable in-memory counters.
* **Self-Contained Unified Deployment**: The FastAPI application directly serves the compiled React SPA from `frontend/dist` on a single port for seamless review.

---

## 2. Technology Stack

| Component | Choice | Reason |
|---|---|---|
| **Language / Framework** | Python 3.11+ / FastAPI / Uvicorn | High throughput, asynchronous lifespan, minimal boilerplate |
| **Database** | PostgreSQL 18 (Native install) | ACID transactions, advisory locking, partial unique indexes |
| **Database Driver** | `psycopg` 3.x + `psycopg_pool` | Raw SQL, explicit transactions, native connection pooling |
| **MQTT Engine** | `paho-mqtt` 2.x (`loop_start` background worker) | QoS 1, canonical SHA-256 digest, last will & heartbeat |
| **Frontend UI** | React 18, Vite, TypeScript, Tailwind CSS | Reactive dashboard, live 5s polling, responsive CSS grid |
| **Test Suite** | `pytest` + `TestClient` | Real PostgreSQL test database (`fse01_test`) |

---

## 3. Directory Layout

```
├── IMPLEMENTATION_PLAN.md      # Approved system blueprint and specifications
├── checklist.md                # Milestone & change request task tracker
├── migrations/
│   ├── 001_init.sql            # Database schema DDL & indexes
│   └── run_migrations.py       # Standalone migration execution runner
├── src/
│   ├── main.py                 # Application factory, lifespan, static SPA mount
│   ├── shared/
│   │   ├── db.py               # Connection pool and transaction helper
│   │   ├── contracts.py        # Shared domain dataclasses
│   │   └── domain_events.py    # Transaction-scoped in-process pub/sub
│   └── modules/
│       ├── events/             # Ingestion, validation, repository, service
│       ├── state/              # Durable state queries, summary, exceptions
│       ├── ack/                # Event acknowledgment pipeline
│       └── mqtt/               # Challenge protocol, MQTT worker, status router
├── frontend/                   # React + Vite TypeScript SPA
│   ├── src/                    # UI Components (SummaryCards, JsonSubmitForm, StateTable, MqttPanel)
│   └── dist/                   # Production build served by FastAPI
├── tests/                      # Full pytest test suite (25 tests)
└── requirements.txt            # Python dependencies
```

---

## 4. Setup & Installation

### Prerequisites
* **Python 3.11+**
* **PostgreSQL 18** running on `localhost:5432`
* **Node.js v20+** and **npm**

### Step 1: Environment Setup
Clone the repository and create the Python virtual environment:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 2: Database Configuration
Configure `.env` based on `.env.example`:
```ini
DATABASE_URL=postgresql://postgres:Shopnil13@localhost:5432/fse01
TEST_DATABASE_URL=postgresql://postgres:Shopnil13@localhost:5432/fse01_test

PORT=8000
HOST=0.0.0.0

MQTT_BROKER_HOST=152.42.238.142
MQTT_BROKER_PORT=1883
CANDIDATE_ID=shopnil13
ENABLE_MQTT=true
```

Run database migrations to apply the initial schema:
```powershell
python -m migrations.run_migrations
```

### Step 3: Frontend Build
Install frontend packages and compile the production bundle:
```powershell
cd frontend
npm install
npm run build
cd ..
```

---

## 5. Running the Application

### Production / Reviewer Mode (Single Command)
Run the server with Uvicorn. FastAPI automatically serves the built frontend dashboard at `/` and the REST APIs under `/api/*`:
```powershell
.\.venv\Scripts\uvicorn src.main:app --port 8000
```
Open your browser to: **`http://localhost:8000`**

### Development Mode (Separate Hot-Reloading Servers)
Terminal 1 (Backend API):
```powershell
.\.venv\Scripts\uvicorn src.main:app --reload --port 8000
```
Terminal 2 (Frontend Dev Server):
```powershell
cd frontend
npm run dev
```
Access the Vite dev dashboard on **`http://localhost:5173`** (API requests are automatically proxied to port 8000).

---

## 6. Running Tests

The test suite runs against the dedicated test database (`fse01_test`), truncating tables between tests to guarantee clean isolation:
```powershell
.\.venv\Scripts\pytest -v
```

All 25 test cases verify:
* **Core Functionality**: Single & batch event ingestion, COUNT addition, immediate VOID application.
* **CR FSE-01 Quantity Validation**: Quantities 1–500 accepted, $>500$ rejected with clear reason without increasing totals, applied identically across REST and MQTT.
* **CR FSE-01 Summary Metrics**: `rejected_submissions` counts only rejected attempts, returns 0 when none exist, and respects source filtering.
* **Idempotency & Conflicts**: Exact duplicates ignored without duplicate counts; conflicting payloads rejected while preserving existing records.
* **VOID Resolution Order**: FIFO auto-resolution of pending VOIDs when their target COUNT arrives; winning VOID accepted, losing VOIDs rejected.
* **State & Ack**: Repeated acknowledgment handling, NOT_READY for pending items, ALREADY_ACKED for re-submissions, durable summary calculations with source filtering.
* **MQTT Worker**: Canonical digest idempotency, conflict detection, protocol envelope validation, challenge expiration.
* **Concurrency & Recovery**: Multi-threaded submissions, COUNT/VOID race conditions serialized via advisory locks, restart recovery across pool teardowns.

---

## 7. REST API Documentation

### Ingestion: `POST /api/events`
Accepts a single event object or an array of event objects.
```json
{
  "source_id": "line_1",
  "event_id": "evt_101",
  "type": "COUNT",
  "quantity": 25,
  "event_time": "2026-11-04T10:00:00Z"
}
```
**Response (200 OK):**
```json
{
  "results": [
    {
      "status": "ACCEPTED",
      "event_id": "evt_101",
      "source_id": "line_1"
    }
  ]
}
```

### State Reporting: `GET /api/state?view={summary|pending|exceptions|mqtt}&source_id={optional}`
* **`view=summary`**: Returns global or source-specific indicators:
  ```json
  {
    "net_total": 25,
    "processed_events": 1,
    "pending_ack": 1,
    "unresolved": 0,
    "duplicates": 0,
    "conflicts": 0,
    "rejected_submissions": 0
  }
  ```
* **`view=pending`**: Returns list of ACCEPTED COUNT events not yet acknowledged.
* **`view=exceptions`**: Returns pending reference events, rejected events with failure reasons, and conflicting submission attempts.
* **`view=mqtt`**: Returns live MQTT connection status and challenge metrics (folded into `/api/state` to maintain the 3 core endpoints).

### Acknowledgment: `POST /api/ack`
Processes event IDs in request order inside one transaction:
```json
{
  "event_ids": ["evt_101", "evt_101", "non_existent"]
}
```
**Response (200 OK):**
```json
{
  "results": [
    { "event_id": "evt_101", "status": "ACKED" },
    { "event_id": "evt_101", "status": "ALREADY_ACKED" },
    { "event_id": "non_existent", "status": "NOT_FOUND" }
  ]
}
```

---

## 8. Change Request FSE-01 Review Guide

* **01. Production Quantity Validation (`MAX_COUNT_QUANTITY = 500`)**:
  * Implemented in `src/modules/events/validation.py`.
  * Quantities must be integer between 1 and 500 inclusive. Any quantity $>500$ returns `REJECTED` with `"quantity exceeds maximum of 500"`.
  * Logged in `submission_attempts` without incrementing logical totals.
  * Shared by both REST and MQTT challenge handlers through the unified `validate_event()` entry point.
* **02. `rejected_submissions` in Summary & MQTT State**:
  * Added to `Summary` contract (`src/shared/contracts.py`) and durable SQL query (`src/modules/state/queries.py`).
  * Counts stored submission attempts with status `REJECTED` only (excluding DUPLICATE, CONFLICT, and PENDING_REFERENCE).
  * Returns 0 when none exist and respects the optional `source_id` filter.
  * Embedded automatically in the MQTT challenge response's `state` object.
* **03. Production Source Filter in Frontend**:
  * Input with datalist autocomplete and instant clear (`✕`) button.
  * Seamlessly filters Summary, Pending, and Exceptions views using backend `source_id` query parameter.
* **04. Seventh Indicator ("Rejected Submissions")**:
  * Rendered as an alert card in `frontend/src/components/SummaryCards.tsx` visually distinguished with red accenting.
  * Updates live with polling and source selection.
* **Architecture Preservation**:
  * Zero rewrite required: the modular monolith function boundaries allowed adding the quantity ceiling in one validation constant and the rejected metric in one query subclause.
  * Preserved the 3-endpoint REST footprint (`/api/events`, `/api/state`, `/api/ack`) with `GET /api/state?view=mqtt`.
