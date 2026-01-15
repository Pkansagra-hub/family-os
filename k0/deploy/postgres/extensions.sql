-- K0 PostgreSQL Extensions Configuration
-- Part of Milestone 1.1.1 - PostgreSQL Infrastructure
--
-- Extensions required for K0 kernel operations:
-- 1. vector (pgvector) - Vector similarity search for embeddings
-- 2. pg_trgm - Trigram similarity for fuzzy text search
-- 3. uuid-ossp - UUID generation
-- 4. pgcrypto - Cryptographic functions for hashing
--
-- NOTE: This script runs in k0_kernel database context (set via POSTGRES_DB)

-- Vector similarity search (embeddings)
-- Used by: k0/drivers/pgvector.py, st_vec table, st_hipp_events.embedding
CREATE EXTENSION IF NOT EXISTS vector;

-- Trigram similarity (fuzzy text search)
-- Used by: Full-text search queries with similarity matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- UUID generation
-- Used by: envelope_id, correlation_id, trace_id generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Cryptographic functions
-- Used by: Content hashing, checksum validation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Verify critical extensions are installed
DO $$
BEGIN
    -- Check pgvector (critical for embeddings)
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'CRITICAL: pgvector extension not installed. Vector operations will fail.';
    END IF;

    -- Check pg_trgm (critical for fuzzy search)
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        RAISE EXCEPTION 'CRITICAL: pg_trgm extension not installed. Fuzzy search will fail.';
    END IF;

    RAISE NOTICE 'All required extensions installed successfully';
END $$;

-- Grant extension usage to k0user
GRANT USAGE ON SCHEMA public TO k0user;
