"""Integration tests for PostReconciliationHookRunner (M9.6 D10).

These tests verify the full hook execution flow:
  R7 write → hook runner → summary + centroid → DB update.
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np

from k0.modules.consolidation.reconciliation.hooks import (
    HOOK_RECOMPUTE_CENTROID,
    HOOK_REGENERATE_SUMMARY,
)
from k0.modules.consolidation.reconciliation.hooks.centroid_recompute import (
    CentroidResult,
    ndarray_to_bytes,
)
from k0.modules.consolidation.reconciliation.hooks.episode_summary import StructuredEpisodeSummary
from k0.modules.consolidation.reconciliation.hooks.runner import PostReconciliationHookRunner
from k0.modules.consolidation.reconciliation.hooks.summary_regen import SummaryRegenResult

# ---------------------------------------------------------------------------
# Shared fakes — replicate from unit test files for isolation
# ---------------------------------------------------------------------------


def _make_embedding(dim: int = 768) -> np.ndarray:
    rng = np.random.default_rng(99)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


class FakeSummaryRegen:
    def __init__(self, text: str = "regen-text", model: str = "ultrabert-v2.1.0"):
        self._text = text
        self._model = model
        self.calls: list[dict] = []

    async def regenerate(self, layer, record_id, spec, source_event_ids, record_data, conn=None):
        self.calls.append(
            {
                "layer": layer,
                "record_id": record_id,
                "event_ids": source_event_ids,
            }
        )
        summary_json = None
        if layer == "st_epi":
            s = StructuredEpisodeSummary(title="Integration test", event_count=1)
            summary_json = s.to_json()
        return SummaryRegenResult(
            embedding_text=self._text,
            summary_json=summary_json,
            embedding_model=self._model,
            source_texts_json='["test"]',
        )


class FakeCentroidRecomp:
    def __init__(self):
        self._vector = ndarray_to_bytes(_make_embedding())
        self.calls: list[dict] = []

    async def recompute(
        self, layer, record_id, spec, source_event_ids, embedding_text=None, conn=None
    ):
        self.calls.append(
            {
                "layer": layer,
                "record_id": record_id,
                "embedding_text": embedding_text,
            }
        )
        return CentroidResult(
            embedding_vector=self._vector,
            embedding_model="ultrabert-v2.1.0",
            centroid_variance=0.042,
            strategy_used="hybrid",
            member_count=len(source_event_ids),
        )


class TrackingDBWriter:
    """Records every UPDATE that the runner would perform."""

    def __init__(self):
        self.writes: list[dict[str, Any]] = []

    async def write_hook_outputs(
        self,
        layer: str,
        record_id: str,
        pk_column: str,
        summary_json: str | None,
        embedding_text: str | None,
        embedding_vector: bytes | None,
        embedding_model: str | None,
        source_texts_json: str | None,
    ) -> None:
        self.writes.append(
            {
                "layer": layer,
                "record_id": record_id,
                "pk_column": pk_column,
                "has_summary": summary_json is not None,
                "has_centroid": embedding_vector is not None,
            }
        )


# ---------------------------------------------------------------------------
# Fixtures for ReconciliationResult + StagedWrite
# ---------------------------------------------------------------------------


def _result(
    record_id: str = "rec-1",
    layer: str = "st_epi",
    action: str = "CREATE",
    hooks: list[str] | None = None,
) -> Any:
    """Lightweight stub mirroring ReconciliationResult."""
    if hooks is None:
        hooks = [HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID]

    class _R:
        pass

    r = _R()
    r.record_id = record_id
    r.layer = layer
    r.action = action
    r.hooks_required = hooks
    r.match_id = record_id
    return r


def _write(
    record_id: str = "rec-1",
    layer: str = "st_epi",
    event_ids: list[str] | None = None,
) -> Any:
    """Lightweight stub mirroring StagedWrite."""
    if event_ids is None:
        event_ids = ["ev-1"]

    class _W:
        pass

    w = _W()
    w.record_id = record_id
    w.layer = layer
    w.source_event_ids = event_ids
    w.record_data = {"episode_summary": "stub", "start_time_utc": 1000, "end_time_utc": 2000}
    return w


class FakeRegistry:
    def get(self, layer):
        return None


# ===========================================================================
# Integration: full flow
# ===========================================================================


class TestFullHookFlow:
    """Verifies the complete R7 → hook runner → DB update path."""

    def test_create_episodic_runs_both_hooks(self) -> None:
        summary = FakeSummaryRegen()
        centroid = FakeCentroidRecomp()
        writer = TrackingDBWriter()

        runner = PostReconciliationHookRunner(
            summary_regen=summary,
            centroid_recomputer=centroid,
            db_writer=writer,
            registry=FakeRegistry(),
        )

        hook_inputs = [(_result(), _write())]
        batch = asyncio.get_event_loop().run_until_complete(runner.run(hook_inputs))

        assert batch.total == 1
        assert batch.summary_regen_count == 1
        assert batch.centroid_recompute_count == 1
        assert batch.failed == 0

        # Verify DB writer got a single call
        assert len(writer.writes) == 1
        w = writer.writes[0]
        assert w["layer"] == "st_epi"
        assert w["record_id"] == "rec-1"
        assert w["has_summary"] is True
        assert w["has_centroid"] is True

    def test_extend_episodic_full_chain(self) -> None:
        summary = FakeSummaryRegen()
        centroid = FakeCentroidRecomp()
        writer = TrackingDBWriter()

        runner = PostReconciliationHookRunner(
            summary_regen=summary,
            centroid_recomputer=centroid,
            db_writer=writer,
            registry=FakeRegistry(),
        )

        hook_inputs = [
            (
                _result(action="EXTEND", hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID]),
                _write(),
            ),
        ]
        batch = asyncio.get_event_loop().run_until_complete(runner.run(hook_inputs))

        assert batch.summary_regen_count == 1
        assert batch.centroid_recompute_count == 1

    def test_centroid_receives_embedding_text_from_summary(self) -> None:
        """Centroid step should use the embedding_text produced by summary step."""
        summary = FakeSummaryRegen(text="fresh-embedding-text")
        centroid = FakeCentroidRecomp()
        writer = TrackingDBWriter()

        runner = PostReconciliationHookRunner(
            summary_regen=summary,
            centroid_recomputer=centroid,
            db_writer=writer,
            registry=FakeRegistry(),
        )

        hook_inputs = [(_result(), _write())]
        asyncio.get_event_loop().run_until_complete(runner.run(hook_inputs))

        assert centroid.calls[0]["embedding_text"] == "fresh-embedding-text"


# ===========================================================================
# Integration: batch of multiple records
# ===========================================================================


class TestBatchProcessing:
    def test_multiple_records_processed(self) -> None:
        writer = TrackingDBWriter()
        runner = PostReconciliationHookRunner(
            summary_regen=FakeSummaryRegen(),
            centroid_recomputer=FakeCentroidRecomp(),
            db_writer=writer,
            registry=FakeRegistry(),
        )

        hook_inputs = [
            (_result(record_id="ep-1"), _write(record_id="ep-1")),
            (_result(record_id="ep-2"), _write(record_id="ep-2")),
            (_result(record_id="ep-3"), _write(record_id="ep-3")),
        ]
        batch = asyncio.get_event_loop().run_until_complete(runner.run(hook_inputs))

        assert batch.total == 3
        assert batch.failed == 0
        assert len(writer.writes) == 3
        ids = {w["record_id"] for w in writer.writes}
        assert ids == {"ep-1", "ep-2", "ep-3"}

    def test_one_record_per_db_write(self) -> None:
        """Each record should produce exactly one DB write call."""
        writer = TrackingDBWriter()
        runner = PostReconciliationHookRunner(
            summary_regen=FakeSummaryRegen(),
            centroid_recomputer=FakeCentroidRecomp(),
            db_writer=writer,
            registry=FakeRegistry(),
        )

        hook_inputs = [
            (_result(record_id="ep-1"), _write(record_id="ep-1")),
            (_result(record_id="ep-2"), _write(record_id="ep-2")),
        ]
        asyncio.get_event_loop().run_until_complete(runner.run(hook_inputs))
        assert len(writer.writes) == 2


# ===========================================================================
# Integration: mixed layers in same batch
# ===========================================================================


class TestMixedLayerBatch:
    def test_episodic_and_semantic_together(self) -> None:
        writer = TrackingDBWriter()
        runner = PostReconciliationHookRunner(
            summary_regen=FakeSummaryRegen(),
            centroid_recomputer=FakeCentroidRecomp(),
            db_writer=writer,
            registry=FakeRegistry(),
        )

        hook_inputs = [
            (_result(record_id="ep-1", layer="st_epi"), _write(record_id="ep-1", layer="st_epi")),
            (_result(record_id="sem-1", layer="st_sem"), _write(record_id="sem-1", layer="st_sem")),
        ]
        batch = asyncio.get_event_loop().run_until_complete(runner.run(hook_inputs))
        assert batch.total == 2
        layers = {w["layer"] for w in writer.writes}
        assert layers == {"st_epi", "st_sem"}


# ===========================================================================
# Integration: failure isolation
# ===========================================================================


class FailingSummaryRegen:
    async def regenerate(self, layer, record_id, spec, source_event_ids, record_data, conn=None):
        raise RuntimeError("summary explosion")


class TestFailureIsolation:
    def test_one_failure_doesnt_block_others(self) -> None:
        writer = TrackingDBWriter()
        runner = PostReconciliationHookRunner(
            summary_regen=FailingSummaryRegen(),
            centroid_recomputer=FakeCentroidRecomp(),
            db_writer=writer,
            registry=FakeRegistry(),
        )

        hook_inputs = [
            (_result(record_id="ep-fail"), _write(record_id="ep-fail")),
            (
                _result(record_id="ep-ok", hooks=[HOOK_RECOMPUTE_CENTROID]),
                _write(record_id="ep-ok"),
            ),
        ]
        batch = asyncio.get_event_loop().run_until_complete(runner.run(hook_inputs))

        assert batch.total == 2
        assert batch.failed >= 1

        # The non-failing record should still be written
        ok_writes = [w for w in writer.writes if w["record_id"] == "ep-ok"]
        assert len(ok_writes) == 1


# ===========================================================================
# Integration: HookBatchResult aggregation
# ===========================================================================


class TestBatchResultAggregation:
    def test_empty_batch(self) -> None:
        writer = TrackingDBWriter()
        runner = PostReconciliationHookRunner(
            summary_regen=FakeSummaryRegen(),
            centroid_recomputer=FakeCentroidRecomp(),
            db_writer=writer,
            registry=FakeRegistry(),
        )

        batch = asyncio.get_event_loop().run_until_complete(runner.run([]))
        assert batch.total == 0
        assert batch.failed == 0
        assert batch.summary_regen_count == 0
        assert batch.centroid_recompute_count == 0

    def test_skipped_records_counted(self) -> None:
        writer = TrackingDBWriter()
        runner = PostReconciliationHookRunner(
            summary_regen=FakeSummaryRegen(),
            centroid_recomputer=FakeCentroidRecomp(),
            db_writer=writer,
            registry=FakeRegistry(),
        )

        hook_inputs = [
            (_result(record_id="ep-1", hooks=[]), _write(record_id="ep-1")),
        ]
        batch = asyncio.get_event_loop().run_until_complete(runner.run(hook_inputs))
        assert batch.skipped == 1
        assert batch.total == 1
        assert len(writer.writes) == 0
