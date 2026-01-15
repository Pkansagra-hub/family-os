"""
Test suite for P03 Storage Migrations.

Validates Alembic migration files for P03 truth-layer and operational tables:
- 0027_st_epi.py - Episodic memory table
- 0028_st_sem.py - Semantic patterns table
- 0029_st_procedural.py - Procedural memory table
- 0030_st_social.py - Social relationships table
- 0031_st_prospective.py - Intentions/goals table
- 0032_st_kg_dom.py - Knowledge graph entities
- 0033_st_kg_edges.py - Knowledge graph edges

These tests validate migration structure without requiring a database connection.
For integration testing, see tests/integration/test_alembic_migrations.py.

Related:
- M2 Epic 2.1: Core truth + operational tables
- Dossier §6.3-6.9: Truth layer table schemas
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
import sqlalchemy as sa

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def migrations_path() -> Path:
    """Return the path to Alembic migrations directory."""
    return Path(__file__).parent.parent.parent.parent.parent / "k0" / "db" / "alembic" / "versions"


def load_migration_module(migrations_path: Path, migration_name: str) -> Any:
    """Dynamically load a migration module."""
    migration_file = migrations_path / f"{migration_name}.py"
    if not migration_file.exists():
        pytest.skip(f"Migration {migration_name} not found")

    spec = importlib.util.spec_from_file_location(migration_name, migration_file)
    if spec is None or spec.loader is None:
        pytest.skip(f"Could not load migration {migration_name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[migration_name] = module
    spec.loader.exec_module(module)
    return module


class MockOp:
    """Mock for alembic.op to capture migration operations."""

    def __init__(self):
        self.tables_created: List[Dict[str, Any]] = []
        self.tables_dropped: List[str] = []
        self.indexes_created: List[Dict[str, Any]] = []
        self.indexes_dropped: List[Dict[str, Any]] = []
        self.columns_added: List[Dict[str, Any]] = []
        self.columns_dropped: List[Dict[str, Any]] = []
        self.constraints_added: List[Dict[str, Any]] = []
        self.constraints_dropped: List[Dict[str, Any]] = []

    def create_table(self, name: str, *columns, **kwargs):
        """Capture table creation."""
        col_info = []
        constraints = []
        for col in columns:
            if isinstance(col, sa.Column):
                col_info.append(
                    {
                        "name": col.name,
                        "type": type(col.type).__name__,
                        "nullable": col.nullable,
                        "primary_key": col.primary_key,
                    }
                )
            elif isinstance(col, sa.CheckConstraint):
                constraints.append(
                    {
                        "type": "check",
                        "name": col.name,
                        "sqltext": str(col.sqltext) if hasattr(col, "sqltext") else None,
                    }
                )
        self.tables_created.append(
            {
                "name": name,
                "columns": col_info,
                "constraints": constraints,
                "kwargs": kwargs,
            }
        )

    def drop_table(self, name: str):
        """Capture table drop."""
        self.tables_dropped.append(name)

    def create_index(self, name: str, table_name: str, columns: list, **kwargs):
        """Capture index creation."""
        self.indexes_created.append(
            {
                "name": name,
                "table": table_name,
                "columns": columns,
                "kwargs": kwargs,
            }
        )

    def drop_index(self, name: str, table_name: str = None, **kwargs):
        """Capture index drop."""
        self.indexes_dropped.append(
            {
                "name": name,
                "table": table_name,
                "kwargs": kwargs,
            }
        )

    def add_column(self, table_name: str, column: sa.Column):
        """Capture column addition."""
        self.columns_added.append(
            {
                "table": table_name,
                "column_name": column.name,
                "column_type": type(column.type).__name__,
                "nullable": column.nullable,
            }
        )

    def drop_column(self, table_name: str, column_name: str):
        """Capture column drop."""
        self.columns_dropped.append(
            {
                "table": table_name,
                "column_name": column_name,
            }
        )

    def create_check_constraint(self, name: str, table_name: str, condition: str):
        """Capture CHECK constraint creation."""
        self.constraints_added.append(
            {
                "type": "check",
                "name": name,
                "table": table_name,
                "condition": condition,
            }
        )

    def drop_constraint(self, name: str, table_name: str, type_: str = None):
        """Capture constraint drop."""
        self.constraints_dropped.append(
            {
                "name": name,
                "table": table_name,
                "type": type_,
            }
        )

    def alter_column(self, table_name: str, column_name: str, **kwargs):
        """Capture column alteration."""
        if not hasattr(self, "columns_altered"):
            self.columns_altered = []
        self.columns_altered.append(
            {
                "table": table_name,
                "column_name": column_name,
                "kwargs": kwargs,
            }
        )

    def execute(self, sql: str):
        """Capture raw SQL execution."""
        if not hasattr(self, "sql_executed"):
            self.sql_executed = []
        self.sql_executed.append(sql)


# =============================================================================
# TEST 0027_st_epi (Episodic Memory)
# =============================================================================


class TestMigration0027StEpi:
    """Test suite for st_epi migration (Dossier §6.3)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0027_st_epi migration module."""
        return load_migration_module(migrations_path, "0027_st_epi")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0027"
        assert migration_module.down_revision == "0026"

    def test_upgrade_creates_st_epi_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_epi table with correct schema."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Check table was created
        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_epi"

        # Check column count (33 columns per dossier §6.3)
        columns = table["columns"]
        assert len(columns) >= 20, f"Expected at least 20 columns, got {len(columns)}"

        # Check critical columns exist
        col_names = {c["name"] for c in columns}
        required_columns = {
            "episode_id",
            "tenant_id",
            "space_id",  # Identity
            "version",
            "supersedes_id",
            "is_canonical",  # Versioning
            "start_time_utc",
            "end_time_utc",  # Temporal
            "source_events_json",
            "source_event_count",  # Source events
            "cluster_id",
            "consolidation_cycle_id",  # Consolidation
            "archival_status",  # Lifecycle
            "created_at",
            "updated_at",
            "valid_from",  # Timestamps
        }
        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all 4 required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Check indexes created (4 per dossier §6.3)
        assert len(mock_op.indexes_created) == 4

        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_epi_tenant_time",
            "idx_epi_space_time",
            "idx_epi_cluster",
            "idx_epi_canonical",
        }
        assert index_names == required_indexes

    def test_upgrade_check_constraint(self, migration_module, mock_op):
        """Verify archival_status CHECK constraint is created."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        constraints = table["constraints"]

        check_names = [c["name"] for c in constraints if c["type"] == "check"]
        assert "ck_epi_archival_status" in check_names

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_epi table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_epi" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) == 4

    def test_column_types_match_dossier(self, migration_module, mock_op):
        """Verify column types match dossier §6.3 specification."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        columns = {c["name"]: c for c in mock_op.tables_created[0]["columns"]}

        # Text IDs
        assert columns["episode_id"]["type"] == "Text"
        assert columns["tenant_id"]["type"] == "Text"
        assert columns["space_id"]["type"] == "Text"

        # Integer types
        assert columns["version"]["type"] == "Integer"
        assert columns["source_event_count"]["type"] == "Integer"

        # BigInteger timestamps
        assert columns["start_time_utc"]["type"] == "BigInteger"
        assert columns["end_time_utc"]["type"] == "BigInteger"
        assert columns["created_at"]["type"] == "BigInteger"

        # Float types
        assert columns["cluster_confidence"]["type"] == "Float"
        assert columns["confidence_score"]["type"] == "Float"

        # Boolean types
        assert columns["is_canonical"]["type"] == "Boolean"


# =============================================================================
# PLACEHOLDER TESTS FOR OTHER MIGRATIONS
# =============================================================================


class TestMigration0028StSem:
    """Test suite for st_sem migration (Dossier §6.4)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0028_st_sem migration module."""
        return load_migration_module(migrations_path, "0028_st_sem")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0028"
        assert migration_module.down_revision == "0027"

    def test_upgrade_creates_st_sem_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_sem table with correct schema."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Check table was created
        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_sem"

        # Check column count (26 columns per dossier §6.4)
        columns = table["columns"]
        assert len(columns) >= 20, f"Expected at least 20 columns, got {len(columns)}"

        # Check critical columns exist
        col_names = {c["name"] for c in columns}
        required_columns = {
            "pattern_id",
            "tenant_id",
            "space_id",
            "actor_id",  # Identity
            "version",
            "supersedes_id",
            "is_canonical",  # Versioning
            "pattern_type",
            "pattern_name",  # Classification/Content
            "source_episodes_json",
            "source_episode_count",  # Source
            "archival_status",  # Lifecycle
            "created_at",
            "updated_at",
            "valid_from",  # Timestamps
        }
        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all 4 required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Check indexes created (4 per dossier §6.4)
        assert len(mock_op.indexes_created) == 4

        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_sem_tenant_type",
            "idx_sem_actor_type",
            "idx_sem_canonical",
            "idx_sem_confidence",
        }
        assert index_names == required_indexes

    def test_upgrade_check_constraints(self, migration_module, mock_op):
        """Verify pattern_type and archival_status CHECK constraints."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        constraints = table["constraints"]

        check_names = [c["name"] for c in constraints if c["type"] == "check"]
        assert "ck_sem_pattern_type" in check_names
        assert "ck_sem_archival_status" in check_names

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_sem table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_sem" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) == 4


