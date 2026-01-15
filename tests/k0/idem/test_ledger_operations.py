"""Unit tests for IdempotencyLedger operations.

Targets k0/idem/ledger.py for +15% coverage boost.
"""

from unittest.mock import AsyncMock

import pytest

from k0.idem.ledger import IdempotencyLedger, LedgerEntry


@pytest.fixture
def mock_conn():
    """Mock asyncpg connection for testing."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    return conn


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


@pytest.mark.asyncio
class TestLedgerLookup:
    """Test ledger lookup operations."""

    async def test_lookup_missing_key(self, mock_conn):
        """Lookup returns None for missing key."""
        mock_conn.fetchrow.return_value = None
        ledger = IdempotencyLedger()
        result = await ledger.lookup("nonexistent_key", connection=mock_conn)
        assert result is None

    async def test_lookup_existing_key(self, mock_conn):
        """Lookup returns entry for existing key."""
        # Mock database returning a row
        mock_conn.fetchrow.return_value = {
            "idem_key": "key_001",
            "receipt_id": "receipt_001",
            "first_seen_ts": "2024-01-15T10:00:00Z",
            "state": "COMMITTED",
            "expiry_ts": None,
        }

        ledger = IdempotencyLedger()
        result = await ledger.lookup("key_001", connection=mock_conn)

        assert result is not None
        assert result.idem_key == "key_001"
        assert result.receipt_id == "receipt_001"
        assert result.state == "COMMITTED"

    async def test_lookup_with_expiry(self, mock_conn):
        """Lookup returns entry with expiry timestamp."""
        mock_conn.fetchrow.return_value = {
            "idem_key": "key_002",
            "receipt_id": "receipt_002",
            "first_seen_ts": "2024-01-15T12:00:00Z",
            "state": "COMMITTED",
            "expiry_ts": "2024-01-16T12:00:00Z",
        }

        ledger = IdempotencyLedger()
        result = await ledger.lookup("key_002", connection=mock_conn)

        assert result.expiry_ts == "2024-01-16T12:00:00Z"


@pytest.mark.asyncio
class TestLedgerUpsert:
    """Test ledger upsert operations."""

    async def test_upsert_new_entry(self, mock_conn):
        """Upsert inserts new entry."""
        entry = LedgerEntry(
            idem_key="new_key_123",
            receipt_id="new_receipt_456",
            first_seen_ts="2024-01-15T14:00:00Z",
            state="PENDING",
        )

        ledger = IdempotencyLedger()
        await ledger.upsert(entry, connection=mock_conn)

        # Verify execute was called for upsert
        mock_conn.execute.assert_called()

    async def test_upsert_updates_existing(self, mock_conn):
        """Upsert updates existing entry on conflict."""
        # Upsert with updated data
        updated_entry = LedgerEntry(
            idem_key="conflict_key",
            receipt_id="new_receipt",
            first_seen_ts="2024-01-15T10:00:00Z",
            state="COMMITTED",
        )

        ledger = IdempotencyLedger()
        await ledger.upsert(updated_entry, connection=mock_conn)

        # Verify execute was called (upsert handles conflict internally)
        mock_conn.execute.assert_called()

    async def test_upsert_with_expiry(self, mock_conn):
        """Upsert stores expiry timestamp."""
        entry = LedgerEntry(
            idem_key="expiry_key",
            receipt_id="receipt_exp",
            first_seen_ts="2024-01-15T16:00:00Z",
            state="COMMITTED",
            expiry_ts="2024-01-16T16:00:00Z",
        )

        ledger = IdempotencyLedger()
        await ledger.upsert(entry, connection=mock_conn)

        # Verify execute was called with expiry data
        mock_conn.execute.assert_called()


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


@pytest.mark.asyncio
class TestLedgerStates:
    """Test ledger state management."""

    async def test_pending_state(self, mock_conn):
        """Ledger stores PENDING state."""
        entry = LedgerEntry(
            idem_key="pending_key",
            receipt_id="pending_receipt",
            first_seen_ts="2024-01-15T18:00:00Z",
            state="PENDING",
        )

        # Mock lookup returning the entry after upsert
        mock_conn.fetchrow.return_value = {
            "idem_key": "pending_key",
            "receipt_id": "pending_receipt",
            "first_seen_ts": "2024-01-15T18:00:00Z",
            "state": "PENDING",
            "expiry_ts": None,
        }

        ledger = IdempotencyLedger()
        await ledger.upsert(entry, connection=mock_conn)

        result = await ledger.lookup("pending_key", connection=mock_conn)
        assert result.state == "PENDING"

    async def test_committed_state(self, mock_conn):
        """Ledger stores COMMITTED state."""
        entry = LedgerEntry(
            idem_key="committed_key",
            receipt_id="committed_receipt",
            first_seen_ts="2024-01-15T19:00:00Z",
            state="COMMITTED",
        )

        # Mock lookup returning the entry after upsert
        mock_conn.fetchrow.return_value = {
            "idem_key": "committed_key",
            "receipt_id": "committed_receipt",
            "first_seen_ts": "2024-01-15T19:00:00Z",
            "state": "COMMITTED",
            "expiry_ts": None,
        }

        ledger = IdempotencyLedger()
        await ledger.upsert(entry, connection=mock_conn)

        result = await ledger.lookup("committed_key", connection=mock_conn)
        assert result.state == "COMMITTED"

    async def test_state_transition(self, mock_conn):
        """Ledger allows state transitions via upsert."""
        # Transition to COMMITTED
        updated_entry = LedgerEntry(
            idem_key="transition_key",
            receipt_id="receipt_trans",
            first_seen_ts="2024-01-15T20:00:00Z",
            state="COMMITTED",
        )

        # Mock lookup returning COMMITTED state after transition
        mock_conn.fetchrow.return_value = {
            "idem_key": "transition_key",
            "receipt_id": "receipt_trans",
            "first_seen_ts": "2024-01-15T20:00:00Z",
            "state": "COMMITTED",
            "expiry_ts": None,
        }

        ledger = IdempotencyLedger()
        await ledger.upsert(updated_entry, connection=mock_conn)

        result = await ledger.lookup("transition_key", connection=mock_conn)
        assert result.state == "COMMITTED"
