-- ========================================================================================
-- Migration 0026: Inline Embedding via UltraBERT - st_vec Table
-- ========================================================================================
-- Created: 2025-12-13
-- ADR: K003 - Inline Embedding Generation via UltraBERT Single-Pass Cache
-- Purpose: Create st_vec table for storing 768-dim UltraBERT embeddings inline with P02
--          Replaces async P08 embedding generation with immediate inline storage
-- Related: docs/architecture/decisions-K0/pipelines/k003-inline-embedding-ultrabert.md
--          docs/pipelines/P08_embedding_dossier_v2.md (P08 repurposed for FAISS/backfill)
--          docs/plans/P02_P08_inline_embedding_implementation_plan.md
-- ========================================================================================
-- Impact:
--   - NEW table: st_vec (10 columns) - Primary embedding storage (replaces P08 async path)
--   - st_embedding_queue remains but DEPRECATED (kept for legacy backfill via P08 v2)
--   - P02 writes embeddings directly to st_vec with status=READY (immediate availability)
--   - P08 v2 repurposed for: FAISS indexing, backfill, model upgrades, cleanup
--   - Embedding model: UltraBERT v2.1.0 (768-dim) replaces MiniLM (384-dim)
--   - Storage increase: 3072 bytes per vector (768 floats × 4 bytes) vs 1536 bytes
-- ========================================================================================
-- Architecture Change Summary:
--   BEFORE (Async P08):
--     P02 → st_embedding_queue (PENDING) → P08 claims job → MiniLM computes 384-dim
--         → st_vec/st_embeddings → status=READY (seconds later)
--
--   AFTER (Inline P02 + ADR-K003):
--     P02 → M22 extracts 768-dim from UltraBERT cache (~0ms)
--         → M23 writes directly to st_vec (status=READY, immediate availability)
--         → P03 consolidation can use embeddings immediately (no fallback to Jaccard)
-- ========================================================================================

BEGIN;

PRAGMA foreign_keys=ON;

-- ========================================================================================
-- Table: st_vec (NEW) - Inline Embedding Storage
-- ========================================================================================
-- Purpose: Store 768-dimensional UltraBERT embeddings generated inline by P02 M22/M23
--          Primary embedding storage replacing async P08 pattern
-- Usage:
--   - P02 M23 (builders.embedding_write:v1): Writes embeddings with status=READY
--   - P08 M24 (embedding.faiss_indexer:v1): Updates status to INDEXED after FAISS add
--   - P08 M25 (embedding.backfill:v1): Backfills legacy PENDING embeddings from st_embedding_queue
--   - P03 CA1 Bridge: Reads for semantic similarity scoring (no PENDING fallback needed)
-- Columns: 10 (Identity, Linkage, Vector Data, Model Info, Status, Timestamps)
-- Indexes: 4 (Event lookup, Tenant/Space queries, Model version, FAISS status)
-- ========================================================================================

CREATE TABLE IF NOT EXISTS st_vec (
  -- Identity
  embedding_id TEXT PRIMARY KEY,

  -- Linkage to event
  event_id TEXT NOT NULL,

  -- Tenant/Space Context
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Vector Data (768-dim UltraBERT, stored as packed float32 binary blob)
  vector BLOB NOT NULL,              -- 768 floats × 4 bytes = 3072 bytes
  vector_dim INTEGER NOT NULL DEFAULT 768,

  -- Model Metadata
  model_id TEXT NOT NULL DEFAULT 'ultrabert_v2.1.0',

  -- Status Tracking
  -- READY: Embedding stored by P02 inline (immediately available)
  -- INDEXED: Also added to FAISS index by P08 M24
  -- FAILED: Generation/indexing failed
  status TEXT NOT NULL DEFAULT 'READY' CHECK(status IN ('READY', 'INDEXED', 'FAILED')),

  -- Timestamps
  created_at INTEGER NOT NULL,       -- Unix timestamp (set by P02 M23)
  updated_at INTEGER NOT NULL,       -- Unix timestamp (updated by P08 M24 when indexed)

  -- Foreign Key Constraint
  -- Links embedding to parent event in st_hipp_events
  -- NOTE: event_id must exist before st_vec insert (enforced by P02 M16 atomic writer)
  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id) ON DELETE CASCADE
);

