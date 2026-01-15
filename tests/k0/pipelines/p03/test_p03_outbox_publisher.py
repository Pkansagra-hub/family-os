"""Tests for P03 Outbox Publisher — Issue 3.1.3.

This module tests the P03OutboxPublisher responsible for:
- Draining outbox entries to the event bus
- Exponential backoff with jitter on transient failures
- DLQ escalation after max retries
- Metrics emission for observability
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest

from k0.bus.core import BusMessage
from k0.pipelines.p03.outbox_publisher import (
    OutboxPublisherConfig,
    P03OutboxPublisher,
    PublishResult,
)
from k0.storage.dlq import DeadLetter
from k0.storage.outbox import OutboxEntry

# ============================================================================
# Test Fixtures
# ============================================================================


@dataclass
class MockOutboxStore:
    """Mock OutboxStore for testing."""

    entries: list[OutboxEntry] = field(default_factory=list)
    applied_ids: list[int] = field(default_factory=list)
    failures: list[tuple[int, int, str, datetime | None]] = field(default_factory=list)
    dequeue_error: Exception | None = None

    async def dequeue_ready_batch(
        self,
        driver: str,
        limit: int,
    ) -> list[OutboxEntry]:
        if self.dequeue_error:
            raise self.dequeue_error
        return [e for e in self.entries if e.driver == driver][:limit]

    async def mark_applied(
        self,
        entry_id: int,
        *,
        connection: Any = None,
    ) -> None:
        self.applied_ids.append(entry_id)
        self.entries = [e for e in self.entries if e.id != entry_id]

    async def record_failure(
        self,
        entry: OutboxEntry,
        *,
        retries: int,
        requeue_seq: int,
        last_error: str,
        next_attempt_ts: datetime | None = None,
        backoff_exp: int = 0,
        status: str = "PENDING",
        connection: Any = None,
    ) -> None:
        self.failures.append((entry.id, retries, last_error, next_attempt_ts))
        entry.retries = retries
        entry.last_error = last_error
        entry.backoff_exp = backoff_exp


@dataclass
class MockDeadLetterQueue:
    """Mock DeadLetterQueue for testing."""

    entries: list[DeadLetter] = field(default_factory=list)
    next_id: int = 1

    async def record(
        self,
        letter: DeadLetter,
        *,
        connection: Any = None,
    ) -> int:
        letter.id = self.next_id
        self.next_id += 1
        self.entries.append(letter)
        return letter.id


@dataclass
class MockBusDispatcher:
    """Mock BusDispatcher for testing."""

    dispatched: list[BusMessage] = field(default_factory=list)
    dispatch_error: Exception | None = None

    async def dispatch(self, messages: list[BusMessage]) -> None:
        if self.dispatch_error:
            raise self.dispatch_error
        self.dispatched.extend(messages)


@dataclass
class MockMetrics:
    """Mock MetricsExporter for testing."""

    emitted: list[tuple[str, float, dict[str, str]]] = field(default_factory=list)
    observed: list[tuple[str, float, dict[str, str]]] = field(default_factory=list)

    def emit(self, metric_name: str, value: float = 1.0, **labels: str) -> None:
        self.emitted.append((metric_name, value, labels))

    def observe(
        self,
        metric_name: str,
        value: float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        self.observed.append((metric_name, value, labels or {}))


def create_test_entry(
    *,
    id: int = 1,
    wal_pos: int = 100,
    tenant_id: str = "tenant-1",
    space_id: str = "space-1",
    driver: str = "p03",
    op_kind: str = "p03.consolidation.complete.v1",
    payload: bytes | None = None,
    fingerprint: str = "fp-001",
    retries: int = 0,
    requeue_seq: int = 0,
) -> OutboxEntry:
    """Create a test OutboxEntry."""
    if payload is None:
        payload = json.dumps({"status": "SUCCESS", "trace_id": "trace-123"}).encode()
    return OutboxEntry(
        id=id,
        wal_pos=wal_pos,
        tenant_id=tenant_id,
        space_id=space_id,
        driver=driver,
        op_kind=op_kind,
        payload=payload,
        fingerprint=fingerprint,
        requeue_seq=requeue_seq,
        retries=retries,
    )


@pytest.fixture
def outbox_store() -> MockOutboxStore:
    """Create a mock outbox store."""
    return MockOutboxStore()


@pytest.fixture
def dlq_store() -> MockDeadLetterQueue:
    """Create a mock DLQ store."""
    return MockDeadLetterQueue()


@pytest.fixture
def bus_dispatcher() -> MockBusDispatcher:
    """Create a mock bus dispatcher."""
    return MockBusDispatcher()


@pytest.fixture
def metrics() -> MockMetrics:
    """Create a mock metrics exporter."""
    return MockMetrics()


@pytest.fixture
def publisher(
    outbox_store: MockOutboxStore,
    bus_dispatcher: MockBusDispatcher,
    dlq_store: MockDeadLetterQueue,
    metrics: MockMetrics,
) -> P03OutboxPublisher:
    """Create a P03OutboxPublisher with mocked dependencies."""
    return P03OutboxPublisher(
        outbox_store=outbox_store,  # type: ignore[arg-type]
        bus_dispatcher=bus_dispatcher,  # type: ignore[arg-type]
        dlq_store=dlq_store,  # type: ignore[arg-type]
        metrics=metrics,  # type: ignore[arg-type]
    )


# ============================================================================
# OutboxPublisherConfig Tests
# ============================================================================


class TestOutboxPublisherConfig:
    """Tests for OutboxPublisherConfig dataclass."""

    def test_default_values(self) -> None:
        """Config has sensible defaults."""
        config = OutboxPublisherConfig()

        assert config.driver == "p03"
        assert config.batch_size == 100
        assert config.max_retries == 3
        assert config.base_delay_ms == 100
        assert config.max_delay_ms == 30000
        assert config.jitter_factor == 0.1

    def test_custom_values(self) -> None:
        """Config can be customized."""
        config = OutboxPublisherConfig(
            driver="custom",
            batch_size=50,
            max_retries=5,
            base_delay_ms=200,
            max_delay_ms=60000,
            jitter_factor=0.2,
        )

        assert config.driver == "custom"
        assert config.batch_size == 50
        assert config.max_retries == 5
        assert config.base_delay_ms == 200
        assert config.max_delay_ms == 60000
        assert config.jitter_factor == 0.2


# ============================================================================
# PublishResult Tests
# ============================================================================


class TestPublishResult:
    """Tests for PublishResult dataclass."""

    def test_default_values(self) -> None:
        """Result starts with zero counts."""
        result = PublishResult()

        assert result.processed == 0
        assert result.published == 0
        assert result.retried == 0
        assert result.dlq_count == 0
        assert result.errors == []


# ============================================================================
# P03OutboxPublisher Tests - Successful Publishing
# ============================================================================


class TestP03OutboxPublisherSuccess:
    """Tests for successful outbox publishing."""

    @pytest.mark.asyncio
    async def test_drain_empty_batch_returns_zero(
        self,
        publisher: P03OutboxPublisher,
    ) -> None:
        """Draining empty batch returns zero processed."""
        result = await publisher.drain_batch()

        assert result.processed == 0
        assert result.published == 0
        assert result.retried == 0
        assert result.dlq_count == 0

    @pytest.mark.asyncio
    async def test_drain_single_entry_publishes_to_bus(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
    ) -> None:
        """Single entry is published to bus and marked applied."""
        entry = create_test_entry(id=1)
        outbox_store.entries.append(entry)

        result = await publisher.drain_batch()

        assert result.processed == 1
        assert result.published == 1
        assert len(bus_dispatcher.dispatched) == 1
        assert outbox_store.applied_ids == [1]

    @pytest.mark.asyncio
    async def test_drain_multiple_entries_publishes_all(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
    ) -> None:
        """Multiple entries are all published."""
        for i in range(5):
            outbox_store.entries.append(create_test_entry(id=i + 1))

        result = await publisher.drain_batch()

        assert result.processed == 5
        assert result.published == 5
        assert len(bus_dispatcher.dispatched) == 5
        assert outbox_store.applied_ids == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_bus_message_has_correct_structure(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
    ) -> None:
        """BusMessage has correct topic, payload, and metadata."""
        entry = create_test_entry(
            id=1,
            op_kind="p03.gap.detected.v1",
            tenant_id="t1",
            space_id="s1",
            fingerprint="fp-test",
            wal_pos=999,
        )
        outbox_store.entries.append(entry)

        await publisher.drain_batch()

        msg = bus_dispatcher.dispatched[0]
        assert msg.topic == "p03.gap.detected.v1"
        assert msg.payload == entry.payload
        assert msg.offset == 999
        assert msg.space_id == "s1"
        assert msg.metadata["tenant_id"] == "t1"
        assert msg.metadata["fingerprint"] == "fp-test"
        assert msg.metadata["driver"] == "p03"

    @pytest.mark.asyncio
    async def test_trace_id_extracted_from_payload(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
    ) -> None:
        """trace_id is extracted from JSON payload."""
        payload = json.dumps({"status": "OK", "trace_id": "my-trace-id"}).encode()
        entry = create_test_entry(id=1, payload=payload)
        outbox_store.entries.append(entry)

        await publisher.drain_batch()

        msg = bus_dispatcher.dispatched[0]
        assert msg.trace_id == "my-trace-id"

    @pytest.mark.asyncio
    async def test_only_processes_p03_driver_entries(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
    ) -> None:
        """Only entries with driver='p03' are processed."""
        outbox_store.entries.append(create_test_entry(id=1, driver="p03"))
        outbox_store.entries.append(create_test_entry(id=2, driver="p02"))  # Different driver

        result = await publisher.drain_batch()

        # Mock dequeue filters by driver
        assert result.processed == 1
        assert outbox_store.applied_ids == [1]


# ============================================================================
# P03OutboxPublisher Tests - Failure Handling
# ============================================================================


class TestP03OutboxPublisherFailures:
    """Tests for failure handling with backoff and DLQ."""

    @pytest.mark.asyncio
    async def test_transient_failure_triggers_retry(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
    ) -> None:
        """Transient failure schedules entry for retry."""
        entry = create_test_entry(id=1, retries=0)
        outbox_store.entries.append(entry)
        bus_dispatcher.dispatch_error = RuntimeError("Network error")

        result = await publisher.drain_batch()

        assert result.processed == 1
        assert result.published == 0
        assert result.retried == 1
        assert result.dlq_count == 0
        assert len(outbox_store.failures) == 1
        assert outbox_store.failures[0][1] == 1  # retries = 1

    @pytest.mark.asyncio
    async def test_retry_increments_retry_count(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
    ) -> None:
        """Each retry increments the retry count."""
        entry = create_test_entry(id=1, retries=2)  # Already retried twice
        outbox_store.entries.append(entry)
        bus_dispatcher.dispatch_error = RuntimeError("Transient error")

        await publisher.drain_batch()

        assert outbox_store.failures[0][1] == 3  # retries = 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_escalates_to_dlq(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
        dlq_store: MockDeadLetterQueue,
    ) -> None:
        """Entry is escalated to DLQ after max retries exceeded."""
        entry = create_test_entry(id=1, retries=3)  # At max retries
        outbox_store.entries.append(entry)
        bus_dispatcher.dispatch_error = RuntimeError("Permanent error")

        result = await publisher.drain_batch()

        assert result.processed == 1
        assert result.published == 0
        assert result.retried == 0
        assert result.dlq_count == 1
        assert len(dlq_store.entries) == 1
        assert outbox_store.applied_ids == [1]  # Removed from outbox

    @pytest.mark.asyncio
    async def test_dlq_entry_has_correct_context(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
        dlq_store: MockDeadLetterQueue,
    ) -> None:
        """DLQ entry includes P03 context."""
        entry = create_test_entry(
            id=1,
            retries=3,
            tenant_id="t-dlq",
            space_id="s-dlq",
            op_kind="p03.test.topic.v1",
            fingerprint="fp-dlq",
        )
        outbox_store.entries.append(entry)
        bus_dispatcher.dispatch_error = ValueError("Bad payload")

        await publisher.drain_batch()

        dlq_entry = dlq_store.entries[0]
        assert dlq_entry.tenant_id == "t-dlq"
        assert dlq_entry.space_id == "s-dlq"
        assert dlq_entry.driver == "p03"
        assert dlq_entry.op_kind == "p03.test.topic.v1"
        assert dlq_entry.fingerprint == "fp-dlq"
        assert "P03 publish failed" in dlq_entry.reason
        assert "4 attempts" in dlq_entry.reason  # 3 retries + 1 = 4 attempts

    @pytest.mark.asyncio
    async def test_failure_sets_next_attempt_ts(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
    ) -> None:
        """Failure records next_attempt_ts for backoff."""
        entry = create_test_entry(id=1, retries=0)
        outbox_store.entries.append(entry)
        bus_dispatcher.dispatch_error = RuntimeError("Error")

        await publisher.drain_batch()

        assert outbox_store.failures[0][3] is not None  # next_attempt_ts set

    @pytest.mark.asyncio
    async def test_partial_batch_failure_continues_processing(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
    ) -> None:
        """Failure of one entry doesn't stop processing others."""
        # Create dispatcher that fails only on first call
        call_count = 0

        async def dispatch_with_one_failure(messages: list[BusMessage]) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First call fails")
            bus_dispatcher.dispatched.extend(messages)

        # Patch dispatcher
        bus_dispatcher.dispatch = dispatch_with_one_failure  # type: ignore[method-assign]

        outbox_store.entries.append(create_test_entry(id=1))
        outbox_store.entries.append(create_test_entry(id=2))
        outbox_store.entries.append(create_test_entry(id=3))

        result = await publisher.drain_batch()

        assert result.processed == 3
        assert result.retried == 1  # First one failed
        assert result.published == 2  # Others succeeded


