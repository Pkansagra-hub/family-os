-- Migration: 0007_core_directory_tables
-- Description: Core directory tables - people (person directory) and households (tenant metadata)
-- Author: K0 Architecture Team
-- Date: 2025-11-10
-- Dependencies: 0006_phase1_core_memory_foundation
-- Related ADRs: ADR-0001c (K0/K1 boundary), whiteboard_schema.md (core tables)

BEGIN;

-- ============================================================================
-- Table: people (Person Directory - Family Member Registry)
-- ============================================================================
-- Purpose: Central directory of all people in the household/tenant
-- Source: User onboarding, P19 personalization, social cognition
-- Lifecycle: Long-term (people records rarely deleted, usually tombstoned)
-- Integration: References Neo4j :Person nodes for knowledge graph traversal

CREATE TABLE IF NOT EXISTS people (
    -- IDENTITY
    person_id TEXT PRIMARY KEY,               -- Unique person identifier (matches Neo4j :Person node ID)
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- PERSON INFO
    label TEXT NOT NULL,                      -- Display name (Mom, Dad, Alice, Bob)
    full_name TEXT,                           -- Legal/full name (if provided)
    nicknames TEXT,                           -- JSON array of alternative names
    birth_date TEXT,                          -- ISO8601 date (optional, for age calculation)

    -- RELATIONSHIPS
    relationships TEXT,                       -- JSON array: [{"person_id": "person_002", "type": "mother", "since": "1990-01-01"}]
    household_id TEXT,                        -- Primary household (foreign key to households table)
    household_role TEXT,                      -- adult, child, teen, senior, guest

    -- SYSTEM DEFAULTS
    visibility_default TEXT DEFAULT 'personal', -- Default space visibility (personal, household, shared)
    band_default TEXT DEFAULT 'AMBER',        -- Default privacy band for this person's memories
    consent_status TEXT DEFAULT 'pending',    -- pending, granted, revoked (for data collection)

    -- IDENTITY MERGING (for duplicate detection)
    merge_keys TEXT,                          -- JSON array: [{"type": "email", "value": "alice@example.com"}, {"type": "phone", "value": "+1234567890"}]
    canonical_person_id TEXT,                 -- If merged, points to canonical person_id
    merged_from TEXT,                         -- JSON array of person_ids merged into this one

    -- DEVICE ASSOCIATION
    primary_device_id TEXT,                   -- Main device this person uses
    registered_devices TEXT,                  -- JSON array of device_ids associated with this person

    -- PREFERENCES & SETTINGS
    timezone TEXT DEFAULT 'UTC',              -- Person's timezone (America/Los_Angeles, etc.)
    language TEXT DEFAULT 'en',               -- Preferred language code
    contact_preferences TEXT,                 -- JSON: {"phone": "+1234567890", "email": "alice@example.com", "preferred_method": "text"}

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL,                  -- Family/household ID
    space_id TEXT NOT NULL,                   -- Memory space (usually shared:household)
    privacy_band TEXT NOT NULL DEFAULT 'AMBER' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    owner_id TEXT NOT NULL,                   -- Who created this person record (usually themselves or parent)
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids who can see this record

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag (people are rarely hard-deleted)
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- LIFECYCLE
    created_at TEXT NOT NULL,                 -- Record creation time
    updated_at TEXT NOT NULL,                 -- Last update
    onboarded_at TEXT,                        -- When person completed onboarding
    last_active_at TEXT,                      -- Most recent activity timestamp
    deactivated_at TEXT,                      -- If person left household or deactivated account

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (household_id) REFERENCES households(household_id) ON DELETE SET NULL
);

CREATE INDEX idx_people_tenant ON people(tenant_id);
CREATE INDEX idx_people_household ON people(household_id) WHERE household_id IS NOT NULL;
CREATE INDEX idx_people_label ON people(label);
CREATE INDEX idx_people_canonical ON people(canonical_person_id) WHERE canonical_person_id IS NOT NULL;
CREATE INDEX idx_people_privacy ON people(privacy_band);
CREATE INDEX idx_people_crdt_tombstone ON people(crdt_tombstone, tenant_id);
CREATE INDEX idx_people_last_active ON people(last_active_at DESC);

-- ============================================================================
-- Table: households (Tenant Metadata - Family/Household Configuration)
-- ============================================================================
-- Purpose: Tenant-level configuration and policy profiles
-- Source: Household onboarding, admin configuration
-- Lifecycle: Long-term (one record per household/tenant)

