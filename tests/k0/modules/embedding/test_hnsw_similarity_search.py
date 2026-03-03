"""Integration tests for HNSW similarity search DDL validation.

Validates that the pgvector HNSW index in migration 0071 is correctly
configured for cosine distance nearest-neighbor queries:
- HNSW index on vector column
- vector_cosine_ops operator class (cosine distance)
- m=16 (max neighbors per node)
- ef_construction=64 (build-time search width)
- Index name follows naming convention
- Separate B-tree indexes for filtered queries

Epic: M4 4.21
Migration: k0/db/alembic/versions/0071_st_vec_pgvector_native.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = Path("k0/db/alembic/versions/0071_st_vec_pgvector_native.py")


@pytest.fixture(scope="module")
def migration_text() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def hnsw_ddl(migration_text: str) -> str:
    """Extract the HNSW CREATE INDEX statement (including WITH clause)."""
    # Find the full op.execute block containing ix_st_vec_hnsw
    start = migration_text.index("ix_st_vec_hnsw")
    # Find the closing triple-quote after the HNSW DDL
    end = migration_text.index('"""', start)
    return migration_text[start:end]


# =============================================================================
# HNSW Index Configuration Tests
# =============================================================================


class TestHNSWIndexConfiguration:
    """Validate HNSW index parameters for optimal cosine similarity search."""

    def test_hnsw_index_uses_correct_table(self, hnsw_ddl: str) -> None:
        assert "ON st_vec" in hnsw_ddl

    def test_hnsw_index_on_vector_column(self, hnsw_ddl: str) -> None:
        assert "(vector" in hnsw_ddl or "( vector" in hnsw_ddl or "(vector " in hnsw_ddl

    def test_cosine_distance_operator(self, hnsw_ddl: str) -> None:
        assert (
            "vector_cosine_ops" in hnsw_ddl
        ), "Must use vector_cosine_ops for cosine distance (not L2 or inner product)"

    def test_hnsw_m_parameter(self, hnsw_ddl: str) -> None:
        match = re.search(r"m\s*=\s*(\d+)", hnsw_ddl)
        assert match, "HNSW m parameter not found"
        assert int(match.group(1)) == 16, "HNSW m should be 16"

    def test_hnsw_ef_construction_parameter(self, hnsw_ddl: str) -> None:
        match = re.search(r"ef_construction\s*=\s*(\d+)", hnsw_ddl)
        assert match, "HNSW ef_construction parameter not found"
        assert int(match.group(1)) == 64, "HNSW ef_construction should be 64"

    def test_hnsw_index_name(self, hnsw_ddl: str) -> None:
        assert "ix_st_vec_hnsw" in hnsw_ddl, "HNSW index should be named ix_st_vec_hnsw"


# =============================================================================
# B-tree Indexes for Filtered Queries
# =============================================================================


class TestBTreeIndexes:
    """Validate B-tree indexes for pre-filtering before HNSW scan."""

    def test_event_id_index(self, migration_text: str) -> None:
        assert "ix_st_vec_event" in migration_text, "Event ID B-tree index missing"

    def test_tenant_space_index(self, migration_text: str) -> None:
        assert "ix_st_vec_tenant" in migration_text, "Tenant/space B-tree index missing"
        assert (
            "(tenant_id, space_id)" in migration_text
        ), "Tenant index should be composite (tenant_id, space_id)"

    def test_model_id_index(self, migration_text: str) -> None:
        assert "ix_st_vec_model" in migration_text, "Model ID B-tree index missing"

    def test_status_index(self, migration_text: str) -> None:
        assert "ix_st_vec_status" in migration_text, "Status B-tree index missing"

    def test_created_at_index(self, migration_text: str) -> None:
        assert "ix_st_vec_created" in migration_text, "Created timestamp B-tree index missing"

    def test_total_index_count(self, migration_text: str) -> None:
        # 5 B-tree + 1 HNSW = 6 total indexes
        btree_indexes = re.findall(r"CREATE INDEX (ix_st_vec_\w+)", migration_text)
        assert (
            len(btree_indexes) == 6
        ), f"Expected 6 indexes, found {len(btree_indexes)}: {btree_indexes}"


# =============================================================================
# Vector Dimension Contract
# =============================================================================


class TestVectorDimensionContract:
    """Validate vector dimension is fixed at 768 for UltraBERT v2.1.0."""

    def test_vector_dim_768(self, migration_text: str) -> None:
        assert "VECTOR(768)" in migration_text

    def test_vector_dim_default(self, migration_text: str) -> None:
        assert "DEFAULT 768" in migration_text, "vector_dim should default to 768"

    def test_vector_column_not_nullable(self, migration_text: str) -> None:
        # The vector column line should have NOT NULL
        vector_line_match = re.search(r"vector\s+VECTOR\(768\)\s+NOT NULL", migration_text)
        assert vector_line_match, "vector column must be NOT NULL"
