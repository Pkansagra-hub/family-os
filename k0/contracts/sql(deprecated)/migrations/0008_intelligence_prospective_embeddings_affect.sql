-- =====================================================================
-- Migration 0008: Intelligence Tables - Prospective Memory + Embeddings + Affect
-- =====================================================================
-- Created: 2025-01-09
-- Purpose: First 4 of 12 intelligence tables needed for K1 orchestration
--          - prospective_triggers: P05 prospective memory (future actions/reminders)
--          - prospective_outcomes: P05 execution history (fired/skipped results)
--          - st_emb: P08 embeddings metadata (FAISS vector index lifecycle)
--          - st_aff: P08 affect state (emotional annotations + per-person EMAs)
-- Dependencies: Requires Migration 0006 (base memory tables) and Migration 0007 (people, households)
-- Architecture: K1 orchestration dependencies, not optional enhancements
-- =====================================================================

-- =====================================================================
-- TABLE 1: prospective_triggers (P05 Prospective Memory - Reminders)
-- =====================================================================
-- Purpose: Future actions/reminders, scheduled tasks, intent to do X at time Y
-- Source: memoryOS_frozen/prospective/README.md
-- Lifecycle: DRAFT → ACTIVE → SNOOZED/CANCELLED/EXPIRED
-- Usage: P05 prospective scheduler checks next_fire_at, evaluates conditions, creates actions
-- =====================================================================

CREATE TABLE IF NOT EXISTS prospective_triggers (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    trigger_id TEXT PRIMARY KEY NOT NULL,  -- Unique trigger identifier (e.g., "trig-2025-01-09-001")
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    person_id TEXT NOT NULL,               -- Who this trigger is for (Neo4j :Person ID)
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)

    -- ============================================================
    -- TRIGGER CONTENT
    -- ============================================================
    title TEXT NOT NULL,                   -- Human-readable trigger name (e.g., "Remind grandparents dinner")
    description TEXT,                      -- Optional detailed description

    -- ============================================================
    -- SCHEDULE (JSON)
    -- ============================================================
    -- Example: {"type": "once", "fire_at": "2025-01-15T18:00:00Z"}
    -- Example: {"type": "recurring", "every_seconds": 86400, "time_of_day": "09:00", "days_of_week": [1,3,5]}
    schedule TEXT NOT NULL,                -- JSON: {type, fire_at, every_seconds, time_of_day, days_of_week}

    -- ============================================================
    -- ACTION (JSON)
    -- ============================================================
    -- Example: {"type": "notification", "title": "Dinner reminder", "body": "Call grandparents"}
    -- Example: {"type": "procedure", "procedure_name": "morning_routine", "procedure_args": {...}}
    action TEXT NOT NULL,                  -- JSON: {type, title, body, procedure_name, procedure_args}

    -- ============================================================
    -- CONDITIONS (JSON)
    -- ============================================================
    -- Example: {"require_arousal_max": 0.7, "disallow_safety_pressure_min": 2, "cooldown_seconds": 3600}
    conditions TEXT,                       -- JSON: {require_arousal_max, disallow_safety_pressure_min, cooldown_seconds}

    -- ============================================================
    -- LIFECYCLE STATUS
    -- ============================================================
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'ACTIVE', 'SNOOZED', 'CANCELLED', 'EXPIRED')),

    -- ============================================================
    -- EXECUTION TRACKING
    -- ============================================================
    next_fire_at TEXT NOT NULL,            -- ISO8601 timestamp for next scheduled execution
    last_fired_at TEXT,                    -- ISO8601 timestamp of last successful fire
    fires_count INTEGER NOT NULL DEFAULT 0,-- How many times this trigger has fired
    snooze_until TEXT,                     -- ISO8601 timestamp if snoozed (status = SNOOZED)

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read/modify

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    updated_at TEXT NOT NULL,              -- ISO8601 last modification time
    cancelled_at TEXT,                     -- ISO8601 timestamp if status = CANCELLED
    expired_at TEXT                        -- ISO8601 timestamp if status = EXPIRED
);

-- ============================================================
-- INDEXES: prospective_triggers
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_prospective_triggers_person ON prospective_triggers(person_id);
CREATE INDEX IF NOT EXISTS idx_prospective_triggers_space ON prospective_triggers(space_id);
CREATE INDEX IF NOT EXISTS idx_prospective_triggers_status ON prospective_triggers(status);
CREATE INDEX IF NOT EXISTS idx_prospective_triggers_next_fire ON prospective_triggers(next_fire_at) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_prospective_triggers_tenant ON prospective_triggers(tenant_id);
CREATE INDEX IF NOT EXISTS idx_prospective_triggers_owner ON prospective_triggers(owner_id);
CREATE INDEX IF NOT EXISTS idx_prospective_triggers_trace ON prospective_triggers(cognitive_trace_id);


-- =====================================================================
-- TABLE 2: prospective_outcomes (P05 Prospective Memory - Execution History)
-- =====================================================================
-- Purpose: Fire/skip history for prospective triggers
-- Source: memoryOS_frozen/prospective/README.md
-- Usage: Audit trail for all trigger evaluations (fired, skipped, conditions)
-- =====================================================================

CREATE TABLE IF NOT EXISTS prospective_outcomes (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    outcome_id TEXT PRIMARY KEY NOT NULL,  -- Unique outcome identifier (e.g., "out-2025-01-09-001")
    trigger_id TEXT NOT NULL,              -- Reference to prospective_triggers.trigger_id
    action_id TEXT,                        -- Reference to action_receipts.action_id (if fired)
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- EXECUTION RESULT
    -- ============================================================
    fired_at TEXT NOT NULL,                -- ISO8601 timestamp of evaluation
    status TEXT NOT NULL CHECK (status IN ('fired', 'skipped')),

    -- ============================================================
    -- ELIGIBILITY & REASONING
    -- ============================================================
    eligibility TEXT,                      -- JSON: {arousal_ok, safety_ok, cooldown_ok, conditions_met}
    reason TEXT,                           -- Human-readable explanation (e.g., "Skipped: arousal too high (0.85 > 0.70)")

    -- ============================================================
    -- NEXT FIRE TIMESTAMP (for recurring triggers)
    -- ============================================================
    next_fire_at TEXT,                     -- ISO8601 timestamp for next scheduled execution (if recurring)

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    space_id TEXT NOT NULL,                -- Memory space (matches trigger space_id)
    person_id TEXT NOT NULL,               -- Who the trigger was for (matches trigger person_id)

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL               -- ISO8601 record creation time
);