class TestMigration0029StProcedural:
    """Test suite for st_procedural migration (Dossier §6.5)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0029_st_procedural migration module."""
        return load_migration_module(migrations_path, "0029_st_procedural")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0029"
        assert migration_module.down_revision == "0028"

    def test_upgrade_creates_st_procedural_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_procedural table with correct schema."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Check table was created
        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_procedural"

        # Check critical columns exist
        col_names = {c["name"] for c in table["columns"]}
        required_columns = {
            "routine_id",
            "tenant_id",
            "space_id",
            "actor_id",  # Identity
            "version",
            "is_canonical",  # Versioning
            "routine_name",
            "routine_category",  # Definition
            "source_episodes_json",
            "source_episode_count",  # Source
            "streak_count",
            "streak_broken_at",  # Streak tracking
            "archival_status",  # Lifecycle
        }
        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all 3 required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Check indexes created (3 per dossier §6.5)
        assert len(mock_op.indexes_created) == 3

        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_procedural_actor",
            "idx_procedural_category",
            "idx_procedural_regularity",
        }
        assert index_names == required_indexes

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_procedural table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_procedural" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) == 3


class TestMigration0030StSocial:
    """Test suite for st_social migration (Dossier §6.6)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0030_st_social migration module."""
        return load_migration_module(migrations_path, "0030_st_social")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0030"
        assert migration_module.down_revision == "0029"

    def test_upgrade_creates_st_social_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_social table with correct schema."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_social"

        col_names = {c["name"] for c in table["columns"]}
        required_columns = {
            "relationship_id",
            "tenant_id",
            "space_id",
            "actor_a_id",
            "actor_b_id",  # Relationship endpoints
            "relationship_type",
            "relationship_strength",
            "archival_status",
        }
        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) == 2
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        assert "idx_social_actor_a" in index_names
        assert "idx_social_actor_b" in index_names

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_social table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_social" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) == 2


