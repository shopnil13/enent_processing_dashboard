# Implementation Checklist: NorthBridge Production Counter (FSE 01)

## Milestone 1: Foundation & Database
- [x] Create python virtual environment (`.venv`) and install dependencies
- [x] Create `requirements.txt` (`fastapi`, `uvicorn`, `psycopg[binary,pool]`, `paho-mqtt`, `python-dotenv`, `pytest`, `httpx`)
- [x] Create `.gitignore` (ignoring `.venv`, `.env`, `__pycache__`, `node_modules`, `dist`, `.pytest_cache`)
- [x] Create `.env.example` and local `.env` with DB connection and MQTT defaults
- [x] Create `migrations/001_init.sql` with exact DDL from spec
- [x] Create `migrations/run_migrations.py` (lightweight SQL runner)
- [x] Implement `src/shared/db.py` (psycopg connection pool and transaction helper)
- [x] Implement `src/shared/contracts.py` (dataclasses: ValidatedEvent, ItemResult, Summary, AckResult, etc.)
- [x] Implement `src/shared/domain_events.py` (lightweight transaction-scoped in-process pub/sub)
- [x] Add tests for DB pool & migration runner in `tests/test_db.py`
- [x] Verify all tests pass on `milestone-1-foundation`
- [x] Single clean commit: `feat(db): set up project foundation, migrations, and db pool`

## Milestone 2: Events Ingestion Module (`POST /api/events`)
- [ ] Implement `src/modules/events/validation.py` (pure validation logic)
- [ ] Implement `src/modules/events/repository.py` (raw SQL for events, attempts, advisory locks)
- [ ] Implement `src/modules/events/service.py` (COUNT / VOID business logic, advisory locks, resolve pending voids)
- [ ] Implement `src/modules/events/routes.py` (`POST /api/events`)
- [ ] Mount events router in `src/main.py`
- [ ] Implement required tests:
  - Test 1: COUNT + total calculation
  - Test 2: Duplicate not double-counted (idempotency)
  - Test 3: VOID-before-COUNT auto resolution
- [ ] Verify all tests pass
- [ ] Single clean commit: `feat(events): implement event ingestion, validation, and void resolution`

## Milestone 3: State & Acknowledgment Modules
- [ ] Implement `src/modules/state/queries.py` & `service.py` (durable SQL summaries, pending events, exceptions)
- [ ] Implement `src/modules/state/routes.py` (`GET /api/state?view=summary|pending|exceptions&source_id=`)
- [ ] Implement `src/modules/ack/repository.py`, `service.py` & `routes.py` (`POST /api/ack`)
- [ ] Mount state and ack routers in `src/main.py`
- [ ] Implement required test:
  - Test 4: Repeated ACK handling (`ACKED`, `ALREADY_ACKED`, `NOT_READY`, `NOT_FOUND`)
- [ ] Verify all tests pass
- [ ] Single clean commit: `feat(state): implement state reporting and event acknowledgment`

## Milestone 4: MQTT Worker Module
- [ ] Implement `src/modules/mqtt/protocol.py` (envelope parsing, SHA-256 canonical digest)
- [ ] Implement `src/modules/mqtt/service.py` (challenge handling, idempotency via `mqtt_challenges`, expiration)
- [ ] Implement `src/modules/mqtt/worker.py` (paho-mqtt client, heartbeat thread, last will, loop_start)
- [ ] Implement `GET /api/mqtt/status` for dashboard visibility
- [ ] Wire MQTT worker lifecycle in `src/main.py` lifespan
- [ ] Implement required test:
  - Test 5: Repeated MQTT challenge returns stored response without reprocessing
- [ ] Verify all tests pass
- [ ] Single clean commit: `feat(mqtt): implement mqtt challenge worker and protocol handler`

## Milestone 5: Frontend Dashboard
- [ ] Initialize React + Vite + TypeScript in `frontend/`
- [ ] Implement `JsonSubmitForm` (textarea, validation, results display)
- [ ] Implement `SummaryCards` (6 indicators from `GET /api/state?view=summary`)
- [ ] Implement `StateTable` (pending & exceptions views, select & acknowledge button)
- [ ] Implement `MqttPanel` (live status, metrics, challenge stats)
- [ ] Implement `frontend/src/api.ts` (typed API client, 5s polling, error handling)
- [ ] Connect FastAPI static mounting for `frontend/dist` in production
- [ ] Test frontend build and end-to-end functionality
- [ ] Single clean commit: `feat(frontend): implement dashboard ui and static serving`

## Milestone 6: Extra-Credit Tests & Documentation
- [ ] Add extra-credit test cases:
  - Conflict preserves original event
  - Mixed batch handling (valid + invalid)
  - Multi-threaded concurrent submissions for same event_id
  - Two pending VOIDs resolution order
  - Restart recovery verification
  - Source mismatch VOID rejection
- [ ] Update `README.md` with complete setup instructions, architecture, and live review guide
- [ ] Create `TECHNICAL_EXPLANATION.md` & `AI_USAGE.md`
- [ ] Final verification of entire test suite and server startup
- [ ] Single clean commit: `docs(all): complete test suite, technical explanation, and user guide`

