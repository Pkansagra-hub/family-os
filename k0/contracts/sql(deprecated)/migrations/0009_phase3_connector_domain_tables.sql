-- ========================================================================================
-- K0 Connector Domain Tables (Phase 3)
-- ========================================================================================
-- Migration: 0009
-- Created: 2025-01-22
-- Description: Connector integration tables for external data ingestion
-- Philosophy: "Build a smooth road for companies to integrate"
-- Architecture: Three-pass sorting (Domain → Event Type → Structured Fields)
-- First Release Domains: Health, Financial, Calendar, Shopping
-- ========================================================================================
-- Tables Created:
--   1. st_health (10 event types)
--   2. st_financial (10 event types)
--   3. st_calendar (8 event types)
--   4. st_shopping (10 event types)
--   5. st_envelope_metadata (ingestion tracking)
--   6. st_unprocessed_bag (failed validations)
--   7. st_connector_registry (active connectors)
-- ========================================================================================

-- ========================================================================================
-- TABLE 1: st_health - Health & Fitness Domain
-- ========================================================================================
-- Purpose: Store health and fitness events from external connectors
-- Connectors: Strava, Apple Health, Fitbit, MyFitnessPal, Epic MyChart, CVS Pharmacy
-- Event Types: 10 types covering fitness, medical, nutrition, vitals
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_health (
    -- ==================== IDENTITY ====================
    health_event_id         TEXT PRIMARY KEY DEFAULT ('health_' || lower(hex(randomblob(16)))),
    envelope_id             TEXT NOT NULL,
    source_connector        TEXT NOT NULL,  -- 'strava', 'apple_health', 'fitbit', 'myfitnesspal', 'epic_mychart'
    connector_event_id      TEXT NOT NULL,  -- Original event ID from connector
    cognitive_trace_id      TEXT NOT NULL,

    -- ==================== EVENT CLASSIFICATION ====================
    event_type              TEXT NOT NULL CHECK(event_type IN (
        'fitness_activity',      -- Steps, runs, workouts, exercise sessions
        'sleep_session',         -- Sleep duration, quality, stages (deep/REM/light)
        'vitals_measurement',    -- Heart rate, blood pressure, temperature, SpO2
        'nutrition_entry',       -- Meals, calories, macros, food logging
        'weight_measurement',    -- Body weight, BMI, body composition
        'medical_appointment',   -- Doctor visits, checkups, specialist consultations
        'prescription',          -- Medications, dosage, refills, pharmacy pickups
        'lab_result',            -- Blood tests, imaging results, diagnostic reports
        'symptom_log',           -- Feeling sick, pain tracking, health observations
        'vaccination'            -- Immunizations, boosters, vaccine records
    )),
    occurred_at             INTEGER NOT NULL,  -- Unix timestamp (ms) of event occurrence

    -- ==================== STRUCTURED PAYLOAD ====================
    payload                 TEXT NOT NULL,  -- JSON blob with connector-specific fields

    -- ==================== COMMON EXTRACTED FIELDS ====================
    person_id               TEXT,  -- FK to people table (NULL if not mapped)
    value_numeric           REAL,  -- Numeric value (steps, weight, heart rate, etc.)
    value_text              TEXT,  -- Text value (medication name, symptom description, etc.)
    unit                    TEXT,  -- Unit of measurement ('steps', 'lbs', 'bpm', 'mg', etc.)
    category                TEXT,  -- Sub-category ('cardio', 'strength', 'sleep', 'nutrition', etc.)

    -- ==================== ACCESS CONTROL ====================
    tenant_id               TEXT NOT NULL DEFAULT 'family_001',
    space_id                TEXT NOT NULL DEFAULT 'default',
    privacy_band            TEXT NOT NULL DEFAULT 'AMBER' CHECK(privacy_band IN ('GREEN', 'AMBER', 'RED')),
    owner_id                TEXT,
    visible_to              TEXT,  -- JSON array of user_ids

    -- ==================== METADATA ====================
    received_at             INTEGER NOT NULL,  -- Unix timestamp (ms) when envelope received
    processed_at            INTEGER NOT NULL,  -- Unix timestamp (ms) when event processed
    validation_status       TEXT NOT NULL DEFAULT 'valid' CHECK(validation_status IN ('valid', 'invalid', 'pending')),

    -- ==================== LIFECYCLE ====================
    vector_clock            TEXT NOT NULL DEFAULT '0',
    tombstone               INTEGER NOT NULL DEFAULT 0 CHECK(tombstone IN (0, 1)),
    lamport                 INTEGER NOT NULL DEFAULT 0
);

