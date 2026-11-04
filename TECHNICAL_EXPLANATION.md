# Technical Architecture & Engineering Decisions

This document outlines the architectural patterns, database isolation strategies, and edge-case handling mechanisms implemented in the **NorthBridge Production Counter (FSE 01)**.

---

## 1. Modular Monolith Architecture

The system is structured as an explainable modular monolith rather than premature microservices or a monolithic script:

```
src/
  ├── modules/
  │     ├── events/   # Ingestion, validation, repository, service
  │     ├── state/    # Durable SQL metric queries & reporting
  │     ├── ack/      # Event acknowledgment workflow
  │     └── mqtt/     # Challenge worker, canonical protocol digest
  └── shared/
        ├── db.py            # Psycopg 3 connection pool & transaction manager
        ├── contracts.py     # Strongly typed domain dataclasses
        └── domain_events.py # Transaction-scoped commit-hook event publisher
```

### Architectural Principles:
1. **Separation of Concerns**: Routes perform request extraction and status code mapping; services orchestrate business workflows and domain invariants; repositories encapsulate pure raw SQL.
2. **Single Ingestion Pipeline**: Both HTTP REST (`POST /api/events`) and MQTT (`PROCESS_EVENTS` challenge commands) invoke the identical `process_events(conn, raw_items, channel)` domain entry point. Invariants cannot diverge between ingestion channels.
3. **Decoupled Module Communication**: Cross-module communication uses explicit function interfaces and lightweight, in-process transaction-scoped domain events (`EVENT_ACCEPTED`, `VOID_RESOLVED`, `EVENT_ACKNOWLEDGED`).

---

## 2. Concurrency & Race Condition Elimination

### Problem: Simultaneous COUNT and VOID Ingestion
When a device emits a `COUNT` event and a subsequent `VOID` event in rapid succession, network jitter or concurrent HTTP/MQTT workers can deliver them to the server simultaneously on different threads.
If executed concurrently:
* A thread executing `process_void` could check for the target `COUNT`, find nothing, and mark the `VOID` as `PENDING_REFERENCE`.
* Meanwhile, the thread executing `process_count` could insert the `COUNT` and check for pending voids before the void transaction commits.
* Result: A race condition where a valid VOID fails to immediately void its COUNT.

### Solution: Transactional Advisory Locks
We utilize PostgreSQL transaction-scoped advisory locks:
```sql
SELECT pg_advisory_xact_lock(hashtext(source_id || ':' || target_event_id));
```
* Before inserting or evaluating any COUNT or VOID, the transaction acquires this lock based on the hash of `source_id:count_event_id`.
* The lock is automatically held until the transaction commits or rolls back (`_xact_lock`).
* If a COUNT and VOID for the same event arrive concurrently across different threads or processes, one will block until the other completes.
* If the VOID arrives first, it safely becomes `PENDING_REFERENCE`. As soon as it commits, the COUNT transaction proceeds, acquires the lock, inserts the COUNT, and immediately triggers `resolve_pending_voids`, auto-resolving the pending VOID in FIFO order.
* Backed up by the partial unique index:
  ```sql
  CREATE UNIQUE INDEX one_void_per_count 
  ON production_events (source_id, target_event_id)
  WHERE type = 'VOID' AND status = 'ACCEPTED';
  ```

---

## 3. Idempotency & Deduplication Strategy

The system guarantees idempotency at two critical boundaries:

### A. Logical Events Boundary
When an event arrives with an existing `(source_id, event_id)`:
1. The insertion is attempted via:
   ```sql
   INSERT INTO production_events (...) VALUES (...) 
   ON CONFLICT (source_id, event_id) DO NOTHING RETURNING id;
   ```
2. If no row is returned, the original event is loaded and its normalized fields are compared:
   * `type`
   * `quantity`
   * `target_event_id`
   * `event_time` (normalized to UTC)
3. **Identical Re-submission (`DUPLICATE`)**: Returns status `DUPLICATE` without double-counting quantities.
4. **Conflicting Re-submission (`CONFLICT`)**: Returns status `CONFLICT` with a descriptive error. The original stored event is **never mutated**.
5. Every single submission (valid, duplicate, conflict, or rejected) is recorded in `submission_attempts` to provide a complete, immutable audit trail.

### B. MQTT Challenge Boundary
To protect against repeated or retransmitted MQTT challenges:
1. For incoming challenge payload $P$, the canonical JSON string is computed (sorted keys, compact delimiters) and hashed via SHA-256:
   $$\text{digest} = \text{SHA-256}(\text{CanonicalJSON}(P))$$
2. The database is checked for an existing record with `challenge_id`:
   * **Identical Digest**: The pre-computed response stored in `mqtt_challenges.response` is returned immediately without re-processing events.
   * **Different Digest**: Returns `status: FAILED` with error code `CHALLENGE_CONFLICT`.

---

## 4. Pure SQL Metrics on Durable State

All operational metrics are derived dynamically from durable tables:

$$\text{Net Total} = \sum_{\substack{\text{status}=\text{ACCEPTED} \\ \text{type}=\text{COUNT} \\ \neg \exists \text{ACCEPTED VOID}}} \text{quantity}$$

By computing `net_total`, `processed_events`, `pending_ack`, `unresolved`, `duplicates`, and `conflicts` directly in SQL:
* System restarts or container recycles do not lose counters.
* The state is always mathematically consistent with table contents.
* Multi-source filtering (`source_id = ...`) is handled natively by the database engine with index acceleration.

---

## 5. Microservice Decomposition Path

If NorthBridge scales to a distributed microservice topology:
1. **Modules to Services**:
   * `events` module becomes the Ingestion Service owning `production_events` and `submission_attempts`.
   * `state` and `ack` modules become the State Reporting Service.
   * `mqtt` worker becomes a dedicated edge gateway service.
2. **Communication Migration**:
   * Replace in-process function calls with gRPC definitions matching `src/shared/contracts.py`.
   * Replace `src/shared/domain_events.py` with an external event bus (Kafka / RabbitMQ / Google PubSub).
3. **Zero Business Logic Rewrite**: All domain functions in `events/service.py` remain identical.