# ============================================================================
# P03OutboxPublisher Tests - Backoff Calculation
# ============================================================================


class TestBackoffCalculation:
    """Tests for exponential backoff calculation."""

    def test_backoff_doubles_with_retries(
        self,
        publisher: P03OutboxPublisher,
    ) -> None:
        """Backoff delay doubles with each retry (minus jitter)."""
        with patch("random.uniform", return_value=0):  # No jitter
            delay_1 = publisher._calculate_backoff(1)
            delay_2 = publisher._calculate_backoff(2)
            delay_3 = publisher._calculate_backoff(3)

        # base=100, so: 100*2^1=200, 100*2^2=400, 100*2^3=800
        assert delay_1 == 200
        assert delay_2 == 400
        assert delay_3 == 800

    def test_backoff_capped_at_max_delay(
        self,
        publisher: P03OutboxPublisher,
    ) -> None:
        """Backoff is capped at max_delay_ms."""
        with patch("random.uniform", return_value=0):
            delay = publisher._calculate_backoff(20)  # 100 * 2^20 = huge

        assert delay == 30000  # max_delay_ms

    def test_backoff_includes_jitter(
        self,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
        dlq_store: MockDeadLetterQueue,
    ) -> None:
        """Backoff includes random jitter."""
        publisher = P03OutboxPublisher(
            outbox_store=outbox_store,  # type: ignore[arg-type]
            bus_dispatcher=bus_dispatcher,  # type: ignore[arg-type]
            dlq_store=dlq_store,  # type: ignore[arg-type]
            config=OutboxPublisherConfig(jitter_factor=0.5),
        )

        # With jitter_factor=0.5, jitter can be up to 50% of base_delay
        delays = [publisher._calculate_backoff(1) for _ in range(100)]

        # Should have some variation
        assert len(set(delays)) > 1