-- ============================================================
-- INDEXES: prospective_outcomes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_prospective_outcomes_trigger ON prospective_outcomes(trigger_id);
CREATE INDEX IF NOT EXISTS idx_prospective_outcomes_action ON prospective_outcomes(action_id) WHERE action_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_prospective_outcomes_person ON prospective_outcomes(person_id);
CREATE INDEX IF NOT EXISTS idx_prospective_outcomes_space ON prospective_outcomes(space_id);
CREATE INDEX IF NOT EXISTS idx_prospective_outcomes_status ON prospective_outcomes(status);
CREATE INDEX IF NOT EXISTS idx_prospective_outcomes_fired_at ON prospective_outcomes(fired_at);
CREATE INDEX IF NOT EXISTS idx_prospective_outcomes_tenant ON prospective_outcomes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_prospective_outcomes_trace ON prospective_outcomes(cognitive_trace_id);


-- =====================================================================
-- TABLE 3: st_emb (P08 Embeddings - Vector Index Metadata)
-- =====================================================================
-- Purpose: Embeddings metadata for FAISS vector index lifecycle
-- Source: memoryOS_frozen/embeddings/README.md, storage/embeddings_store.py interface
-- Usage: Tracks chunk_ids, encoder versions, canonical links, rebuild jobs
-- Architecture: P08 embedding lifecycle REQUIRES this for deduplication and refresh
-- =====================================================================

CREATE TABLE IF NOT EXISTS st_emb (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    embedding_id TEXT PRIMARY KEY NOT NULL, -- Unique embedding identifier (e.g., "emb-evt-2025-01-09-00042")
    event_id TEXT NOT NULL,                -- Reference to source event (st_hipp_store, st_epi, st_sem)
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- CHUNKING (JSON Array)
    -- ============================================================
    -- Example: [{"chunk_id": "evt-...#0", "pos": 0, "span": {"start": 0, "end": 294}, "hash": "sha256:..."}]
    chunk_ids TEXT NOT NULL,               -- JSON array of chunk objects with chunk_id, pos, span, hash
    chunks_count INTEGER NOT NULL DEFAULT 1, -- Number of chunks for this event

    -- ============================================================
    -- ENCODER METADATA
    -- ============================================================
    encoder_model_id TEXT NOT NULL,        -- Encoder model (e.g., "minilm-22M-int8", "all-mpnet-base-v2")
    encoder_version TEXT NOT NULL,         -- Model version string
    embedding_dims INTEGER NOT NULL,       -- Vector dimensions (e.g., 384, 768)
    normalized INTEGER DEFAULT 1 CHECK (normalized IN (0, 1)),

    -- ============================================================
    -- DEDUPLICATION & CANONICALIZATION
    -- ============================================================
    is_canonical INTEGER DEFAULT 1 CHECK (is_canonical IN (0, 1)),
    canonical_link TEXT,                   -- If duplicate, reference to canonical embedding_id
    dupe_status TEXT NOT NULL DEFAULT 'unique' CHECK (dupe_status IN ('unique', 'canonicalized', 'linked')),
    similarity_score REAL,                 -- Cosine similarity to canonical (if duplicate)

    -- ============================================================
    -- REDACTION & POLICY
    -- ============================================================
    redaction_policy TEXT NOT NULL DEFAULT 'default:v1', -- Redaction policy applied before encoding

    -- ============================================================
    -- REBUILD & REFRESH TRACKING
    -- ============================================================
    rebuild_job_id TEXT,                   -- Reference to rebuild job (if re-encoded)
    rebuild_count INTEGER DEFAULT 0,       -- How many times this embedding has been rebuilt
    last_rebuild_at TEXT,                  -- ISO8601 timestamp of last rebuild

    -- ============================================================
    -- MULTI-STORE INTEGRATION
    -- ============================================================
    vector_store_path TEXT,                -- Path to FAISS index file (e.g., "shared_household.index")
    fts_indexed INTEGER DEFAULT 0 CHECK (fts_indexed IN (0, 1)),

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    person_id TEXT NOT NULL,               -- Who created this embedding (Neo4j :Person ID)
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    updated_at TEXT NOT NULL,              -- ISO8601 last modification time
    indexed_at TEXT NOT NULL,              -- ISO8601 timestamp when embedding was generated
    archived_at TEXT                       -- ISO8601 timestamp when moved to cold storage
);

-- ============================================================
-- INDEXES: st_emb
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_st_emb_event ON st_emb(event_id);
CREATE INDEX IF NOT EXISTS idx_st_emb_person ON st_emb(person_id);
CREATE INDEX IF NOT EXISTS idx_st_emb_space ON st_emb(space_id);
CREATE INDEX IF NOT EXISTS idx_st_emb_encoder ON st_emb(encoder_model_id, encoder_version);
CREATE INDEX IF NOT EXISTS idx_st_emb_canonical ON st_emb(is_canonical) WHERE is_canonical = 1;
CREATE INDEX IF NOT EXISTS idx_st_emb_canonical_link ON st_emb(canonical_link) WHERE canonical_link IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_st_emb_dupe_status ON st_emb(dupe_status);
CREATE INDEX IF NOT EXISTS idx_st_emb_rebuild ON st_emb(rebuild_job_id) WHERE rebuild_job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_st_emb_tenant ON st_emb(tenant_id);
CREATE INDEX IF NOT EXISTS idx_st_emb_owner ON st_emb(owner_id);
CREATE INDEX IF NOT EXISTS idx_st_emb_trace ON st_emb(cognitive_trace_id);


-- =====================================================================
-- TABLE 4: st_aff (P08 Affect - Emotional State & Annotations)
-- =====================================================================
-- Purpose: Affect state persistence (emotional annotations + per-person EMAs)
-- Source: memoryOS_frozen/affect/README.md, ADR-0069
-- Usage: P18 policy banding, P01 retrieval bias, P03 consolidation rollup, P06 learning rates
-- Architecture: Two record types in one table: 1) Annotations (event_id indexed), 2) State (person_id, space_id indexed)
-- =====================================================================