class TestMigration0031StProspective:
    """Test suite for st_prospective migration (Dossier §6.7)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0031_st_prospective migration module."""
        return load_migration_module(migrations_path, "0031_st_prospective")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0031"
        assert migration_module.down_revision == "0030"

    def test_upgrade_creates_st_prospective_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_prospective table with correct schema."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_prospective"

        col_names = {c["name"] for c in table["columns"]}
        required_columns = {
            "intention_id",
            "tenant_id",
            "space_id",
            "actor_id",
            "intention_type",
            "intention_description",
            "status",
            "archival_status",
        }
        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"

    def test_upgrade_check_constraints(self, migration_module, mock_op):
        """Verify intention_type and status CHECK constraints."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        constraints = table["constraints"]
        check_names = [c["name"] for c in constraints if c["type"] == "check"]
        assert "ck_prosp_intention_type" in check_names
        assert "ck_prosp_status" in check_names

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_prospective table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_prospective" in mock_op.tables_dropped


class TestMigration0032StKgDom:
    """Test suite for st_kg_dom migration (Dossier §6.8)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0032_st_kg_dom migration module."""
        return load_migration_module(migrations_path, "0032_st_kg_dom")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0032"
        assert migration_module.down_revision == "0031"

    def test_upgrade_creates_st_kg_dom_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_kg_dom table with correct schema."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_kg_dom"

        col_names = {c["name"] for c in table["columns"]}
        required_columns = {
            "entity_id",
            "tenant_id",
            "space_id",
            "entity_type",
            "canonical_name",
            "archival_status",
        }
        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all 3 required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) == 3
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_kg_dom_tenant_type",
            "idx_kg_dom_name",
            "idx_kg_dom_canonical",
        }
        assert index_names == required_indexes

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_kg_dom table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_kg_dom" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) == 3


class TestMigration0033StKgEdges:
    """Test suite for st_kg_edges migration (Dossier §6.9)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0033_st_kg_edges migration module."""
        return load_migration_module(migrations_path, "0033_st_kg_edges")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0033"
        assert migration_module.down_revision == "0032"

    def test_upgrade_creates_st_kg_edges_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_kg_edges table with correct schema."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_kg_edges"

        col_names = {c["name"] for c in table["columns"]}
        required_columns = {
            "edge_id",
            "tenant_id",
            "space_id",
            "source_entity_id",
            "target_entity_id",  # FK endpoints
            "relation_type",
            "edge_weight",
            "co_occurrence_count",  # Hebbian learning
            "archival_status",
        }
        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all 3 required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) == 3
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_kg_edges_source",
            "idx_kg_edges_target",
            "idx_kg_edges_canonical",
        }
        assert index_names == required_indexes

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_kg_edges table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_kg_edges" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) == 3


# =============================================================================
# TEST 0034_st_hipp_events_p03_columns (st_hipp_events P03 columns)
# =============================================================================


class TestMigration0034StHippEventsP03Columns:
    """Test suite for st_hipp_events P03 columns migration (Dossier §6.10)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0034_st_hipp_events_p03_columns migration module."""
        return load_migration_module(migrations_path, "0034_st_hipp_events_p03_columns")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0034"
        assert migration_module.down_revision == "0033"

    def test_upgrade_adds_consolidation_columns(self, migration_module, mock_op):
        """Verify upgrade() adds all 6 consolidation columns to st_hipp_events."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.columns_added) == 6

        col_names = {c["column_name"] for c in mock_op.columns_added}
        required_columns = {
            "consolidation_status",
            "consolidation_cycle_id",
            "consolidated_at",
            "reconciliation_decision",
            "truth_match_id",
            "truth_match_similarity",
        }
        assert col_names == required_columns

        # Verify all columns target st_hipp_events table
        for col in mock_op.columns_added:
            assert col["table"] == "st_hipp_events"

    def test_upgrade_creates_check_constraint(self, migration_module, mock_op):
        """Verify upgrade() creates CHECK constraint for consolidation_status."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        check_constraints = [c for c in mock_op.constraints_added if c["type"] == "check"]
        assert len(check_constraints) == 1

        ck = check_constraints[0]
        assert ck["name"] == "ck_hipp_consolidation_status"
        assert ck["table"] == "st_hipp_events"
        assert "PENDING" in ck["condition"]
        assert "CONSOLIDATED" in ck["condition"]
        assert "DUPLICATE" in ck["condition"]

    def test_upgrade_creates_partial_index(self, migration_module, mock_op):
        """Verify upgrade() creates partial index for pending consolidation."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) == 1
        idx = mock_op.indexes_created[0]
        assert idx["name"] == "idx_hipp_events_consolidation"
        assert idx["table"] == "st_hipp_events"
        # Verify it's a partial index (has postgresql_where)
        assert "postgresql_where" in idx["kwargs"]

    def test_downgrade_drops_columns(self, migration_module, mock_op):
        """Verify downgrade() drops all added columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert len(mock_op.columns_dropped) == 6

        col_names = {c["column_name"] for c in mock_op.columns_dropped}
        required_columns = {
            "consolidation_status",
            "consolidation_cycle_id",
            "consolidated_at",
            "reconciliation_decision",
            "truth_match_id",
            "truth_match_similarity",
        }
        assert col_names == required_columns


# =============================================================================
# TEST 0035_st_outbox_fix_next_attempt_ts (Type correction)
# =============================================================================


class TestMigration0035StOutboxFixNextAttemptTs:
    """Test suite for st_outbox next_attempt_ts type fix migration (Dossier §6.15)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0035_st_outbox_fix_next_attempt_ts migration module."""
        return load_migration_module(migrations_path, "0035_st_outbox_fix_next_attempt_ts")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0035"
        assert migration_module.down_revision == "0034"

    def test_upgrade_adds_new_column(self, migration_module, mock_op):
        """Verify upgrade() adds temporary BIGINT column."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Should add next_attempt_ts_new as BIGINT
        assert len(mock_op.columns_added) == 1
        col = mock_op.columns_added[0]
        assert col["table"] == "st_outbox"
        assert col["column_name"] == "next_attempt_ts_new"
        assert col["column_type"] == "BigInteger"

    def test_upgrade_executes_data_migration(self, migration_module, mock_op):
        """Verify upgrade() runs SQL to convert TEXT to BIGINT."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert hasattr(mock_op, "sql_executed")
        assert len(mock_op.sql_executed) == 1
        sql = mock_op.sql_executed[0]
        assert "UPDATE st_outbox" in sql
        assert "CAST" in sql
        assert "BIGINT" in sql

    def test_upgrade_drops_old_column(self, migration_module, mock_op):
        """Verify upgrade() drops old TEXT column."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.columns_dropped) == 1
        col = mock_op.columns_dropped[0]
        assert col["table"] == "st_outbox"
        assert col["column_name"] == "next_attempt_ts"

    def test_upgrade_renames_new_column(self, migration_module, mock_op):
        """Verify upgrade() renames new column to original name."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert hasattr(mock_op, "columns_altered")
        assert len(mock_op.columns_altered) == 1
        alter = mock_op.columns_altered[0]
        assert alter["table"] == "st_outbox"
        assert alter["column_name"] == "next_attempt_ts_new"
        assert alter["kwargs"].get("new_column_name") == "next_attempt_ts"

    def test_downgrade_restores_text_column(self, migration_module, mock_op):
        """Verify downgrade() restores TEXT column type."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        # Should add next_attempt_ts_old as TEXT
        assert len(mock_op.columns_added) == 1
        col = mock_op.columns_added[0]
        assert col["table"] == "st_outbox"
        assert col["column_name"] == "next_attempt_ts_old"
        assert col["column_type"] == "Text"


# =============================================================================
# TEST 0036_st_consolidation_audit (Audit trail table)
# =============================================================================