-- ==================== INDEXES ====================
CREATE INDEX IF NOT EXISTS idx_health_envelope ON st_health(envelope_id);
CREATE INDEX IF NOT EXISTS idx_health_source ON st_health(source_connector) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_health_event_type ON st_health(event_type) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_health_occurred ON st_health(occurred_at DESC) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_health_person ON st_health(person_id) WHERE person_id IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_health_category ON st_health(category) WHERE category IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_health_trace ON st_health(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_health_tenant_space ON st_health(tenant_id, space_id) WHERE tombstone = 0;
CREATE UNIQUE INDEX IF NOT EXISTS idx_health_connector_event ON st_health(source_connector, connector_event_id);

-- ========================================================================================
-- TABLE 2: st_financial - Financial Domain
-- ========================================================================================
-- Purpose: Store financial events from external connectors
-- Connectors: Plaid, Chase, Amex, Fidelity, PayPal, Venmo, Robinhood, Mint
-- Event Types: 10 types covering transactions, transfers, investments, bills
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_financial (
    -- ==================== IDENTITY ====================
    financial_event_id      TEXT PRIMARY KEY DEFAULT ('fin_' || lower(hex(randomblob(16)))),
    envelope_id             TEXT NOT NULL,
    source_connector        TEXT NOT NULL,  -- 'plaid', 'chase', 'amex', 'fidelity', 'paypal', 'venmo'
    connector_event_id      TEXT NOT NULL,  -- Original event ID from connector
    cognitive_trace_id      TEXT NOT NULL,

    -- ==================== EVENT CLASSIFICATION ====================
    event_type              TEXT NOT NULL CHECK(event_type IN (
        'transaction',           -- Debit/credit card purchases, POS transactions
        'transfer',              -- Money movement between accounts
        'bill_payment',          -- Utilities, rent, recurring bills
        'investment_trade',      -- Stock buy/sell, portfolio transactions
        'account_balance',       -- Periodic balance snapshots
        'credit_card_statement', -- Monthly statement summaries
        'loan_payment',          -- Mortgage, car loan, student loan payments
        'refund',                -- Purchase returns, chargebacks
        'fee',                   -- Bank fees, interest charges, penalties
        'dividend'               -- Investment income, interest earnings
    )),
    occurred_at             INTEGER NOT NULL,  -- Unix timestamp (ms) of event occurrence

    -- ==================== STRUCTURED PAYLOAD ====================
    payload                 TEXT NOT NULL,  -- JSON blob with connector-specific fields

    -- ==================== COMMON EXTRACTED FIELDS ====================
    person_id               TEXT,  -- FK to people table (NULL if not mapped)
    amount                  REAL NOT NULL,  -- Transaction amount (positive or negative)
    currency                TEXT NOT NULL DEFAULT 'USD',  -- ISO 4217 currency code
    category                TEXT,  -- Transaction category ('groceries', 'dining', 'gas', 'rent', etc.)
    merchant                TEXT,  -- Merchant name or description
    account_id              TEXT,  -- External account ID from connector

    -- ==================== ACCESS CONTROL ====================
    tenant_id               TEXT NOT NULL DEFAULT 'family_001',
    space_id                TEXT NOT NULL DEFAULT 'default',
    privacy_band            TEXT NOT NULL DEFAULT 'RED' CHECK(privacy_band IN ('GREEN', 'AMBER', 'RED')),
    owner_id                TEXT,
    visible_to              TEXT,  -- JSON array of user_ids

    -- ==================== METADATA ====================
    received_at             INTEGER NOT NULL,  -- Unix timestamp (ms) when envelope received
    processed_at            INTEGER NOT NULL,  -- Unix timestamp (ms) when event processed
    validation_status       TEXT NOT NULL DEFAULT 'valid' CHECK(validation_status IN ('valid', 'invalid', 'pending')),

    -- ==================== LIFECYCLE ====================
    vector_clock            TEXT NOT NULL DEFAULT '0',
    tombstone               INTEGER NOT NULL DEFAULT 0 CHECK(tombstone IN (0, 1)),
    lamport                 INTEGER NOT NULL DEFAULT 0
);

-- ==================== INDEXES ====================
CREATE INDEX IF NOT EXISTS idx_financial_envelope ON st_financial(envelope_id);
CREATE INDEX IF NOT EXISTS idx_financial_source ON st_financial(source_connector) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_financial_event_type ON st_financial(event_type) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_financial_occurred ON st_financial(occurred_at DESC) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_financial_person ON st_financial(person_id) WHERE person_id IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_financial_category ON st_financial(category) WHERE category IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_financial_merchant ON st_financial(merchant) WHERE merchant IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_financial_amount ON st_financial(amount) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_financial_trace ON st_financial(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_financial_tenant_space ON st_financial(tenant_id, space_id) WHERE tombstone = 0;
CREATE UNIQUE INDEX IF NOT EXISTS idx_financial_connector_event ON st_financial(source_connector, connector_event_id);

-- ========================================================================================
-- TABLE 3: st_calendar - Calendar Domain
-- ========================================================================================
-- Purpose: Store calendar events from external connectors
-- Connectors: Google Calendar, Outlook, Apple Calendar
-- Event Types: 8 types covering appointments, meetings, reminders, tasks
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_calendar (
    -- ==================== IDENTITY ====================
    calendar_event_id       TEXT PRIMARY KEY DEFAULT ('cal_' || lower(hex(randomblob(16)))),
    envelope_id             TEXT NOT NULL,
    source_connector        TEXT NOT NULL,  -- 'google_calendar', 'outlook', 'apple_calendar'
    connector_event_id      TEXT NOT NULL,  -- Original event ID from connector
    cognitive_trace_id      TEXT NOT NULL,

    -- ==================== EVENT CLASSIFICATION ====================
    event_type              TEXT NOT NULL CHECK(event_type IN (
        'appointment',       -- Doctor, dentist, haircut, one-on-one meetings
        'meeting',           -- Work meetings, school conferences, group gatherings
        'event',             -- Birthday parties, weddings, social events
        'reminder',          -- One-time reminders, alerts
        'recurring_event',   -- Weekly soccer practice, monthly book club
        'all_day_event',     -- Holidays, vacation days, travel days
        'deadline',          -- Project due dates, bill due dates
        'task'               -- Todo items with due dates
    )),
    occurred_at             INTEGER NOT NULL,  -- Unix timestamp (ms) of event occurrence

    -- ==================== STRUCTURED PAYLOAD ====================
    payload                 TEXT NOT NULL,  -- JSON blob with connector-specific fields

    -- ==================== COMMON EXTRACTED FIELDS ====================
    person_id               TEXT,  -- FK to people table (NULL if not mapped)
    title                   TEXT NOT NULL,  -- Event title or subject
    start_time              INTEGER NOT NULL,  -- Unix timestamp (ms) of event start
    end_time                INTEGER,  -- Unix timestamp (ms) of event end (NULL for tasks/reminders)
    location                TEXT,  -- Event location or meeting URL
    attendees               TEXT,  -- JSON array of attendee objects
    status                  TEXT,  -- Event status ('confirmed', 'tentative', 'cancelled')

    -- ==================== ACCESS CONTROL ====================
    tenant_id               TEXT NOT NULL DEFAULT 'family_001',
    space_id                TEXT NOT NULL DEFAULT 'default',
    privacy_band            TEXT NOT NULL DEFAULT 'GREEN' CHECK(privacy_band IN ('GREEN', 'AMBER', 'RED')),
    owner_id                TEXT,
    visible_to              TEXT,  -- JSON array of user_ids

    -- ==================== METADATA ====================
    received_at             INTEGER NOT NULL,  -- Unix timestamp (ms) when envelope received
    processed_at            INTEGER NOT NULL,  -- Unix timestamp (ms) when event processed
    validation_status       TEXT NOT NULL DEFAULT 'valid' CHECK(validation_status IN ('valid', 'invalid', 'pending')),

    -- ==================== LIFECYCLE ====================
    vector_clock            TEXT NOT NULL DEFAULT '0',
    tombstone               INTEGER NOT NULL DEFAULT 0 CHECK(tombstone IN (0, 1)),
    lamport                 INTEGER NOT NULL DEFAULT 0
);

-- ==================== INDEXES ====================
CREATE INDEX IF NOT EXISTS idx_calendar_envelope ON st_calendar(envelope_id);
CREATE INDEX IF NOT EXISTS idx_calendar_source ON st_calendar(source_connector) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_calendar_event_type ON st_calendar(event_type) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_calendar_occurred ON st_calendar(occurred_at DESC) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_calendar_person ON st_calendar(person_id) WHERE person_id IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_calendar_start_time ON st_calendar(start_time) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_calendar_end_time ON st_calendar(end_time) WHERE end_time IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_calendar_status ON st_calendar(status) WHERE status IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_calendar_trace ON st_calendar(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_calendar_tenant_space ON st_calendar(tenant_id, space_id) WHERE tombstone = 0;
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_connector_event ON st_calendar(source_connector, connector_event_id);

-- ========================================================================================
-- TABLE 4: st_shopping - Shopping Domain
-- ========================================================================================
-- Purpose: Store shopping and e-commerce events from external connectors
-- Connectors: Amazon, Instacart, DoorDash, eBay, Shopify
-- Event Types: 10 types covering orders, deliveries, returns, subscriptions
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_shopping (
    -- ==================== IDENTITY ====================
    shopping_event_id       TEXT PRIMARY KEY DEFAULT ('shop_' || lower(hex(randomblob(16)))),
    envelope_id             TEXT NOT NULL,
    source_connector        TEXT NOT NULL,  -- 'amazon', 'instacart', 'doordash', 'ebay', 'shopify'
    connector_event_id      TEXT NOT NULL,  -- Original event ID from connector
    cognitive_trace_id      TEXT NOT NULL,

    -- ==================== EVENT CLASSIFICATION ====================
    event_type              TEXT NOT NULL CHECK(event_type IN (
        'order_placed',          -- Purchase confirmed, order created
        'order_shipped',         -- Package in transit, tracking number assigned
        'order_delivered',       -- Package received, delivery confirmed
        'order_cancelled',       -- Order cancelled by user or seller
        'return_initiated',      -- Return request submitted
        'refund_issued',         -- Money returned to customer
        'subscription_renewal',  -- Recurring subscription charged
        'price_drop_alert',      -- Tracked item price decreased
        'cart_abandoned',        -- Items left in cart without purchase
        'product_review'         -- Customer review posted
    )),
    occurred_at             INTEGER NOT NULL,  -- Unix timestamp (ms) of event occurrence

    -- ==================== STRUCTURED PAYLOAD ====================
    payload                 TEXT NOT NULL,  -- JSON blob with connector-specific fields

    -- ==================== COMMON EXTRACTED FIELDS ====================
    person_id               TEXT,  -- FK to people table (NULL if not mapped)
    order_id                TEXT,  -- External order ID from connector
    merchant                TEXT NOT NULL,  -- Merchant or seller name
    total_amount            REAL,  -- Total order amount
    currency                TEXT DEFAULT 'USD',  -- ISO 4217 currency code
    status                  TEXT,  -- Order status ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')

    -- ==================== ACCESS CONTROL ====================
    tenant_id               TEXT NOT NULL DEFAULT 'family_001',
    space_id                TEXT NOT NULL DEFAULT 'default',
    privacy_band            TEXT NOT NULL DEFAULT 'GREEN' CHECK(privacy_band IN ('GREEN', 'AMBER', 'RED')),
    owner_id                TEXT,
    visible_to              TEXT,  -- JSON array of user_ids

    -- ==================== METADATA ====================
    received_at             INTEGER NOT NULL,  -- Unix timestamp (ms) when envelope received
    processed_at            INTEGER NOT NULL,  -- Unix timestamp (ms) when event processed
    validation_status       TEXT NOT NULL DEFAULT 'valid' CHECK(validation_status IN ('valid', 'invalid', 'pending')),

    -- ==================== LIFECYCLE ====================
    vector_clock            TEXT NOT NULL DEFAULT '0',
    tombstone               INTEGER NOT NULL DEFAULT 0 CHECK(tombstone IN (0, 1)),
    lamport                 INTEGER NOT NULL DEFAULT 0
);

-- ==================== INDEXES ====================
CREATE INDEX IF NOT EXISTS idx_shopping_envelope ON st_shopping(envelope_id);
CREATE INDEX IF NOT EXISTS idx_shopping_source ON st_shopping(source_connector) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_shopping_event_type ON st_shopping(event_type) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_shopping_occurred ON st_shopping(occurred_at DESC) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_shopping_person ON st_shopping(person_id) WHERE person_id IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_shopping_order ON st_shopping(order_id) WHERE order_id IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_shopping_merchant ON st_shopping(merchant) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_shopping_status ON st_shopping(status) WHERE status IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_shopping_trace ON st_shopping(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_shopping_tenant_space ON st_shopping(tenant_id, space_id) WHERE tombstone = 0;
CREATE UNIQUE INDEX IF NOT EXISTS idx_shopping_connector_event ON st_shopping(source_connector, connector_event_id);

-- ========================================================================================
-- TABLE 5: st_envelope_metadata - Envelope Ingestion Tracking
-- ========================================================================================
-- Purpose: Track all connector ingestion attempts, routing, and validation
-- Used by: K0 gate layer, envelope validation pipeline
-- Relationship: One envelope → one domain table event
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_envelope_metadata (
    -- ==================== IDENTITY ====================
    envelope_id             TEXT PRIMARY KEY DEFAULT ('env_' || lower(hex(randomblob(16)))),
    cognitive_trace_id      TEXT NOT NULL,

    -- ==================== INGESTION ====================
    source_connector        TEXT NOT NULL,  -- Connector that sent the envelope
    connector_version       TEXT,  -- API version or SDK version
    received_at             INTEGER NOT NULL,  -- Unix timestamp (ms) when received at K0 gate
    raw_envelope            TEXT NOT NULL,  -- Original JSON envelope (immutable audit trail)

    -- ==================== CLASSIFICATION ====================
    domain                  TEXT CHECK(domain IN ('health', 'financial', 'calendar', 'shopping', 'unknown')),
    event_type              TEXT,  -- Specific event type within domain
    classification_confidence REAL CHECK(classification_confidence >= 0 AND classification_confidence <= 1),

    -- ==================== ROUTING ====================
    target_table            TEXT,  -- Table where event was stored ('st_health', 'st_financial', etc.)
    target_row_id           TEXT,  -- Primary key of inserted row in target table
    processed_at            INTEGER,  -- Unix timestamp (ms) when processing completed
    processing_duration_ms  INTEGER,  -- Time taken to process (ms)

    -- ==================== VALIDATION ====================
    validation_status       TEXT NOT NULL DEFAULT 'pending' CHECK(validation_status IN ('valid', 'invalid', 'pending', 'retrying')),
    validation_errors       TEXT,  -- JSON array of validation error messages
    schema_version          TEXT NOT NULL,  -- K0 envelope schema version used for validation

    -- ==================== METADATA ====================
    tenant_id               TEXT NOT NULL DEFAULT 'family_001',

    -- ==================== LIFECYCLE ====================
    vector_clock            TEXT NOT NULL DEFAULT '0',
    tombstone               INTEGER NOT NULL DEFAULT 0 CHECK(tombstone IN (0, 1)),
    lamport                 INTEGER NOT NULL DEFAULT 0
);

-- ==================== INDEXES ====================
CREATE INDEX IF NOT EXISTS idx_envelope_source ON st_envelope_metadata(source_connector) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_envelope_received ON st_envelope_metadata(received_at DESC) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_envelope_domain ON st_envelope_metadata(domain) WHERE domain IS NOT NULL AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_envelope_status ON st_envelope_metadata(validation_status) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_envelope_target ON st_envelope_metadata(target_table, target_row_id) WHERE target_table IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_envelope_trace ON st_envelope_metadata(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_envelope_tenant ON st_envelope_metadata(tenant_id) WHERE tombstone = 0;

-- ========================================================================================
-- TABLE 6: st_unprocessed_bag - Failed Validation & Retry Logic
-- ========================================================================================
-- Purpose: Store envelopes that failed validation for retry and manual review
-- Used by: K0 retry scheduler, admin dashboard, debugging
-- Lifecycle: Retries up to max_retries, then requires manual intervention
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_unprocessed_bag (
    -- ==================== IDENTITY ====================
    unprocessed_id          TEXT PRIMARY KEY DEFAULT ('unproc_' || lower(hex(randomblob(16)))),
    envelope_id             TEXT NOT NULL,  -- FK to st_envelope_metadata
    cognitive_trace_id      TEXT NOT NULL,

    -- ==================== FAILURE DETAILS ====================
    source_connector        TEXT NOT NULL,  -- Connector that sent the envelope
    raw_payload             TEXT NOT NULL,  -- Original payload (immutable)
    rejection_reason        TEXT NOT NULL,  -- Human-readable rejection reason
    error_details           TEXT,  -- JSON object with stack traces, validation errors
    received_at             INTEGER NOT NULL,  -- Unix timestamp (ms) when first received

    -- ==================== RETRY LOGIC ====================
    retry_count             INTEGER NOT NULL DEFAULT 0,  -- Number of retry attempts
    last_retry_at           INTEGER,  -- Unix timestamp (ms) of last retry attempt
    next_retry_at           INTEGER,  -- Unix timestamp (ms) for next scheduled retry
    max_retries             INTEGER NOT NULL DEFAULT 3,  -- Maximum retry attempts before giving up
    retry_status            TEXT NOT NULL DEFAULT 'pending' CHECK(retry_status IN ('pending', 'retrying', 'exhausted', 'resolved')),

    -- ==================== RESOLUTION ====================
    resolved_at             INTEGER,  -- Unix timestamp (ms) when issue resolved
    resolved_to_table       TEXT,  -- Target table if successfully reprocessed
    manual_review           INTEGER NOT NULL DEFAULT 0 CHECK(manual_review IN (0, 1)),  -- Requires human intervention

    -- ==================== METADATA ====================
    tenant_id               TEXT NOT NULL DEFAULT 'family_001',

    -- ==================== LIFECYCLE ====================
    vector_clock            TEXT NOT NULL DEFAULT '0',
    tombstone               INTEGER NOT NULL DEFAULT 0 CHECK(tombstone IN (0, 1)),
    lamport                 INTEGER NOT NULL DEFAULT 0
);

-- ==================== INDEXES ====================
CREATE INDEX IF NOT EXISTS idx_unprocessed_envelope ON st_unprocessed_bag(envelope_id);
CREATE INDEX IF NOT EXISTS idx_unprocessed_source ON st_unprocessed_bag(source_connector) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_unprocessed_status ON st_unprocessed_bag(retry_status) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_unprocessed_next_retry ON st_unprocessed_bag(next_retry_at) WHERE retry_status = 'pending' AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_unprocessed_manual ON st_unprocessed_bag(manual_review) WHERE manual_review = 1 AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_unprocessed_trace ON st_unprocessed_bag(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_unprocessed_tenant ON st_unprocessed_bag(tenant_id) WHERE tombstone = 0;

-- ========================================================================================
-- TABLE 7: st_connector_registry - Active Connector Management
-- ========================================================================================
-- Purpose: Registry of active connectors with sync state and authentication
-- Used by: K0 admin dashboard, connector health monitoring, webhook validation
-- Lifecycle: Connectors added by admin, updated by sync scheduler
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_connector_registry (
    -- ==================== IDENTITY ====================
    connector_id            TEXT PRIMARY KEY DEFAULT ('conn_' || lower(hex(randomblob(16)))),
    cognitive_trace_id      TEXT NOT NULL,

    -- ==================== CONNECTOR INFO ====================
    connector_name          TEXT NOT NULL UNIQUE,  -- Human-readable name ('Strava', 'Chase Bank', etc.)
    connector_type          TEXT NOT NULL CHECK(connector_type IN ('health', 'financial', 'calendar', 'shopping')),
    connector_version       TEXT,  -- API version or SDK version
    display_name            TEXT NOT NULL,  -- User-facing display name
    icon_url                TEXT,  -- URL to connector icon/logo

    -- ==================== SYNC STATE ====================
    active                  INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),  -- Is connector enabled?
    last_sync_at            INTEGER,  -- Unix timestamp (ms) of last successful sync
    next_sync_at            INTEGER,  -- Unix timestamp (ms) for next scheduled sync
    sync_frequency          INTEGER NOT NULL DEFAULT 900000,  -- Sync frequency in ms (default 15 min)
    sync_status             TEXT NOT NULL DEFAULT 'idle' CHECK(sync_status IN ('idle', 'syncing', 'error', 'paused')),

    -- ==================== STATISTICS ====================
    total_events_sent       INTEGER NOT NULL DEFAULT 0,  -- Total events ingested from this connector
    events_today            INTEGER NOT NULL DEFAULT 0,  -- Events ingested today (reset daily)
    success_rate            REAL CHECK(success_rate >= 0 AND success_rate <= 1),  -- Percentage of successful ingestions
    avg_latency_ms          INTEGER,  -- Average processing latency (ms)

    -- ==================== AUTHENTICATION ====================
    auth_method             TEXT CHECK(auth_method IN ('oauth2', 'api_key', 'webhook', 'basic_auth')),
    auth_expires_at         INTEGER,  -- Unix timestamp (ms) when auth token expires

    -- ==================== METADATA ====================
    tenant_id               TEXT NOT NULL DEFAULT 'family_001',
    created_at              INTEGER NOT NULL,
    updated_at              INTEGER NOT NULL,

    -- ==================== LIFECYCLE ====================
    vector_clock            TEXT NOT NULL DEFAULT '0',
    tombstone               INTEGER NOT NULL DEFAULT 0 CHECK(tombstone IN (0, 1)),
    lamport                 INTEGER NOT NULL DEFAULT 0
);

-- ==================== INDEXES ====================
CREATE INDEX IF NOT EXISTS idx_connector_type ON st_connector_registry(connector_type) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_connector_active ON st_connector_registry(active) WHERE active = 1 AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_connector_sync_status ON st_connector_registry(sync_status) WHERE tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_connector_next_sync ON st_connector_registry(next_sync_at) WHERE active = 1 AND tombstone = 0;
CREATE INDEX IF NOT EXISTS idx_connector_trace ON st_connector_registry(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_connector_tenant ON st_connector_registry(tenant_id) WHERE tombstone = 0;

-- ========================================================================================
-- MIGRATION COMPLETE: Phase 3 Connector Domain Tables
-- ========================================================================================
-- Tables Created: 7
-- Event Types Supported: 38 total (10 health + 10 financial + 8 calendar + 10 shopping)
-- Connectors Supported: Strava, Apple Health, Fitbit, MyFitnessPal, Epic MyChart, CVS Pharmacy,
--                       Plaid, Chase, Amex, Fidelity, PayPal, Venmo, Robinhood, Mint,
--                       Google Calendar, Outlook, Apple Calendar,
--                       Amazon, Instacart, DoorDash, eBay, Shopify
-- ========================================================================================
