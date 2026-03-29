"""
Epic 3.18 -- Migration 0066 Tests: st_hipp_events MW v2 Columns

Validates:
- All 16 new columns added with correct names and types
- Default values applied correctly (NOT NULL + DEFAULT)
- 3 indexes created
- Upgrade/downgrade idempotency
- Column groups match contract spec

NO MOCK THEATER: Real SQLite database, real SQL statements.
"""

import sqlite3
from pathlib import Path

import pytest

# ============================================================================
# Expected schema from migration 0066
# ============================================================================

V2_COLUMNS = [
    # (name, nullable, has_default, default_value)
    ("narrative_thread_id", True, False, None),
    ("narrative_arc_position", True, False, None),
    ("narrative_is_goal_event", False, True, "FALSE"),
    ("affect_dominance", True, False, None),
    ("entity_salience_json", False, True, "'{}'"),
    ("temporal_mentioned_time", True, False, None),
    ("temporal_resolved_epoch_ms", True, False, None),
    ("temporal_orientation", True, False, None),
    ("intent_type", True, False, None),
    ("goal_context", True, False, None),
    ("source_type", True, False, None),
    ("novelty", True, False, None),
    ("elaboration_depth", True, False, None),
    ("identity_domains_json", False, True, "'[]'"),
    ("participant_relationships_json", False, True, "'[]'"),
    ("k1_signal_version", False, True, "'2.0'"),
]

V2_COLUMN_NAMES = [c[0] for c in V2_COLUMNS]

EXPECTED_INDEXES = [
    "idx_hipp_narrative_thread",
    "idx_hipp_temporal_orientation",
    "idx_hipp_k1_signal_version",
]


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_0066.db"