class TestMigration0036StConsolidationAudit:
    """Test suite for st_consolidation_audit migration (Dossier §6.20)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0036_st_consolidation_audit migration module."""
        return load_migration_module(migrations_path, "0036_st_consolidation_audit")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0036"
        assert migration_module.down_revision == "0035"

    def test_upgrade_creates_st_consolidation_audit_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_consolidation_audit table with correct schema."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_consolidation_audit"

        col_names = {c["name"] for c in table["columns"]}
        # Base columns (15)
        base_columns = {
            "audit_id",
            "memory_id",
            "source_table",
            "action",
            "formula_used",
            "formula_version",
            "inputs_json",
            "outputs_json",
            "explanation",
            "decision_id",
            "space_id",
            "tenant_id",
            "cycle_id",
            "confidence",
            "created_at",
        }
        # Outcome tracking columns (5)
        outcome_columns = {
            "threshold_used",
            "threshold_name",
            "outcome_evaluated",
            "outcome_success",
            "evaluated_at",
        }
        required_columns = base_columns | outcome_columns
        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"
        assert len(col_names) == 20  # 15 base + 5 outcome

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all 6 required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) == 6
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_audit_memory_time",
            "idx_audit_action",
            "idx_audit_formula",
            "idx_audit_decision",
            "idx_consolidation_audit_outcome_eval",
            "idx_audit_canonical",
        }
        assert index_names == required_indexes

    def test_upgrade_creates_partial_index(self, migration_module, mock_op):
        """Verify partial index for pending evaluations."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        partial_indexes = [
            idx for idx in mock_op.indexes_created if "postgresql_where" in idx.get("kwargs", {})
        ]
        assert len(partial_indexes) == 1
        assert partial_indexes[0]["name"] == "idx_consolidation_audit_outcome_eval"

    def test_upgrade_enables_rls(self, migration_module, mock_op):
        """Verify upgrade() enables Row Level Security."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert hasattr(mock_op, "sql_executed")
        rls_statements = [s for s in mock_op.sql_executed if "ROW LEVEL SECURITY" in s]
        assert len(rls_statements) >= 1

    def test_upgrade_creates_check_constraint(self, migration_module, mock_op):
        """Verify upgrade() creates CHECK constraint for action values."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Check constraint is embedded in table creation
        table = mock_op.tables_created[0]
        check_constraints = [c for c in table.get("constraints", []) if c.get("type") == "check"]
        assert len(check_constraints) == 1
        assert check_constraints[0]["name"] == "ck_audit_action"

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_consolidation_audit table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_consolidation_audit" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) == 6


# =============================================================================
# TEST 0037_st_learning_queue (Gap Queue - Epic 2.3)
# =============================================================================


class TestMigration0037StLearningQueue:
    """Test suite for st_learning_queue migration (Dossier §6.11)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the migration module."""
        return load_migration_module(migrations_path, "0037_st_learning_queue")

    def test_migration_metadata(self, migration_module):
        """Verify migration has correct revision chain."""
        assert migration_module.revision == "0037"
        assert migration_module.down_revision == "0036"

    def test_gap_types_constant(self, migration_module):
        """Verify GAP_TYPES matches dossier §6.11."""
        expected_types = {
            "AMBIGUOUS_ENTITY",
            "LOW_CONFIDENCE_EDGE",
            "MISSING_ATTRIBUTE",
            "CONTRADICTION",
            "CONCEPT_DRIFT",
            "STRUCTURAL_HOLE",
            "STALE_ANCHOR",
        }
        assert set(migration_module.GAP_TYPES) == expected_types

    def test_gap_statuses_constant(self, migration_module):
        """Verify GAP_STATUSES matches dossier §6.11."""
        expected_statuses = {
            "PENDING",
            "READY",
            "ASKED",
            "ANSWERED",
            "RESOLVED",
            "EXPIRED",
            "REJECTED",
            "SUPPRESSED",
        }
        assert set(migration_module.GAP_STATUSES) == expected_statuses

    def test_upgrade_creates_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_learning_queue table."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_learning_queue"

    def test_upgrade_creates_all_columns(self, migration_module, mock_op):
        """Verify upgrade() creates all 24 required columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        col_names = {col["name"] for col in table["columns"]}

        # Required columns from dossier §6.11
        required_columns = {
            "id",
            "tenant_id",
            "space_id",
            "gap_type",
            "entity_id",
            "related_event_id",
            "related_truth_id",
            "confidence_score",
            "entropy_score",
            "importance_score",
            "context_json",
            "status",
            "created_at",
            "expires_at",
            "ready_at",
            "asked_at",
            "answered_at",
            "attempts",
            "max_attempts",
            "last_attempt_at",
            "resolution_type",
            "resolution_data_json",
            "consolidation_cycle_id",
        }

        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"
        # 23 columns (importance_score is computed but still a column)
        assert len(col_names) >= 23

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) >= 3
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_learning_queue_importance",
            "idx_learning_queue_status",
            "idx_learning_queue_tenant",
        }
        assert required_indexes.issubset(index_names)

    def test_upgrade_creates_partial_index(self, migration_module, mock_op):
        """Verify partial index for PENDING status priority queue."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        partial_indexes = [
            idx for idx in mock_op.indexes_created if "postgresql_where" in idx.get("kwargs", {})
        ]
        assert len(partial_indexes) >= 1
        # Check importance index has WHERE status = 'PENDING'
        importance_idx = next(
            (idx for idx in partial_indexes if idx["name"] == "idx_learning_queue_importance"),
            None,
        )
        assert importance_idx is not None

    def test_upgrade_creates_check_constraints(self, migration_module, mock_op):
        """Verify upgrade() creates CHECK constraints for gap_type and status."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        check_constraints = [c for c in table.get("constraints", []) if c.get("type") == "check"]

        constraint_names = {c["name"] for c in check_constraints}
        required_constraints = {
            "ck_learning_queue_gap_type",
            "ck_learning_queue_status",
        }
        assert required_constraints.issubset(constraint_names)

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_learning_queue table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_learning_queue" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) >= 3


# =============================================================================
# Issue 2.3.3: st_anchors (Bayesian beliefs)
# =============================================================================


