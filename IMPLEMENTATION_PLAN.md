# FSE 01 – Implementation Plan (NorthBridge Production Counter)

Goal: a small, correct, explainable modular monolith. One FastAPI app, one PostgreSQL database, one MQTT worker inside the same process, one React dashboard.

## 1. Fixed stack

| Layer | Choice | Why |
|---|---|---|
| Language / API | Python 3.12 + FastAPI + uvicorn | Thin routes, easy to explain |
| Database | PostgreSQL (native install), separate `fse01_test` database for tests | Required by the brief |
| DB access | psycopg 3 + `psycopg_pool`, raw SQL, plain `.sql` migrations | Explicit `ON CONFLICT`, locks, transactions |
| MQTT | `paho-mqtt` 2.x, `loop_start()` background thread, same process | One deployment |
| Frontend | React + Vite (TypeScript), dev server on :5173; production build served by FastAPI | Two commands in dev, one for the reviewer |
| Tests | pytest + FastAPI `TestClient` | Real PostgreSQL, no mocks for the DB |
| Config | `.env` + `.env.example` (python-dotenv) | No secrets committed |

No ORM, no Kafka/RabbitMQ, no Docker requirement, no extra framework.

## 2. Folder layout

```
src/
  main.py                      # app factory, mounts routers, starts/stops MQTT worker, serves frontend/dist
  modules/
    events/  routes.py  validation.py  service.py  repository.py
    ack/     routes.py  service.py  repository.py
    state/   routes.py  service.py  queries.py
    mqtt/    worker.py  protocol.py  service.py
    audit/   service.py  repository.py     # thin: logs domain events
  shared/
    db.py            # pool, transaction helper
    contracts.py     # dataclasses: ValidatedEvent, ItemResult, Summary, ...
    domain_events.py # tiny in-process publish/subscribe
frontend/  migrations/  tests/
```

Rules: routes only parse the request and call a service; services hold business rules; repositories hold SQL. COUNT/VOID logic lives only in `events/service.py`.

## 3. Database (migrations/001_init.sql)

```sql
production_sources(source_id text PK, display_name text, created_at timestamptz)

production_events(
  id bigserial PK,                    -- insertion order = "first stored"
  source_id text REFERENCES production_sources,
  event_id text NOT NULL,
  type text CHECK (type IN ('COUNT','VOID')),
  quantity int, target_event_id text,
  event_time timestamptz NOT NULL,    -- from the device
  received_at timestamptz NOT NULL DEFAULT now(),  -- server receipt
  status text CHECK (status IN ('ACCEPTED','PENDING_REFERENCE','REJECTED')),
  failure_reason text,
  acknowledged_at timestamptz,
  UNIQUE (source_id, event_id),
  CHECK ((type='COUNT' AND quantity>0 AND target_event_id IS NULL)
      OR (type='VOID'  AND quantity IS NULL AND target_event_id IS NOT NULL))
)
-- one applied VOID per COUNT:
CREATE UNIQUE INDEX one_void_per_count ON production_events (source_id, target_event_id)
  WHERE type='VOID' AND status='ACCEPTED';

submission_attempts(
  id bigserial PK, raw_payload jsonb, source_id text NULL, event_id text NULL,
  classification text CHECK (classification IN
    ('ACCEPTED','DUPLICATE','CONFLICT','PENDING_REFERENCE','REJECTED')),
  error text, received_at timestamptz DEFAULT now(), channel text  -- 'REST' | 'MQTT'
)

mqtt_challenges(
  challenge_id text PK, request_digest text, request_body jsonb,
  response jsonb, status text, received_at timestamptz, responded_at timestamptz
)
```

Rejected items (invalid payloads) exist only in `submission_attempts`. They never become logical events.

## 4. Core functions (the "who owns what" answer)

`events/validation.py`
- `validate_event(raw: dict) -> ValidatedEvent | ValidationError`: pure function, no DB.

`events/service.py` (the only place with COUNT/VOID rules)
- `process_events(conn, raw_items, channel) -> list[ItemResult]`: loops over items in order, each item inside a nested transaction (savepoint).
- `process_event(conn, raw)`: validate, record attempt, dispatch to `process_count` or `process_void`.
- `process_count(conn, ev)`: insert the event as ACCEPTED, then call `resolve_pending_voids`.
- `process_void(conn, ev)`: apply it, mark it pending, or reject it.
- `resolve_pending_voids(conn, source_id, count_event_id)`: the lowest `id` pending VOID becomes ACCEPTED (auto-acknowledged), and the others become REJECTED with the reason "target already voided by <event_id>".

`events/repository.py`: `insert_event_on_conflict`, `get_event`, `lock_key`, `list_pending_voids`, `mark_void_accepted`, `mark_void_rejected`, `insert_attempt`.

