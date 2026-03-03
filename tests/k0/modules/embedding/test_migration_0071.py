"""Integration tests for Migration 0071 -- st_vec pgvector-native schema.

Validates the DDL in 0071_st_vec_pgvector_native.py conforms to the
st_vec_v2.columns.yaml contract:
- VECTOR(768) column with pgvector native type
- HNSW index with vector_cosine_ops (m=16, ef_construction=64)
- TEXT primary key and foreign key (matches st_hipp_events.event_id TEXT)
- No FAISS columns (faiss_id, indexed_at removed)
- TIMESTAMPTZ timestamps (not BigInteger epoch)
- Status CHECK: READY/FAILED only (INDEXED removed)
- FK constraint fk_st_vec_event with ON DELETE CASCADE

Epic: M4 4.21
Contract: k0/contracts/schemas/st_vec_v2.columns.yaml
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

MIGRATION_PATH = Path("k0/db/alembic/versions/0071_st_vec_pgvector_native.py")
SCHEMA_CONTRACT_PATH = Path("k0/contracts/schemas/st_vec_v2.columns.yaml")


@pytest.fixture(scope="module")
def migration_sql() -> str:
    """Read migration file and extract the full CREATE TABLE statement."""
    content = MIGRATION_PATH.read_text(encoding="utf-8")
    return content


@pytest.fixture(scope="module")
def schema_contract() -> dict:
    """Load the st_vec v2 schema contract."""
    return yaml.safe_load(SCHEMA_CONTRACT_PATH.read_text(encoding="utf-8"))


# =============================================================================
# Schema Structural Tests
# =============================================================================


class TestMigration0071Schema:
    """Validate migration DDL matches st_vec v2 contract."""

    def test_migration_file_exists(self) -> None:
        assert MIGRATION_PATH.exists(), "Migration 0071 file missing"

    def test_schema_contract_exists(self) -> None:
        assert SCHEMA_CONTRACT_PATH.exists(), "st_vec v2 schema contract missing"

    def test_vector_768_column_present(self, migration_sql: str) -> None:
        assert "VECTOR(768)" in migration_sql, "pgvector VECTOR(768) column not found"

    def test_hnsw_index_present(self, migration_sql: str) -> None:
        assert "using hnsw" in migration_sql.lower(), "HNSW index not found"

    def test_hnsw_cosine_ops(self, migration_sql: str) -> None:
        assert "vector_cosine_ops" in migration_sql, "vector_cosine_ops operator class missing"

    def test_hnsw_m16(self, migration_sql: str) -> None:
        assert "m = 16" in migration_sql, "HNSW m=16 parameter missing"

    def test_hnsw_ef_construction_64(self, migration_sql: str) -> None:
        assert "ef_construction = 64" in migration_sql, "HNSW ef_construction=64 missing"

    def test_no_faiss_id_column(self, migration_sql: str) -> None:
        # The CREATE TABLE should not contain faiss_id
        # (old drop_index references are OK -- they clean up legacy)
        create_start = migration_sql.index("CREATE TABLE st_vec")
        create_end = migration_sql.index(")", create_start + 100) + 1
        create_ddl = migration_sql[create_start:create_end]
        assert "faiss_id" not in create_ddl, "faiss_id column should be removed in v2"

    def test_no_indexed_at_column(self, migration_sql: str) -> None:
        create_start = migration_sql.index("CREATE TABLE st_vec")
        create_end = migration_sql.index(")", create_start + 100) + 1
        create_ddl = migration_sql[create_start:create_end]
        assert "indexed_at" not in create_ddl, "indexed_at column should be removed in v2"

    def test_embedding_id_text_primary_key(self, migration_sql: str) -> None:
        assert (
            "embedding_id    TEXT PRIMARY KEY" in migration_sql
        ), "embedding_id must be TEXT PRIMARY KEY (not UUID)"

    def test_event_id_text_not_null(self, migration_sql: str) -> None:
        assert (
            "event_id        TEXT NOT NULL" in migration_sql
        ), "event_id must be TEXT NOT NULL (matches st_hipp_events.event_id TEXT)"

    def test_fk_constraint_present(self, migration_sql: str) -> None:
        assert "fk_st_vec_event" in migration_sql, "FK constraint fk_st_vec_event missing"

    def test_fk_references_st_hipp_events(self, migration_sql: str) -> None:
        assert (
            "REFERENCES st_hipp_events(event_id)" in migration_sql
        ), "FK must reference st_hipp_events(event_id)"

    def test_fk_cascade_delete(self, migration_sql: str) -> None:
        assert "ON DELETE CASCADE" in migration_sql, "FK must use ON DELETE CASCADE"

    def test_timestamptz_created_at(self, migration_sql: str) -> None:
        assert "TIMESTAMPTZ" in migration_sql, "created_at should be TIMESTAMPTZ"

    def test_status_check_constraint(self, migration_sql: str) -> None:
        assert "ck_st_vec_status" in migration_sql, "Status CHECK constraint missing"
        assert "'READY'" in migration_sql, "READY status missing from CHECK"
        assert "'FAILED'" in migration_sql, "FAILED status missing from CHECK"

    def test_no_indexed_status(self, migration_sql: str) -> None:
        # INDEXED was removed in v2 -- only READY and FAILED allowed
        check_start = migration_sql.index("ck_st_vec_status")
        check_end = migration_sql.index(")", check_start)
        check_clause = migration_sql[check_start:check_end]
        assert "INDEXED" not in check_clause, "INDEXED status should be removed in v2"

    def test_pgvector_extension_created(self, migration_sql: str) -> None:
        assert "CREATE EXTENSION IF NOT EXISTS vector" in migration_sql


# =============================================================================
# Contract Alignment Tests
# =============================================================================


class TestMigration0071ContractAlignment:
    """Verify migration DDL matches the schema contract YAML."""

    def test_contract_version(self, schema_contract: dict) -> None:
        assert schema_contract["version"] == "2.0.0"

    def test_contract_migration_id(self, schema_contract: dict) -> None:
        assert schema_contract["migration"] == "0071"

    def test_contract_column_count(self, schema_contract: dict) -> None:
        assert schema_contract["column_count"] == 11
        assert len(schema_contract["columns"]) == 11

    def test_contract_engine(self, schema_contract: dict) -> None:
        assert schema_contract["engine"] == "pgvector"

    def test_contract_embedding_id_type(self, schema_contract: dict) -> None:
        col = schema_contract["columns"]["embedding_id"]
        assert col["type"] == "TEXT"
        assert col["primary_key"] is True

    def test_contract_event_id_type(self, schema_contract: dict) -> None:
        col = schema_contract["columns"]["event_id"]
        assert col["type"] == "TEXT"
        assert col["foreign_key"]["table"] == "st_hipp_events"

    def test_contract_vector_type(self, schema_contract: dict) -> None:
        col = schema_contract["columns"]["vector"]
        assert col["type"] == "VECTOR(768)"

    def test_btree_indexes_in_migration(self, migration_sql: str) -> None:
        expected_indexes = [
            "ix_st_vec_event",
            "ix_st_vec_tenant",
            "ix_st_vec_model",
            "ix_st_vec_status",
            "ix_st_vec_created",
        ]
        for idx_name in expected_indexes:
            assert idx_name in migration_sql, f"B-tree index {idx_name} missing"

    def test_hnsw_index_in_migration(self, migration_sql: str) -> None:
        assert "ix_st_vec_hnsw" in migration_sql, "HNSW index ix_st_vec_hnsw missing"

    def test_downgrade_drops_table(self, migration_sql: str) -> None:
        assert "DROP TABLE IF EXISTS st_vec" in migration_sql, "Downgrade must drop st_vec"
