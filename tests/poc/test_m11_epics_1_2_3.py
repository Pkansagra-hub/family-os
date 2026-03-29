"""
Tests for Epics 11.1, 11.2, 11.3 -- SessionDelta, Delta Bus Topics & Emitters,
DeltaAggregator Core.

Epic 11.1: SessionDelta Dataclass
    V2 Design Ref: Section 5 (DeltaAggregator, session delta structure)
    SessionDelta validation, serialization, dedup_key, round-trip.

Epic 11.2: Delta Bus Topics & Emitters
    V2 Design Ref: Section 3 (session topics), Section 5 (delta lane)
    Topic constants, emit_artifact, emit_task_state_change.

Epic 11.3: DeltaAggregator Core
    V2 Design Ref: Section 5 (500ms window, deduplication, causal ordering)
    DeltaAggregator batching, dedup, causal order, stats.

Source of truth: implemented code + concierge_poc_design_v2.md
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

from poc.k1_poc.delta.aggregator import DEFAULT_BATCH_WINDOW_MS, DeltaAggregator, DeltaBatch
from poc.k1_poc.delta.emitters import VALID_TASK_STATUSES, emit_artifact, emit_task_state_change
from poc.k1_poc.delta.session_delta import (
    VALID_DELTA_OPERATIONS,
    VALID_DELTA_SECTIONS,
    SessionDelta,
)
from poc.k1_poc.delta.topics import (
    ALL_DELTA_TOPICS,
    ARTIFACT_CREATED,
    STATE_UPDATED,
    TASK_STATE_CHANGED,
)

# =========================================================================
# Helpers
# =========================================================================


def _delta(
    section: str = "task_state",
    key: str = "task-1",
    operation: str = "set",
    data: dict | None = None,
    delta_id: str | None = None,
    source_task_id: str | None = None,
    parent_delta_id: str | None = None,
    timestamp_ns: int = 0,
) -> SessionDelta:
    kwargs: dict = {
        "section": section,
        "key": key,
        "operation": operation,
        "data": data if data is not None else {},
    }
    if delta_id is not None:
        kwargs["delta_id"] = delta_id
    if source_task_id is not None:
        kwargs["source_task_id"] = source_task_id
    if parent_delta_id is not None:
        kwargs["parent_delta_id"] = parent_delta_id
    if timestamp_ns != 0:
        kwargs["timestamp_ns"] = timestamp_ns
    return SessionDelta(**kwargs)


# =========================================================================
# Epic 11.1 -- SessionDelta Dataclass
# =========================================================================


class TestSessionDeltaCreation:
    """11.1.1 -- SessionDelta basic construction and validation."""

    def test_basic_creation(self):
        """SessionDelta creates with valid section and operation."""
        d = _delta(
            section="task_state", key="task-001", operation="set", data={"status": "COMPLETED"}
        )
        assert d.section == "task_state"
        assert d.key == "task-001"
        assert d.operation == "set"
        assert d.data == {"status": "COMPLETED"}
        assert d.delta_id.startswith("delta-")

    def test_auto_generated_delta_id(self):
        """delta_id is auto-generated with 'delta-' prefix."""
        d1 = _delta()
        d2 = _delta()
        assert d1.delta_id.startswith("delta-")
        assert d2.delta_id.startswith("delta-")
        assert d1.delta_id != d2.delta_id

    def test_explicit_delta_id(self):
        """Explicit delta_id is preserved."""
        d = _delta(delta_id="delta-custom")
        assert d.delta_id == "delta-custom"

    def test_optional_fields_default(self):
        """Optional fields default to None/0."""
        d = _delta()
        assert d.source_task_id is None
        assert d.parent_delta_id is None
        assert d.timestamp_ns == 0

    def test_optional_fields_set(self):
        """Optional fields are set when provided."""
        d = _delta(source_task_id="task-42", parent_delta_id="delta-parent", timestamp_ns=123456789)
        assert d.source_task_id == "task-42"
        assert d.parent_delta_id == "delta-parent"
        assert d.timestamp_ns == 123456789

    @pytest.mark.parametrize("section", sorted(VALID_DELTA_SECTIONS))
    def test_all_valid_sections(self, section: str):
        """All valid sections are accepted."""
        d = _delta(section=section)
        assert d.section == section

    @pytest.mark.parametrize("operation", sorted(VALID_DELTA_OPERATIONS))
    def test_all_valid_operations(self, operation: str):
        """All valid operations are accepted."""
        d = _delta(operation=operation)
        assert d.operation == operation


class TestSessionDeltaValidation:
    """11.1.1 -- SessionDelta validation rejects invalid inputs."""

    def test_invalid_section_raises(self):
        """Invalid section raises ValueError."""
        with pytest.raises(ValueError, match="section"):
            _delta(section="invalid_section")

    def test_invalid_operation_raises(self):
        """Invalid operation raises ValueError."""
        with pytest.raises(ValueError, match="operation"):
            _delta(operation="upsert")

    def test_empty_section_raises(self):
        with pytest.raises(ValueError, match="section"):
            _delta(section="")

    def test_empty_operation_raises(self):
        with pytest.raises(ValueError, match="operation"):
            _delta(operation="")

    @pytest.mark.parametrize(
        "bad_section",
        [
            "beliefs_active",
            "scoreboard",
            "affective_now",
            "persona",
            "narrative_active",
            "clarifications",
        ],
    )
    def test_cognitive_sections_rejected(self, bad_section: str):
        """Cognitive sections (Front-written) are NOT valid delta targets.

        V2 Section 5: Back never writes SS directly. Cognitive sections
        are written by Front LLM cognitive tools, not via deltas.
        """
        with pytest.raises(ValueError, match="section"):
            _delta(section=bad_section)


class TestSessionDeltaDedupKey:
    """11.1.1 -- dedup_key() for batch deduplication."""

    def test_dedup_key_format(self):
        """dedup_key is 'section:key'."""
        d = _delta(section="task_artifacts", key="booking-1")
        assert d.dedup_key() == "task_artifacts:booking-1"

    def test_same_section_key_same_dedup(self):
        """Same section+key produces same dedup_key."""
        d1 = _delta(section="task_state", key="task-1")
        d2 = _delta(section="task_state", key="task-1")
        assert d1.dedup_key() == d2.dedup_key()

    def test_different_key_different_dedup(self):
        """Different key produces different dedup_key."""
        d1 = _delta(key="task-1")
        d2 = _delta(key="task-2")
        assert d1.dedup_key() != d2.dedup_key()

    def test_different_section_different_dedup(self):
        """Different section produces different dedup_key."""
        d1 = _delta(section="task_state", key="x")
        d2 = _delta(section="task_artifacts", key="x")
        assert d1.dedup_key() != d2.dedup_key()


class TestSessionDeltaSerialization:
    """11.1.1 -- SessionDelta serialization round-trip."""

    def test_to_dict_minimal(self):
        """to_dict includes required fields."""
        d = _delta(
            delta_id="delta-abc", section="task_state", key="task-1", operation="set", data={"x": 1}
        )
        result = d.to_dict()
        assert result["delta_id"] == "delta-abc"
        assert result["section"] == "task_state"
        assert result["key"] == "task-1"
        assert result["operation"] == "set"
        assert result["data"] == {"x": 1}
        # Optional fields not included when default
        assert "source_task_id" not in result
        assert "parent_delta_id" not in result
        assert "timestamp_ns" not in result

    def test_to_dict_with_optional_fields(self):
        """to_dict includes optional fields when set."""
        d = _delta(source_task_id="task-42", parent_delta_id="delta-p", timestamp_ns=999)
        result = d.to_dict()
        assert result["source_task_id"] == "task-42"
        assert result["parent_delta_id"] == "delta-p"
        assert result["timestamp_ns"] == 999

    def test_round_trip_dict(self):
        """from_dict(to_dict()) produces equivalent delta."""
        original = _delta(
            section="task_state",
            key="task-001",
            operation="update",
            data={"status": "IN_PROGRESS"},
            source_task_id="task-001",
            parent_delta_id="delta-parent",
            timestamp_ns=42,
        )
        restored = SessionDelta.from_dict(original.to_dict())
        assert restored.section == original.section
        assert restored.key == original.key
        assert restored.operation == original.operation
        assert restored.data == original.data
        assert restored.source_task_id == original.source_task_id
        assert restored.parent_delta_id == original.parent_delta_id
        assert restored.timestamp_ns == original.timestamp_ns

    def test_round_trip_payload(self):
        """from_payload(to_payload()) produces equivalent delta."""
        original = _delta(
            section="task_artifacts",
            key="task-1:booking",
            operation="append",
            data={"type": "booking", "confirmation": "ACM-123"},
            source_task_id="task-1",
        )
        payload = original.to_payload()
        assert isinstance(payload, bytes)
        restored = SessionDelta.from_payload(payload)
        assert restored.section == original.section
        assert restored.key == original.key
        assert restored.data == original.data
        assert restored.delta_id == original.delta_id

    def test_to_payload_is_compact_json(self):
        """to_payload uses compact JSON (no spaces)."""
        d = _delta(data={"a": 1, "b": 2})
        payload = d.to_payload()
        text = payload.decode("utf-8")
        assert " " not in text  # compact separators

    def test_from_dict_generates_id_if_missing(self):
        """from_dict generates delta_id when not in input."""
        d = SessionDelta.from_dict(
            {
                "section": "task_state",
                "key": "x",
                "operation": "set",
                "data": {},
            }
        )
        assert d.delta_id.startswith("delta-")


class TestValidDeltaConstants:
    """11.1 -- Validate exported section/operation sets."""

    def test_valid_sections_contents(self):
        """VALID_DELTA_SECTIONS matches design doc Section 5."""
        assert VALID_DELTA_SECTIONS == frozenset(
            {
                "task_state",
                "task_artifacts",
                "history_active",
                "control",
                "meta",
            }
        )

    def test_valid_operations_contents(self):
        """VALID_DELTA_OPERATIONS: set, append, update, delete."""
        assert VALID_DELTA_OPERATIONS == frozenset(
            {
                "set",
                "append",
                "update",
                "delete",
            }
        )

    def test_sections_are_frozenset(self):
        assert isinstance(VALID_DELTA_SECTIONS, frozenset)

    def test_operations_are_frozenset(self):
        assert isinstance(VALID_DELTA_OPERATIONS, frozenset)


# =========================================================================
# Epic 11.2 -- Delta Bus Topics & Emitters
# =========================================================================


class TestDeltaTopics:
    """11.2.1 -- Delta bus topic constants."""

    def test_artifact_created_topic(self):
        assert ARTIFACT_CREATED == "k1.session.artifact.created.v1"

    def test_task_state_changed_topic(self):
        assert TASK_STATE_CHANGED == "k1.session.task.state.v1"

    def test_state_updated_topic(self):
        assert STATE_UPDATED == "k1.session.state.updated.v1"

    def test_all_topics_uses_session_prefix(self):
        """All delta topics use k1.session prefix for STRICT delivery."""
        for topic in ALL_DELTA_TOPICS:
            assert topic.startswith("k1.session."), f"{topic} missing k1.session prefix"

    def test_all_topics_count(self):
        assert len(ALL_DELTA_TOPICS) == 3

    def test_all_topics_is_frozenset(self):
        assert isinstance(ALL_DELTA_TOPICS, frozenset)

    def test_all_topics_contains_all(self):
        assert ARTIFACT_CREATED in ALL_DELTA_TOPICS
        assert TASK_STATE_CHANGED in ALL_DELTA_TOPICS
        assert STATE_UPDATED in ALL_DELTA_TOPICS


class TestEmitArtifact:
    """11.2.2 -- emit_artifact() Back-side emitter."""

    @pytest.mark.asyncio
    async def test_emit_artifact_basic(self):
        """emit_artifact creates and publishes a task_artifacts delta."""
        published: list[tuple[str, SessionDelta]] = []

        async def mock_publish(topic: str, delta: SessionDelta) -> None:
            published.append((topic, delta))

        delta = await emit_artifact(
            task_id="task-001",
            artifact_type="booking",
            artifact_data={"confirmation": "ACM-123", "hotel": "Vineyard Inn"},
            publish_fn=mock_publish,
        )

        assert delta.section == "task_artifacts"
        assert delta.key == "task-001:booking"
        assert delta.operation == "append"
        assert delta.data["type"] == "booking"
        assert delta.data["task_id"] == "task-001"
        assert delta.data["confirmation"] == "ACM-123"
        assert delta.data["hotel"] == "Vineyard Inn"
        assert delta.source_task_id == "task-001"
        assert delta.timestamp_ns > 0
        assert delta.delta_id.startswith("delta-")

    @pytest.mark.asyncio
    async def test_emit_artifact_publishes_to_correct_topic(self):
        """emit_artifact publishes to ARTIFACT_CREATED topic."""
        published: list[tuple[str, SessionDelta]] = []

        async def mock_publish(topic: str, delta: SessionDelta) -> None:
            published.append((topic, delta))

        await emit_artifact(
            task_id="task-x",
            artifact_type="search_results",
            artifact_data={"results": [{"name": "Bistro"}]},
            publish_fn=mock_publish,
        )

        assert len(published) == 1
        assert published[0][0] == ARTIFACT_CREATED

    @pytest.mark.asyncio
    async def test_emit_artifact_returns_delta(self):
        """emit_artifact returns the created SessionDelta."""

        async def mock_publish(topic: str, delta: SessionDelta) -> None:
            pass

        result = await emit_artifact(
            task_id="task-ret",
            artifact_type="doc",
            artifact_data={"text": "hello"},
            publish_fn=mock_publish,
        )
        assert isinstance(result, SessionDelta)

    @pytest.mark.asyncio
    async def test_emit_artifact_multiple_types(self):
        """Different artifact types produce different delta keys."""
        published: list[tuple[str, SessionDelta]] = []

        async def mock_publish(topic: str, delta: SessionDelta) -> None:
            published.append((topic, delta))

        d1 = await emit_artifact("task-1", "booking", {"x": 1}, mock_publish)
        d2 = await emit_artifact("task-1", "itinerary", {"y": 2}, mock_publish)

        assert d1.key == "task-1:booking"
        assert d2.key == "task-1:itinerary"
        assert d1.dedup_key() != d2.dedup_key()


class TestEmitTaskStateChange:
    """11.2.2 -- emit_task_state_change() Back-side emitter."""

    @pytest.mark.asyncio
    async def test_emit_state_change_basic(self):
        """emit_task_state_change creates and publishes a task_state delta."""
        published: list[tuple[str, SessionDelta]] = []

        async def mock_publish(topic: str, delta: SessionDelta) -> None:
            published.append((topic, delta))

        delta = await emit_task_state_change(
            task_id="task-001",
            new_status="COMPLETED",
            metadata={"tool_calls": 2},
            publish_fn=mock_publish,
        )

        assert delta.section == "task_state"
        assert delta.key == "task-001"
        assert delta.operation == "update"
        assert delta.data["status"] == "COMPLETED"
        assert delta.data["tool_calls"] == 2
        assert delta.source_task_id == "task-001"
        assert delta.timestamp_ns > 0

    @pytest.mark.asyncio
    async def test_emit_state_change_publishes_to_correct_topic(self):
        """emit_task_state_change publishes to TASK_STATE_CHANGED topic."""
        published: list[tuple[str, SessionDelta]] = []

        async def mock_publish(topic: str, delta: SessionDelta) -> None:
            published.append((topic, delta))

        await emit_task_state_change(
            task_id="task-x",
            new_status="IN_PROGRESS",
            publish_fn=mock_publish,
        )

        assert len(published) == 1
        assert published[0][0] == TASK_STATE_CHANGED

    @pytest.mark.asyncio
    async def test_emit_state_change_no_publish_fn(self):
        """emit_task_state_change without publish_fn creates but doesn't publish."""
        delta = await emit_task_state_change(
            task_id="task-offline",
            new_status="DISPATCHED",
        )
        assert isinstance(delta, SessionDelta)
        assert delta.data["status"] == "DISPATCHED"

    @pytest.mark.asyncio
    async def test_emit_state_change_no_metadata(self):
        """emit_task_state_change without metadata produces clean data."""
        delta = await emit_task_state_change(
            task_id="task-clean",
            new_status="FAILED",
        )
        assert delta.data == {"status": "FAILED"}

    @pytest.mark.asyncio
    async def test_emit_state_change_invalid_status_raises(self):
        """emit_task_state_change with invalid status raises ValueError."""
        with pytest.raises(ValueError, match="Invalid task status"):
            await emit_task_state_change(
                task_id="task-bad",
                new_status="UNKNOWN_STATUS",
            )

    @pytest.mark.parametrize("status", sorted(VALID_TASK_STATUSES))
    @pytest.mark.asyncio
    async def test_all_valid_statuses_accepted(self, status: str):
        """All valid task statuses are accepted."""
        delta = await emit_task_state_change(
            task_id="task-param",
            new_status=status,
        )
        assert delta.data["status"] == status


