"""Unit tests for IdempotencyLedger operations.

Targets k0/idem/ledger.py for +15% coverage boost.
"""

import sqlite3

import pytest

from k0.idem.ledger import IdempotencyLedger, LedgerEntry


@pytest.fixture(scope="function")
def test_db():
    """In-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create idem_ledger table
    conn.execute(
        """
        CREATE TABLE idem_ledger (
            idem_key TEXT PRIMARY KEY,
            receipt_id TEXT NOT NULL,
            first_seen_ts TEXT NOT NULL,
            state TEXT NOT NULL,
            expiry_ts TEXT
        )
    """
    )
    conn.commit()

    yield conn
    conn.close()


@pytest.fixture
def ledger():
    """Idempotency ledger instance."""
    return IdempotencyLedger()


class TestLedgerEntry:
    """Test LedgerEntry dataclass."""

    def test_entry_creation(self):
        """LedgerEntry creates with all fields."""
        entry = LedgerEntry(
            idem_key="test_key_123",
            receipt_id="receipt_abc",
            first_seen_ts="2024-01-15T10:30:00Z",
            state="COMMITTED",
            expiry_ts="2024-01-16T10:30:00Z",
        )
        assert entry.idem_key == "test_key_123"
        assert entry.receipt_id == "receipt_abc"
        assert entry.first_seen_ts == "2024-01-15T10:30:00Z"
        assert entry.state == "COMMITTED"
        assert entry.expiry_ts == "2024-01-16T10:30:00Z"

    def test_entry_without_expiry(self):
        """LedgerEntry allows None expiry_ts."""
        entry = LedgerEntry(
            idem_key="test_key_456",
            receipt_id="receipt_def",
            first_seen_ts="2024-01-15T11:00:00Z",
            state="PENDING",
        )
        assert entry.expiry_ts is None


class TestIdempotencyLedgerInitialization:
    """Test ledger initialization."""

    def test_ledger_initialization(self):
        """Ledger initializes with default settings."""
        ledger = IdempotencyLedger()
        assert ledger._metrics is None
        assert ledger._observability is None

    def test_ledger_with_metrics(self):
        """Ledger accepts metrics exporter."""
        from k0.obs import MetricsExporter

        metrics = MetricsExporter()
        ledger = IdempotencyLedger(metrics=metrics)
        assert ledger._metrics is metrics

    def test_ledger_with_observability(self):
        """Ledger accepts observability emitter."""
        from k0.obs import ObservabilityEmitter

        obs = ObservabilityEmitter()
        ledger = IdempotencyLedger(observability=obs)
        assert ledger._observability is obs


class TestLedgerLookup:
    """Test ledger lookup operations."""

    def test_lookup_missing_key(self, test_db):
        """Lookup returns None for missing key."""
        ledger = IdempotencyLedger()
        result = ledger.lookup("nonexistent_key", connection=test_db)
        assert result is None

    def test_lookup_existing_key(self, test_db):
        """Lookup returns entry for existing key."""
        # Insert test entry
        test_db.execute(
            "INSERT INTO idem_ledger (idem_key, receipt_id, first_seen_ts, state, expiry_ts) VALUES (?, ?, ?, ?, ?)",
            ("key_001", "receipt_001", "2024-01-15T10:00:00Z", "COMMITTED", None),
        )
        test_db.commit()

        ledger = IdempotencyLedger()
        result = ledger.lookup("key_001", connection=test_db)

        assert result is not None
        assert result.idem_key == "key_001"
        assert result.receipt_id == "receipt_001"
        assert result.state == "COMMITTED"

    def test_lookup_with_expiry(self, test_db):
        """Lookup returns entry with expiry timestamp."""
        test_db.execute(
            "INSERT INTO idem_ledger VALUES (?, ?, ?, ?, ?)",
            ("key_002", "receipt_002", "2024-01-15T12:00:00Z", "COMMITTED", "2024-01-16T12:00:00Z"),
        )
        test_db.commit()

        ledger = IdempotencyLedger()
        result = ledger.lookup("key_002", connection=test_db)

        assert result.expiry_ts == "2024-01-16T12:00:00Z"


class TestLedgerUpsert:
    """Test ledger upsert operations."""

    def test_upsert_new_entry(self, test_db):
        """Upsert inserts new entry."""
        entry = LedgerEntry(
            idem_key="new_key_123",
            receipt_id="new_receipt_456",
            first_seen_ts="2024-01-15T14:00:00Z",
            state="PENDING",
        )

        ledger = IdempotencyLedger()
        ledger.upsert(entry, connection=test_db)

        # Verify insertion
        row = test_db.execute(
            "SELECT * FROM idem_ledger WHERE idem_key = ?",
            ("new_key_123",),
        ).fetchone()

        assert row is not None
        assert row["receipt_id"] == "new_receipt_456"
        assert row["state"] == "PENDING"

    def test_upsert_updates_existing(self, test_db):
        """Upsert updates existing entry on conflict."""
        # Insert initial entry
        test_db.execute(
            "INSERT INTO idem_ledger VALUES (?, ?, ?, ?, ?)",
            ("conflict_key", "old_receipt", "2024-01-15T10:00:00Z", "PENDING", None),
        )
        test_db.commit()

        # Upsert with updated data
        updated_entry = LedgerEntry(
            idem_key="conflict_key",
            receipt_id="new_receipt",
            first_seen_ts="2024-01-15T10:00:00Z",
            state="COMMITTED",
        )

        ledger = IdempotencyLedger()
        ledger.upsert(updated_entry, connection=test_db)

        # Verify update
        row = test_db.execute(
            "SELECT * FROM idem_ledger WHERE idem_key = ?",
            ("conflict_key",),
        ).fetchone()

        assert row["receipt_id"] == "new_receipt"
        assert row["state"] == "COMMITTED"

    def test_upsert_with_expiry(self, test_db):
        """Upsert stores expiry timestamp."""
        entry = LedgerEntry(
            idem_key="expiry_key",
            receipt_id="receipt_exp",
            first_seen_ts="2024-01-15T16:00:00Z",
            state="COMMITTED",
            expiry_ts="2024-01-16T16:00:00Z",
        )

        ledger = IdempotencyLedger()
        ledger.upsert(entry, connection=test_db)

        row = test_db.execute(
            "SELECT expiry_ts FROM idem_ledger WHERE idem_key = ?",
            ("expiry_key",),
        ).fetchone()

        assert row["expiry_ts"] == "2024-01-16T16:00:00Z"


class TestMetricsAttachment:
    """Test metrics exporter attachment."""

    def test_attach_metrics_exporter(self):
        """Ledger allows attaching metrics exporter."""
        from k0.obs import MetricsExporter

        ledger = IdempotencyLedger()
        assert ledger._metrics is None

        metrics = MetricsExporter()
        ledger.attach_metrics_exporter(metrics)
        assert ledger._metrics is metrics

    def test_replace_metrics_exporter(self):
        """Ledger allows replacing metrics exporter."""
        from k0.obs import MetricsExporter

        metrics1 = MetricsExporter()
        ledger = IdempotencyLedger(metrics=metrics1)

        metrics2 = MetricsExporter()
        ledger.attach_metrics_exporter(metrics2)
        assert ledger._metrics is metrics2

    def test_detach_metrics_exporter(self):
        """Ledger allows detaching metrics exporter."""
        from k0.obs import MetricsExporter

        metrics = MetricsExporter()
        ledger = IdempotencyLedger(metrics=metrics)

        ledger.attach_metrics_exporter(None)
        assert ledger._metrics is None


class TestObservabilityAttachment:
    """Test observability emitter attachment."""

    def test_attach_observability_emitter(self):
        """Ledger allows attaching observability emitter."""
        from k0.obs import ObservabilityEmitter

        ledger = IdempotencyLedger()
        assert ledger._observability is None

        obs = ObservabilityEmitter()
        ledger.attach_observability_emitter(obs)
        assert ledger._observability is obs

    def test_replace_observability_emitter(self):
        """Ledger allows replacing observability emitter."""
        from k0.obs import ObservabilityEmitter

        obs1 = ObservabilityEmitter()
        ledger = IdempotencyLedger(observability=obs1)

        obs2 = ObservabilityEmitter()
        ledger.attach_observability_emitter(obs2)
        assert ledger._observability is obs2

    def test_detach_observability_emitter(self):
        """Ledger allows detaching observability emitter."""
        from k0.obs import ObservabilityEmitter

        obs = ObservabilityEmitter()
        ledger = IdempotencyLedger(observability=obs)

        ledger.attach_observability_emitter(None)
        assert ledger._observability is None


class TestLedgerStates:
    """Test ledger state management."""

    def test_pending_state(self, test_db):
        """Ledger stores PENDING state."""
        entry = LedgerEntry(
            idem_key="pending_key",
            receipt_id="pending_receipt",
            first_seen_ts="2024-01-15T18:00:00Z",
            state="PENDING",
        )

        ledger = IdempotencyLedger()
        ledger.upsert(entry, connection=test_db)

        result = ledger.lookup("pending_key", connection=test_db)
        assert result.state == "PENDING"

    def test_committed_state(self, test_db):
        """Ledger stores COMMITTED state."""
        entry = LedgerEntry(
            idem_key="committed_key",
            receipt_id="committed_receipt",
            first_seen_ts="2024-01-15T19:00:00Z",
            state="COMMITTED",
        )

        ledger = IdempotencyLedger()
        ledger.upsert(entry, connection=test_db)

        result = ledger.lookup("committed_key", connection=test_db)
        assert result.state == "COMMITTED"

    def test_state_transition(self, test_db):
        """Ledger allows state transitions via upsert."""
        # Start with PENDING
        test_db.execute(
            "INSERT INTO idem_ledger VALUES (?, ?, ?, ?, ?)",
            ("transition_key", "receipt_trans", "2024-01-15T20:00:00Z", "PENDING", None),
        )
        test_db.commit()

        # Transition to COMMITTED
        updated_entry = LedgerEntry(
            idem_key="transition_key",
            receipt_id="receipt_trans",
            first_seen_ts="2024-01-15T20:00:00Z",
            state="COMMITTED",
        )

        ledger = IdempotencyLedger()
        ledger.upsert(updated_entry, connection=test_db)

        result = ledger.lookup("transition_key", connection=test_db)
        assert result.state == "COMMITTED"
        result = ledger.lookup("transition_key", connection=test_db)
        assert result.state == "COMMITTED"
        result = ledger.lookup("transition_key", connection=test_db)
        assert result.state == "COMMITTED"
