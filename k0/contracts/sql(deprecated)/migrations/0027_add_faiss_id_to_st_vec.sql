-- ========================================================================================
-- Migration 0027: Add FAISS ID Mapping to st_vec Table
-- ========================================================================================
-- Created: 2025-12-13
-- ADR: K003 - Inline Embedding Generation (P08 v2 FAISS Integration)
-- Purpose: Add faiss_id column to st_vec for UUID ↔ int64 ID mapping
--          Enables efficient FAISS index operations (FAISS requires int64 IDs)
-- Related: docs/plans/P02_P08_inline_embedding_implementation_plan.md (Milestone 3)
--          k0/runtime/faiss_manager.py (FaissIndexManager)
-- ========================================================================================
-- Impact:
--   - ADD COLUMN: faiss_id INTEGER (nullable, auto-assigned by FaissIndexManager)
--   - ADD INDEX: idx_vec_faiss_id for reverse lookups (FAISS ID → embedding_id)
--   - ADD COLUMN: indexed_at INTEGER (tracks when FAISS indexing completed)
--   - Enables P08 M24 (embedding.faiss_indexer) to add vectors to FAISS IVF256,PQ64 index
-- ========================================================================================
-- Architecture Notes:
--   - FAISS requires int64 IDs, we use UUID strings (embedding_id)
--   - FaissIndexManager maintains in-memory mapping during runtime
--   - faiss_id persisted here for rebuild/restart scenarios
--   - indexed_at tracks P08 M24 completion (status=INDEXED when not NULL)
-- ========================================================================================

BEGIN;

PRAGMA foreign_keys=ON;

-- ========================================================================================
-- Add faiss_id Column
-- ========================================================================================
-- Purpose: Store FAISS int64 ID for each embedding
-- Values:
--   - NULL: Not yet indexed by P08 M24 (status=READY)
--   - int64: Indexed in FAISS (status=INDEXED)
-- Auto-assigned by FaissIndexManager.register_embedding_id()
-- ========================================================================================

ALTER TABLE st_vec
ADD COLUMN faiss_id INTEGER;

-- ========================================================================================
-- Add indexed_at Column
-- ========================================================================================
-- Purpose: Track when FAISS indexing completed (Unix timestamp)
-- Values:
--   - NULL: Not indexed (status=READY)
--   - timestamp: Indexed by P08 M24 (status=INDEXED)
-- ========================================================================================

ALTER TABLE st_vec
ADD COLUMN indexed_at INTEGER;

-- ========================================================================================
-- Create Index on faiss_id
-- ========================================================================================
-- Purpose: Enable fast reverse lookups (FAISS ID → embedding_id)
-- Used by: FaissIndexManager.search() to map int64 results back to UUIDs
-- ========================================================================================

CREATE INDEX idx_vec_faiss_id ON st_vec(faiss_id);

-- ========================================================================================
-- Verification Queries
-- ========================================================================================
-- Run these queries after applying migration to verify correctness:
--
-- [ ] Columns added:
--     PRAGMA table_info(st_vec);
--     Expected: faiss_id INTEGER, indexed_at INTEGER (at end of column list)
--
-- [ ] Index created:
--     SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='st_vec';
--     Expected: idx_vec_faiss_id (in addition to existing 4 indexes)
--
-- [ ] Existing rows have NULL values:
--     SELECT COUNT(*) FROM st_vec WHERE faiss_id IS NULL;
--     Expected: All rows (backward compatible)
--
-- [ ] Test assignment:
--     UPDATE st_vec SET faiss_id=12345, indexed_at=1234567890 WHERE embedding_id='test_id';
--     SELECT faiss_id, indexed_at FROM st_vec WHERE embedding_id='test_id';
--     Expected: 12345, 1234567890
-- ========================================================================================

COMMIT;

-- ========================================================================================
-- Rollback Script (Run to undo this migration)
-- ========================================================================================
-- WARNING: SQLite does not support DROP COLUMN directly.
-- Rollback requires table recreation (data preserved).
--
-- BEGIN;
--   PRAGMA foreign_keys=OFF;
--
--   -- Create new table without faiss_id and indexed_at
--   CREATE TABLE st_vec_new (
--     embedding_id TEXT PRIMARY KEY,
--     event_id TEXT NOT NULL,
--     tenant_id TEXT NOT NULL,
--     space_id TEXT NOT NULL,
--     vector BLOB NOT NULL,
--     vector_dim INTEGER NOT NULL DEFAULT 768,
--     model_id TEXT NOT NULL DEFAULT 'ultrabert_v2.1.0',
--     status TEXT NOT NULL DEFAULT 'READY' CHECK(status IN ('READY', 'INDEXED', 'FAILED')),
--     created_at INTEGER NOT NULL,
--     updated_at INTEGER NOT NULL,
--     FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id) ON DELETE CASCADE
--   );
--
--   -- Copy data (excluding faiss_id and indexed_at)
--   INSERT INTO st_vec_new
--   SELECT embedding_id, event_id, tenant_id, space_id, vector, vector_dim,
--          model_id, status, created_at, updated_at
--   FROM st_vec;
--
--   -- Drop old table
--   DROP TABLE st_vec;
--
--   -- Rename new table
--   ALTER TABLE st_vec_new RENAME TO st_vec;
--
--   -- Recreate original indexes
--   CREATE INDEX idx_vec_event_id ON st_vec(event_id);
--   CREATE INDEX idx_vec_tenant_space ON st_vec(tenant_id, space_id);
--   CREATE INDEX idx_vec_model_id ON st_vec(model_id);
--   CREATE INDEX idx_vec_status_created ON st_vec(status, created_at) WHERE status = 'READY';
--
--   PRAGMA foreign_keys=ON;
-- COMMIT;
-- ========================================================================================
