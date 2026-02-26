"""
Tests for Epics 11.7, 11.8, 11.9 -- Overflow Protection, Package Structure,
E2E Integration.

Epic 11.7: Overflow Protection & Eviction
    V2 Design Ref: Section 5 (HOT Tier Budget, Pruning Lifecycle)
    SectionOverflowHandler eviction by section strategy.

Epic 11.8: Delta Module Package Structure
    V2 Design Ref: Section 5 (delta pipeline module organization)
    9 submodules, 24 exports, module importability.

Epic 11.9: End-to-End Integration Tests
    V2 Design Ref: Section 5 (DeltaAggregator Write Pipeline, full flow)
    Emitter -> Aggregator -> Applicator pipeline, dedup, MutationGuard,
    single writer serialization.

Source of truth: implemented code + concierge_poc_design_v2.md
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

from poc.k1_poc.delta.aggregator import DeltaAggregator, DeltaBatch
from poc.k1_poc.delta.applicator import ApplyResult, DeltaApplicator
from poc.k1_poc.delta.emitters import VALID_TASK_STATUSES, emit_artifact, emit_task_state_change
from poc.k1_poc.delta.overflow import (
    HISTORY_WINDOW_SIZE,
    HOT_BUDGET_TOTAL,
    SECTION_BUDGETS,
    TERMINAL_TASK_STATUSES,
    SectionOverflowHandler,
)
from poc.k1_poc.delta.session_delta import SessionDelta

# =========================================================================
# Helpers
# =========================================================================


def _delta(
    section: str = "task_state",
    key: str = "task-1",
    operation: str = "set",
    data: dict | None = None,
    delta_id: str | None = None,
    timestamp_ns: int = 0,
) -> SessionDelta:
    kwargs: dict = {
        "section": section,
        "key": key,
        "operation": operation,
        "data": data if data is not None else {},
        "timestamp_ns": timestamp_ns,
    }
    if delta_id is not None:
        kwargs["delta_id"] = delta_id
    return SessionDelta(**kwargs)


def _batch(deltas: list[SessionDelta], batch_id: str = "batch-test") -> DeltaBatch:
    return DeltaBatch(
        deltas=deltas,
        batch_id=batch_id,
        collected_at_ns=0,
    )


class FakeApproval:
    """Duck-typed Approval for MutationGuard preflight tests."""

    def __init__(self, approved: bool, reason: str = "") -> None:
        self.approved = approved
        self.reason = reason


# =========================================================================
# EPIC 11.7 -- SectionOverflowHandler
# =========================================================================


class TestSectionOverflowHandlerInit:
    """Constructor and attribute tests for SectionOverflowHandler."""

    def test_default_budgets(self) -> None:
        handler = SectionOverflowHandler()
        assert handler.get_budget("task_state") == 4096
        assert handler.get_budget("task_artifacts") == 4096
        assert handler.get_budget("history_active") == 8192

    def test_custom_budgets(self) -> None:
        handler = SectionOverflowHandler(section_budgets={"task_state": 2048})
        assert handler.get_budget("task_state") == 2048
        assert handler.get_budget("task_artifacts") is None

    def test_custom_history_window(self) -> None:
        handler = SectionOverflowHandler(history_window=10)
        data = {f"turn-{i:03d}": {"text": f"turn {i}"} for i in range(20)}
        remaining, evicted = handler.evict_oldest("history_active", data, 0)
        assert len(remaining) == 10

    def test_initial_log_empty(self) -> None:
        handler = SectionOverflowHandler()
        assert handler.eviction_log == []
        assert handler.total_evicted == 0

    def test_unknown_section_budget_returns_none(self) -> None:
        handler = SectionOverflowHandler()
        assert handler.get_budget("nonexistent") is None


class TestSectionOverflowHandlerConstants:
    """Verify module-level constants match V2 Section 5."""

    def test_section_budgets_has_10_sections(self) -> None:
        assert len(SECTION_BUDGETS) == 10

    def test_section_budgets_known_sections(self) -> None:
        expected = {
            "control",
            "beliefs_active",
            "scoreboard",
            "history_active",
            "clarifications",
            "affective_now",
            "narrative_active",
            "meta",
            "task_state",
            "task_artifacts",
        }
        assert set(SECTION_BUDGETS.keys()) == expected

    def test_hot_budget_total(self) -> None:
        computed = sum(SECTION_BUDGETS.values())
        assert computed == HOT_BUDGET_TOTAL

    def test_history_window_default_20(self) -> None:
        assert HISTORY_WINDOW_SIZE == 20

    def test_terminal_statuses(self) -> None:
        assert TERMINAL_TASK_STATUSES == frozenset({"COMPLETED", "FAILED", "CANCELLED"})

    def test_terminal_statuses_subset_of_valid(self) -> None:
        assert TERMINAL_TASK_STATUSES.issubset(VALID_TASK_STATUSES)


class TestEvictArtifacts:
    """task_artifacts eviction: oldest by timestamp_ns."""

    def test_evicts_oldest_first(self) -> None:
        handler = SectionOverflowHandler()
        data = {
            "art-1": {"type": "search", "timestamp_ns": 100},
            "art-2": {"type": "booking", "timestamp_ns": 300},
            "art-3": {"type": "receipt", "timestamp_ns": 200},
        }
        remaining, evicted = handler.evict_oldest("task_artifacts", data, 10)
        assert evicted[0] == "art-1"
        assert "art-1" not in remaining

    def test_evicts_enough_to_meet_needed_bytes(self) -> None:
        handler = SectionOverflowHandler()
        small = {"type": "x", "timestamp_ns": 0}
        data = {f"a-{i}": {**small, "timestamp_ns": i * 100} for i in range(5)}
        # Request a lot so we evict multiple
        remaining, evicted = handler.evict_oldest("task_artifacts", data, 99999)
        assert len(evicted) == 5
        assert len(remaining) == 0

    def test_evicts_minimum_needed(self) -> None:
        handler = SectionOverflowHandler()
        data = {
            "a": {"type": "x", "timestamp_ns": 1},
            "b": {"type": "y", "timestamp_ns": 2},
            "c": {"type": "z", "timestamp_ns": 3},
        }
        # Small needed_bytes -> only oldest is evicted
        remaining, evicted = handler.evict_oldest("task_artifacts", data, 1)
        assert evicted == ["a"]
        assert set(remaining.keys()) == {"b", "c"}

    def test_empty_data_no_eviction(self) -> None:
        handler = SectionOverflowHandler()
        remaining, evicted = handler.evict_oldest("task_artifacts", {}, 100)
        assert remaining == {}
        assert evicted == []

    def test_entries_without_timestamp_treated_as_zero(self) -> None:
        handler = SectionOverflowHandler()
        data = {
            "no-ts": {"type": "plain"},
            "has-ts": {"type": "x", "timestamp_ns": 999},
        }
        remaining, evicted = handler.evict_oldest("task_artifacts", data, 1)
        assert evicted[0] == "no-ts"

    def test_non_dict_values_evicted_correctly(self) -> None:
        handler = SectionOverflowHandler()
        data = {
            "scalar": "just-a-string",
            "dict-val": {"type": "x", "timestamp_ns": 999},
        }
        remaining, evicted = handler.evict_oldest("task_artifacts", data, 1)
        assert "scalar" in evicted  # timestamp 0 sorts first


class TestEvictTerminalTasks:
    """task_state eviction: clear terminal tasks (COMPLETED/FAILED/CANCELLED)."""

    def test_evicts_completed(self) -> None:
        handler = SectionOverflowHandler()
        data = {
            "task-1": {"status": "COMPLETED", "result": "ok"},
            "task-2": {"status": "IN_PROGRESS"},
        }
        remaining, evicted = handler.evict_oldest("task_state", data, 0)
        assert "task-1" in evicted
        assert "task-2" in remaining
        assert "task-1" not in remaining

    def test_evicts_failed(self) -> None:
        handler = SectionOverflowHandler()
        data = {
            "task-1": {"status": "FAILED", "error": "timeout"},
        }
        remaining, evicted = handler.evict_oldest("task_state", data, 0)
        assert evicted == ["task-1"]
        assert remaining == {}

    def test_evicts_cancelled(self) -> None:
        handler = SectionOverflowHandler()
        data = {"task-1": {"status": "CANCELLED"}}
        remaining, evicted = handler.evict_oldest("task_state", data, 0)
        assert evicted == ["task-1"]

    def test_keeps_active_tasks(self) -> None:
        handler = SectionOverflowHandler()
        data = {
            "t-1": {"status": "DISPATCHED"},
            "t-2": {"status": "IN_PROGRESS"},
            "t-3": {"status": "SUSPENDED"},
        }
        remaining, evicted = handler.evict_oldest("task_state", data, 0)
        assert evicted == []
        assert len(remaining) == 3

    def test_mixed_terminal_and_active(self) -> None:
        handler = SectionOverflowHandler()
        data = {
            "t-1": {"status": "COMPLETED"},
            "t-2": {"status": "IN_PROGRESS"},
            "t-3": {"status": "FAILED"},
            "t-4": {"status": "DISPATCHED"},
            "t-5": {"status": "CANCELLED"},
        }
        remaining, evicted = handler.evict_oldest("task_state", data, 0)
        assert set(evicted) == {"t-1", "t-3", "t-5"}
        assert set(remaining.keys()) == {"t-2", "t-4"}

    def test_no_status_field_kept(self) -> None:
        handler = SectionOverflowHandler()
        data = {"t-1": {"description": "no status"}}
        remaining, evicted = handler.evict_oldest("task_state", data, 0)
        assert evicted == []
        assert "t-1" in remaining

    def test_non_dict_value_kept(self) -> None:
        handler = SectionOverflowHandler()
        data = {"t-1": "just-a-string"}
        remaining, evicted = handler.evict_oldest("task_state", data, 0)
        assert evicted == []
        assert "t-1" in remaining

    def test_empty_data_no_eviction(self) -> None:
        handler = SectionOverflowHandler()
        remaining, evicted = handler.evict_oldest("task_state", {}, 0)
        assert remaining == {}
        assert evicted == []


class TestEvictOldestTurns:
    """history_active eviction: sliding window, keep last N turns."""

    def test_keeps_last_20_when_over(self) -> None:
        handler = SectionOverflowHandler()
        data = {f"turn-{i:03d}": {"text": f"turn {i}"} for i in range(30)}
        remaining, evicted = handler.evict_oldest("history_active", data, 0)
        assert len(remaining) == 20
        assert len(evicted) == 10

    def test_evicted_are_oldest(self) -> None:
        handler = SectionOverflowHandler()
        data = {f"turn-{i:03d}": {"text": f"t{i}"} for i in range(25)}
        remaining, evicted = handler.evict_oldest("history_active", data, 0)
        # Evicted should be turn-000 through turn-004
        for i in range(5):
            assert f"turn-{i:03d}" in evicted
        # Remaining should be turn-005 through turn-024
        for i in range(5, 25):
            assert f"turn-{i:03d}" in remaining

    def test_no_eviction_at_limit(self) -> None:
        handler = SectionOverflowHandler()
        data = {f"turn-{i:03d}": {"text": f"t{i}"} for i in range(20)}
        remaining, evicted = handler.evict_oldest("history_active", data, 0)
        assert len(remaining) == 20
        assert evicted == []

    def test_no_eviction_under_limit(self) -> None:
        handler = SectionOverflowHandler()
        data = {f"turn-{i:03d}": {"text": f"t{i}"} for i in range(5)}
        remaining, evicted = handler.evict_oldest("history_active", data, 0)
        assert len(remaining) == 5
        assert evicted == []

    def test_empty_data(self) -> None:
        handler = SectionOverflowHandler()
        remaining, evicted = handler.evict_oldest("history_active", {}, 0)
        assert remaining == {}
        assert evicted == []

    def test_custom_window_size(self) -> None:
        handler = SectionOverflowHandler(history_window=5)
        data = {f"turn-{i:03d}": {"text": f"t{i}"} for i in range(10)}
        remaining, evicted = handler.evict_oldest("history_active", data, 0)
        assert len(remaining) == 5
        assert len(evicted) == 5

    def test_window_preserves_newest(self) -> None:
        handler = SectionOverflowHandler(history_window=3)
        data = {f"turn-{i:03d}": {"text": f"t{i}"} for i in range(6)}
        remaining, evicted = handler.evict_oldest("history_active", data, 0)
        assert set(remaining.keys()) == {"turn-003", "turn-004", "turn-005"}

    def test_single_entry_kept(self) -> None:
        handler = SectionOverflowHandler()
        data = {"turn-000": {"text": "only"}}
        remaining, evicted = handler.evict_oldest("history_active", data, 0)
        assert len(remaining) == 1
        assert evicted == []


class TestUnknownSectionPassthrough:
    """Unknown sections pass through unchanged with no eviction."""

    def test_unknown_section_returns_data_unchanged(self) -> None:
        handler = SectionOverflowHandler()
        data = {"key": "value", "other": "data"}
        remaining, evicted = handler.evict_oldest("beliefs_active", data, 100)
        assert remaining == data
        assert evicted == []

    def test_control_section_passthrough(self) -> None:
        handler = SectionOverflowHandler()
        data = {"fsm_state": "PLANNING"}
        remaining, evicted = handler.evict_oldest("control", data, 100)
        assert remaining == data
        assert evicted == []

    def test_meta_section_passthrough(self) -> None:
        handler = SectionOverflowHandler()
        data = {"version": 42}
        remaining, evicted = handler.evict_oldest("meta", data, 100)
        assert remaining == data
        assert evicted == []

    def test_completely_unknown_section_passthrough(self) -> None:
        handler = SectionOverflowHandler()
        data = {"x": 1}
        remaining, evicted = handler.evict_oldest("not_a_real_section", data, 100)
        assert remaining == data
        assert evicted == []


class TestEvictionLog:
    """eviction_log observability for SectionOverflowHandler."""

    def test_log_populated_after_artifact_eviction(self) -> None:
        handler = SectionOverflowHandler()
        data = {"art-1": {"type": "x", "timestamp_ns": 1}}
        handler.evict_oldest("task_artifacts", data, 1)
        log = handler.eviction_log
        assert len(log) == 1
        assert log[0]["section"] == "task_artifacts"
        assert log[0]["evicted_count"] == 1
        assert log[0]["evicted_keys"] == ["art-1"]
        assert log[0]["freed_bytes"] > 0

    def test_log_populated_after_task_eviction(self) -> None:
        handler = SectionOverflowHandler()
        data = {"t-1": {"status": "COMPLETED"}}
        handler.evict_oldest("task_state", data, 0)
        log = handler.eviction_log
        assert len(log) == 1
        assert log[0]["section"] == "task_state"

    def test_log_populated_after_history_eviction(self) -> None:
        handler = SectionOverflowHandler()
        data = {f"turn-{i:03d}": {"text": f"t{i}"} for i in range(25)}
        handler.evict_oldest("history_active", data, 0)
        log = handler.eviction_log
        assert len(log) == 1
        assert log[0]["section"] == "history_active"
        assert log[0]["evicted_count"] == 5

    def test_total_evicted_accumulates(self) -> None:
        handler = SectionOverflowHandler()
        # Evict 1 artifact
        handler.evict_oldest("task_artifacts", {"a": {"timestamp_ns": 1}}, 1)
        # Evict 2 terminal tasks
        handler.evict_oldest(
            "task_state",
            {"t1": {"status": "COMPLETED"}, "t2": {"status": "FAILED"}},
            0,
        )
        assert handler.total_evicted == 3
        assert len(handler.eviction_log) == 2

    def test_no_log_for_no_eviction(self) -> None:
        handler = SectionOverflowHandler()
        handler.evict_oldest("task_state", {"t": {"status": "IN_PROGRESS"}}, 0)
        assert handler.eviction_log == []
        assert handler.total_evicted == 0

    def test_log_is_readonly_copy(self) -> None:
        handler = SectionOverflowHandler()
        handler.evict_oldest("task_artifacts", {"a": {"timestamp_ns": 1}}, 1)
        log = handler.eviction_log
        log.clear()
        assert len(handler.eviction_log) == 1  # original unaffected

    def test_log_keys_present(self) -> None:
        handler = SectionOverflowHandler()
        handler.evict_oldest("task_artifacts", {"a": {"timestamp_ns": 1}}, 1)
        entry = handler.eviction_log[0]
        assert set(entry.keys()) == {"section", "evicted_count", "evicted_keys", "freed_bytes"}


class TestOverflowSlots:
    """SectionOverflowHandler uses __slots__ for performance."""

    def test_has_slots(self) -> None:
        assert hasattr(SectionOverflowHandler, "__slots__")

    def test_slot_fields(self) -> None:
        expected = {"_budgets", "_eviction_log", "_total_evicted", "_history_window"}
        assert set(SectionOverflowHandler.__slots__) == expected

    def test_no_dict_attribute(self) -> None:
        handler = SectionOverflowHandler()
        assert not hasattr(handler, "__dict__")


class TestOverflowIntegrationWithApplicator:
    """SectionOverflowHandler as evict_fn callback for DeltaApplicator."""

    @pytest.mark.asyncio
    async def test_handler_used_as_evict_fn(self) -> None:
        handler = SectionOverflowHandler()
        section_data = {
            "old-artifact": {"type": "x", "timestamp_ns": 1},
            "new-artifact": {"type": "y", "timestamp_ns": 999},
        }
        reject_count = 0

        def preflight(section, op, size):
            nonlocal reject_count
            reject_count += 1
            if reject_count <= 1:
                return FakeApproval(False, "capacity exceeded")
            return FakeApproval(True)

        writes = []

        async def write_fn(section, key, op, data):
            writes.append((section, key))

        async def evict_fn(section, needed_bytes):
            remaining, evicted_keys = handler.evict_oldest(
                section, dict(section_data), needed_bytes
            )
            return len(evicted_keys)

        applicator = DeltaApplicator(
            preflight_fn=preflight,
            write_fn=write_fn,
            evict_fn=evict_fn,
        )
        d = _delta(section="task_artifacts", key="new", data={"payload": "x"})
        batch = _batch([d])
        result = await applicator.apply(batch)
        assert result.applied == 1
        assert result.evicted >= 1


# =========================================================================
# EPIC 11.8 -- Delta Module Package Structure
# =========================================================================


class TestDeltaPackageImportability:
    """All delta submodules are importable without errors."""

    EXPECTED_MODULES = [
        "poc.k1_poc.delta.session_delta",
        "poc.k1_poc.delta.topics",
        "poc.k1_poc.delta.emitters",
        "poc.k1_poc.delta.aggregator",
        "poc.k1_poc.delta.applicator",
        "poc.k1_poc.delta.writer_registry",
        "poc.k1_poc.delta.snapshot_reader",
        "poc.k1_poc.delta.overflow",
    ]

    @pytest.mark.parametrize("module_name", EXPECTED_MODULES)
    def test_module_importable(self, module_name: str) -> None:
        mod = importlib.import_module(module_name)
        assert mod is not None

    def test_top_level_package_importable(self) -> None:
        mod = importlib.import_module("poc.k1_poc.delta")
        assert mod is not None


class TestDeltaPackageExports:
    """Verify __init__.py exports and __all__ completeness."""

    def test_export_count_is_24(self) -> None:
        import poc.k1_poc.delta as delta

        assert len(delta.__all__) == 24

    def test_all_exports_accessible(self) -> None:
        import poc.k1_poc.delta as delta

        for name in delta.__all__:
            assert hasattr(delta, name), f"{name} in __all__ but not accessible"

    def test_session_delta_exported(self) -> None:
        from poc.k1_poc.delta import SessionDelta

        assert SessionDelta is not None

    def test_topics_exported(self) -> None:
        from poc.k1_poc.delta import ALL_DELTA_TOPICS

        assert ALL_DELTA_TOPICS is not None

    def test_emitters_exported(self) -> None:
        from poc.k1_poc.delta import VALID_TASK_STATUSES

        assert VALID_TASK_STATUSES is not None

    def test_aggregator_exported(self) -> None:
        from poc.k1_poc.delta import DEFAULT_BATCH_WINDOW_MS

        assert DEFAULT_BATCH_WINDOW_MS == 500

    def test_applicator_exported(self) -> None:
        from poc.k1_poc.delta import ApplyResult

        assert ApplyResult is not None

    def test_writer_registry_exported(self) -> None:
        from poc.k1_poc.delta import WriterRole

        assert WriterRole is not None

    def test_snapshot_reader_exported(self) -> None:
        from poc.k1_poc.delta import SnapshotReader

        assert SnapshotReader is not None

    def test_overflow_handler_exported(self) -> None:
        from poc.k1_poc.delta import SectionOverflowHandler

        assert SectionOverflowHandler is not None

    def test_all_exports_match_expected(self) -> None:
        import poc.k1_poc.delta as delta

        expected = {
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
            "DeltaApplicator",
            "ApplyResult",
            "WriterRole",
            "SingleWriterViolation",
            "SECTION_WRITERS",
            "ALL_WRITER_SECTIONS",
            "validate_writer",
            "enforce_writer",
            "SectionSnapshot",
            "SnapshotReader",
            "SectionOverflowHandler",
        }
        assert set(delta.__all__) == expected


class TestDeltaPackageStructure:
    """Verify structural properties of the delta package."""

    def test_package_has_init(self) -> None:
        import poc.k1_poc.delta as delta

        assert hasattr(delta, "__all__")

    def test_submodule_count(self) -> None:
        """8 submodules: session_delta, topics, emitters, aggregator,
        applicator, writer_registry, snapshot_reader, overflow."""
        modules = [
            "session_delta",
            "topics",
            "emitters",
            "aggregator",
            "applicator",
            "writer_registry",
            "snapshot_reader",
            "overflow",
        ]
        for m in modules:
            mod = importlib.import_module(f"poc.k1_poc.delta.{m}")
            assert mod is not None

    def test_no_circular_imports(self) -> None:
        """All submodules can be imported without circular dependency."""
        import importlib

        importlib.invalidate_caches()
        # Re-import fresh
        mod = importlib.import_module("poc.k1_poc.delta")
        assert len(mod.__all__) >= 24


# =========================================================================
# EPIC 11.9 -- End-to-End Integration Tests
# =========================================================================


class TestE2EArtifactPipeline:
    """E2E: Back emits artifact -> aggregator batches -> applicator writes."""

    @pytest.mark.asyncio
    async def test_full_artifact_pipeline(self) -> None:
        """emit_artifact -> DeltaAggregator.collect -> flush -> DeltaApplicator.apply -> write."""
        writes: list[tuple[str, str, str, dict]] = []

        async def write_fn(section, key, op, data):
            writes.append((section, key, op, data))

        async def notify_fn(batch_id, count):
            pass

        applicator = DeltaApplicator(write_fn=write_fn, notify_fn=notify_fn)

        aggregator = DeltaAggregator(
            flush_fn=lambda batch: applicator.apply(batch),
            batch_window_ms=1,  # fast window for tests
        )

        # Back emits artifact via bus
        collected: list[SessionDelta] = []

        async def publish_fn(topic, delta):
            collected.append(delta)
            await aggregator.collect(delta)

        await emit_artifact(
            task_id="task-42",
            artifact_type="search_results",
            artifact_data={"query": "flights", "results": [1, 2, 3]},
            publish_fn=publish_fn,
        )

        # Wait for batch to flush
        await asyncio.sleep(0.05)

        assert len(collected) == 1
        assert len(writes) == 1
        section, key, op, data = writes[0]
        assert section == "task_artifacts"
        assert "task-42" in key
        assert op == "append"
        assert data["type"] == "search_results"

    @pytest.mark.asyncio
    async def test_multiple_artifacts_batched(self) -> None:
        """Two artifacts within batch window are batched together."""
        writes: list[tuple] = []

        async def write_fn(section, key, op, data):
            writes.append((section, key))

        applicator = DeltaApplicator(write_fn=write_fn)
        aggregator = DeltaAggregator(
            flush_fn=lambda batch: applicator.apply(batch),
            batch_window_ms=50,
        )

        async def publish_fn(topic, delta):
            await aggregator.collect(delta)

        await emit_artifact("task-1", "booking", {"ref": "ABC"}, publish_fn)
        await emit_artifact("task-2", "receipt", {"id": "R-1"}, publish_fn)

        await asyncio.sleep(0.15)

        assert len(writes) == 2

    @pytest.mark.asyncio
    async def test_task_state_pipeline(self) -> None:
        """emit_task_state_change flows through pipeline."""
        writes: list[tuple] = []

        async def write_fn(section, key, op, data):
            writes.append((section, key, data))

        applicator = DeltaApplicator(write_fn=write_fn)
        aggregator = DeltaAggregator(
            flush_fn=lambda batch: applicator.apply(batch),
            batch_window_ms=1,
        )

        async def publish_fn(topic, delta):
            await aggregator.collect(delta)

        await emit_task_state_change(
            task_id="task-99",
            new_status="COMPLETED",
            metadata={"tool_calls": 3},
            publish_fn=publish_fn,
        )

        await asyncio.sleep(0.05)

        assert len(writes) == 1
        section, key, data = writes[0]
        assert section == "task_state"
        assert key == "task-99"
        assert data["status"] == "COMPLETED"
        assert data["tool_calls"] == 3


class TestE2EDedupWithinBatchWindow:
    """E2E: deduplication within a single batch window."""

    @pytest.mark.asyncio
    async def test_dedup_same_section_key(self) -> None:
        """Two deltas for same section+key: last-write-wins."""
        writes: list[tuple] = []

        async def write_fn(section, key, op, data):
            writes.append((section, key, data))

        applicator = DeltaApplicator(write_fn=write_fn)
        aggregator = DeltaAggregator(
            flush_fn=lambda batch: applicator.apply(batch),
            batch_window_ms=50,
        )

        d1 = _delta(
            section="task_state", key="task-1", operation="set", data={"status": "IN_PROGRESS"}
        )
        d2 = _delta(
            section="task_state", key="task-1", operation="set", data={"status": "COMPLETED"}
        )

        await aggregator.collect(d1)
        await aggregator.collect(d2)
        await asyncio.sleep(0.15)

        # Only last write should be applied
        assert len(writes) == 1
        assert writes[0][2]["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_dedup_different_keys_both_kept(self) -> None:
        """Two deltas for different keys: both kept."""
        writes: list[tuple] = []

        async def write_fn(section, key, op, data):
            writes.append((section, key))

        applicator = DeltaApplicator(write_fn=write_fn)
        aggregator = DeltaAggregator(
            flush_fn=lambda batch: applicator.apply(batch),
            batch_window_ms=50,
        )

        d1 = _delta(section="task_state", key="task-1", data={"status": "A"})
        d2 = _delta(section="task_state", key="task-2", data={"status": "B"})

        await aggregator.collect(d1)
        await aggregator.collect(d2)
        await asyncio.sleep(0.15)

        assert len(writes) == 2

    @pytest.mark.asyncio
    async def test_dedup_count_tracked_in_batch(self) -> None:
        """Aggregator tracks dedup count accurately."""
        batches: list[DeltaBatch] = []

        async def capture_fn(batch):
            batches.append(batch)

        aggregator = DeltaAggregator(
            flush_fn=capture_fn,
            batch_window_ms=50,
        )

        d1 = _delta(section="task_state", key="task-1", data={"v": 1})
        d2 = _delta(section="task_state", key="task-1", data={"v": 2})
        d3 = _delta(section="task_state", key="task-1", data={"v": 3})

        await aggregator.collect(d1)
        await aggregator.collect(d2)
        await aggregator.collect(d3)
        await asyncio.sleep(0.15)

        assert len(batches) == 1
        assert batches[0].dedup_count == 2  # 3 collected, 1 kept
        assert len(batches[0].deltas) == 1


class TestE2EMutationGuardReject:
    """E2E: MutationGuard rejects oversized write through pipeline."""

    @pytest.mark.asyncio
    async def test_preflight_rejects_no_evict(self) -> None:
        """Preflight always rejects, no evict_fn -> delta rejected."""
        writes: list[tuple] = []

        def preflight(section, op, size):
            return FakeApproval(False, "section full")

        async def write_fn(section, key, op, data):
            writes.append((section, key))

        applicator = DeltaApplicator(
            preflight_fn=preflight,
            write_fn=write_fn,
        )
        aggregator = DeltaAggregator(
            flush_fn=lambda batch: applicator.apply(batch),
            batch_window_ms=1,
        )

        d = _delta(section="task_artifacts", key="big", data={"huge": "x" * 10000})
        await aggregator.collect(d)
        await asyncio.sleep(0.05)

        assert len(writes) == 0

    @pytest.mark.asyncio
    async def test_preflight_rejects_then_evict_rescues(self) -> None:
        """Preflight rejects first, eviction frees space, retry succeeds."""
        call_count = 0
        writes: list[tuple] = []

        def preflight(section, op, size):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return FakeApproval(False, "capacity")
            return FakeApproval(True)

        async def write_fn(section, key, op, data):
            writes.append((section, key))

        async def evict_fn(section, needed):
            return 2  # evicted 2 entries

        applicator = DeltaApplicator(
            preflight_fn=preflight,
            write_fn=write_fn,
            evict_fn=evict_fn,
        )
        aggregator = DeltaAggregator(
            flush_fn=lambda batch: applicator.apply(batch),
            batch_window_ms=1,
        )

        d = _delta(section="task_artifacts", key="art-1", data={"type": "x"})
        await aggregator.collect(d)
        await asyncio.sleep(0.05)

        assert len(writes) == 1
        assert call_count == 2  # preflight called twice (reject + retry)

    @pytest.mark.asyncio
    async def test_preflight_rejects_after_evict_still_rejected(self) -> None:
        """Preflight rejects, eviction runs, retry still fails -> final rejection."""
        writes: list[tuple] = []
        results: list[ApplyResult] = []

        def preflight(section, op, size):
            return FakeApproval(False, "always full")

        async def write_fn(section, key, op, data):
            writes.append((section, key))

        async def evict_fn(section, needed):
            return 1

        async def capture_apply(batch):
            applicator = DeltaApplicator(
                preflight_fn=preflight,
                write_fn=write_fn,
                evict_fn=evict_fn,
            )
            r = await applicator.apply(batch)
            results.append(r)

        aggregator = DeltaAggregator(
            flush_fn=capture_apply,
            batch_window_ms=1,
        )

        d = _delta(section="task_state", key="t-1", data={"status": "X"})
        await aggregator.collect(d)
        await asyncio.sleep(0.05)

        assert len(writes) == 0
        assert len(results) == 1
        assert results[0].rejected == 1
        assert len(results[0].rejections) == 1

    @pytest.mark.asyncio
    async def test_mixed_approved_and_rejected(self) -> None:
        """Batch with 3 deltas: 2 approved, 1 rejected."""
        call_count = 0
        writes: list[tuple] = []

        def preflight(section, op, size):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return FakeApproval(False, "too big")
            return FakeApproval(True)

        async def write_fn(section, key, op, data):
            writes.append((section, key))

        applicator = DeltaApplicator(
            preflight_fn=preflight,
            write_fn=write_fn,
        )

        d1 = _delta(section="task_state", key="t-1", data={"status": "A"})
        d2 = _delta(section="task_artifacts", key="a-1", data={"type": "x"})
        d3 = _delta(section="control", key="c-1", data={"state": "PLANNING"})
        batch = _batch([d1, d2, d3])
        result = await applicator.apply(batch)

        assert result.applied == 2
        assert result.rejected == 1


class TestE2ESingleWriterSerialization:
    """E2E: Two batches are serialized (not concurrent)."""

    @pytest.mark.asyncio
    async def test_sequential_batches(self) -> None:
        """Two manual flushes produce two sequential batches."""
        batch_ids: list[str] = []

        async def write_fn(section, key, op, data):
            pass

        async def notify_fn(batch_id, count):
            batch_ids.append(batch_id)

        applicator = DeltaApplicator(write_fn=write_fn, notify_fn=notify_fn)
        aggregator = DeltaAggregator(
            flush_fn=lambda batch: applicator.apply(batch),
            batch_window_ms=10000,  # large window -- we flush manually
        )

        d1 = _delta(section="task_state", key="t-1", data={"status": "A"})
        d2 = _delta(section="task_state", key="t-2", data={"status": "B"})

        await aggregator.collect(d1)
        await aggregator.flush()

        await aggregator.collect(d2)
        await aggregator.flush()

        assert len(batch_ids) == 2
        assert batch_ids[0] != batch_ids[1]

    @pytest.mark.asyncio
    async def test_flush_empty_no_batch(self) -> None:
        """Flushing with no pending deltas produces no batch."""
        batch_ids: list[str] = []

        async def notify_fn(batch_id, count):
            batch_ids.append(batch_id)

        applicator = DeltaApplicator(notify_fn=notify_fn)
        aggregator = DeltaAggregator(
            flush_fn=lambda batch: applicator.apply(batch),
            batch_window_ms=10000,
        )

        result = await aggregator.flush()
        assert result is None
        assert len(batch_ids) == 0

    @pytest.mark.asyncio
    async def test_batch_ids_increment(self) -> None:
        """Each batch gets an incrementing batch ID."""
        batches: list[DeltaBatch] = []

        async def capture_fn(batch):
            batches.append(batch)

        aggregator = DeltaAggregator(
            flush_fn=capture_fn,
            batch_window_ms=10000,
        )

        for i in range(3):
            d = _delta(section="task_state", key=f"t-{i}", data={"i": i})
            await aggregator.collect(d)
            await aggregator.flush()

        assert len(batches) == 3
        assert batches[0].batch_id == "batch-1"
        assert batches[1].batch_id == "batch-2"
        assert batches[2].batch_id == "batch-3"

    @pytest.mark.asyncio
    async def test_apply_result_success_rate(self) -> None:
        """ApplyResult.success_rate reflects applied vs total."""

        async def write_fn(section, key, op, data):
            pass

        applicator = DeltaApplicator(write_fn=write_fn)
        deltas = [_delta(section="task_state", key=f"t-{i}", data={"v": i}) for i in range(5)]
        batch = _batch(deltas)
        result = await applicator.apply(batch)

        assert result.applied == 5
        assert result.rejected == 0
        assert result.success_rate == 1.0
        assert result.total == 5


class TestE2EWithOverflowHandler:
    """E2E: Full pipeline with SectionOverflowHandler as eviction backend."""

    @pytest.mark.asyncio
    async def test_overflow_evicts_then_write_succeeds(self) -> None:
        """Full E2E: emit -> aggregate -> preflight reject ->
        overflow evicts artifacts -> retry -> write succeeds."""
        handler = SectionOverflowHandler()
        section_store: dict[str, dict] = {
            "task_artifacts": {
                "old-1": {"type": "x", "timestamp_ns": 1},
                "old-2": {"type": "y", "timestamp_ns": 2},
            }
        }
        writes: list[tuple] = []
        reject_first = True

        def preflight(section, op, size):
            nonlocal reject_first
            if reject_first:
                reject_first = False
                return FakeApproval(False, "section full")
            return FakeApproval(True)

        async def write_fn(section, key, op, data):
            writes.append((section, key, data))

        async def evict_fn(section, needed_bytes):
            current = section_store.get(section, {})
            remaining, evicted_keys = handler.evict_oldest(section, current, needed_bytes)
            section_store[section] = remaining
            return len(evicted_keys)

        applicator = DeltaApplicator(
            preflight_fn=preflight,
            write_fn=write_fn,
            evict_fn=evict_fn,
        )
        aggregator = DeltaAggregator(
            flush_fn=lambda batch: applicator.apply(batch),
            batch_window_ms=1,
        )

        async def publish_fn(topic, delta):
            await aggregator.collect(delta)

        await emit_artifact(
            task_id="task-new",
            artifact_type="booking",
            artifact_data={"ref": "XYZ"},
            publish_fn=publish_fn,
        )

        await asyncio.sleep(0.05)

        assert len(writes) == 1
        assert writes[0][0] == "task_artifacts"
        assert handler.total_evicted >= 1
        assert len(handler.eviction_log) == 1

    @pytest.mark.asyncio
    async def test_overflow_with_history_sliding_window(self) -> None:
        """E2E: history_active overflow triggers sliding window eviction."""
        handler = SectionOverflowHandler(history_window=3)
        section_store: dict[str, dict] = {
            "history_active": {f"turn-{i:03d}": {"text": f"turn {i}"} for i in range(5)}
        }
        reject_first = True

        def preflight(section, op, size):
            nonlocal reject_first
            if reject_first and section == "history_active":
                reject_first = False
                return FakeApproval(False, "section full")
            return FakeApproval(True)

        writes: list[tuple] = []

        async def write_fn(section, key, op, data):
            writes.append((section, key))

        async def evict_fn(section, needed_bytes):
            current = section_store.get(section, {})
            remaining, evicted_keys = handler.evict_oldest(section, current, needed_bytes)
            section_store[section] = remaining
            return len(evicted_keys)

        applicator = DeltaApplicator(
            preflight_fn=preflight,
            write_fn=write_fn,
            evict_fn=evict_fn,
        )

        d = _delta(
            section="history_active",
            key="turn-005",
            operation="append",
            data={"text": "new turn"},
        )
        batch = _batch([d])
        result = await applicator.apply(batch)

        assert result.applied == 1
        assert result.evicted == 2  # 5 - 3 = 2 evicted by sliding window
        assert handler.total_evicted == 2