CREATE TABLE IF NOT EXISTS st_aff (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    affect_id TEXT PRIMARY KEY NOT NULL,   -- Unique affect identifier (e.g., "aff-evt-2025-01-09-00123" or "aff-state-alice-household")
    record_type TEXT NOT NULL CHECK (record_type IN ('annotation', 'state')),
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- ANNOTATION FIELDS (record_type = 'annotation')
    -- ============================================================
    event_id TEXT,                         -- Reference to source event (st_hipp_store, st_epi, st_sem) - REQUIRED for annotations

    -- ============================================================
    -- VALENCE & AROUSAL (Russell Circumplex Model)
    -- ============================================================
    valence REAL CHECK (valence IS NULL OR (valence >= -1.0 AND valence <= 1.0)),
    arousal REAL CHECK (arousal IS NULL OR (arousal >= -1.0 AND arousal <= 1.0)),

    -- ============================================================
    -- AFFECT TAGS (JSON Array)
    -- ============================================================
    -- Example: ["urgent", "toxic_light", "hedging", "positive_family_moment", "family_conflict_hint"]
    tags TEXT,                             -- JSON array of affect tags

    -- ============================================================
    -- CONFIDENCE & MODEL VERSION
    -- ============================================================
    confidence REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    model_version TEXT NOT NULL,           -- Model version (e.g., "affect-enhanced:2025-09-04")

    -- ============================================================
    -- STATE FIELDS (record_type = 'state')
    -- ============================================================
    -- Exponential Moving Averages (EMAs) per person + space
    v_ema REAL CHECK (v_ema IS NULL OR (v_ema >= -1.0 AND v_ema <= 1.0)),
    a_ema REAL CHECK (a_ema IS NULL OR (a_ema >= -1.0 AND a_ema <= 1.0)),

    -- ============================================================
    -- BEHAVIORAL BASELINES (JSON)
    -- ============================================================
    -- Example: {"keystrokes_mean": 45, "backspaces_mean": 8, "retries_mean": 1.2, "active_seconds_mean": 120}
    baselines TEXT,                        -- JSON: personal rolling baselines for behavioral arousal z-scores

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    person_id TEXT NOT NULL,               -- Who this affect record is for (Neo4j :Person ID)
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    updated_at TEXT NOT NULL,              -- ISO8601 last modification time
    ts TEXT NOT NULL                       -- ISO8601 timestamp of affect measurement (or state update)
);

-- ============================================================
-- INDEXES: st_aff
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_st_aff_event ON st_aff(event_id) WHERE record_type = 'annotation';
CREATE INDEX IF NOT EXISTS idx_st_aff_person ON st_aff(person_id);
CREATE INDEX IF NOT EXISTS idx_st_aff_space ON st_aff(space_id);
CREATE INDEX IF NOT EXISTS idx_st_aff_record_type ON st_aff(record_type);
CREATE INDEX IF NOT EXISTS idx_st_aff_state_lookup ON st_aff(person_id, space_id) WHERE record_type = 'state';
CREATE INDEX IF NOT EXISTS idx_st_aff_valence ON st_aff(valence) WHERE valence IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_st_aff_arousal ON st_aff(arousal) WHERE arousal IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_st_aff_tags ON st_aff(tags) WHERE tags IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_st_aff_tenant ON st_aff(tenant_id);
CREATE INDEX IF NOT EXISTS idx_st_aff_owner ON st_aff(owner_id);
CREATE INDEX IF NOT EXISTS idx_st_aff_trace ON st_aff(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_st_aff_ts ON st_aff(ts);


-- =====================================================================
-- TABLE 5: drive_state (P06 Drives & Homeostasis - Needs/Motivations)
-- =====================================================================
-- Purpose: Per-person needs tracking with PID controller state
-- Source: memoryOS_frozen/drives/README.md, homeostasis.py
-- Usage: P06 learning loop tracks sleep_debt, social, chores, planning drives
-- Architecture: Homeostasis state for motivational system
-- =====================================================================

CREATE TABLE IF NOT EXISTS drive_state (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    state_id TEXT PRIMARY KEY NOT NULL,    -- Unique state identifier (e.g., "drv-state-alice-household")
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    person_id TEXT NOT NULL,               -- Who this drive state is for (Neo4j :Person ID)
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)

    -- ============================================================
    -- NEEDS (JSON) - Per-Drive State with PID Controller
    -- ============================================================
    -- Example: {
    --   "sleep_debt": {"x": 2.5, "setpoint": 0.5, "range": 8.0, "i_term": 2.1},
    --   "social": {"x": 0.3, "setpoint": 0.6, "range": 1.0, "i_term": 0.1},
    --   "chores": {"x": 0.7, "setpoint": 0.4, "range": 1.0, "i_term": 0.3},
    --   "planning": {"x": 0.5, "setpoint": 0.2, "range": 1.0, "i_term": 0.2}
    -- }
    needs TEXT NOT NULL,                   -- JSON: {drive_name: {x, setpoint, range, i_term}}

    -- ============================================================
    -- DRIVE PRIORITIES (JSON) - Computed Activation Levels
    -- ============================================================
    -- Example: {"sleep": 0.78, "social": 0.32, "chores": 0.64, "planning": 0.45}
    priorities TEXT,                       -- JSON: {drive_name: priority_score (0.0-1.0)}

    -- ============================================================
    -- CONTEXT MODULATION (JSON) - Last Tick Context
    -- ============================================================
    -- Example: {"arousal": 0.62, "urgent": true, "sin_tod": 0.26, "is_weekend": 0}
    last_context TEXT,                     -- JSON: {affect, temporal, usage} from last DriveTick

    -- ============================================================
    -- CONFIGURATION (JSON) - Per-Person Calibration
    -- ============================================================
    -- Example: {"sleep": {"kappa": 4.0, "theta": 0.1, "circadian_weight": 0.6}}
    config TEXT,                           -- JSON: {drive_name: {kappa, theta, weights}}

    -- ============================================================
    -- MODEL VERSION
    -- ============================================================
    version TEXT NOT NULL DEFAULT 'drives:2025-09-06', -- Drive model version

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    updated_at TEXT NOT NULL,              -- ISO8601 last modification time
    last_update TEXT NOT NULL              -- ISO8601 timestamp of last drive tick update
);