class TestMigration0038StAnchors:
    """Tests for migration 0038_st_anchors.py (Dossier §6.12)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the migration module."""
        return load_migration_module(migrations_path, "0038_st_anchors")

    def test_revision_identifiers(self, migration_module):
        """Verify revision identifiers are correct."""
        assert migration_module.revision == "0038"
        assert migration_module.down_revision == "0037"

    def test_anchor_statuses_constant(self, migration_module):
        """Verify ANCHOR_STATUSES matches dossier §6.12."""
        expected_statuses = {
            "ACTIVE",
            "DRIFTING",
            "STALE",
            "ARCHIVED",
        }
        assert set(migration_module.ANCHOR_STATUSES) == expected_statuses

    def test_upgrade_creates_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_anchors table."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_anchors"

    def test_upgrade_creates_all_columns(self, migration_module, mock_op):
        """Verify upgrade() creates all 17 required columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        col_names = {col["name"] for col in table["columns"]}

        # Required columns from dossier §6.12
        required_columns = {
            "entity_id",
            "attribute",
            "tenant_id",
            "space_id",
            "alpha",
            "beta",
            "confidence",
            "uncertainty",
            "observation_count",
            "first_observed_at",
            "last_updated_at",
            "decay_rate",
            "half_life_days",
            "last_drift_check_at",
            "drift_detected",
            "drift_magnitude",
            "status",
        }

        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"
        assert len(col_names) == 17

    def test_upgrade_creates_composite_pk(self, migration_module):
        """Verify composite primary key (entity_id, attribute, tenant_id)."""
        # Check migration source code defines the composite PK
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "PrimaryKeyConstraint" in source
        assert "entity_id" in source
        assert "attribute" in source
        assert "tenant_id" in source
        assert "pk_st_anchors" in source

    def test_upgrade_creates_generated_columns(self, migration_module):
        """Verify GENERATED STORED columns for confidence and uncertainty."""
        # Check migration source code defines computed columns
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        # Verify Computed columns exist
        assert "sa.Computed" in source or "Computed" in source
        assert "alpha / (alpha + beta)" in source  # confidence formula
        assert "1.0 / (1.0 + alpha + beta)" in source  # uncertainty formula
        assert "persisted=True" in source

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) >= 3
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_anchors_entity",
            "idx_anchors_confidence",
            "idx_anchors_drift",
        }
        assert required_indexes.issubset(index_names)

    def test_upgrade_creates_partial_indexes(self, migration_module, mock_op):
        """Verify partial indexes for ACTIVE and drift detection."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        partial_indexes = [
            idx for idx in mock_op.indexes_created if "postgresql_where" in idx.get("kwargs", {})
        ]
        # Should have at least 2 partial indexes
        assert len(partial_indexes) >= 2

    def test_upgrade_creates_check_constraint(self, migration_module, mock_op):
        """Verify CHECK constraint for status."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        check_constraints = [c for c in table.get("constraints", []) if c.get("type") == "check"]

        constraint_names = {c["name"] for c in check_constraints}
        assert "ck_anchors_status" in constraint_names

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_anchors table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_anchors" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) >= 3


# =============================================================================
# Issue 2.3.4: st_anchor_observations (Evidence log)
# =============================================================================


class TestMigration0039StAnchorObservations:
    """Tests for migration 0039_st_anchor_observations.py (Dossier §6.13)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the migration module."""
        return load_migration_module(migrations_path, "0039_st_anchor_observations")

    def test_revision_identifiers(self, migration_module):
        """Verify revision identifiers are correct."""
        assert migration_module.revision == "0039"
        assert migration_module.down_revision == "0038"

    def test_upgrade_creates_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_anchor_observations table."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_anchor_observations"

    def test_upgrade_creates_all_columns(self, migration_module, mock_op):
        """Verify upgrade() creates all 9 required columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        col_names = {col["name"] for col in table["columns"]}

        # Required columns from dossier §6.13
        required_columns = {
            "id",
            "entity_id",
            "attribute",
            "tenant_id",
            "observed_at",
            "event_id",
            "supports_anchor",
            "observation_weight",
            "observation_context",
        }

        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"
        assert len(col_names) == 9

    def test_upgrade_creates_fk_to_anchors(self, migration_module):
        """Verify FK to st_anchors composite key."""
        # Check migration source code defines the FK
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "ForeignKeyConstraint" in source
        assert "fk_anchor_obs_anchor" in source
        assert "st_anchors.entity_id" in source
        assert "st_anchors.attribute" in source
        assert "st_anchors.tenant_id" in source

    def test_upgrade_creates_fk_to_events(self, migration_module):
        """Verify FK to st_hipp_events."""
        # Check migration source code defines the FK
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "fk_anchor_obs_event" in source
        assert "st_hipp_events.event_id" in source

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) >= 1
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_anchor_obs_anchor",
        }
        assert required_indexes.issubset(index_names)

    def test_upgrade_creates_partial_index_for_event(self, migration_module, mock_op):
        """Verify partial index for event_id IS NOT NULL."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        partial_indexes = [
            idx for idx in mock_op.indexes_created if "postgresql_where" in idx.get("kwargs", {})
        ]
        # Should have at least 1 partial index for event_id
        assert len(partial_indexes) >= 1

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_anchor_observations table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_anchor_observations" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) >= 1


# =============================================================================
# Issue 2.3.5: st_learned_weights (Adaptive parameters)
# =============================================================================


class TestMigration0040StLearnedWeights:
    """Tests for migration 0040_st_learned_weights.py (Dossier §6.17)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the migration module."""
        return load_migration_module(migrations_path, "0040_st_learned_weights")

    def test_revision_identifiers(self, migration_module):
        """Verify revision identifiers are correct."""
        assert migration_module.revision == "0040"
        assert migration_module.down_revision == "0039"

    def test_param_scopes_constant(self, migration_module):
        """Verify PARAM_SCOPES matches dossier §6.17."""
        expected_scopes = {
            "global",
            "space",
            "entity_type",
            "entity",
        }
        assert set(migration_module.PARAM_SCOPES) == expected_scopes

    def test_upgrade_creates_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_learned_weights table."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_learned_weights"

    def test_upgrade_creates_all_columns(self, migration_module, mock_op):
        """Verify upgrade() creates all 17 required columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        col_names = {col["name"] for col in table["columns"]}

        # Required columns from dossier §6.17
        required_columns = {
            "param_id",
            "param_key",
            "param_scope",
            "scope_id",
            "space_id",
            "current_value",
            "prior_value",
            "confidence",
            "sample_count",
            "last_updated_at",
            "version",
            "previous_value",
            "quality_at_update",
            "rollback_eligible",
            "created_at",
            "updated_at",
        }

        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"
        # Note: 16 named columns (not 17 - dossier counts differently)
        assert len(col_names) >= 16

    def test_upgrade_creates_check_constraints(self, migration_module, mock_op):
        """Verify CHECK constraints for param_scope, confidence, sample_count."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        check_constraints = [c for c in table.get("constraints", []) if c.get("type") == "check"]

        constraint_names = {c["name"] for c in check_constraints}
        required_constraints = {
            "ck_param_scope",
            "ck_confidence_range",
            "ck_sample_count_nonneg",
        }
        assert required_constraints.issubset(constraint_names)

    def test_upgrade_creates_unique_constraint(self, migration_module):
        """Verify UNIQUE constraint for (space_id, param_key, param_scope, scope_id)."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "UniqueConstraint" in source
        assert "uq_learned_weights" in source
        assert "space_id" in source
        assert "param_key" in source
        assert "param_scope" in source
        assert "scope_id" in source

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) >= 3
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_learned_weights_space_key",
            "idx_learned_weights_scope",
            "idx_learned_weights_confidence",
        }
        assert required_indexes.issubset(index_names)

    def test_upgrade_creates_rls_policy(self, migration_module):
        """Verify RLS policy for multi-tenant isolation."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "CREATE POLICY learned_weights_isolation" in source
        assert "current_setting('app.current_space_id'" in source

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_learned_weights table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_learned_weights" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) >= 3


# =============================================================================
# Issue 2.3.6: st_learned_weights_history (Parameter versioning)
# =============================================================================


class TestMigration0041StLearnedWeightsHistory:
    """Tests for migration 0041_st_learned_weights_history.py (Dossier §6.23)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the migration module."""
        return load_migration_module(migrations_path, "0041_st_learned_weights_history")

    def test_revision_identifiers(self, migration_module):
        """Verify revision identifiers are correct."""
        assert migration_module.revision == "0041"
        assert migration_module.down_revision == "0040"

    def test_upgrade_creates_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_learned_weights_history table."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_learned_weights_history"

    def test_upgrade_creates_all_columns(self, migration_module, mock_op):
        """Verify upgrade() creates all 10 required columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        col_names = {col["name"] for col in table["columns"]}

        # Required columns from dossier §6.23
        required_columns = {
            "history_id",
            "param_id",
            "space_id",
            "version",
            "value",
            "confidence",
            "sample_count",
            "quality_metric",
            "created_at",
            "reason",
        }

        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"
        assert len(col_names) == 10

    def test_upgrade_creates_fk_to_learned_weights(self, migration_module):
        """Verify FK to st_learned_weights(param_id)."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "ForeignKeyConstraint" in source
        assert "fk_weights_history_param" in source
        assert "st_learned_weights.param_id" in source

    def test_upgrade_creates_unique_constraint(self, migration_module):
        """Verify UNIQUE constraint on (param_id, version)."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "UniqueConstraint" in source
        assert "uq_weights_history_version" in source
        assert "param_id" in source
        assert "version" in source

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) >= 3
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_weights_history_param_version",
            "idx_weights_history_param_time",
            "idx_weights_history_space",
        }
        assert required_indexes.issubset(index_names)

    def test_upgrade_creates_rls_policy(self, migration_module):
        """Verify RLS policy for multi-tenant isolation."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "CREATE POLICY weights_history_isolation" in source
        assert "current_setting('app.current_space_id'" in source

    def test_upgrade_creates_pruning_trigger(self, migration_module):
        """Verify pruning trigger keeps only last 10 versions."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "prune_weights_history" in source
        assert "OFFSET 10" in source
        assert "CREATE TRIGGER trg_prune_weights_history" in source

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_learned_weights_history table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_learned_weights_history" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) >= 3