-- Indexes for st_vec
CREATE INDEX idx_vec_event_id ON st_vec(event_id);
CREATE INDEX idx_vec_tenant_space ON st_vec(tenant_id, space_id);
CREATE INDEX idx_vec_model_id ON st_vec(model_id);
CREATE INDEX idx_vec_status_created ON st_vec(status, created_at) WHERE status = 'READY';

-- ========================================================================================
-- DEPRECATION NOTICE: st_embedding_queue
-- ========================================================================================
-- Table st_embedding_queue (created in migration 0024) is now DEPRECATED.
-- Reason: ADR-K003 moves primary embedding generation from async P08 to inline P02.
--
-- Status: ❌ Deprecated (NOT dropped - kept for P08 v2 backfill use cases)
--
-- Use Cases (P08 v2 only):
--   1. Backfill legacy PENDING embeddings (pre-ADR-K003 events)
--   2. Model upgrade recomputation (when model_id changes)
--   3. Manual embedding regeneration requests
--
-- Do NOT use st_embedding_queue for new P02 events:
--   - P02 M14 (builders.embedding_queue_write) is DEPRECATED
--   - Use P02 M23 (builders.embedding_write) → st_vec directly
--
-- Related ADR: k009.2-embedding-queue-writer.md (superseded by K003)
--
-- Migration Path:
--   - Keep st_embedding_queue table for P08 v2 backfill operations
--   - Update st_hipp_events.embedding_status semantics:
--       PENDING → needs backfill (legacy or failed inline)
--       READY → in st_vec, immediately available
--       INDEXED → also in FAISS index
--   - P08 M25 queries st_hipp_events WHERE embedding_status='PENDING' to backfill
-- ========================================================================================

-- ========================================================================================
-- Verification Queries
-- ========================================================================================
-- Run these queries after applying migration to verify correctness:
--
-- [ ] Table exists:
--     SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='st_vec';
--     Expected: 1
--
-- [ ] Column count:
--     PRAGMA table_info(st_vec);
--     Expected: 10 columns (embedding_id, event_id, tenant_id, space_id, vector,
--                           vector_dim, model_id, status, created_at, updated_at)
--
-- [ ] Indexes created:
--     SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='st_vec';
--     Expected: idx_vec_event_id, idx_vec_tenant_space, idx_vec_model_id, idx_vec_status_created
--
-- [ ] Foreign key enforced:
--     PRAGMA foreign_key_list(st_vec);
--     Expected: 1 FK to st_hipp_events(event_id)
--
-- [ ] Check constraint on status:
--     SELECT sql FROM sqlite_master WHERE type='table' AND name='st_vec';
--     Expected: CHECK(status IN ('READY', 'INDEXED', 'FAILED'))
--
-- [ ] Default values:
--     INSERT INTO st_vec (embedding_id, event_id, tenant_id, space_id, vector, created_at, updated_at)
--       VALUES ('test_id', 'test_event', 'tenant1', 'space1', X'00000000', 1234567890, 1234567890);
--     SELECT vector_dim, model_id, status FROM st_vec WHERE embedding_id='test_id';
--     Expected: 768, 'ultrabert_v2.1.0', 'READY'
--     Cleanup: DELETE FROM st_vec WHERE embedding_id='test_id';
-- ========================================================================================

COMMIT;

-- ========================================================================================
-- Rollback Script (Run to undo this migration)
-- ========================================================================================
-- WARNING: This will DELETE all embeddings stored in st_vec.
-- Only run if migration needs to be reverted (e.g., ADR-K003 rejected).
--
-- BEGIN;
--   DROP TABLE IF EXISTS st_vec;
--   -- NOTE: st_embedding_queue remains (was not created by this migration)
--   -- To fully revert to async P08 pattern:
--   --   1. Re-enable P02 M14 (builders.embedding_queue_write)
--   --   2. Re-enable P08 v1 (sentence-transformers pipeline)
--   --   3. Set feature flag: K0_EMBEDDING_INLINE=0
-- COMMIT;
-- ========================================================================================