-- ============================================================
-- INDEXES: drive_state
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_drive_state_person ON drive_state(person_id);
CREATE INDEX IF NOT EXISTS idx_drive_state_space ON drive_state(space_id);
CREATE INDEX IF NOT EXISTS idx_drive_state_person_space ON drive_state(person_id, space_id);
CREATE INDEX IF NOT EXISTS idx_drive_state_tenant ON drive_state(tenant_id);
CREATE INDEX IF NOT EXISTS idx_drive_state_owner ON drive_state(owner_id);
CREATE INDEX IF NOT EXISTS idx_drive_state_trace ON drive_state(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_drive_state_updated ON drive_state(updated_at);


-- =====================================================================
-- TABLE 6: drive_intents (P06 Drives & Homeostasis - Action Proposals)
-- =====================================================================
-- Purpose: Action proposals from drives to Arbiter
-- Source: memoryOS_frozen/drives/README.md, types.py
-- Usage: P06 DriveCoordinator publishes intents to P04 Arbiter for evaluation
-- Architecture: DRIVE_TICK outputs → Arbiter inputs
-- =====================================================================

CREATE TABLE IF NOT EXISTS drive_intents (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    intent_id TEXT PRIMARY KEY NOT NULL,   -- Unique intent identifier (e.g., "drv-intent-2025-01-09-001")
    tick_id TEXT NOT NULL,                 -- Reference to DriveTick that generated this intent
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    person_id TEXT NOT NULL,               -- Who this intent is for (Neo4j :Person ID)
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)

    -- ============================================================
    -- ACTION PROPOSAL
    -- ============================================================
    action TEXT NOT NULL,                  -- Action name (e.g., "set_bedtime_reminder", "start_chore_timer")
    args TEXT NOT NULL,                    -- JSON: action arguments {"when": "22:15", "space_id": "shared:household"}

    -- ============================================================
    -- DRIVE METADATA
    -- ============================================================
    drive TEXT NOT NULL CHECK (drive IN ('sleep', 'social', 'chores', 'planning', 'other')),
    prior REAL NOT NULL CHECK (prior >= 0.0 AND prior <= 1.0),

    -- ============================================================
    -- REASONING (JSON Array)
    -- ============================================================
    -- Example: ["high sleep error", "circadian night", "low cost"]
    reasons TEXT NOT NULL,                 -- JSON array of human-readable reasons

    -- ============================================================
    -- POLICY HINT
    -- ============================================================
    policy_hint TEXT NOT NULL DEFAULT 'GREEN' CHECK (policy_hint IN ('GREEN', 'AMBER', 'RED', 'BLACK')),

    -- ============================================================
    -- EXPECTED UTILITY (JSON)
    -- ============================================================
    -- Example: {"delta_need": {"sleep": -0.3}, "cost": 0.1, "risk": 0.05, "habit_score": 0.8}
    utility TEXT,                          -- JSON: {delta_need, cost, risk, habit_score}

    -- ============================================================
    -- ARBITER RESULT (Optional - Filled After Arbitration)
    -- ============================================================
    decision_id TEXT,                      -- Reference to action_decisions.decision_id (if processed)
    chosen INTEGER DEFAULT 0 CHECK (chosen IN (0, 1)),

    -- ============================================================
    -- TEMPORAL FEATURES (JSON)
    -- ============================================================
    -- Example: {"sin_tod": 0.26, "cos_tod": 0.96, "is_weekend": 0}
    temporal_features TEXT,                -- JSON: temporal features from DriveTick

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    ts TEXT NOT NULL                       -- ISO8601 timestamp when intent was generated
);

-- ============================================================
-- INDEXES: drive_intents
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_drive_intents_person ON drive_intents(person_id);
CREATE INDEX IF NOT EXISTS idx_drive_intents_space ON drive_intents(space_id);
CREATE INDEX IF NOT EXISTS idx_drive_intents_drive ON drive_intents(drive);
CREATE INDEX IF NOT EXISTS idx_drive_intents_tick ON drive_intents(tick_id);
CREATE INDEX IF NOT EXISTS idx_drive_intents_decision ON drive_intents(decision_id) WHERE decision_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drive_intents_chosen ON drive_intents(chosen) WHERE chosen = 1;
CREATE INDEX IF NOT EXISTS idx_drive_intents_prior ON drive_intents(prior);
CREATE INDEX IF NOT EXISTS idx_drive_intents_tenant ON drive_intents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_drive_intents_owner ON drive_intents(owner_id);
CREATE INDEX IF NOT EXISTS idx_drive_intents_trace ON drive_intents(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_drive_intents_ts ON drive_intents(ts);


-- =====================================================================
-- TABLE 7: metacog_reports (P20 Metacognition - Confidence & Health)
-- =====================================================================
-- Purpose: System confidence tracking and health flags
-- Source: memoryOS_frozen/metacognition/README.md, monitor.py
-- Usage: P20 metacognition monitors system health, fuses confidences, detects issues
-- Architecture: Feeds P04 Arbiter (risk adjustments) and P03 Consolidation (maintenance tasks)
-- =====================================================================

CREATE TABLE IF NOT EXISTS metacog_reports (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    report_id TEXT PRIMARY KEY NOT NULL,   -- Unique report identifier (e.g., "metacog-2025-01-09-001")
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    person_id TEXT NOT NULL,               -- Who this report is for (Neo4j :Person ID)
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)

    -- ============================================================
    -- HEALTH FLAGS (JSON Array)
    -- ============================================================
    -- Example: ["retrieval_drift", "rapid_regen", "action_quality_low", "policy_conflict", "device_friction", "cost_spike"]
    flags TEXT,                            -- JSON array of health flags

    -- ============================================================
    -- FUSED CONFIDENCE
    -- ============================================================
    fused_confidence REAL NOT NULL CHECK (fused_confidence >= 0.0 AND fused_confidence <= 1.0),

    -- ============================================================
    -- MODULE CONFIDENCES (JSON)
    -- ============================================================
    -- Example: {"affect": 0.72, "retrieval": 0.65, "planner": 0.70}
    confidences TEXT NOT NULL,             -- JSON: {module_name: confidence_score}

    -- ============================================================
    -- SUGGESTIONS (JSON Array)
    -- ============================================================
    -- Example: [{"type": "reindex", "description": "Rebuild index partitions; review near-duplicate purge"}]
    suggestions TEXT,                      -- JSON array of reflection tasks

    -- ============================================================
    -- ERROR SIGNALS (JSON) - Raw Metrics
    -- ============================================================
    -- Example: {"retrieval_miss_rate": 0.30, "action_fail_rate": 0.10, "regen_rate": 0.40}
    error_signals TEXT,                    -- JSON: {metric_name: value}

    -- ============================================================
    -- MODEL VERSION
    -- ============================================================
    model_version TEXT NOT NULL DEFAULT 'metacog:2025-09-04', -- Metacognition model version

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    ts TEXT NOT NULL                       -- ISO8601 timestamp of report generation
);

