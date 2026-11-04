-- NorthBridge Production Counter Initial Schema (001_init.sql)

CREATE TABLE IF NOT EXISTS production_sources (
    source_id text PRIMARY KEY,
    display_name text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS production_events (
    id bigserial PRIMARY KEY,
    source_id text NOT NULL REFERENCES production_sources(source_id),
    event_id text NOT NULL,
    type text NOT NULL CHECK (type IN ('COUNT', 'VOID')),
    quantity int,
    target_event_id text,
    event_time timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL CHECK (status IN ('ACCEPTED', 'PENDING_REFERENCE', 'REJECTED')),
    failure_reason text,
    acknowledged_at timestamptz,
    CONSTRAINT uq_source_event UNIQUE (source_id, event_id),
    CONSTRAINT chk_event_type_fields CHECK (
        (type = 'COUNT' AND quantity > 0 AND target_event_id IS NULL)
        OR
        (type = 'VOID' AND quantity IS NULL AND target_event_id IS NOT NULL)
    )
);

-- Ensure only one accepted VOID per target event in the same source
CREATE UNIQUE INDEX IF NOT EXISTS one_void_per_count 
    ON production_events (source_id, target_event_id)
    WHERE type = 'VOID' AND status = 'ACCEPTED';

-- Query optimization index for pending voids lookup
CREATE INDEX IF NOT EXISTS idx_events_pending_voids 
    ON production_events (source_id, target_event_id, id)
    WHERE type = 'VOID' AND status = 'PENDING_REFERENCE';

-- Query optimization index for state and ack queries
CREATE INDEX IF NOT EXISTS idx_events_status 
    ON production_events (source_id, status);

CREATE TABLE IF NOT EXISTS submission_attempts (
    id bigserial PRIMARY KEY,
    raw_payload jsonb NOT NULL,
    source_id text NULL,
    event_id text NULL,
    classification text NOT NULL CHECK (
        classification IN ('ACCEPTED', 'DUPLICATE', 'CONFLICT', 'PENDING_REFERENCE', 'REJECTED')
    ),
    error text,
    received_at timestamptz NOT NULL DEFAULT now(),
    channel text NOT NULL CHECK (channel IN ('REST', 'MQTT'))
);

CREATE INDEX IF NOT EXISTS idx_attempts_source 
    ON submission_attempts (source_id);

CREATE TABLE IF NOT EXISTS mqtt_challenges (
    challenge_id text PRIMARY KEY,
    request_digest text NOT NULL,
    request_body jsonb NOT NULL,
    response jsonb NOT NULL,
    status text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    responded_at timestamptz NOT NULL DEFAULT now()
);