class TestValidTaskStatuses:
    """11.2 -- VALID_TASK_STATUSES constant validation."""

    def test_valid_statuses_contents(self):
        """VALID_TASK_STATUSES matches design doc Section 5 TaskStateEntry."""
        assert VALID_TASK_STATUSES == frozenset(
            {
                "DISPATCHED",
                "IN_PROGRESS",
                "SUSPENDED",
                "COMPLETED",
                "FAILED",
                "CANCELLED",
            }
        )

    def test_valid_statuses_count(self):
        assert len(VALID_TASK_STATUSES) == 6

    def test_valid_statuses_is_frozenset(self):
        assert isinstance(VALID_TASK_STATUSES, frozenset)


# =========================================================================
# Epic 11.3 -- DeltaAggregator Core
# =========================================================================


class TestDeltaAggregatorBatching:
    """11.3.1 -- DeltaAggregator 500ms batch window."""

    @pytest.mark.asyncio
    async def test_single_delta_flushes_after_window(self):
        """Single delta flushes after batch window expires."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)
        await agg.collect(_delta(data={"status": "COMPLETED"}))
        await asyncio.sleep(0.1)

        assert len(batches) == 1
        assert len(batches[0].deltas) == 1
        assert batches[0].batch_id == "batch-1"

    @pytest.mark.asyncio
    async def test_multiple_deltas_in_one_batch(self):
        """Multiple deltas within window are batched together."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=100)
        await agg.collect(_delta(key="task-1", data={"status": "A"}))
        await agg.collect(_delta(key="task-2", data={"status": "B"}))
        await agg.collect(_delta(key="task-3", data={"status": "C"}))
        await asyncio.sleep(0.15)

        assert len(batches) == 1
        assert len(batches[0].deltas) == 3

    @pytest.mark.asyncio
    async def test_manual_flush_before_window(self):
        """Manual flush() processes pending deltas immediately."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=5000)
        await agg.collect(_delta(data={"x": 1}))
        batch = await agg.flush()

        assert batch is not None
        assert len(batch.deltas) == 1
        assert agg.pending_count == 0

    @pytest.mark.asyncio
    async def test_flush_empty_returns_none(self):
        """flush() with no pending deltas returns None."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush)
        result = await agg.flush()

        assert result is None
        assert len(batches) == 0

    @pytest.mark.asyncio
    async def test_two_separate_batches(self):
        """Deltas after flush start a new batch."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)

        await agg.collect(_delta(key="task-1"))
        await asyncio.sleep(0.1)

        await agg.collect(_delta(key="task-2"))
        await asyncio.sleep(0.1)

        assert len(batches) == 2
        assert batches[0].batch_id == "batch-1"
        assert batches[1].batch_id == "batch-2"

    @pytest.mark.asyncio
    async def test_pending_count(self):
        """pending_count reflects uncollected deltas."""

        async def on_flush(batch: DeltaBatch) -> None:
            pass

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=5000)
        assert agg.pending_count == 0

        await agg.collect(_delta(key="a"))
        assert agg.pending_count == 1

        await agg.collect(_delta(key="b"))
        assert agg.pending_count == 2

        await agg.flush()
        assert agg.pending_count == 0

    @pytest.mark.asyncio
    async def test_default_batch_window(self):
        """DEFAULT_BATCH_WINDOW_MS is 500."""
        assert DEFAULT_BATCH_WINDOW_MS == 500


class TestDeltaAggregatorDedup:
    """11.3.2 -- DeltaAggregator deduplication (last-write-wins)."""

    @pytest.mark.asyncio
    async def test_dedup_same_key_last_wins(self):
        """Two deltas to same section+key: last-write-wins."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=100)
        await agg.collect(_delta(key="task-1", data={"status": "IN_PROGRESS"}))
        await agg.collect(_delta(key="task-1", data={"status": "COMPLETED"}))
        await asyncio.sleep(0.15)

        assert len(batches) == 1
        assert len(batches[0].deltas) == 1
        assert batches[0].deltas[0].data["status"] == "COMPLETED"
        assert batches[0].dedup_count == 1

    @pytest.mark.asyncio
    async def test_no_dedup_different_keys(self):
        """Deltas to different keys are not deduplicated."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)
        await agg.collect(_delta(key="task-1", data={"status": "A"}))
        await agg.collect(_delta(key="task-2", data={"status": "B"}))
        await asyncio.sleep(0.1)

        assert len(batches) == 1
        assert len(batches[0].deltas) == 2
        assert batches[0].dedup_count == 0

    @pytest.mark.asyncio
    async def test_no_dedup_different_sections(self):
        """Deltas to same key but different sections are not deduplicated."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)
        await agg.collect(_delta(section="task_state", key="task-1"))
        await agg.collect(_delta(section="task_artifacts", key="task-1"))
        await asyncio.sleep(0.1)

        assert len(batches) == 1
        assert len(batches[0].deltas) == 2
        assert batches[0].dedup_count == 0

    @pytest.mark.asyncio
    async def test_dedup_three_writes_same_key(self):
        """Three rapid writes to same key: only final survives."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=100)
        await agg.collect(_delta(key="t1", data={"v": 1}))
        await agg.collect(_delta(key="t1", data={"v": 2}))
        await agg.collect(_delta(key="t1", data={"v": 3}))
        await asyncio.sleep(0.15)

        assert len(batches[0].deltas) == 1
        assert batches[0].deltas[0].data["v"] == 3
        assert batches[0].dedup_count == 2

    @pytest.mark.asyncio
    async def test_dedup_mixed_keys(self):
        """Mix of duplicate and unique keys."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)
        await agg.collect(_delta(key="a", data={"v": 1}))
        await agg.collect(_delta(key="b", data={"v": 2}))
        await agg.collect(_delta(key="a", data={"v": 3}))  # overwrites first
        await asyncio.sleep(0.1)

        assert len(batches[0].deltas) == 2
        assert batches[0].dedup_count == 1
        # Order: 'a' (final) and 'b' -- both present
        keys = {d.key for d in batches[0].deltas}
        assert keys == {"a", "b"}