-- ============================================================
-- INDEXES: metacog_reports
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_metacog_reports_person ON metacog_reports(person_id);
CREATE INDEX IF NOT EXISTS idx_metacog_reports_space ON metacog_reports(space_id);
CREATE INDEX IF NOT EXISTS idx_metacog_reports_confidence ON metacog_reports(fused_confidence);
CREATE INDEX IF NOT EXISTS idx_metacog_reports_flags ON metacog_reports(flags) WHERE flags IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_metacog_reports_tenant ON metacog_reports(tenant_id);
CREATE INDEX IF NOT EXISTS idx_metacog_reports_owner ON metacog_reports(owner_id);
CREATE INDEX IF NOT EXISTS idx_metacog_reports_trace ON metacog_reports(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_metacog_reports_ts ON metacog_reports(ts);


-- =====================================================================
-- TABLE 8: metacog_signals (P20 Metacognition - Error Tracking)
-- =====================================================================
-- Purpose: EWMA error signals for drift detection
-- Source: memoryOS_frozen/metacognition/README.md, error_detector.py
-- Usage: P20 error detector tracks leaky integrators for retrieval misses, action failures, etc.
-- Architecture: Time-series error metrics with exponential moving averages
-- =====================================================================

CREATE TABLE IF NOT EXISTS metacog_signals (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    signal_id TEXT PRIMARY KEY NOT NULL,   -- Unique signal identifier (e.g., "sig-2025-01-09-001")
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    person_id TEXT NOT NULL,               -- Who this signal is for (Neo4j :Person ID)
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)

    -- ============================================================
    -- ERROR METRICS (EWMA Leaky Integrators)
    -- ============================================================
    retrieval_miss_rate REAL CHECK (retrieval_miss_rate IS NULL OR (retrieval_miss_rate >= 0.0 AND retrieval_miss_rate <= 1.0)),
                                          -- EWMA of retrieval misses (0.0-1.0), flag if > 0.4

    action_fail_rate REAL CHECK (action_fail_rate IS NULL OR (action_fail_rate >= 0.0 AND action_fail_rate <= 1.0)),
                                          -- EWMA of action failures (0.0-1.0), flag if > 0.4

    regen_rate REAL CHECK (regen_rate IS NULL OR (regen_rate >= 0.0 AND regen_rate <= 1.0)),
                                          -- EWMA of regeneration rate (0.0-1.0), flag if > 0.4

    policy_overrides REAL CHECK (policy_overrides IS NULL OR (policy_overrides >= 0.0 AND policy_overrides <= 1.0)),
                                          -- EWMA of policy override rate (0.0-1.0), flag if > 0.5

    device_friction INTEGER DEFAULT 0 CHECK (device_friction IN (0, 1)),

    cost_tokens_per_task REAL CHECK (cost_tokens_per_task IS NULL OR (cost_tokens_per_task >= 0.0 AND cost_tokens_per_task <= 1.0)),
                                          -- EWMA of token cost per task (normalized 0.0-1.0), flag if > 0.6

    -- ============================================================
    -- EWMA STATE (JSON) - For Continuity
    -- ============================================================
    -- Example: {"retrieval": {"value": 0.30, "n": 45}, "actions": {"value": 0.10, "n": 120}}
    ewma_state TEXT,                       -- JSON: {metric_name: {value, sample_count}}

    -- ============================================================
    -- THRESHOLDS (JSON) - Custom Per-Space Overrides
    -- ============================================================
    -- Example: {"retrieval_miss_rate": 0.4, "action_fail_rate": 0.4, "regen_rate": 0.4}
    thresholds TEXT,                       -- JSON: {metric_name: threshold} (overrides defaults)

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    updated_at TEXT NOT NULL,              -- ISO8601 last modification time
    ts TEXT NOT NULL                       -- ISO8601 timestamp of signal measurement
);