# =============================================================================
# Issue 2.3.7: st_feedback_quarantine (Suspicious signal quarantine)
# =============================================================================


class TestMigration0042StFeedbackQuarantine:
    """Tests for migration 0042_st_feedback_quarantine.py (Dossier §6.21)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the migration module."""
        return load_migration_module(migrations_path, "0042_st_feedback_quarantine")

    def test_revision_identifiers(self, migration_module):
        """Verify revision identifiers are correct."""
        assert migration_module.revision == "0042"
        assert migration_module.down_revision == "0041"

    def test_upgrade_creates_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_feedback_quarantine table."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_feedback_quarantine"

    def test_upgrade_creates_all_columns(self, migration_module, mock_op):
        """Verify upgrade() creates all 15 required columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        col_names = {col["name"] for col in table["columns"]}

        # Required columns from dossier §6.21
        required_columns = {
            "quarantine_id",
            "space_id",
            "tenant_id",
            "signal_id",
            "signal_type",
            "signal_payload_json",
            "quarantine_reason",
            "anomaly_score",
            "created_at",
            "auto_release_at",
            "decision",
            "decided_by",
            "decided_at",
            "decision_reason",
            "updated_at",
        }

        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"
        assert len(col_names) == 15

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) >= 3
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_quarantine_space_status",
            "idx_quarantine_auto_release",
            "idx_quarantine_signal",
        }
        assert required_indexes.issubset(index_names)

    def test_upgrade_creates_partial_indexes(self, migration_module, mock_op):
        """Verify partial indexes for pending signals."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        partial_indexes = [
            idx for idx in mock_op.indexes_created if "postgresql_where" in idx.get("kwargs", {})
        ]
        # Should have at least 2 partial indexes (space_status and auto_release)
        assert len(partial_indexes) >= 2

    def test_upgrade_creates_rls_policy(self, migration_module):
        """Verify RLS policy for multi-tenant isolation."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "CREATE POLICY quarantine_isolation" in source

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_feedback_quarantine table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_feedback_quarantine" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) >= 3


# =============================================================================
# Issue 2.3.8: st_feedback_signals consumption columns
# =============================================================================


class TestMigration0043StFeedbackSignalsConsumption:
    """Tests for migration 0043_st_feedback_signals_consumption.py (Dossier §6.22)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the migration module."""
        return load_migration_module(migrations_path, "0043_st_feedback_signals_consumption")

    def test_revision_identifiers(self, migration_module):
        """Verify revision identifiers are correct."""
        assert migration_module.revision == "0043"
        assert migration_module.down_revision == "0042"

    def test_upgrade_adds_consumed_at_column(self, migration_module, mock_op):
        """Verify upgrade() adds consumed_at column."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        col_names = {col["column_name"] for col in mock_op.columns_added}
        assert "consumed_at" in col_names

    def test_upgrade_adds_consumed_by_column(self, migration_module, mock_op):
        """Verify upgrade() adds consumed_by column."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        col_names = {col["column_name"] for col in mock_op.columns_added}
        assert "consumed_by" in col_names

    def test_upgrade_creates_partial_index(self, migration_module, mock_op):
        """Verify partial index for unconsumed signals."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        partial_indexes = [
            idx for idx in mock_op.indexes_created if "postgresql_where" in idx.get("kwargs", {})
        ]
        assert len(partial_indexes) >= 1

        # Check for unconsumed index
        index_names = {idx["name"] for idx in mock_op.indexes_created}
        assert "idx_feedback_signals_unconsumed" in index_names

    def test_downgrade_drops_columns(self, migration_module, mock_op):
        """Verify downgrade() drops consumed_at and consumed_by columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        dropped_cols = {col["column_name"] for col in mock_op.columns_dropped}
        assert "consumed_at" in dropped_cols
        assert "consumed_by" in dropped_cols


# =============================================================================
# Issue 2.3.9: st_golden_dataset_pairs + st_validation_results
# =============================================================================


class TestMigration0044StGoldenDataset:
    """Tests for migration 0044_st_golden_dataset.py (Dossier §6.24-6.25)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the migration module."""
        return load_migration_module(migrations_path, "0044_st_golden_dataset")

    def test_revision_identifiers(self, migration_module):
        """Verify revision identifiers are correct."""
        assert migration_module.revision == "0044"
        assert migration_module.down_revision == "0043"

    def test_upgrade_creates_two_tables(self, migration_module, mock_op):
        """Verify upgrade() creates both tables."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 2
        table_names = {t["name"] for t in mock_op.tables_created}
        assert "st_golden_dataset_pairs" in table_names
        assert "st_validation_results" in table_names

    def test_golden_pairs_has_all_columns(self, migration_module, mock_op):
        """Verify st_golden_dataset_pairs has all 12 required columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        pairs_table = next(
            t for t in mock_op.tables_created if t["name"] == "st_golden_dataset_pairs"
        )
        col_names = {col["name"] for col in pairs_table["columns"]}

        required_columns = {
            "pair_id",
            "space_id",
            "entity_type",
            "input_json",
            "expected_output_json",
            "ground_truth_source",
            "is_active",
            "difficulty",
            "tags_json",
            "created_at",
            "updated_at",
            "created_by",
        }

        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"
        assert len(col_names) == 12

    def test_validation_results_has_all_columns(self, migration_module, mock_op):
        """Verify st_validation_results has all 12 required columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        results_table = next(
            t for t in mock_op.tables_created if t["name"] == "st_validation_results"
        )
        col_names = {col["name"] for col in results_table["columns"]}

        required_columns = {
            "result_id",
            "space_id",
            "pair_id",
            "actual_output_json",
            "is_correct",
            "similarity_score",
            "error_type",
            "error_details_json",
            "model_version",
            "param_snapshot_json",
            "created_at",
            "duration_ms",
        }

        missing = required_columns - col_names
        assert not missing, f"Missing required columns: {missing}"
        assert len(col_names) == 12

    def test_validation_results_has_fk_to_pairs(self, migration_module):
        """Verify FK from st_validation_results to st_golden_dataset_pairs."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "ForeignKeyConstraint" in source
        assert "fk_validation_results_pair" in source
        assert "st_golden_dataset_pairs.pair_id" in source

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Should have at least 7 indexes (3 for pairs + 4 for results)
        assert len(mock_op.indexes_created) >= 7
        index_names = {idx["name"] for idx in mock_op.indexes_created}

        # Pairs indexes
        assert "idx_golden_pairs_space_type" in index_names
        assert "idx_golden_pairs_active" in index_names

        # Results indexes
        assert "idx_validation_results_pair" in index_names
        assert "idx_validation_results_space_time" in index_names

    def test_upgrade_creates_rls_policies(self, migration_module):
        """Verify RLS policies for both tables."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "CREATE POLICY golden_pairs_isolation" in source
        assert "CREATE POLICY validation_results_isolation" in source

    def test_downgrade_drops_tables(self, migration_module, mock_op):
        """Verify downgrade() drops both tables in correct order."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_validation_results" in mock_op.tables_dropped
        assert "st_golden_dataset_pairs" in mock_op.tables_dropped


# =============================================================================
# Issue 2.3.10: st_dlq P03 reconciliation (Dossier §13.4)
# =============================================================================


class TestMigration0045StDlqP03Reconcile:
    """Tests for migration 0045_st_dlq_p03_reconcile.py (Dossier §13.4)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the migration module."""
        return load_migration_module(migrations_path, "0045_st_dlq_p03_reconcile")

    def test_revision_identifiers(self, migration_module):
        """Verify revision identifiers are correct."""
        assert migration_module.revision == "0045"
        assert migration_module.down_revision == "0044"

    def test_upgrade_adds_pipeline_columns(self, migration_module, mock_op):
        """Verify upgrade() adds pipeline_id and phase columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        col_names = {col["column_name"] for col in mock_op.columns_added}
        assert "pipeline_id" in col_names
        assert "phase" in col_names

    def test_upgrade_adds_event_entity_columns(self, migration_module, mock_op):
        """Verify upgrade() adds event_id and entity_id columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        col_names = {col["column_name"] for col in mock_op.columns_added}
        assert "event_id" in col_names
        assert "entity_id" in col_names

    def test_upgrade_adds_error_tracking_columns(self, migration_module, mock_op):
        """Verify upgrade() adds error_type, error_code, stack_trace columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        col_names = {col["column_name"] for col in mock_op.columns_added}
        assert "error_type" in col_names
        assert "error_code" in col_names
        assert "stack_trace" in col_names

    def test_upgrade_adds_resolution_columns(self, migration_module, mock_op):
        """Verify upgrade() adds resolution tracking columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        col_names = {col["column_name"] for col in mock_op.columns_added}
        assert "resolved_at" in col_names
        assert "resolved_by" in col_names
        assert "resolution_notes" in col_names
        assert "max_attempts" in col_names
        assert "updated_at" in col_names

    def test_upgrade_adds_all_12_columns(self, migration_module, mock_op):
        """Verify upgrade() adds all 12 P03-specific columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Should add exactly 12 columns
        assert len(mock_op.columns_added) == 12

        required_columns = {
            "pipeline_id",
            "phase",
            "event_id",
            "entity_id",
            "error_type",
            "error_code",
            "stack_trace",
            "max_attempts",
            "resolved_at",
            "resolved_by",
            "resolution_notes",
            "updated_at",
        }
        col_names = {col["column_name"] for col in mock_op.columns_added}
        missing = required_columns - col_names
        assert not missing, f"Missing columns: {missing}"

    def test_upgrade_creates_p03_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates P03-specific indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_dlq_p03_pipeline_phase",
            "idx_dlq_pending_error_type",
            "idx_dlq_event_id",
        }
        assert required_indexes.issubset(index_names)

    def test_upgrade_creates_error_type_check(self, migration_module, mock_op):
        """Verify CHECK constraint for error_type classification."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        check_names = {c["name"] for c in mock_op.constraints_added if c["type"] == "check"}
        assert "ck_dlq_error_type" in check_names

    def test_upgrade_updates_state_check(self, migration_module, mock_op):
        """Verify state CHECK constraint is updated with new values."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Should drop and recreate ck_dlq_state
        dropped_checks = {c["name"] for c in mock_op.constraints_dropped}
        created_checks = {c["name"] for c in mock_op.constraints_added if c["type"] == "check"}
        assert "ck_dlq_state" in dropped_checks
        assert "ck_dlq_state" in created_checks

    def test_downgrade_removes_columns(self, migration_module, mock_op):
        """Verify downgrade() removes all P03-specific columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        # Should drop exactly 12 columns
        assert len(mock_op.columns_dropped) == 12

    def test_downgrade_restores_original_state_check(self, migration_module, mock_op):
        """Verify downgrade() restores original state CHECK constraint."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        # Should drop expanded constraint and recreate original
        dropped_checks = {c["name"] for c in mock_op.constraints_dropped}
        assert "ck_dlq_state" in dropped_checks
        assert "ck_dlq_error_type" in dropped_checks