`ack/service.py`: `acknowledge_events(conn, event_ids) -> list[AckResult]`.
`state/service.py` + `queries.py`: `get_summary(source_id=None)`, `get_pending(source_id=None)`, `get_exceptions(source_id=None)`. These are read functions, also called by the MQTT service.
`mqtt/service.py`: `handle_mqtt_challenge(raw_payload) -> response dict`, which calls `process_events(...)` and `get_summary()`.
`shared/domain_events.py`: `publish(name, payload)` / `subscribe(name, fn)`. Events: `EVENT_ACCEPTED`, `VOID_RESOLVED`, `EVENT_ACKNOWLEDGED`. They are queued during the transaction and published only after commit. The audit module subscribes and logs.

## 5. Processing rules (decisions already agreed)

- **Key:** `UNIQUE(source_id, event_id)`. The same `event_id` from another source is an independent event.
- **Batch:** one transaction per batch. Business failures (invalid, duplicate, conflict) never abort it. An unexpected DB error rolls back the whole batch and returns 500 `INTERNAL_ERROR` with no internals exposed.
- **Parsing:** the route reads the raw JSON itself (no Pydantic body model), so one bad item cannot turn into a 422 for the whole batch. Top-level body that is not an object or array → 400.
- **Duplicate vs conflict:** insert with `ON CONFLICT (source_id, event_id) DO NOTHING RETURNING`. If nothing is returned, load the original and compare normalized fields (`type`, `quantity`, `target_event_id` with null = omitted, `event_time` as UTC). Same → DUPLICATE, different → CONFLICT. The original is never changed.
- **VOID logic:**
  1. The target COUNT exists in the same source and is ACCEPTED, and no accepted VOID targets it → ACCEPTED (the unique index backs this up).
  2. The target exists only under another source → REJECTED, reason "source mismatch".
  3. The target does not exist anywhere → PENDING_REFERENCE.
  4. The target is already voided, is itself a VOID, or is the VOID's own ID → REJECTED with a clear reason.
- **Concurrency:** take `pg_advisory_xact_lock(hashtext(source_id || ':' || <count event_id>))` in both `process_count` and `process_void`. A VOID and its COUNT arriving at the same moment are then serialized, so a pending VOID can never be missed.
- **Acknowledgement:** VOIDs get `acknowledged_at` at the moment they complete (accepted or resolved). Ack matches by `event_id` across sources, in request order, inside one transaction:
  - no rows → `NOT_FOUND`
  - no ACCEPTED rows → `NOT_READY`
  - an ACCEPTED row with `acknowledged_at IS NULL` → set it → `ACKED`
  - otherwise → `ALREADY_ACKED`
  A repeated ID in one request therefore becomes `ALREADY_ACKED` after the first. Ack never touches COUNT/VOID logic.
- **Summary (all SQL on durable data, no in-memory counters):**
  - `net_total` = sum of ACCEPTED COUNT quantities with no ACCEPTED VOID against them
  - `processed_events` = rows with status ACCEPTED
  - `pending_ack` = ACCEPTED rows with `acknowledged_at IS NULL`
  - `unresolved` = rows with status PENDING_REFERENCE
  - `duplicates` / `conflicts` = attempts with that classification
  - `source_id` filters events by stored source and attempts by the attempt's own `source_id`
- **Views:** `pending` = ACCEPTED COUNTs not yet acknowledged. `exceptions` = PENDING_REFERENCE events, REJECTED events and attempts (with reason), and CONFLICT attempts. Attempts without a usable `source_id` appear only when unfiltered.
- **Sources:** an unknown `source_id` is inserted into `production_sources` on the first valid event.

## 6. MQTT worker

- Config: broker `152.42.238.142:1883`, `CANDIDATE_ID` from `.env`, client ID `fse01-{CANDIDATE_ID}-{6 random chars}`, QoS 1, retain false.
- Connect with `reconnect_delay_set(1, 60)`. Set the **last will** to OFFLINE on the status topic before connecting.
- Topics: subscribe to `fse-01/{CANDIDATE_ID}/challenge`, publish responses to `fse-01/{CANDIDATE_ID}/response` and status to `fse-01/{CANDIDATE_ID}/status`. On connect, subscribe, then publish ONLINE from the `on_subscribe` callback (after the subscription is confirmed). A heartbeat thread publishes HEARTBEAT every 20 s. Every reconnect re-subscribes in `on_connect`.
- `handle_mqtt_challenge` order:
  1. Parse JSON. Unparseable → log and publish FAILED/`VALIDATION_ERROR`.
  2. Check `protocol_version == "1.0"` (`UNSUPPORTED_PROTOCOL`), `candidate_id` (`CANDIDATE_MISMATCH`), `command == "PROCESS_EVENTS"` and `events` is a list (`VALIDATION_ERROR`).
  3. Look up `challenge_id` in `mqtt_challenges`. Same digest → republish the stored response (no processing). Different digest → FAILED/`CHALLENGE_CONFLICT`.
  4. Check `expires_at` → `CHALLENGE_EXPIRED` before processing.
  5. In ONE transaction: `process_events(..., channel='MQTT')`, `get_summary()` (global), insert the challenge row with its response.
  6. Publish the response after commit. Anything unexpected → FAILED/`INTERNAL_ERROR`.