class TestDeltaAggregatorCausalOrder:
    """11.3.3 -- DeltaAggregator causal ordering (parent before child)."""

    @pytest.mark.asyncio
    async def test_parent_before_child(self):
        """Child delta with parent_delta_id is ordered after parent."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)

        parent = _delta(delta_id="delta-parent", key="task-A", data={"status": "COMPLETED"})
        child = _delta(
            delta_id="delta-child",
            section="task_artifacts",
            key="task-A:booking",
            operation="append",
            data={"type": "booking"},
            parent_delta_id="delta-parent",
        )
        # Collect child BEFORE parent to test ordering
        await agg.collect(child)
        await agg.collect(parent)
        await asyncio.sleep(0.1)

        assert len(batches) == 1
        ordered = batches[0].deltas
        parent_idx = next(i for i, d in enumerate(ordered) if d.delta_id == "delta-parent")
        child_idx = next(i for i, d in enumerate(ordered) if d.delta_id == "delta-child")
        assert parent_idx < child_idx, "Parent must come before child"

    @pytest.mark.asyncio
    async def test_no_causal_links_preserves_order(self):
        """Without causal links, input order is preserved."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)
        d1 = _delta(delta_id="d-1", key="a")
        d2 = _delta(delta_id="d-2", key="b")
        d3 = _delta(delta_id="d-3", key="c")
        await agg.collect(d1)
        await agg.collect(d2)
        await agg.collect(d3)
        await asyncio.sleep(0.1)

        ordered_ids = [d.delta_id for d in batches[0].deltas]
        assert ordered_ids == ["d-1", "d-2", "d-3"]

    @pytest.mark.asyncio
    async def test_chain_of_three(self):
        """Three-level chain: grandparent -> parent -> child."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)

        gp = _delta(delta_id="gp", key="task-gp")
        p = _delta(delta_id="p", key="task-p", parent_delta_id="gp")
        c = _delta(delta_id="c", section="task_artifacts", key="task-c", parent_delta_id="p")
        # Reverse order
        await agg.collect(c)
        await agg.collect(p)
        await agg.collect(gp)
        await asyncio.sleep(0.1)

        ordered_ids = [d.delta_id for d in batches[0].deltas]
        assert ordered_ids.index("gp") < ordered_ids.index("p")
        assert ordered_ids.index("p") < ordered_ids.index("c")

    @pytest.mark.asyncio
    async def test_orphan_parent_outside_batch(self):
        """Child with parent not in batch is treated as root."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)

        orphan = _delta(delta_id="orphan", key="x", parent_delta_id="not-in-batch")
        regular = _delta(delta_id="regular", key="y")
        await agg.collect(orphan)
        await agg.collect(regular)
        await asyncio.sleep(0.1)

        # Both should appear (no crash)
        assert len(batches[0].deltas) == 2

    @pytest.mark.asyncio
    async def test_single_delta_no_ordering_needed(self):
        """Single delta passes through without ordering."""
        batches: list[DeltaBatch] = []

        async def on_flush(batch: DeltaBatch) -> None:
            batches.append(batch)

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)
        await agg.collect(_delta(delta_id="solo", key="x"))
        await asyncio.sleep(0.1)

        assert len(batches[0].deltas) == 1
        assert batches[0].deltas[0].delta_id == "solo"