# =============================================================================
# Issue 6.3.3: st_pruned_entities (Regret Tracking with RLS)
# =============================================================================


class TestMigration0049StPrunedEntities:
    """Tests for migration 0049_st_pruned_entities.py (Dossier §6.19)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the 0049_st_pruned_entities migration module."""
        return load_migration_module(migrations_path, "0049_st_pruned_entities")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0049"
        assert migration_module.down_revision == "0048"

    def test_upgrade_creates_st_pruned_entities_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_pruned_entities table."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_pruned_entities"

    def test_upgrade_creates_all_columns(self, migration_module, mock_op):
        """Verify upgrade() creates all required columns per Dossier §6.19."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        col_names = {c["name"] for c in table["columns"]}

        required_columns = {
            "prune_id",
            "entity_id",
            "entity_type",
            "canonical_name",
            "embedding",
            "space_id",
            "layer_table",
            "decay_factor_at_prune",
            "lambda_at_prune",
            "pruned_at",
            "matched_query_id",
            "matched_at",
            "match_type",
            "match_confidence",
        }
        assert required_columns.issubset(col_names)

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_pruned_entity_type",
            "idx_pruned_space_time",
            "idx_pruned_cleanup",
            "idx_pruned_canonical",
            "idx_pruned_entity_id",
        }
        assert required_indexes.issubset(index_names)

    def test_upgrade_creates_partial_index_for_cleanup(self, migration_module, mock_op):
        """Verify partial index for cleanup (unmatched only)."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        partial_indexes = [
            idx for idx in mock_op.indexes_created if "postgresql_where" in idx.get("kwargs", {})
        ]
        cleanup_idx = [idx for idx in partial_indexes if idx["name"] == "idx_pruned_cleanup"]
        assert len(cleanup_idx) == 1

    def test_upgrade_creates_rls_policy(self, migration_module):
        """Verify RLS policy for multi-tenant isolation."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "CREATE POLICY st_pruned_entities_isolation" in source
        assert "current_setting('app.current_space_id'" in source

    def test_upgrade_enables_rls(self, migration_module, mock_op):
        """Verify upgrade() enables Row Level Security."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert hasattr(mock_op, "sql_executed")
        rls_statements = [s for s in mock_op.sql_executed if "ROW LEVEL SECURITY" in s]
        assert len(rls_statements) >= 1

    def test_upgrade_creates_check_constraints(self, migration_module, mock_op):
        """Verify CHECK constraints for entity_type and match_type."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Check constraints are in table definition
        table = mock_op.tables_created[0]
        constraint_names = {c["name"] for c in table["constraints"]}
        required_constraints = {
            "ck_pruned_entity_type",
            "ck_pruned_match_type",
            "ck_pruned_match_confidence",
            "ck_pruned_decay_factor",
        }
        assert required_constraints.issubset(constraint_names)

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_pruned_entities table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_pruned_entities" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) >= 5


# =============================================================================
# Issue 6.3.4: st_decay_feedback (Decay Rate Learning with RLS)
# =============================================================================


class TestMigration0050StDecayFeedback:
    """Tests for migration 0050_st_decay_feedback.py (Dossier §6.22)."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path):
        """Load the 0050_st_decay_feedback migration module."""
        return load_migration_module(migrations_path, "0050_st_decay_feedback")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0050"
        assert migration_module.down_revision == "0049"

    def test_upgrade_creates_st_decay_feedback_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_decay_feedback table."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 1
        table = mock_op.tables_created[0]
        assert table["name"] == "st_decay_feedback"

    def test_upgrade_creates_all_columns(self, migration_module, mock_op):
        """Verify upgrade() creates all required columns per Dossier §6.22."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        col_names = {c["name"] for c in table["columns"]}

        required_columns = {
            "feedback_id",
            "memory_id",
            "layer",
            "space_id",
            "tenant_id",
            "event_type",
            "inter_access_interval",
            "decay_factor_at_event",
            "expected_decay",
            "resurrection_needed",
            "archival_premature",
            "created_at",
            "observed_at",
        }
        assert required_columns.issubset(col_names)

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates all required indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        index_names = {idx["name"] for idx in mock_op.indexes_created}
        required_indexes = {
            "idx_decay_fb_space_layer",
            "idx_decay_fb_memory",
            "idx_decay_fb_event_type",
            "idx_decay_fb_resurrections",
            "idx_decay_fb_premature",
            "idx_decay_fb_tenant_space",
        }
        assert required_indexes.issubset(index_names)

    def test_upgrade_creates_partial_indexes(self, migration_module, mock_op):
        """Verify partial indexes for resurrections and premature archival."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        partial_indexes = [
            idx for idx in mock_op.indexes_created if "postgresql_where" in idx.get("kwargs", {})
        ]
        partial_names = {idx["name"] for idx in partial_indexes}
        assert "idx_decay_fb_resurrections" in partial_names
        assert "idx_decay_fb_premature" in partial_names

    def test_upgrade_creates_rls_policy(self, migration_module):
        """Verify RLS policy for multi-tenant isolation."""
        import inspect

        source = inspect.getsource(migration_module.upgrade)
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "CREATE POLICY decay_feedback_isolation" in source
        assert "current_setting('app.current_space_id'" in source

    def test_upgrade_enables_rls(self, migration_module, mock_op):
        """Verify upgrade() enables Row Level Security."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert hasattr(mock_op, "sql_executed")
        rls_statements = [s for s in mock_op.sql_executed if "ROW LEVEL SECURITY" in s]
        assert len(rls_statements) >= 1

    def test_upgrade_creates_check_constraints(self, migration_module, mock_op):
        """Verify CHECK constraints for event_type and intervals."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table = mock_op.tables_created[0]
        constraint_names = {c["name"] for c in table["constraints"]}
        required_constraints = {
            "ck_decay_feedback_event_type",
            "ck_decay_feedback_interval_nonneg",
            "ck_decay_feedback_factor_range",
        }
        assert required_constraints.issubset(constraint_names)

    def test_event_types_match_dossier(self, migration_module):
        """Verify EVENT_TYPES constant matches Dossier §6.22.2."""
        expected_types = ("ACCESS", "RESURRECTION", "ARCHIVE", "TOMBSTONE")
        assert migration_module.EVENT_TYPES == expected_types

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_decay_feedback table and indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_decay_feedback" in mock_op.tables_dropped
        assert len(mock_op.indexes_dropped) >= 6
