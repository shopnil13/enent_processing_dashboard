# AI Usage & Attribution Report

This report outlines how AI assistance was leveraged during the development of the **NorthBridge Production Counter (FSE 01)**.

---

## 1. Scope of AI Assistance

AI assistance was utilized across the project lifecycle adhering strictly to the constraints outlined in `IMPLEMENTATION_PLAN.md`:

1. **Architecture & Foundation**:
   * Scaffolding the modular monolith directory structure and clean contracts (`contracts.py`).
   * Generating migration DDL (`migrations/001_init.sql`) with explicit constraints, foreign keys, and PostgreSQL partial unique indexes.
   * Designing the connection pooling and transaction context manager with domain event commit hooks.

2. **Core Domain Implementation**:
   * Implementation of the pure validation rules in `src/modules/events/validation.py`.
   * Translation of the business rules for COUNT/VOID handling, FIFO pending VOID resolution, and conflict classification in `src/modules/events/service.py`.
   * Advisory lock integration (`pg_advisory_xact_lock`) to serialize concurrent COUNT and VOID operations.

3. **MQTT Challenge Worker & Protocol**:
   * Designing the canonical JSON digest computation (`compute_canonical_digest`) using SHA-256 for challenge deduplication and idempotency.
   * Writing the Paho MQTT 2.x worker lifecycle management (last will, subscription callback, heartbeat thread).

4. **Frontend Dashboard**:
   * Building the React + TypeScript single-page dashboard with Vite.
   * Implementing `SummaryCards`, `JsonSubmitForm` (with local JSON validation and sample buttons), `StateTable` (with multi-select acknowledgment), and `MqttPanel`.
   * Setting up automatic 5-second polling and production SPA mounting via FastAPI.

5. **Test Automation**:
   * Creating the 22-test automated test suite using `pytest` and `TestClient` against a real PostgreSQL test database (`fse01_test`).
   * Authoring concurrency race tests with Python thread pools to verify advisory locking behavior.

---

## 2. Verification and Human Review

* All AI-generated components were verified against real PostgreSQL 18 instances with strict transaction rollbacks and isolation checks.
* The test suite was executed iteratively across every milestone branch before committing.
* No mock databases were used: all tests execute against real PostgreSQL tables with automatic fixture-driven table truncation.