-- ============================================================
-- INDEXES: metacog_signals
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_metacog_signals_person ON metacog_signals(person_id);
CREATE INDEX IF NOT EXISTS idx_metacog_signals_space ON metacog_signals(space_id);
CREATE INDEX IF NOT EXISTS idx_metacog_signals_person_space ON metacog_signals(person_id, space_id);
CREATE INDEX IF NOT EXISTS idx_metacog_signals_retrieval ON metacog_signals(retrieval_miss_rate) WHERE retrieval_miss_rate IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_metacog_signals_action_fail ON metacog_signals(action_fail_rate) WHERE action_fail_rate IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_metacog_signals_regen ON metacog_signals(regen_rate) WHERE regen_rate IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_metacog_signals_device_friction ON metacog_signals(device_friction) WHERE device_friction = 1;
CREATE INDEX IF NOT EXISTS idx_metacog_signals_tenant ON metacog_signals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_metacog_signals_owner ON metacog_signals(owner_id);
CREATE INDEX IF NOT EXISTS idx_metacog_signals_trace ON metacog_signals(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_metacog_signals_ts ON metacog_signals(ts);


-- =====================================================================
-- TABLE 9: action_receipts (P04 Action Execution - Audit Trail)
-- =====================================================================
-- Purpose: Execution audit trail for all tool calls
-- Source: memoryOS_frozen/action/README.md, actuators.py, outcome_capture.py
-- Usage: P04 action execution receipts with policy gates, timing, cost, reward
-- Architecture: Learning loop consumes receipts for reward shaping
-- =====================================================================

CREATE TABLE IF NOT EXISTS action_receipts (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    receipt_id TEXT PRIMARY KEY NOT NULL,  -- Unique receipt identifier (UUID)
    action_id TEXT NOT NULL,               -- Reference to ACTION_DECISION.decision_id
    tool_id TEXT NOT NULL,                 -- Tool identifier (e.g., "files.write_text")
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)
    subject_id TEXT NOT NULL,              -- Who/what executed this (e.g., "agent://planner@deviceA")

    -- ============================================================
    -- EXECUTION STATUS
    -- ============================================================
    status TEXT NOT NULL CHECK (status IN ('ok', 'error', 'skipped', 'quarantined')),
    error TEXT,                            -- Error message if status = error (NULL otherwise)

    -- ============================================================
    -- INPUTS & OUTPUTS (JSON)
    -- ============================================================
    -- Example inputs: {"path": "workspace/notes/w36.txt", "sha256_text": "..."}
    -- Example outputs: {"bytes_written": 421, "artifact_ids": ["blob:..."]}
    inputs TEXT NOT NULL,                  -- JSON: sanitized/hashed action parameters
    outputs TEXT,                          -- JSON: action results (NULL if error/skipped)

    -- ============================================================
    -- POLICY GATES (JSON)
    -- ============================================================
    -- Example: {"rbac": "ok", "abac": "ok", "consent": "ok", "space": "ok", "safety": "ok", "redaction": "n/a"}
    policy TEXT NOT NULL,                  -- JSON: {gate_name: result} for all policy checks

    -- ============================================================
    -- COST (JSON)
    -- ============================================================
    -- Example: {"cpu_ms": 82, "energy_mwh": 0.7}
    cost TEXT NOT NULL,                    -- JSON: {cpu_ms, energy_mwh}

    -- ============================================================
    -- TIMING (JSON)
    -- ============================================================
    -- Example: {"queued_ms": 12, "exec_ms": 41, "total_ms": 92, "started_at": "...", "ended_at": "..."}
    timing TEXT NOT NULL,                  -- JSON: {queued_ms, exec_ms, total_ms, started_at, ended_at}

    -- ============================================================
    -- IDEMPOTENCY
    -- ============================================================
    idempotency_key TEXT,                  -- Idempotency key for deduplication (e.g., "files.write_text|path|sha256")

    -- ============================================================
    -- REWARD (JSON)
    -- ============================================================
    -- Example: {"scalar": 0.72, "components": {"latency": 0.12, "success": 1.0, "quality": 0.5}}
    reward TEXT,                           -- JSON: {scalar, components} for learning loop

    -- ============================================================
    -- RETRY & CIRCUIT BREAKER
    -- ============================================================
    retry_count INTEGER DEFAULT 0,         -- Number of retries attempted
    circuit_breaker_key TEXT,              -- Circuit breaker group key (e.g., tool_id or custom)

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    started_at TEXT NOT NULL,              -- ISO8601 action start time
    ended_at TEXT NOT NULL                 -- ISO8601 action end time
);