- The digest is SHA-256 of the canonical JSON (sorted keys). `candidate_id` in the envelope is not part of event identity.
- In-memory status object for the dashboard: connected, candidate ID, last challenge ID/time, last response status, last error. Challenge counts are read from `mqtt_challenges`, so they survive a restart.

## 7. REST API

| Endpoint | Behaviour |
|---|---|
| `POST /api/events` | Object or array → 200 `{"results":[...]}` in the original order. Not object/array → 400. Empty array → 200 with empty results. |
| `GET /api/state?view=summary\|pending\|exceptions&source_id=` | Invalid `view` → 400 |
| `POST /api/ack` | `{"event_ids":[...]}` → one result per ID, in order |
| `GET /api/mqtt/status` (read-only extra) | Feeds the dashboard's MQTT panel. Flagged as an assumption: the brief lists three APIs but requires MQTT visibility using real backend values. |

## 8. Frontend (React + Vite)

One page, responsive (CSS grid, stacks on mobile).
- `JsonSubmitForm`: textarea, validates JSON locally, shows the per-item results.
- `SummaryCards`: six indicators.
- `StateTable`: Pending / Exceptions switch. Pending rows have checkboxes and an "Acknowledge selected" button. Refreshes after every action.
- `MqttPanel`: connection state, candidate ID, last challenge ID/time, last response status, completed/failed counts, last error.
- A single `api.ts` with typed fetches. Each component handles loading, empty, invalid-input and API-failure states. Poll every 5 s plus a manual Refresh button.
- Dev: `npm run dev` with FastAPI CORS for `http://localhost:5173`. Reviewer: `npm run build`, then FastAPI serves `frontend/dist` at `/`.

## 9. Tests (pytest, real PostgreSQL `fse01_test`, tables truncated between tests)

Required: (1) COUNT + total, (2) duplicate not double counted, (3) VOID-before-COUNT auto resolution, (4) repeated ack, (5) repeated MQTT challenge returns the stored response and does not reprocess (call `handle_mqtt_challenge` directly with a capturing publisher).

Extra credit: conflict preserves the original, mixed batch (valid + invalid), concurrent submissions of one event ID with threads, two pending VOIDs (first wins, second rejected), restart recovery (new pool, same state), source-mismatch VOID.

## 10. Build order (commit after each step)

1. Repo, venv, `requirements.txt`, `.env.example`, `migrations/001_init.sql`, migration runner, `shared/db.py`. *Commit.*
2. `validation.py`, `events/*`, `POST /api/events`, tests 1–3. *Commit.*
3. `state/*`, `ack/*`, tests 4 plus the summary assertions. *Commit.*
4. `mqtt/*`, tests 5, then a live run against the simulator. *Commit.*
5. Frontend, then the build served by FastAPI. *Commit.*
6. Extra-credit tests, then docs: `README.md`, `TECHNICAL_EXPLANATION.md`, `AI_USAGE.md`, screenshots, clean ZIP (no `venv`, `node_modules`, `__pycache__`, `.env`).

Final check: fresh clone, follow the README, send REST + MQTT events, restart the server, confirm the numbers are unchanged.

## 11. Live-review answers to prepare

- Entity model: sources, events, attempts, challenges. Attempts keep history, events hold the logical state.
- COUNT is owned by `process_count`. REST and MQTT call the same `process_events`, so no rule is duplicated.
- Transactions: batch/challenge level, advisory lock for the COUNT/VOID race, unique indexes as the safety net.
- Split path: modules already communicate through functions and the domain events. Moving to services means replacing function calls with HTTP/gRPC and the in-process publisher with a broker, with the events module owning the database tables.
- Rule change demo: change one condition in `process_void` (for example, allow a VOID of a VOID) and show the other modules and tests unaffected.

## 12. Defaults chosen without asking (change any you disagree with)

1. Empty array → 200 with empty results.
2. VOID that targets a VOID, targets itself, or targets an already-voided COUNT → REJECTED with a reason.
3. A losing pending VOID is stored with status REJECTED and a reason when the winner resolves.
4. VOIDs are auto-acknowledged on completion, so acking a VOID returns `ALREADY_ACKED`.
5. `GET /api/mqtt/status` as a fourth, read-only endpoint.
6. The MQTT `state` in the response is global.