CREATE TABLE IF NOT EXISTS households (
    -- IDENTITY
    household_id TEXT PRIMARY KEY,            -- Unique household identifier (matches tenant_id)
    cognitive_trace_id TEXT NOT NULL,         -- End-to-end observability

    -- HOUSEHOLD INFO
    label TEXT NOT NULL,                      -- Display name (The Smith Family, Johnson Household)
    household_type TEXT DEFAULT 'family',     -- family, multi_generational, single_person, shared_living, institutional
    address TEXT,                             -- Physical address (encrypted if sensitive)
    timezone TEXT DEFAULT 'UTC',              -- Household timezone

    -- MEMBERS
    member_count INTEGER DEFAULT 0,           -- Total people in household (denormalized for quick access)
    adult_count INTEGER DEFAULT 0,            -- Number of adults
    child_count INTEGER DEFAULT 0,            -- Number of children
    primary_contact_person_id TEXT,           -- Primary household contact (foreign key to people)

    -- POLICY CONFIGURATION
    policy_profile TEXT DEFAULT 'balanced',   -- strict, balanced, relaxed (affects privacy/sharing defaults)
    retention_defaults TEXT,                  -- JSON: {"episodic_days": 365, "semantic_days": 730, "prospective_hours": 24}
    privacy_defaults TEXT,                    -- JSON: {"default_band": "AMBER", "share_with_household": true, "external_sharing": false}

    -- RATE LIMITS & QUOTAS
    rate_limits TEXT,                         -- JSON: {"api_calls_per_hour": 1000, "writes_per_minute": 100, "embeddings_per_day": 10000}
    storage_quota_gb INTEGER DEFAULT 100,     -- Storage limit in GB
    storage_used_gb REAL DEFAULT 0.0,         -- Current storage usage

    -- SUBSCRIPTION & BILLING (if applicable)
    subscription_tier TEXT DEFAULT 'free',    -- free, basic, premium, enterprise
    subscription_status TEXT DEFAULT 'active', -- active, suspended, cancelled, trial
    subscription_expires_at TEXT,             -- ISO8601 timestamp
    billing_email TEXT,                       -- Contact for billing

    -- FEATURE FLAGS
    features_enabled TEXT,                    -- JSON array: ["prospective_memory", "health_tracking", "financial_connectors", "imagination"]
    experimental_features TEXT,               -- JSON array of beta features enabled

    -- EXTERNAL INTEGRATIONS
    connected_services TEXT,                  -- JSON array: [{"service": "strava", "status": "active", "connected_at": "2025-01-01"}]
    connector_count INTEGER DEFAULT 0,        -- Number of active connectors

    -- ACCESS CONTROL
    tenant_id TEXT NOT NULL UNIQUE,           -- Tenant ID (same as household_id, for foreign key consistency)
    privacy_band TEXT NOT NULL DEFAULT 'AMBER' CHECK (privacy_band IN ('GREEN', 'AMBER', 'RED', 'BLACK')),
    visible_to TEXT NOT NULL,                 -- JSON array of person_ids who can see household config (usually all members)

    -- SYNC (CRDT)
    crdt_vector_clock TEXT NOT NULL,          -- JSON: {"device1": 5, "device2": 3}
    crdt_tombstone INTEGER DEFAULT 0,         -- Soft delete flag (households rarely deleted)
    crdt_lamport INTEGER NOT NULL,            -- Lamport timestamp

    -- LIFECYCLE
    created_at TEXT NOT NULL,                 -- Household creation time
    updated_at TEXT NOT NULL,                 -- Last update
    onboarded_at TEXT,                        -- When household completed setup
    last_active_at TEXT,                      -- Most recent household activity
    deactivated_at TEXT,                      -- If household deactivated

    -- Indexes
    FOREIGN KEY (tenant_id) REFERENCES st_devices(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (primary_contact_person_id) REFERENCES people(person_id) ON DELETE SET NULL
);

CREATE INDEX idx_households_tenant ON households(tenant_id);
CREATE INDEX idx_households_label ON households(label);
CREATE INDEX idx_households_subscription ON households(subscription_tier, subscription_status);
CREATE INDEX idx_households_primary_contact ON households(primary_contact_person_id) WHERE primary_contact_person_id IS NOT NULL;
CREATE INDEX idx_households_crdt_tombstone ON households(crdt_tombstone, tenant_id);
CREATE INDEX idx_households_last_active ON households(last_active_at DESC);

COMMIT;

-- Post-migration validation queries (run manually):
-- SELECT COUNT(*) FROM people;  -- Should be 0 (empty table, populated during onboarding)
-- SELECT COUNT(*) FROM households;  -- Should be 0 (empty table, populated during onboarding)
--
-- -- Test foreign key relationships:
-- SELECT p.person_id, p.label, h.label as household_name
-- FROM people p
-- LEFT JOIN households h ON p.household_id = h.household_id;
--
-- SELECT name FROM sqlite_master WHERE type='table' AND (name = 'people' OR name = 'households') ORDER BY name;
-- SELECT name FROM sqlite_master WHERE type='index' AND (name LIKE 'idx_people_%' OR name LIKE 'idx_households_%') ORDER BY name;