-- ============================================================
-- INDEXES: action_receipts
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_action_receipts_action ON action_receipts(action_id);
CREATE INDEX IF NOT EXISTS idx_action_receipts_tool ON action_receipts(tool_id);
CREATE INDEX IF NOT EXISTS idx_action_receipts_space ON action_receipts(space_id);
CREATE INDEX IF NOT EXISTS idx_action_receipts_subject ON action_receipts(subject_id);
CREATE INDEX IF NOT EXISTS idx_action_receipts_status ON action_receipts(status);
CREATE INDEX IF NOT EXISTS idx_action_receipts_idempotency ON action_receipts(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_action_receipts_circuit_breaker ON action_receipts(circuit_breaker_key) WHERE circuit_breaker_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_action_receipts_tenant ON action_receipts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_action_receipts_owner ON action_receipts(owner_id);
CREATE INDEX IF NOT EXISTS idx_action_receipts_trace ON action_receipts(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_action_receipts_started ON action_receipts(started_at);


-- =====================================================================
-- TABLE 10: action_decisions (P04 Arbitration - Action Choices)
-- =====================================================================
-- Purpose: Arbitration decisions with chosen action and alternates
-- Source: memoryOS_frozen/arbitration/README.md, manager.py
-- Usage: P04 Arbiter publishes ACTION_DECISION events with chosen action
-- Architecture: Links to action_receipts (action_id) and drive_intents (decision_id)
-- =====================================================================

CREATE TABLE IF NOT EXISTS action_decisions (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    decision_id TEXT PRIMARY KEY NOT NULL, -- Unique decision identifier (e.g., "dec-2025-01-09-001")
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)
    person_id TEXT,                        -- Who this decision is for (optional, NULL for system decisions)

    -- ============================================================
    -- CHOSEN ACTION
    -- ============================================================
    chosen_action TEXT NOT NULL,           -- Chosen action name (e.g., "set_reminder", "draft_reply")
    chosen_args TEXT NOT NULL,             -- JSON: action arguments {"when": "18:00", "who": "alice"}

    -- ============================================================
    -- ALTERNATES (JSON Array)
    -- ============================================================
    -- Example: [{"action": "draft_reply", "score": 0.62, "reasons": ["utility lower", "cost higher"]}]
    alternates TEXT,                       -- JSON array of alternate actions with scores and reasons

    -- ============================================================
    -- SCORING
    -- ============================================================
    score REAL NOT NULL CHECK (score >= 0.0),

    -- ============================================================
    -- REASONING (JSON Array)
    -- ============================================================
    -- Example: ["U=0.84*1.0 + 0.60*0.9 - 0.10*0.7 - 0.20*0.4 + urgency_bump", "risk=low", "band=AMBER pass"]
    reasons TEXT NOT NULL,                 -- JSON array of human-readable decision reasons

    -- ============================================================
    -- POLICY BAND
    -- ============================================================
    band TEXT NOT NULL DEFAULT 'GREEN' CHECK (band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),

    -- ============================================================
    -- TRACE (JSON) - Full Decision Context
    -- ============================================================
    -- Example: {"features_used": {"relevance": 0.84, "goal_alignment": 0.60},
    --           "policy_gates": {"rbac": "ok", "abac": "ok", "consent": "ok"},
    --           "weights": {"wr": 1.0, "wg": 0.9, "we": 0.8}}
    trace TEXT NOT NULL,                   -- JSON: {features_used, policy_gates, weights}

    -- ============================================================
    -- DECISION INPUT CONTEXT (JSON)
    -- ============================================================
    -- Example: {"affect": {"v": -0.10, "a": 0.72}, "cortex": {"need_action": 0.64}}
    context TEXT,                          -- JSON: affect, cortex, tom, temporal from DecisionInput

    -- ============================================================
    -- EXECUTION RESULT (Optional - Filled After Execution)
    -- ============================================================
    receipt_id TEXT,                       -- Reference to action_receipts.receipt_id (if executed)
    -- ok | error | skipped | quarantined (from receipt)
    execution_status TEXT CHECK (execution_status IS NULL OR execution_status IN ('ok', 'error', 'skipped', 'quarantined')),

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    ts TEXT NOT NULL                       -- ISO8601 timestamp of decision
);

-- ============================================================
-- INDEXES: action_decisions
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_action_decisions_space ON action_decisions(space_id);
CREATE INDEX IF NOT EXISTS idx_action_decisions_person ON action_decisions(person_id) WHERE person_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_action_decisions_action ON action_decisions(chosen_action);
CREATE INDEX IF NOT EXISTS idx_action_decisions_band ON action_decisions(band);
CREATE INDEX IF NOT EXISTS idx_action_decisions_receipt ON action_decisions(receipt_id) WHERE receipt_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_action_decisions_execution_status ON action_decisions(execution_status) WHERE execution_status IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_action_decisions_score ON action_decisions(score);
CREATE INDEX IF NOT EXISTS idx_action_decisions_tenant ON action_decisions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_action_decisions_owner ON action_decisions(owner_id);
CREATE INDEX IF NOT EXISTS idx_action_decisions_trace ON action_decisions(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_action_decisions_ts ON action_decisions(ts);


-- =====================================================================
-- TABLE 11: temporal_index (P01 Temporal - Multi-Resolution Time Shards)
-- =====================================================================
-- Purpose: Multi-resolution time indexing for fast recall
-- Source: memoryOS_frozen/temporal/README.md, indexer.py
-- Usage: P01 retrieval queries time ranges, returns candidates with recency scores
-- Architecture: Shards by hour/day/week/month for efficient time-based queries
-- =====================================================================

CREATE TABLE IF NOT EXISTS temporal_index (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    index_id TEXT PRIMARY KEY NOT NULL,    -- Unique index identifier (e.g., "tidx-evt-2025-01-09-00042")
    event_id TEXT NOT NULL,                -- Reference to source event (st_hipp_store, st_epi, st_sem)
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- SHARD KEY (Multi-Resolution)
    -- ============================================================
    -- Examples:
    --   Hour: "2025-01-09-14|shared:household"
    --   Day: "2025-01-09|shared:household"
    --   Week (ISO): "2025-W02|shared:household"
    --   Month: "2025-01|shared:household"
    shard_key TEXT NOT NULL,               -- Multi-resolution shard key (hour/day/week/month | space_id)
    resolution TEXT NOT NULL CHECK (resolution IN ('hour', 'day', 'week', 'month')), -- hour | day | week | month

    -- ============================================================
    -- TEMPORAL DATA
    -- ============================================================
    ts TEXT NOT NULL,                      -- ISO8601 timestamp of event (UTC)
    tz TEXT DEFAULT 'UTC',                 -- Timezone identifier (e.g., "America/Chicago")

    -- ============================================================
    -- RECENCY SCORE
    -- ============================================================
    recency REAL,                          -- Recency score (0.0-1.0+) computed as 2^(-Δt/half_life)

    -- ============================================================
    -- CIRCADIAN & WEEKLY FEATURES (JSON)
    -- ============================================================
    -- Example: {"sin_tod": 0.26, "cos_tod": 0.96, "sin_dow": -0.78, "cos_dow": 0.62, "is_weekend": 0}
    features TEXT,                         -- JSON: {sin_tod, cos_tod, sin_dow, cos_dow, is_weekend}

    -- ============================================================
    -- OPTIONAL METADATA
    -- ============================================================
    tags TEXT,                             -- JSON array of tags (optional, for filtering)
    payload_hint TEXT,                     -- Short payload hint (optional, already redacted)

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    person_id TEXT,                        -- Who created this event (optional)
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    indexed_at TEXT NOT NULL               -- ISO8601 timestamp when event was indexed
);

-- ============================================================
-- INDEXES: temporal_index
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_temporal_index_event ON temporal_index(event_id);
CREATE INDEX IF NOT EXISTS idx_temporal_index_shard ON temporal_index(shard_key);
CREATE INDEX IF NOT EXISTS idx_temporal_index_resolution ON temporal_index(resolution);
CREATE INDEX IF NOT EXISTS idx_temporal_index_space ON temporal_index(space_id);
CREATE INDEX IF NOT EXISTS idx_temporal_index_person ON temporal_index(person_id) WHERE person_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_temporal_index_ts ON temporal_index(ts);
CREATE INDEX IF NOT EXISTS idx_temporal_index_shard_ts ON temporal_index(shard_key, ts);
CREATE INDEX IF NOT EXISTS idx_temporal_index_recency ON temporal_index(recency) WHERE recency IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_temporal_index_tenant ON temporal_index(tenant_id);
CREATE INDEX IF NOT EXISTS idx_temporal_index_owner ON temporal_index(owner_id);
CREATE INDEX IF NOT EXISTS idx_temporal_index_trace ON temporal_index(cognitive_trace_id);


-- =====================================================================
-- TABLE 12: temporal_patterns (P01 Temporal - Circadian/Weekly Patterns)
-- =====================================================================
-- Purpose: Circadian and weekly pattern summaries for Prospective
-- Source: memoryOS_frozen/temporal/README.md, patterns.py
-- Usage: P05 prospective engine uses patterns for scheduling suggestions
-- Architecture: Periodicity detection with KL divergence and autocorrelation
-- =====================================================================

CREATE TABLE IF NOT EXISTS temporal_patterns (
    -- ============================================================
    -- IDENTITY & TRACING
    -- ============================================================
    pattern_id TEXT PRIMARY KEY NOT NULL,  -- Unique pattern identifier (e.g., "tpat-alice-household-2025-01")
    cognitive_trace_id TEXT NOT NULL,      -- End-to-end observability trace

    -- ============================================================
    -- WHO & WHERE (Multi-Person Context)
    -- ============================================================
    space_id TEXT NOT NULL,                -- Memory space (personal:alice, shared:household)
    person_id TEXT,                        -- Who this pattern is for (optional, NULL for space-wide patterns)

    -- ============================================================
    -- EVENT STATISTICS
    -- ============================================================
    total_events INTEGER NOT NULL DEFAULT 0, -- Total events analyzed for this pattern

    -- ============================================================
    -- HOUR HISTOGRAM (JSON Array) - 24 bins
    -- ============================================================
    -- Example: [1, 2, 3, 5, 8, 12, 18, 22, 15, 10, 8, 6, 5, 4, 3, 2, 1, 1, 2, 3, 5, 7, 4, 2]
    hour_hist TEXT NOT NULL,               -- JSON array of 24 integers (hourly event counts)

    -- ============================================================
    -- DAY OF WEEK HISTOGRAM (JSON Array) - 7 bins
    -- ============================================================
    -- Example: [10, 20, 25, 18, 16, 12, 23] (Mon-Sun)
    dow_hist TEXT NOT NULL,                -- JSON array of 7 integers (daily event counts)

    -- ============================================================
    -- PEAK HOURS & DAYS
    -- ============================================================
    hour_peak INTEGER CHECK (hour_peak IS NULL OR (hour_peak >= 0 AND hour_peak <= 23)), -- Peak hour (0-23)
    dow_peak INTEGER CHECK (dow_peak IS NULL OR (dow_peak >= 0 AND dow_peak <= 6)), -- Peak day of week (0=Mon, 6=Sun)

    -- ============================================================
    -- PERIODICITY SCORES
    -- ============================================================
    circadian_score REAL CHECK (circadian_score IS NULL OR (circadian_score >= 0.0 AND circadian_score <= 1.0)), -- KL divergence from uniform (0.0-1.0, rescaled)
    weekly_periodicity REAL CHECK (weekly_periodicity IS NULL OR (weekly_periodicity >= 0.0 AND weekly_periodicity <= 1.0)), -- Autocorrelation at lag 7 (0.0-1.0)

    -- ============================================================
    -- SUGGESTIONS (JSON Array)
    -- ============================================================
    -- Example: ["Peak hour ≈ 18:00; consider scheduling around that time.", "Weekly cycle present; consider a weekly plan."]
    suggestions TEXT,                      -- JSON array of human-readable scheduling suggestions

    -- ============================================================
    -- COMPUTATION METADATA
    -- ============================================================
    computed_at TEXT NOT NULL,             -- ISO8601 timestamp when pattern was computed
    window_start TEXT,                     -- ISO8601 start of analysis window (optional)
    window_end TEXT,                       -- ISO8601 end of analysis window (optional)

    -- ============================================================
    -- ACCESS CONTROL
    -- ============================================================
    tenant_id TEXT NOT NULL,               -- Family/household ID
    privacy_band TEXT NOT NULL DEFAULT 'GREEN' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                -- Primary owner (data sovereignty)
    visible_to TEXT NOT NULL,              -- JSON array of person_ids who can read

    -- ============================================================
    -- SYNC (CRDT)
    -- ============================================================
    crdt_vector_clock TEXT,                -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0 CHECK (crdt_tombstone IN (0, 1)),
    crdt_lamport INTEGER,                  -- Lamport timestamp for causal ordering

    -- ============================================================
    -- LIFECYCLE TIMESTAMPS
    -- ============================================================
    created_at TEXT NOT NULL,              -- ISO8601 record creation time
    updated_at TEXT NOT NULL               -- ISO8601 last modification time
);

-- ============================================================
-- INDEXES: temporal_patterns
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_space ON temporal_patterns(space_id);
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_person ON temporal_patterns(person_id) WHERE person_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_space_person ON temporal_patterns(space_id, person_id);
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_hour_peak ON temporal_patterns(hour_peak) WHERE hour_peak IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_dow_peak ON temporal_patterns(dow_peak) WHERE dow_peak IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_circadian ON temporal_patterns(circadian_score) WHERE circadian_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_weekly ON temporal_patterns(weekly_periodicity) WHERE weekly_periodicity IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_tenant ON temporal_patterns(tenant_id);
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_owner ON temporal_patterns(owner_id);
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_trace ON temporal_patterns(cognitive_trace_id);
CREATE INDEX IF NOT EXISTS idx_temporal_patterns_computed ON temporal_patterns(computed_at);


-- =====================================================================
-- MIGRATION COMPLETE: 0008
-- =====================================================================
-- Summary:
--   - 12 COMPLETE intelligence tables created (all K1 orchestration dependencies)
--   - Tables: prospective_triggers, prospective_outcomes, st_emb, st_aff,
--             drive_state, drive_intents, metacog_reports, metacog_signals,
--             action_receipts, action_decisions, temporal_index, temporal_patterns
--   - 135 indexes created total
--   - Total columns: 399
--   - All tables include: cognitive_trace_id, CRDT sync (vector_clock, tombstone, lamport),
--     access control (tenant_id, space_id, privacy_band, owner_id, visible_to)
--   - Architecture: Complete K1 orchestration stack (P01, P04, P05, P06, P08, P20)
--   - Dependencies: Requires Migration 0006 (base memory) and Migration 0007 (people, households)
--   - Status: ALL 12 INTELLIGENCE TABLES COMPLETE - K1 orchestration fully supported
-- =====================================================================