class TestDeltaAggregatorStats:
    """11.3.1 -- DeltaAggregator observability stats."""

    @pytest.mark.asyncio
    async def test_stats_initial(self):
        """Stats are zeroed on creation."""

        async def on_flush(batch: DeltaBatch) -> None:
            pass

        agg = DeltaAggregator(flush_fn=on_flush)
        s = agg.stats
        assert s["batch_count"] == 0
        assert s["total_deltas"] == 0
        assert s["total_deduped"] == 0
        assert s["pending"] == 0

    @pytest.mark.asyncio
    async def test_stats_after_flush(self):
        """Stats reflect collected and flushed deltas."""

        async def on_flush(batch: DeltaBatch) -> None:
            pass

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=50)
        await agg.collect(_delta(key="a"))
        await agg.collect(_delta(key="a", data={"v": 2}))  # will be deduped
        await agg.collect(_delta(key="b"))
        await asyncio.sleep(0.1)

        s = agg.stats
        assert s["batch_count"] == 1
        assert s["total_deltas"] == 3
        assert s["total_deduped"] == 1
        assert s["pending"] == 0

    @pytest.mark.asyncio
    async def test_batch_count_increments(self):
        """batch_count increments with each flush."""

        async def on_flush(batch: DeltaBatch) -> None:
            pass

        agg = DeltaAggregator(flush_fn=on_flush, batch_window_ms=5000)
        await agg.collect(_delta(key="a"))
        await agg.flush()
        assert agg.batch_count == 1

        await agg.collect(_delta(key="b"))
        await agg.flush()
        assert agg.batch_count == 2