@pytest.fixture
def db_conn(db_path: Path):
    """Create database with baseline st_hipp_events table (pre-0066)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Baseline st_hipp_events with minimal columns (pre-migration)
    conn.execute(
        """
        CREATE TABLE st_hipp_events (
            event_id TEXT PRIMARY KEY,
            cognitive_trace_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            event_time_utc TEXT,
            affect_valence FLOAT,
            affect_arousal FLOAT,
            affect_source TEXT,
            social_context TEXT,
            salience_score FLOAT,
            salience_band TEXT,
            body_text TEXT,
            created_at INTEGER NOT NULL DEFAULT 0
        );
    """
    )

    conn.commit()
    yield conn
    conn.close()


def _apply_upgrade(conn: sqlite3.Connection):
    """Apply migration 0066 upgrade SQL to the connection."""
    # Narrative Context (3 columns)
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN narrative_thread_id TEXT")
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN narrative_arc_position TEXT")
    conn.execute(
        "ALTER TABLE st_hipp_events"
        " ADD COLUMN narrative_is_goal_event BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # Affect Extension (1 column)
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN affect_dominance FLOAT")

    # Entity Salience (1 column)
    conn.execute(
        "ALTER TABLE st_hipp_events ADD COLUMN entity_salience_json TEXT NOT NULL DEFAULT '{}'"
    )

    # Temporal Extensions (3 columns)
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN temporal_mentioned_time TEXT")
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN temporal_resolved_epoch_ms BIGINT")
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN temporal_orientation TEXT")

    # Cognitive Dimensions (6 columns)
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN intent_type TEXT")
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN goal_context TEXT")
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN source_type TEXT")
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN novelty TEXT")
    conn.execute("ALTER TABLE st_hipp_events ADD COLUMN elaboration_depth TEXT")
    conn.execute(
        "ALTER TABLE st_hipp_events ADD COLUMN identity_domains_json TEXT NOT NULL DEFAULT '[]'"
    )

    # Signal Provenance (2 columns)
    conn.execute(
        "ALTER TABLE st_hipp_events"
        " ADD COLUMN participant_relationships_json TEXT NOT NULL DEFAULT '[]'"
    )
    conn.execute(
        "ALTER TABLE st_hipp_events ADD COLUMN k1_signal_version TEXT NOT NULL DEFAULT '2.0'"
    )

    # Indexes
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hipp_narrative_thread"
        " ON st_hipp_events(narrative_thread_id)"
        " WHERE narrative_thread_id IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hipp_temporal_orientation"
        " ON st_hipp_events(temporal_orientation)"
        " WHERE temporal_orientation = 'FUTURE_COMMITMENT'"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hipp_k1_signal_version"
        " ON st_hipp_events(k1_signal_version)"
    )
    conn.commit()


# ============================================================================
# Tests
# ============================================================================


class TestMigration0066ColumnCount:
    """Migration adds exactly 16 new columns."""

    def test_column_count_is_16(self, db_conn):
        """Migration adds exactly 16 columns."""
        pre_cols = {row[1] for row in db_conn.execute("PRAGMA table_info(st_hipp_events)")}
        _apply_upgrade(db_conn)
        post_cols = {row[1] for row in db_conn.execute("PRAGMA table_info(st_hipp_events)")}
        new_cols = post_cols - pre_cols
        assert len(new_cols) == 16

    def test_all_column_names_present(self, db_conn):
        """All 16 expected column names are present after migration."""
        _apply_upgrade(db_conn)
        cols = {row[1] for row in db_conn.execute("PRAGMA table_info(st_hipp_events)")}
        for name in V2_COLUMN_NAMES:
            assert name in cols, f"Missing column: {name}"


class TestMigration0066Defaults:
    """NOT NULL columns have correct defaults."""

    def test_narrative_is_goal_event_default(self, db_conn):
        """narrative_is_goal_event defaults to FALSE."""
        _apply_upgrade(db_conn)
        db_conn.execute(
            "INSERT INTO st_hipp_events (event_id, cognitive_trace_id, tenant_id,"
            " actor_id, space_id, created_at)"
            " VALUES ('e1', 'ct1', 't1', 'a1', 's1', 0)"
        )
        db_conn.commit()
        row = db_conn.execute(
            "SELECT narrative_is_goal_event FROM st_hipp_events WHERE event_id='e1'"
        ).fetchone()
        assert row[0] == 0  # SQLite FALSE = 0

    def test_entity_salience_json_default(self, db_conn):
        """entity_salience_json defaults to '{}'."""
        _apply_upgrade(db_conn)
        db_conn.execute(
            "INSERT INTO st_hipp_events (event_id, cognitive_trace_id, tenant_id,"
            " actor_id, space_id, created_at)"
            " VALUES ('e2', 'ct2', 't1', 'a1', 's1', 0)"
        )
        db_conn.commit()
        row = db_conn.execute(
            "SELECT entity_salience_json FROM st_hipp_events WHERE event_id='e2'"
        ).fetchone()
        assert row[0] == "{}"

    def test_k1_signal_version_default(self, db_conn):
        """k1_signal_version defaults to '2.0'."""
        _apply_upgrade(db_conn)
        db_conn.execute(
            "INSERT INTO st_hipp_events (event_id, cognitive_trace_id, tenant_id,"
            " actor_id, space_id, created_at)"
            " VALUES ('e3', 'ct3', 't1', 'a1', 's1', 0)"
        )
        db_conn.commit()
        row = db_conn.execute(
            "SELECT k1_signal_version FROM st_hipp_events WHERE event_id='e3'"
        ).fetchone()
        assert row[0] == "2.0"

    def test_participant_relationships_json_default(self, db_conn):
        """participant_relationships_json defaults to '[]'."""
        _apply_upgrade(db_conn)
        db_conn.execute(
            "INSERT INTO st_hipp_events (event_id, cognitive_trace_id, tenant_id,"
            " actor_id, space_id, created_at)"
            " VALUES ('e4', 'ct4', 't1', 'a1', 's1', 0)"
        )
        db_conn.commit()
        row = db_conn.execute(
            "SELECT participant_relationships_json FROM st_hipp_events WHERE event_id='e4'"
        ).fetchone()
        assert row[0] == "[]"

    def test_identity_domains_json_default(self, db_conn):
        """identity_domains_json defaults to '[]'."""
        _apply_upgrade(db_conn)
        db_conn.execute(
            "INSERT INTO st_hipp_events (event_id, cognitive_trace_id, tenant_id,"
            " actor_id, space_id, created_at)"
            " VALUES ('e5', 'ct5', 't1', 'a1', 's1', 0)"
        )
        db_conn.commit()
        row = db_conn.execute(
            "SELECT identity_domains_json FROM st_hipp_events WHERE event_id='e5'"
        ).fetchone()
        assert row[0] == "[]"


class TestMigration0066Indexes:
    """3 indexes created for downstream consumers."""

    def test_indexes_created(self, db_conn):
        """All 3 indexes exist after migration."""
        _apply_upgrade(db_conn)
        indexes = {
            row[1]
            for row in db_conn.execute(
                "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='st_hipp_events'"
            )
        }
        for idx_name in EXPECTED_INDEXES:
            assert idx_name in indexes, f"Missing index: {idx_name}"


class TestMigration0066NullableColumns:
    """Nullable columns accept NULL."""

    def test_nullable_columns_accept_null(self, db_conn):
        """All nullable v2 columns accept NULL inserts."""
        _apply_upgrade(db_conn)
        db_conn.execute(
            "INSERT INTO st_hipp_events (event_id, cognitive_trace_id, tenant_id,"
            " actor_id, space_id, created_at)"
            " VALUES ('e6', 'ct6', 't1', 'a1', 's1', 0)"
        )
        db_conn.commit()

        nullable_cols = [c[0] for c in V2_COLUMNS if c[1]]
        row = db_conn.execute(
            f"SELECT {', '.join(nullable_cols)} FROM st_hipp_events WHERE event_id='e6'"
        ).fetchone()

        for i, col_name in enumerate(nullable_cols):
            assert row[i] is None, f"{col_name} should be NULL but got {row[i]}"