# ============================================================================
# P03OutboxPublisher Tests - Metrics
# ============================================================================


class TestMetricsEmission:
    """Tests for metrics emission."""

    @pytest.mark.asyncio
    async def test_published_metric_emitted(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        metrics: MockMetrics,
    ) -> None:
        """p03_outbox_published_total metric is emitted on success."""
        outbox_store.entries.append(create_test_entry(id=1, op_kind="test.topic"))

        await publisher.drain_batch()

        published_metrics = [m for m in metrics.emitted if m[0] == "p03_outbox_published_total"]
        assert len(published_metrics) == 1
        assert published_metrics[0][2]["topic"] == "test.topic"

    @pytest.mark.asyncio
    async def test_retry_metric_emitted(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
        metrics: MockMetrics,
    ) -> None:
        """p03_outbox_retry_total metric is emitted on retry."""
        outbox_store.entries.append(create_test_entry(id=1, retries=0))
        bus_dispatcher.dispatch_error = RuntimeError("Error")

        await publisher.drain_batch()

        retry_metrics = [m for m in metrics.emitted if m[0] == "p03_outbox_retry_total"]
        assert len(retry_metrics) == 1

    @pytest.mark.asyncio
    async def test_dlq_metric_emitted(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
        metrics: MockMetrics,
    ) -> None:
        """p03_outbox_dlq_total metric is emitted on DLQ escalation."""
        outbox_store.entries.append(create_test_entry(id=1, retries=3))
        bus_dispatcher.dispatch_error = RuntimeError("Error")

        await publisher.drain_batch()

        dlq_metrics = [m for m in metrics.emitted if m[0] == "p03_outbox_dlq_total"]
        assert len(dlq_metrics) == 1

    @pytest.mark.asyncio
    async def test_drain_duration_metric_observed(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        metrics: MockMetrics,
    ) -> None:
        """p03_outbox_drain_duration_ms histogram is observed."""
        outbox_store.entries.append(create_test_entry(id=1))

        await publisher.drain_batch()

        duration_metrics = [m for m in metrics.observed if m[0] == "p03_outbox_drain_duration_ms"]
        assert len(duration_metrics) == 1
        assert duration_metrics[0][1] >= 0  # Duration is non-negative

    @pytest.mark.asyncio
    async def test_no_metrics_when_exporter_none(
        self,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
        dlq_store: MockDeadLetterQueue,
    ) -> None:
        """No crash when metrics exporter is None."""
        publisher = P03OutboxPublisher(
            outbox_store=outbox_store,  # type: ignore[arg-type]
            bus_dispatcher=bus_dispatcher,  # type: ignore[arg-type]
            dlq_store=dlq_store,  # type: ignore[arg-type]
            metrics=None,
        )
        outbox_store.entries.append(create_test_entry(id=1))

        result = await publisher.drain_batch()

        assert result.published == 1  # Still works