class TestDeltaBatchDataclass:
    """11.3 -- DeltaBatch dataclass structure."""

    def test_batch_fields(self):
        """DeltaBatch has all expected fields."""
        batch = DeltaBatch(
            deltas=[_delta()],
            batch_id="batch-1",
            collected_at_ns=12345,
            dedup_count=2,
        )
        assert batch.batch_id == "batch-1"
        assert batch.collected_at_ns == 12345
        assert batch.dedup_count == 2
        assert len(batch.deltas) == 1

    def test_batch_default_dedup_count(self):
        """dedup_count defaults to 0."""
        batch = DeltaBatch(deltas=[], batch_id="b-1", collected_at_ns=0)
        assert batch.dedup_count == 0


# =========================================================================
# Package exports
# =========================================================================


class TestDeltaPackageExports:
    """Package-level export validation for poc.k1_poc.delta."""

    def test_package_importable(self):
        """delta package is importable."""
        import poc.k1_poc.delta as pkg

        assert hasattr(pkg, "__all__")

    def test_export_count(self):
        """Package exports at least the original 13 symbols."""
        import poc.k1_poc.delta as pkg

        assert len(pkg.__all__) >= 13

    def test_all_exports_accessible(self):
        """Every name in __all__ is accessible on the package."""
        import poc.k1_poc.delta as pkg

        for name in pkg.__all__:
            assert hasattr(pkg, name), f"{name} in __all__ but not accessible"

    @pytest.mark.parametrize(
        "symbol",
        [
            "SessionDelta",
            "VALID_DELTA_SECTIONS",
            "VALID_DELTA_OPERATIONS",
            "ARTIFACT_CREATED",
            "TASK_STATE_CHANGED",
            "STATE_UPDATED",
            "ALL_DELTA_TOPICS",
            "emit_artifact",
            "emit_task_state_change",
            "VALID_TASK_STATUSES",
            "DeltaAggregator",
            "DeltaBatch",
            "DEFAULT_BATCH_WINDOW_MS",
        ],
    )
    def test_export_accessible(self, symbol: str):
        """Each expected export is individually accessible."""
        import poc.k1_poc.delta as pkg

        assert hasattr(pkg, symbol), f"{symbol} not accessible on package"

    def test_submodules_importable(self):
        """All 4 submodules import without error."""
        expected = [
            "poc.k1_poc.delta",
            "poc.k1_poc.delta.session_delta",
            "poc.k1_poc.delta.topics",
            "poc.k1_poc.delta.emitters",
            "poc.k1_poc.delta.aggregator",
        ]
        for mod_path in expected:
            mod = importlib.import_module(mod_path)
            assert mod is not None

    def test_no_circular_imports(self):
        """Package reload succeeds (no circular dependency)."""
        import poc.k1_poc.delta as pkg

        importlib.reload(pkg)
        assert len(pkg.__all__) >= 13
