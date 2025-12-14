-- Migration: 0006_phase1_core_memory_foundation
-- Description: Phase 1 core memory tables (st_hipp_store, st_epi, st_sem) with complete fields from whiteboard schema
-- Author: K0 Architecture Team
-- Date: 2025-11-10
-- Dependencies: 0005_cleanup_orphaned_fts
-- Related ADRs: ADR-0001c (K0/K1 boundary), whiteboard_schema.md (memory formation architecture)

BEGIN;

-- ============================================================================
-- Table: st_hipp_store (Hippocampus Staging - Pattern Separation & Novelty)
-- ============================================================================
-- Purpose: Short-term staging area (7-30 days) for raw sensory/conversational input
-- Cognitive Model: Pattern separation, novelty detection, rapid encoding
-- Consolidation: P03 pipeline classifies and moves to st_epi/st_sem/st_proc/st_social
-- Lifecycle: TEMPORARY (7-30 days) → P03 consolidation → DELETE from st_hipp_store

CREATE TABLE IF NOT EXISTS st_hipp_store (
    -- IDENTITY & TRACING
    event_id TEXT PRIMARY KEY,                -- Unique event identifier
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability
    hipp_version TEXT,                        -- Hippocampus algorithm version

    -- CONTENT
    text TEXT NOT NULL,                       -- Raw input text
    length INTEGER,                           -- Character count
    language TEXT,                            -- Detected language (en, es, etc.)

    -- EXTRACTED METADATA (for P03 consolidation routing)
    topics TEXT,                              -- JSON array of topic keywords
    categories TEXT,                          -- JSON array of event categories
    activity_type TEXT,                       -- What happened (run, dinner, meeting, call)
    activity_category TEXT,                   -- Broader grouping (exercise, social, work)
    activity_metadata TEXT,                   -- JSON blob (duration, distance, calories, etc)

    -- PATTERN SEPARATION (SimHash + MinHash)
    simhash_hex TEXT,                         -- 512-bit binary code (hex encoded)
    simhash_bits INTEGER,                     -- Bit count (default 512)
    minhash32 TEXT,                           -- JSON array of 64 Jaccard sketches
    novelty REAL,                             -- How different from existing (0.0-1.0)
    near_duplicates TEXT,                     -- JSON array [["evt_id", distance], ...]

    -- WHO (Multi-Person - References Neo4j Person IDs)
    author_id TEXT NOT NULL,                  -- Who created this memory (Neo4j :Person ID)
    author_role TEXT,                         -- Relationship role (son, mother, etc.)
    participants TEXT,                        -- JSON array of Neo4j :Person node IDs
    participant_roles TEXT,                   -- JSON: {"person_id": "role"}
    mentions TEXT,                            -- JSON array of Neo4j :Person node IDs
    mention_contexts TEXT,                    -- JSON: {"person_id": "context"}

    -- WHERE (Location - References Neo4j Location IDs)
    location_name TEXT,                       -- Neo4j :Location node ID or name
    location_type TEXT,                       -- Quick filter (home, restaurant, office, etc)
    location_lat REAL,                        -- Latitude (optional)
    location_lon REAL,                        -- Longitude (optional)

    -- WHEN (Temporal)
    ts TEXT NOT NULL,                         -- Event timestamp (ISO 8601)
    temporal_reference TEXT,                  -- future|past|present
    temporal_target TEXT,                     -- ISO8601 (if future/past reference)

    -- SENTIMENT (Extracted)
    sentiment_score REAL,                     -- Positive/negative (-1.0 to 1.0)
    sentiment_label TEXT,                     -- positive|neutral|negative
    emotion_tags TEXT,                        -- JSON array (happy, stressed, excited, etc)

    -- MULTI-STORE INTEGRATION
    embedding_id TEXT,                        -- Reference to FAISS index entry
    embedding_vector_dims INTEGER,            -- 768 for typical embeddings
    embedding_model TEXT,                     -- text-embedding-ada-002, all-mpnet-base-v2
    embedding_generated_at TEXT,              -- ISO8601 timestamp
    fts_indexed INTEGER DEFAULT 0,            -- Was text indexed in FTS5?
    fts_table_name TEXT,                      -- Which FTS5 virtual table
    fts_last_indexed TEXT,                    -- ISO8601 timestamp

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space (personal:*, shared:household)
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                   -- Primary owner (data sovereignty)
    co_owners TEXT,                           -- JSON array of co-owners (shared experiences)
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids who can read

    -- METADATA
    created_at TEXT NOT NULL,                 -- Record creation time
    device_id TEXT,                           -- Originating device
    session_id TEXT,                          -- Conversation session

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_hipp_tenant_space ON st_hipp_store(tenant_id, space_id);
CREATE INDEX idx_hipp_author ON st_hipp_store(author_id);
CREATE INDEX idx_hipp_privacy ON st_hipp_store(privacy_band);
CREATE INDEX idx_hipp_ts ON st_hipp_store(ts DESC);
CREATE INDEX idx_hipp_novelty ON st_hipp_store(novelty DESC);
CREATE INDEX idx_hipp_embedding ON st_hipp_store(embedding_id) WHERE embedding_id IS NOT NULL;
CREATE INDEX idx_hipp_fts ON st_hipp_store(fts_indexed) WHERE fts_indexed = 1;
CREATE INDEX idx_hipp_crdt_tombstone ON st_hipp_store(crdt_tombstone, tenant_id);

-- ============================================================================
-- Table: st_epi (Episodic Memories - Consolidated Events)
-- ============================================================================
-- Purpose: Long-term storage for consolidated autobiographical memories
-- Source: P03 consolidation from st_hipp_store
-- Lifecycle: Indefinite (subject to learning-based decay model)

CREATE TABLE IF NOT EXISTS st_epi (
    -- IDENTITY & TRACING
    event_id TEXT PRIMARY KEY,                -- Unique event identifier
    hipp_id TEXT,                             -- Reference to st_hipp_store (provenance)
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- CONTENT
    text TEXT NOT NULL,                       -- Event description
    summary TEXT,                             -- Generated summary (for quick retrieval)
    language TEXT,                            -- Language code

    -- ENTITIES & SEMANTICS
    external_mentions TEXT,                   -- JSON array of Neo4j :Person IDs mentioned but NOT present
    location_ids TEXT,                        -- JSON array of Neo4j :Location node IDs
    location_names TEXT,                      -- JSON array (denormalized for quick display)
    objects TEXT,                             -- JSON array of things
    actions TEXT,                             -- JSON array of verbs/activities
    topics TEXT,                              -- JSON array of topic keywords
    causal_chain TEXT,                        -- JSON array: [{"cause": "X", "effect": "Y"}, ...]

    -- TEMPORAL
    event_time TEXT NOT NULL,                 -- When event occurred (ISO 8601)
    time_bucket TEXT,                         -- Coarse temporal grouping (YYYY-MM-DD-morning/afternoon/evening)
    temporal_sequence TEXT,                   -- JSON array of ordered actions
    duration_minutes INTEGER,                 -- Event duration (if known)
    time_resolution TEXT,                     -- Precision (year, month, day, hour, minute)
    timezone TEXT,                            -- Event timezone (America/Los_Angeles)

    -- WHO (Multi-Person)
    author_id TEXT NOT NULL,                  -- Who created memory
    author_role TEXT,                         -- Relationship role
    participants TEXT,                        -- JSON array of person_ids present
    participant_roles TEXT,                   -- JSON: {"person_id": "role"}
    mention_contexts TEXT,                    -- JSON: {"person_id": "context"}

    -- RELATIONSHIP CONTEXT
    relationship_context TEXT,                -- Type of interaction (mother_son_conversation, family_gathering)
    social_dynamics TEXT,                     -- Social situation (planning, conflict, celebration)

    -- AFFECT & SALIENCE
    salience_score REAL,                      -- Importance (0.0-1.0, from affect/emotional_salience.py)
    emotional_state TEXT,                     -- Emotional classification
    valence REAL,                             -- Positive/negative (-1.0 to 1.0)
    arousal REAL,                             -- Energy level (-1.0 to 1.0)
    dominance REAL,                           -- Control/power (-1.0 to 1.0)
    physical_state TEXT,                      -- Physical condition (fatigued, energetic)

    -- MULTI-STORE INTEGRATION
    embedding_id TEXT,                        -- Reference to FAISS index entry
    embedding_vector_dims INTEGER,            -- 768 for typical embeddings
    embedding_model TEXT,                     -- text-embedding-ada-002, all-mpnet-base-v2
    embedding_generated_at TEXT,              -- ISO8601 timestamp
    fts_indexed INTEGER DEFAULT 0,            -- Was text indexed in FTS5?
    fts_table_name TEXT,                      -- Which FTS5 virtual table (st_epi_fts)
    fts_last_indexed TEXT,                    -- ISO8601 timestamp

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                   -- Primary owner
    co_owners TEXT,                           -- JSON array of co-owners
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids

    -- PRIVACY & CONSENT
    involves_pii INTEGER DEFAULT 1,           -- Contains personally identifiable information
    consent_required_from TEXT,               -- JSON array of person_ids who must consent
    shared_with_external TEXT,                -- JSON array of external person_ids

    -- PROVENANCE & MEDIA
    media_refs TEXT,                          -- JSON array of attachment blob_ids
    geo TEXT,                                 -- GeoJSON POINT for location
    confidence REAL,                          -- Summary/extraction confidence (0.0-1.0)
    provenance TEXT,                          -- JSON: {method, model_id, prompt_id}

    -- LIFECYCLE & RETENTION
    retention_class TEXT,                     -- hot/warm/cold storage tier
    retire_after_days INTEGER,                -- TTL policy
    archived_at TEXT,                         -- When moved to cold storage
    idempotency_key TEXT UNIQUE,              -- Write deduplication

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- TIMESTAMPS
    created_at TEXT NOT NULL,                 -- Record creation time
    updated_at TEXT NOT NULL,                 -- Last update
    consolidated_at TEXT,                     -- When P03 moved from hippocampus

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_epi_tenant_space ON st_epi(tenant_id, space_id);
CREATE INDEX idx_epi_author ON st_epi(author_id);
CREATE INDEX idx_epi_privacy ON st_epi(privacy_band);
CREATE INDEX idx_epi_event_time ON st_epi(event_time DESC);
CREATE INDEX idx_epi_time_bucket ON st_epi(time_bucket);
CREATE INDEX idx_epi_salience ON st_epi(salience_score DESC);
CREATE INDEX idx_epi_retention ON st_epi(retention_class, retire_after_days);
CREATE INDEX idx_epi_embedding ON st_epi(embedding_id) WHERE embedding_id IS NOT NULL;
CREATE INDEX idx_epi_fts ON st_epi(fts_indexed) WHERE fts_indexed = 1;
CREATE INDEX idx_epi_crdt_tombstone ON st_epi(crdt_tombstone, tenant_id);
CREATE INDEX idx_epi_hipp_id ON st_epi(hipp_id) WHERE hipp_id IS NOT NULL;

-- ============================================================================
-- Table: st_sem (Semantic Memories - Facts & Generalizations)
-- ============================================================================
-- Purpose: Long-term storage for decontextualized facts, concepts, and generalizations
-- Source: P03 consolidation from st_hipp_store OR P04 extraction from st_epi
-- Lifecycle: Indefinite (subject to learning-based decay model)

CREATE TABLE IF NOT EXISTS st_sem (
    -- IDENTITY & TRACING
    fact_id TEXT PRIMARY KEY,                 -- Unique fact identifier
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- SEMANTIC TRIPLE
    subject TEXT NOT NULL,                    -- Who/what (person_id, concept)
    predicate TEXT NOT NULL,                  -- Relation (has_routine, values, prefers)
    object TEXT NOT NULL,                     -- Target (gym_exercise, connection, phone_calls)

    -- CLASSIFICATION
    fact_domain TEXT NOT NULL,                -- health, relationships, preferences, habits, knowledge, routines
    fact_category TEXT,                       -- medical_condition, food_preference, family_dynamics, communication_style
    fact_type TEXT,                           -- attribute, behavior, preference, belief, knowledge

    -- CONFIDENCE & EVIDENCE
    confidence REAL NOT NULL,                 -- Bayesian confidence (0.0-1.0)
    evidence_count INTEGER NOT NULL DEFAULT 1, -- How many episodes support this
    evidence_score REAL,                      -- Bayesian evidence strength
    derived_from_episodic_ids TEXT,           -- JSON array of source event_ids
    supporting_episodes TEXT,                 -- JSON array with episode details
    contradicting_episodes TEXT,              -- JSON array of counter-evidence

    -- WHO (Subject of Fact)
    subject_person_id TEXT,                   -- If subject is a person
    about_persons TEXT,                       -- JSON array of person_ids this fact relates to

    -- TEMPORAL
    first_observed TEXT NOT NULL,             -- When fact first appeared
    last_updated TEXT NOT NULL,               -- Most recent evidence
    deprecated_at TEXT,                       -- If fact is no longer valid
    superseded_by TEXT,                       -- New fact_id that replaces this

    -- DECAY & VERSIONING
    decay_half_life_days INTEGER,             -- Fact decay model parameter
    scope TEXT,                               -- personal/household/global
    stability TEXT,                           -- volatile/stable
    conflicts_with TEXT,                      -- JSON array of conflicting fact_ids

    -- MULTI-STORE INTEGRATION
    embedding_id TEXT,                        -- Reference to FAISS index entry (for semantic similarity of facts)
    embedding_vector_dims INTEGER,            -- 768 for typical embeddings
    embedding_model TEXT,                     -- text-embedding-ada-002, all-mpnet-base-v2
    embedding_generated_at TEXT,              -- ISO8601 timestamp

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                   -- Primary owner
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- TIMESTAMPS
    created_at TEXT NOT NULL,                 -- Record creation time
    updated_at TEXT NOT NULL,                 -- Last update

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_sem_tenant_space ON st_sem(tenant_id, space_id);
CREATE INDEX idx_sem_owner ON st_sem(owner_id);
CREATE INDEX idx_sem_privacy ON st_sem(privacy_band);
CREATE INDEX idx_sem_subject ON st_sem(subject);
CREATE INDEX idx_sem_subject_person ON st_sem(subject_person_id) WHERE subject_person_id IS NOT NULL;
CREATE INDEX idx_sem_fact_domain ON st_sem(fact_domain);
CREATE INDEX idx_sem_confidence ON st_sem(confidence DESC);
CREATE INDEX idx_sem_first_observed ON st_sem(first_observed DESC);
CREATE INDEX idx_sem_embedding ON st_sem(embedding_id) WHERE embedding_id IS NOT NULL;
CREATE INDEX idx_sem_crdt_tombstone ON st_sem(crdt_tombstone, tenant_id);

-- ============================================================================
-- Table: st_ws (Working Memory - Session-Scoped Context)
-- ============================================================================
-- Purpose: Temporary memory for active session context, K1 SessionState checkpoints
-- Source: K1 SessionState, workspace_store.py
-- Lifecycle: Session-scoped (expires after session ends or TTL)

CREATE TABLE IF NOT EXISTS st_ws (
    -- IDENTITY & TRACING
    item_id TEXT PRIMARY KEY,                 -- Unique item identifier
    session_id TEXT NOT NULL,                 -- Session scope
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- CONTENT
    item_type TEXT NOT NULL,                  -- belief, goal, referent, context, checkpoint
    content TEXT NOT NULL,                    -- Item data (JSON or text)
    priority INTEGER DEFAULT 0,               -- Eviction priority (higher = keep longer)

    -- WHO (Session Context)
    author_id TEXT NOT NULL,                  -- Who is in this session
    participants TEXT,                        -- JSON array of active participants

    -- LIFECYCLE
    created_at TEXT NOT NULL,                 -- Creation timestamp
    expires_at TEXT,                          -- Auto-eviction time (TTL)
    last_accessed TEXT,                       -- LRU tracking
    access_count INTEGER DEFAULT 0,           -- Frequency tracking
    eviction_reason TEXT,                     -- lru/ttl/pressure/policy (after eviction)

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    band_at_write TEXT,                       -- Privacy band when written
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids

    -- TRACING
    span_id TEXT,                             -- Trace span reference
    pin_until TEXT,                           -- Prevent eviction until this timestamp

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_ws_session ON st_ws(session_id, created_at DESC);
CREATE INDEX idx_ws_tenant_space ON st_ws(tenant_id, space_id);
CREATE INDEX idx_ws_author ON st_ws(author_id);
CREATE INDEX idx_ws_expires ON st_ws(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_ws_item_type ON st_ws(item_type);
CREATE INDEX idx_ws_priority ON st_ws(priority DESC);
CREATE INDEX idx_ws_crdt_tombstone ON st_ws(crdt_tombstone, tenant_id);

-- ============================================================================
-- Table: st_proc (Procedural Memory - Habits, Routines, Skills)
-- ============================================================================
-- Purpose: Learned procedures, habits, routines, skills, workflows
-- Source: P06 learning loop, P03 consolidation, procedure extraction
-- Lifecycle: Indefinite (archived if unused for long periods)

CREATE TABLE IF NOT EXISTS st_proc (
    -- IDENTITY & TRACING
    procedure_id TEXT PRIMARY KEY,            -- Unique procedure identifier
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- PROCEDURE
    procedure_name TEXT NOT NULL,             -- morning_routine, workout_sequence, meal_prep
    procedure_type TEXT NOT NULL,             -- habit, skill, routine, workflow
    description TEXT,                         -- Human-readable description
    steps TEXT NOT NULL,                      -- JSON array of ordered steps
    triggers TEXT,                            -- JSON array of triggering conditions
    frequency TEXT,                           -- daily, weekly, situational

    -- CONTEXT & APPLICABILITY
    applicable_context TEXT,                  -- morning, evening, at_gym, at_home, when_stressed, before_bed
    context_conditions TEXT,                  -- JSON: {"time_of_day": "morning", "location": "home", "mood": "energetic"}
    prerequisites TEXT,                       -- JSON array of required conditions
    incompatible_with TEXT,                   -- JSON array of conflicting procedure_ids
    optimal_timing TEXT,                      -- Best time to execute (morning, after_work, weekend)

    -- PERFORMANCE
    success_rate REAL DEFAULT 1.0,            -- How often completed successfully (0.0-1.0)
    avg_duration_minutes INTEGER,             -- Average completion time
    execution_count INTEGER DEFAULT 0,        -- How many times executed
    last_executed TEXT,                       -- Most recent execution timestamp
    mastery_level TEXT,                       -- learning, proficient, expert

    -- WHO (Subject of Procedure)
    owner_id TEXT NOT NULL,                   -- Person who performs this
    applicable_to TEXT,                       -- JSON array of person_ids who can perform

    -- EVIDENCE
    derived_from_episodes TEXT,               -- JSON array of source event_ids
    reinforcement_history TEXT,               -- JSON array of feedback/corrections
    first_learned TEXT NOT NULL,              -- When procedure first identified
    last_updated TEXT NOT NULL,               -- Last modification

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- LIFECYCLE
    created_at TEXT NOT NULL,                 -- Record creation time
    updated_at TEXT NOT NULL,                 -- Last update
    archived_at TEXT,                         -- If procedure is deprecated

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_proc_tenant_space ON st_proc(tenant_id, space_id);
CREATE INDEX idx_proc_owner ON st_proc(owner_id);
CREATE INDEX idx_proc_privacy ON st_proc(privacy_band);
CREATE INDEX idx_proc_type ON st_proc(procedure_type);
CREATE INDEX idx_proc_frequency ON st_proc(frequency);
CREATE INDEX idx_proc_success_rate ON st_proc(success_rate DESC);
CREATE INDEX idx_proc_last_executed ON st_proc(last_executed DESC);
CREATE INDEX idx_proc_mastery ON st_proc(mastery_level);
CREATE INDEX idx_proc_crdt_tombstone ON st_proc(crdt_tombstone, tenant_id);

-- ============================================================================
-- Table: st_social (Social Memory - Relationships & Theory of Mind)
-- ============================================================================
-- Purpose: Relationships, interactions, family dynamics, Theory of Mind models
-- Source: P03 consolidation, P19 personalization, social cognition module
-- Lifecycle: Indefinite (updated as relationships evolve)

CREATE TABLE IF NOT EXISTS st_social (
    -- IDENTITY & TRACING
    social_id TEXT PRIMARY KEY,               -- Unique social memory identifier
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- RELATIONSHIP
    person_a_id TEXT NOT NULL,                -- First person in relationship (Neo4j :Person ID)
    person_b_id TEXT NOT NULL,                -- Second person in relationship (Neo4j :Person ID)
    relationship_type TEXT NOT NULL,          -- parent_child, siblings, spouses, friends, colleagues
    relationship_label TEXT,                  -- mother, best_friend, work_colleague
    bidirectional INTEGER DEFAULT 1,          -- Whether relationship goes both ways

    -- DYNAMICS
    interaction_frequency TEXT,               -- daily, weekly, monthly, rarely
    communication_style TEXT,                 -- phone_calls, texts, in_person, video
    emotional_tone TEXT,                      -- supportive, tense, neutral, evolving
    power_dynamics TEXT,                      -- equal, hierarchical, dependent
    conflict_patterns TEXT,                   -- JSON array of recurring conflict types

    -- THEORY OF MIND (ToM)
    beliefs_about_a TEXT,                     -- JSON: Person B's beliefs about Person A
    beliefs_about_b TEXT,                     -- JSON: Person A's beliefs about Person B
    shared_knowledge TEXT,                    -- JSON array of shared context/experiences
    false_beliefs TEXT,                       -- JSON array of detected false belief scenarios
    mental_model_confidence REAL DEFAULT 0.5, -- How accurate ToM model is (0.0-1.0)

    -- TEMPORAL
    relationship_start TEXT,                  -- When relationship began
    relationship_end TEXT,                    -- If relationship ended
    last_interaction TEXT,                    -- Most recent interaction timestamp
    interaction_count INTEGER DEFAULT 0,      -- Total interactions recorded

    -- EVIDENCE
    derived_from_episodes TEXT,               -- JSON array of source event_ids
    interaction_history TEXT,                 -- JSON array of interaction summaries
    significant_events TEXT,                  -- JSON array of milestone events
    first_observed TEXT NOT NULL,             -- When relationship first identified
    last_updated TEXT NOT NULL,               -- Most recent update

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                   -- Primary owner
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids (restricted visibility)

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- LIFECYCLE
    created_at TEXT NOT NULL,                 -- Record creation time
    updated_at TEXT NOT NULL,                 -- Last update

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_social_tenant_space ON st_social(tenant_id, space_id);
CREATE INDEX idx_social_person_a ON st_social(person_a_id);
CREATE INDEX idx_social_person_b ON st_social(person_b_id);
CREATE INDEX idx_social_relationship_type ON st_social(relationship_type);
CREATE INDEX idx_social_privacy ON st_social(privacy_band);
CREATE INDEX idx_social_last_interaction ON st_social(last_interaction DESC);
CREATE INDEX idx_social_interaction_frequency ON st_social(interaction_frequency);
CREATE INDEX idx_social_crdt_tombstone ON st_social(crdt_tombstone, tenant_id);

-- ============================================================================
-- PHASE 2: SELF-MODEL TABLES (Per-Person Personality & Preferences)
-- ============================================================================
-- Purpose: P19 personalization pipeline - individual traits, preferences, health, roles
-- Source: P19 pipeline, P06 learning loop, health connectors

-- ============================================================================
-- Table: self_traits (Per-Person Personality Traits)
-- ============================================================================
-- Purpose: Individual personality traits and characteristics
-- Source: P19 pipeline, P06 learning from behavior patterns
-- Lifecycle: Long-term (updated as evidence accumulates)

CREATE TABLE IF NOT EXISTS self_traits (
    -- IDENTITY
    trait_id TEXT PRIMARY KEY,                -- Unique trait identifier
    person_id TEXT NOT NULL,                  -- Which family member (Neo4j :Person ID)
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- TRAIT
    trait_name TEXT NOT NULL,                 -- introvert, caring, forgetful, organized, punctual, creative
    trait_category TEXT,                      -- personality, cognitive, emotional, physical, behavioral
    trait_value REAL,                         -- Strength/intensity (0.0-1.0)
    confidence REAL DEFAULT 0.5,              -- How certain (0.0-1.0, increases with evidence)

    -- EVIDENCE
    evidence_count INTEGER DEFAULT 1,         -- How many observations support this
    derived_from_episodes TEXT,               -- JSON array of source event_ids
    first_observed TEXT NOT NULL,             -- When trait first identified
    last_updated TEXT NOT NULL,               -- Most recent evidence update

    -- DECAY & PROVENANCE
    decay_model TEXT,                         -- linear/exponential/manual (how trait fades if contradicted)
    last_evidence_span_id TEXT,               -- Tracing reference to most recent evidence
    explainability_blob_id TEXT,              -- Why this trait value (blob reference to explanation)

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space (usually personal:person_id)
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                   -- Person who owns this trait
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids who can see

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- LIFECYCLE
    created_at TEXT NOT NULL,                 -- Record creation time
    updated_at TEXT NOT NULL,                 -- Last update

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_self_traits_person ON self_traits(person_id);
CREATE INDEX idx_self_traits_tenant_space ON self_traits(tenant_id, space_id);
CREATE INDEX idx_self_traits_category ON self_traits(trait_category);
CREATE INDEX idx_self_traits_confidence ON self_traits(confidence DESC);
CREATE INDEX idx_self_traits_privacy ON self_traits(privacy_band);
CREATE INDEX idx_self_traits_crdt_tombstone ON self_traits(crdt_tombstone, tenant_id);

-- ============================================================================
-- Table: self_preferences (Per-Person Preferences & Likes/Dislikes)
-- ============================================================================
-- Purpose: Individual preferences, style vectors, decode-knobs
-- Source: P19 pipeline, ADR-0064 (style vector), user explicit preferences
-- Lifecycle: Long-term (updated as preferences evolve)

CREATE TABLE IF NOT EXISTS self_preferences (
    -- IDENTITY
    preference_id TEXT PRIMARY KEY,           -- Unique preference identifier
    person_id TEXT NOT NULL,                  -- Which family member (Neo4j :Person ID)
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- PREFERENCE
    domain TEXT NOT NULL,                     -- communication, food, activities, time, social, work, entertainment
    preference_name TEXT NOT NULL,            -- prefers_phone_over_text, likes_coffee_meetings, morning_person
    preference_value TEXT,                    -- Value (if categorical/scalar) - JSON or text
    preference_strength REAL DEFAULT 0.5,     -- How strong is this preference (0.0-1.0)
    confidence REAL DEFAULT 0.5,              -- How certain (0.0-1.0)

    -- EVIDENCE
    evidence_count INTEGER DEFAULT 1,         -- How many observations support this
    derived_from_episodes TEXT,               -- JSON array of source event_ids
    first_observed TEXT NOT NULL,             -- When preference first identified
    last_updated TEXT NOT NULL,               -- Most recent evidence update

    -- DECAY & PROVENANCE
    decay_model TEXT,                         -- linear/exponential/manual
    last_evidence_span_id TEXT,               -- Tracing reference
    explainability_blob_id TEXT,              -- Why this preference (blob reference)

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space (usually personal:person_id)
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                   -- Person who owns this preference
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- LIFECYCLE
    created_at TEXT NOT NULL,                 -- Record creation time
    updated_at TEXT NOT NULL,                 -- Last update

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_self_prefs_person ON self_preferences(person_id);
CREATE INDEX idx_self_prefs_tenant_space ON self_preferences(tenant_id, space_id);
CREATE INDEX idx_self_prefs_domain ON self_preferences(domain);
CREATE INDEX idx_self_prefs_confidence ON self_preferences(confidence DESC);
CREATE INDEX idx_self_prefs_privacy ON self_preferences(privacy_band);
CREATE INDEX idx_self_prefs_crdt_tombstone ON self_preferences(crdt_tombstone, tenant_id);

-- ============================================================================
-- Table: self_health (Per-Person Health State & Medical Tracking)
-- ============================================================================
-- Purpose: Current health status, conditions, medications, providers
-- Source: P19 pipeline, health connectors, user input
-- Lifecycle: Long-term (updated as health status changes)

CREATE TABLE IF NOT EXISTS self_health (
    -- IDENTITY
    health_id TEXT PRIMARY KEY,               -- Unique health record identifier
    person_id TEXT NOT NULL,                  -- Which family member (Neo4j :Person ID)
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- HEALTH STATE
    condition_type TEXT,                      -- chronic, acute, wellness, mental, preventive
    condition_name TEXT,                      -- recovering_from_surgery, diabetes, anxiety, hypertension
    status TEXT,                              -- active, resolved, monitoring, improving, declining
    severity TEXT,                            -- mild, moderate, severe
    since_date TEXT,                          -- When condition started (ISO8601)

    -- TRACKING
    current_metrics TEXT,                     -- JSON: {"mobility": "improving", "pain": "2/10", "glucose": "120"}
    trajectory TEXT,                          -- improving, stable, declining, fluctuating
    monitoring_frequency TEXT,                -- daily, weekly, monthly, as_needed

    -- HEALTHCARE TEAM
    providers TEXT,                           -- JSON array: [{"name": "Dr. Smith", "specialty": "orthopedic", "contact": "555-1234", "primary": true}]
    medications TEXT,                         -- JSON array: [{"name": "ibuprofen", "dosage": "200mg", "frequency": "twice daily", "prescribed_by": "Dr. Smith", "start_date": "2025-01-01"}]
    treatment_plan TEXT,                      -- Current treatment protocol description (text or JSON)
    next_appointment TEXT,                    -- ISO8601 date of next medical appointment
    care_team TEXT,                           -- JSON array of healthcare professionals involved

    -- EVIDENCE & SOURCES
    sources TEXT,                             -- JSON array: ["device", "app", "clinician", "self_reported"]
    derived_from_episodes TEXT,               -- JSON array of source event_ids
    hipaa_flag INTEGER DEFAULT 0,             -- HIPAA-protected data marker
    last_updated TEXT NOT NULL,               -- Most recent update

    -- DECAY & PROVENANCE
    decay_model TEXT,                         -- linear/exponential/manual
    last_evidence_span_id TEXT,               -- Tracing reference
    explainability_blob_id TEXT,              -- Why this health state (blob reference)

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space (usually personal:person_id)
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                   -- Person who owns this health record
    visible_to TEXT NOT NULL,                 -- JSON array (restricted visibility for health)

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- LIFECYCLE
    created_at TEXT NOT NULL,                 -- Record creation time
    updated_at TEXT NOT NULL,                 -- Last update

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_self_health_person ON self_health(person_id);
CREATE INDEX idx_self_health_tenant_space ON self_health(tenant_id, space_id);
CREATE INDEX idx_self_health_condition ON self_health(condition_name);
CREATE INDEX idx_self_health_status ON self_health(status);
CREATE INDEX idx_self_health_privacy ON self_health(privacy_band);
CREATE INDEX idx_self_health_hipaa ON self_health(hipaa_flag) WHERE hipaa_flag = 1;
CREATE INDEX idx_self_health_crdt_tombstone ON self_health(crdt_tombstone, tenant_id);

-- ============================================================================
-- Table: self_roles (Per-Person Family & Social Roles)
-- ============================================================================
-- Purpose: Family/social roles each person plays
-- Source: P19 pipeline, social cognition, role inference
-- Lifecycle: Long-term (updated as roles evolve)

CREATE TABLE IF NOT EXISTS self_roles (
    -- IDENTITY
    role_id TEXT PRIMARY KEY,                 -- Unique role identifier
    person_id TEXT NOT NULL,                  -- Which family member (Neo4j :Person ID)
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- ROLE
    role_name TEXT NOT NULL,                  -- primary_caregiver, birthday_planner, family_organizer, tech_support, cook
    role_domain TEXT,                         -- family, work, social, hobby, household, caregiving
    role_strength REAL DEFAULT 0.5,           -- How central is this role (0.0-1.0)
    confidence REAL DEFAULT 0.5,              -- How certain (0.0-1.0)

    -- EVIDENCE
    evidence_count INTEGER DEFAULT 1,         -- How many observations support this role
    derived_from_episodes TEXT,               -- JSON array of source event_ids
    first_observed TEXT NOT NULL,             -- When role first identified
    last_updated TEXT NOT NULL,               -- Most recent evidence update

    -- DECAY & PROVENANCE
    decay_model TEXT,                         -- linear/exponential/manual
    last_evidence_span_id TEXT,               -- Tracing reference
    explainability_blob_id TEXT,              -- Why this role assignment (blob reference)

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space (usually personal:person_id)
    privacy_band TEXT NOT NULL CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                   -- Person who owns this role
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- LIFECYCLE
    created_at TEXT NOT NULL,                 -- Record creation time
    updated_at TEXT NOT NULL,                 -- Last update

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_self_roles_person ON self_roles(person_id);
CREATE INDEX idx_self_roles_tenant_space ON self_roles(tenant_id, space_id);
CREATE INDEX idx_self_roles_domain ON self_roles(role_domain);
CREATE INDEX idx_self_roles_strength ON self_roles(role_strength DESC);
CREATE INDEX idx_self_roles_privacy ON self_roles(privacy_band);
CREATE INDEX idx_self_roles_crdt_tombstone ON self_roles(crdt_tombstone, tenant_id);

COMMIT;

-- Post-migration validation queries (run manually):
-- SELECT COUNT(*) FROM st_hipp_store;  -- Should be 0 (empty table)
-- SELECT COUNT(*) FROM st_epi;  -- Should be 0 (empty table)
-- SELECT COUNT(*) FROM st_sem;  -- Should be 0 (empty table)
-- SELECT COUNT(*) FROM st_ws;  -- Should be 0 (empty table)
-- SELECT COUNT(*) FROM st_proc;  -- Should be 0 (empty table)
-- SELECT COUNT(*) FROM st_social;  -- Should be 0 (empty table)
-- SELECT COUNT(*) FROM self_traits;  -- Should be 0 (empty table)
-- SELECT COUNT(*) FROM self_preferences;  -- Should be 0 (empty table)
-- SELECT COUNT(*) FROM self_health;  -- Should be 0 (empty table)
-- SELECT COUNT(*) FROM self_roles;  -- Should be 0 (empty table)
-- SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'st_%' OR name LIKE 'self_%' ORDER BY name;
-- SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%' ORDER BY name;