# ============================================================================
# P03OutboxPublisher Tests - Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_entry_with_none_id_skipped(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
    ) -> None:
        """Entry with id=None is skipped."""
        entry = create_test_entry(id=None)  # type: ignore[arg-type]
        entry.id = None  # Force None
        outbox_store.entries.append(entry)

        result = await publisher.drain_batch()

        # Entry is processed but skipped
        assert result.processed == 1
        assert result.published == 0

    @pytest.mark.asyncio
    async def test_malformed_payload_still_publishes(
        self,
        publisher: P03OutboxPublisher,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
    ) -> None:
        """Malformed JSON payload still gets published."""
        entry = create_test_entry(id=1, payload=b"not valid json")
        outbox_store.entries.append(entry)

        result = await publisher.drain_batch()

        assert result.published == 1
        msg = bus_dispatcher.dispatched[0]
        assert msg.trace_id is None  # Couldn't extract trace_id

    @pytest.mark.asyncio
    async def test_config_property_returns_config(
        self,
        publisher: P03OutboxPublisher,
    ) -> None:
        """Config property returns the publisher configuration."""
        config = publisher.config

        assert config.driver == "p03"
        assert config.batch_size == 100

    @pytest.mark.asyncio
    async def test_batch_respects_limit(
        self,
        outbox_store: MockOutboxStore,
        bus_dispatcher: MockBusDispatcher,
        dlq_store: MockDeadLetterQueue,
    ) -> None:
        """Drain respects batch_size limit."""
        publisher = P03OutboxPublisher(
            outbox_store=outbox_store,  # type: ignore[arg-type]
            bus_dispatcher=bus_dispatcher,  # type: ignore[arg-type]
            dlq_store=dlq_store,  # type: ignore[arg-type]
            config=OutboxPublisherConfig(batch_size=2),
        )

        for i in range(5):
            outbox_store.entries.append(create_test_entry(id=i + 1))

        result = await publisher.drain_batch()

        # Mock dequeue returns all, but config has batch_size=2
        # Note: actual limit is applied in dequeue_ready_batch
        assert result.processed == 2
