"""Tests for PostReconciliationHookRunner (M9.6 D7)."""

from __future__ import annotations

import asyncio
from typing import Any

from k0.modules.consolidation.reconciliation.hooks import (
    HOOK_RECOMPUTE_CENTROID,
    HOOK_REGENERATE_SUMMARY,
)
from k0.modules.consolidation.reconciliation.hooks.centroid_recompute import (
    CentroidRecomputer,
    CentroidResult,
)
from k0.modules.consolidation.reconciliation.hooks.result import HookResult
from k0.modules.consolidation.reconciliation.hooks.runner import (
    HookBatchResult,
    HookDBWriterLike,
    PostReconciliationHookRunner,
)
from k0.modules.consolidation.reconciliation.hooks.summary_regen import (
    SummaryRegenerator,
    SummaryRegenResult,
)
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.pipelines.p03.event_state import ReconciliationAction
from k0.pipelines.p03.staged_writes import StagedWrite, WriteOperation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result(
    action: ReconciliationAction,
    hooks: list[str] | None = None,
    layer: str = "st_epi",
    match_id: str | None = "ep-001",
) -> ReconciliationResult:
    return ReconciliationResult(
        action=action,
        tier=2,
        match_id=match_id,
        match_layer=layer,
        similarity=0.85,
        identity_match=True,
        confidence=0.9,
        reason="test",
        candidate_id="cand-001",
        layer=layer,
        cycle_id="cycle-001",
        hooks_required=hooks or [],
    )


def _write(
    record_id: str = "ep-001",
    layer: str = "st_epi",
    data: dict[str, Any] | None = None,
    event_ids: list[str] | None = None,
) -> StagedWrite:
    return StagedWrite(
        write_id="w-001",
        layer=layer,
        operation=WriteOperation.INSERT,
        record_id=record_id,
        record_data=data or {"episode_summary": "test"},
        idempotency_key="idem-001",
        source_phase="R2",
        source_event_ids=event_ids or ["ev-1", "ev-2"],
    )


# -- Fake SummaryRegenerator --


class FakeSummaryRegen(SummaryRegenerator):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    async def regenerate(
        self, layer, record_id, spec, source_event_ids, record_data, conn=None
    ) -> SummaryRegenResult:
        self.calls.append({"layer": layer, "record_id": record_id, "event_ids": source_event_ids})
        return SummaryRegenResult(
            embedding_text=f"regen-{record_id}",
            summary_json='{"schema_version":"1.0"}' if layer == "st_epi" else None,
            embedding_model="ultrabert-v2.1.0",
            source_texts_json='["text1"]',
        )


# -- Fake CentroidRecomputer --


class FakeCentroidRecomp(CentroidRecomputer):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    async def recompute(
        self, layer, record_id, spec, source_event_ids, embedding_text=None, conn=None
    ) -> CentroidResult:
        self.calls.append(
            {"layer": layer, "record_id": record_id, "embedding_text": embedding_text}
        )
        return CentroidResult(
            embedding_vector=b"\x00" * 3072,
            embedding_model="ultrabert-v2.1.0",
            centroid_variance=0.05,
            strategy_used="hybrid" if layer == "st_epi" else "text_embed",
            member_count=2,
        )


# -- Fake DB Writer --


class FakeDBWriter(HookDBWriterLike):
    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []

    async def write_hook_outputs(
        self,
        layer,
        record_id,
        pk_column,
        summary_json,
        embedding_text,
        embedding_vector,
        embedding_model,
        source_texts_json,
    ) -> None:
        self.writes.append(
            {
                "layer": layer,
                "record_id": record_id,
                "pk_column": pk_column,
                "summary_json": summary_json,
                "embedding_text": embedding_text,
                "embedding_vector": embedding_vector,
                "embedding_model": embedding_model,
                "source_texts_json": source_texts_json,
            }
        )


def _make_runner(
    summary: FakeSummaryRegen | None = None,
    centroid: FakeCentroidRecomp | None = None,
    db: FakeDBWriter | None = None,
) -> tuple[PostReconciliationHookRunner, FakeSummaryRegen, FakeCentroidRecomp, FakeDBWriter]:
    s = summary or FakeSummaryRegen()
    c = centroid or FakeCentroidRecomp()
    d = db or FakeDBWriter()
    runner = PostReconciliationHookRunner(
        summary_regen=s,
        centroid_recomputer=c,
        db_writer=d,
    )
    return runner, s, c, d


# ===========================================================================
# Test: Skip empty hooks
# ===========================================================================


class TestSkipEmptyHooks:
    def test_skip_no_hooks(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(ReconciliationAction.SKIP, hooks=[])
        batch = asyncio.get_event_loop().run_until_complete(runner.run([(res, _write())]))
        assert batch.skipped == 1
        assert batch.summary_regen_count == 0
        assert batch.centroid_recompute_count == 0
        assert len(s.calls) == 0
        assert len(c.calls) == 0
        assert len(d.writes) == 0

    def test_contradict_no_hooks(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(ReconciliationAction.CONTRADICT, hooks=[])
        batch = asyncio.get_event_loop().run_until_complete(runner.run([(res, _write())]))
        assert batch.skipped == 1

    def test_prune_no_hooks(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(ReconciliationAction.PRUNE, hooks=[])
        batch = asyncio.get_event_loop().run_until_complete(runner.run([(res, _write())]))
        assert batch.skipped == 1


# ===========================================================================
# Test: CREATE triggers both hooks
# ===========================================================================


class TestCreateBothHooks:
    def test_create_dispatches_both(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.CREATE,
            hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID],
            match_id=None,
        )
        w = _write(record_id="ep-new")
        batch = asyncio.get_event_loop().run_until_complete(runner.run([(res, w)]))
        assert batch.summary_regen_count == 1
        assert batch.centroid_recompute_count == 1
        assert batch.skipped == 0
        assert batch.failed == 0
        assert len(s.calls) == 1
        assert len(c.calls) == 1

    def test_create_record_id_fallback(self) -> None:
        """CREATE has no match_id; should use write.record_id."""
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.CREATE,
            hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID],
            match_id=None,
        )
        w = _write(record_id="ep-from-write")
        asyncio.get_event_loop().run_until_complete(runner.run([(res, w)]))
        assert s.calls[0]["record_id"] == "ep-from-write"
        assert c.calls[0]["record_id"] == "ep-from-write"

    def test_create_db_write(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.CREATE,
            hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID],
            match_id=None,
        )
        w = _write(record_id="ep-new")
        asyncio.get_event_loop().run_until_complete(runner.run([(res, w)]))
        assert len(d.writes) == 1
        db = d.writes[0]
        assert db["layer"] == "st_epi"
        assert db["record_id"] == "ep-new"
        assert db["summary_json"] is not None
        assert db["embedding_text"] is not None
        assert db["embedding_vector"] is not None


# ===========================================================================
# Test: REINFORCE triggers centroid only
# ===========================================================================


class TestReinforceCentroidOnly:
    def test_reinforce_centroid_only(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.REINFORCE,
            hooks=[HOOK_RECOMPUTE_CENTROID],
        )
        batch = asyncio.get_event_loop().run_until_complete(runner.run([(res, _write())]))
        assert batch.summary_regen_count == 0
        assert batch.centroid_recompute_count == 1
        assert len(s.calls) == 0
        assert len(c.calls) == 1

    def test_reinforce_no_summary_regen(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.REINFORCE,
            hooks=[HOOK_RECOMPUTE_CENTROID],
        )
        asyncio.get_event_loop().run_until_complete(runner.run([(res, _write())]))
        assert len(s.calls) == 0

    def test_reinforce_db_write_no_summary(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.REINFORCE,
            hooks=[HOOK_RECOMPUTE_CENTROID],
        )
        asyncio.get_event_loop().run_until_complete(runner.run([(res, _write())]))
        assert len(d.writes) == 1
        assert d.writes[0]["summary_json"] is None
        assert d.writes[0]["embedding_text"] is None


# ===========================================================================
# Test: EXTEND triggers both hooks
# ===========================================================================


class TestExtendBothHooks:
    def test_extend_dispatches_both(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.EXTEND,
            hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID],
        )
        batch = asyncio.get_event_loop().run_until_complete(runner.run([(res, _write())]))
        assert batch.summary_regen_count == 1
        assert batch.centroid_recompute_count == 1

    def test_extend_centroid_receives_new_embedding_text(self) -> None:
        """Centroid should receive the embedding_text produced by summary regen."""
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.EXTEND,
            hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID],
        )
        asyncio.get_event_loop().run_until_complete(runner.run([(res, _write())]))
        # Centroid should have received the embedding_text from summary regen
        assert c.calls[0]["embedding_text"] == "regen-ep-001"


# ===========================================================================
# Test: EVOLVE hooks on new record only
# ===========================================================================


class TestEvolveNewRecordOnly:
    def test_evolve_both_hooks(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.EVOLVE,
            hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID],
            match_id="ep-new-evolve",
        )
        batch = asyncio.get_event_loop().run_until_complete(
            runner.run([(res, _write(record_id="ep-new-evolve"))])
        )
        assert batch.summary_regen_count == 1
        assert batch.centroid_recompute_count == 1
        # hooks target the new record, not the superseded one
        assert s.calls[0]["record_id"] == "ep-new-evolve"
        assert c.calls[0]["record_id"] == "ep-new-evolve"


# ===========================================================================
# Test: Hook execution order (summary before centroid)
# ===========================================================================


class TestHookExecutionOrder:
    def test_summary_runs_before_centroid(self) -> None:
        """Summary must produce embedding_text before centroid uses it."""
        call_order: list[str] = []

        class OrderSummary(SummaryRegenerator):
            def __init__(self):
                super().__init__()

            async def regenerate(self, **kwargs) -> SummaryRegenResult:
                call_order.append("summary")
                return SummaryRegenResult(embedding_text="new-text")

        class OrderCentroid(CentroidRecomputer):
            def __init__(self):
                super().__init__()

            async def recompute(self, **kwargs) -> CentroidResult:
                call_order.append("centroid")
                return CentroidResult(
                    embedding_vector=None,
                    embedding_model=None,
                    centroid_variance=None,
                    strategy_used="test",
                    member_count=0,
                )

        runner = PostReconciliationHookRunner(
            summary_regen=OrderSummary(),
            centroid_recomputer=OrderCentroid(),
            db_writer=FakeDBWriter(),
        )
        res = _result(
            ReconciliationAction.CREATE,
            hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID],
            match_id=None,
        )
        asyncio.get_event_loop().run_until_complete(runner.run([(res, _write())]))
        assert call_order == ["summary", "centroid"]


# ===========================================================================
# Test: Failure isolation
# ===========================================================================


class TestFailureIsolation:
    def test_summary_failure_does_not_block_batch(self) -> None:
        class FailingSummary(SummaryRegenerator):
            def __init__(self):
                super().__init__()

            async def regenerate(self, **kwargs) -> SummaryRegenResult:
                raise RuntimeError("summary exploded")

        runner = PostReconciliationHookRunner(
            summary_regen=FailingSummary(),
            centroid_recomputer=FakeCentroidRecomp(),
            db_writer=FakeDBWriter(),
        )
        r1 = _result(
            ReconciliationAction.CREATE,
            hooks=[HOOK_REGENERATE_SUMMARY],
            match_id=None,
        )
        r2 = _result(
            ReconciliationAction.REINFORCE,
            hooks=[HOOK_RECOMPUTE_CENTROID],
            match_id="ep-002",
        )
        w1 = _write(record_id="ep-001")
        w2 = _write(record_id="ep-002")
        batch = asyncio.get_event_loop().run_until_complete(runner.run([(r1, w1), (r2, w2)]))
        assert batch.failed == 1
        assert batch.centroid_recompute_count == 1
        # The failed record should appear in per_record
        failed_results = [r for r in batch.per_record if r.failed]
        assert len(failed_results) == 1
        assert "summary exploded" in failed_results[0].error_message

    def test_single_record_failure_preserves_others(self) -> None:
        class FailOnFirst(SummaryRegenerator):
            def __init__(self):
                super().__init__()
                self.call_count = 0

            async def regenerate(self, **kwargs) -> SummaryRegenResult:
                self.call_count += 1
                if self.call_count == 1:
                    raise RuntimeError("first fails")
                return SummaryRegenResult(embedding_text="ok")

        runner = PostReconciliationHookRunner(
            summary_regen=FailOnFirst(),
            centroid_recomputer=FakeCentroidRecomp(),
            db_writer=FakeDBWriter(),
        )
        inputs = []
        for i in range(3):
            r = _result(
                ReconciliationAction.EXTEND,
                hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID],
                match_id=f"ep-{i}",
            )
            inputs.append((r, _write(record_id=f"ep-{i}")))

        batch = asyncio.get_event_loop().run_until_complete(runner.run(inputs))
        assert batch.failed == 1
        assert batch.summary_regen_count == 2


# ===========================================================================
# Test: Batch result counts
# ===========================================================================


class TestBatchResultCounts:
    def test_mixed_batch_counts(self) -> None:
        runner, s, c, d = _make_runner()
        inputs = [
            # CREATE: both hooks
            (
                _result(
                    ReconciliationAction.CREATE,
                    hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID],
                    match_id=None,
                ),
                _write(record_id="ep-new"),
            ),
            # REINFORCE: centroid only
            (
                _result(
                    ReconciliationAction.REINFORCE,
                    hooks=[HOOK_RECOMPUTE_CENTROID],
                    match_id="ep-002",
                ),
                _write(record_id="ep-002"),
            ),
            # SKIP: no hooks
            (
                _result(ReconciliationAction.SKIP, hooks=[]),
                _write(record_id="ep-003"),
            ),
            # CONTRADICT: no hooks
            (
                _result(ReconciliationAction.CONTRADICT, hooks=[]),
                _write(record_id="ep-004"),
            ),
        ]
        batch = asyncio.get_event_loop().run_until_complete(runner.run(inputs))
        assert batch.total == 4
        assert batch.summary_regen_count == 1
        assert batch.centroid_recompute_count == 2
        assert batch.skipped == 2
        assert batch.failed == 0
        assert len(batch.per_record) == 2  # only hookable records
        assert batch.total_time_ms > 0

    def test_empty_batch(self) -> None:
        runner, s, c, d = _make_runner()
        batch = asyncio.get_event_loop().run_until_complete(runner.run([]))
        assert batch.total == 0
        assert batch.skipped == 0
        assert batch.failed == 0

    def test_all_skipped(self) -> None:
        runner, s, c, d = _make_runner()
        inputs = [
            (_result(ReconciliationAction.SKIP, hooks=[]), _write()),
            (_result(ReconciliationAction.CONTRADICT, hooks=[]), _write()),
            (_result(ReconciliationAction.PRUNE, hooks=[]), _write()),
        ]
        batch = asyncio.get_event_loop().run_until_complete(runner.run(inputs))
        assert batch.skipped == 3
        assert len(batch.per_record) == 0


# ===========================================================================
# Test: Non-episodic layers
# ===========================================================================


class TestNonEpisodicLayers:
    def test_sem_no_summary_json(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.EXTEND,
            hooks=[HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID],
            layer="st_sem",
            match_id="sem-001",
        )
        w = _write(record_id="sem-001", layer="st_sem")
        asyncio.get_event_loop().run_until_complete(runner.run([(res, w)]))
        assert len(d.writes) == 1
        # Non-episodic: summary_json should be None
        assert d.writes[0]["summary_json"] is None

    def test_kg_edges_no_hooks(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.REINFORCE,
            hooks=[],
            layer="st_kg_edges",
            match_id="edge-001",
        )
        batch = asyncio.get_event_loop().run_until_complete(
            runner.run([(res, _write(record_id="edge-001", layer="st_kg_edges"))])
        )
        assert batch.skipped == 1


# ===========================================================================
# Test: PK column resolution
# ===========================================================================


class TestPKColumnResolution:
    def test_epi_pk(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.EXTEND,
            hooks=[HOOK_REGENERATE_SUMMARY],
            layer="st_epi",
        )
        asyncio.get_event_loop().run_until_complete(runner.run([(res, _write())]))
        assert d.writes[0]["pk_column"] == "episode_id"

    def test_sem_pk(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.EXTEND,
            hooks=[HOOK_REGENERATE_SUMMARY],
            layer="st_sem",
            match_id="sem-001",
        )
        asyncio.get_event_loop().run_until_complete(
            runner.run([(res, _write(record_id="sem-001", layer="st_sem"))])
        )
        assert d.writes[0]["pk_column"] == "pattern_id"

    def test_procedural_pk(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.EXTEND,
            hooks=[HOOK_REGENERATE_SUMMARY],
            layer="st_procedural",
            match_id="rout-001",
        )
        asyncio.get_event_loop().run_until_complete(
            runner.run([(res, _write(record_id="rout-001", layer="st_procedural"))])
        )
        assert d.writes[0]["pk_column"] == "routine_id"

    def test_social_pk(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.EXTEND,
            hooks=[HOOK_REGENERATE_SUMMARY],
            layer="st_social",
            match_id="rel-001",
        )
        asyncio.get_event_loop().run_until_complete(
            runner.run([(res, _write(record_id="rel-001", layer="st_social"))])
        )
        assert d.writes[0]["pk_column"] == "relationship_id"

    def test_kg_dom_pk(self) -> None:
        runner, s, c, d = _make_runner()
        res = _result(
            ReconciliationAction.EXTEND,
            hooks=[HOOK_REGENERATE_SUMMARY],
            layer="st_kg_dom",
            match_id="ent-001",
        )
        asyncio.get_event_loop().run_until_complete(
            runner.run([(res, _write(record_id="ent-001", layer="st_kg_dom"))])
        )
        assert d.writes[0]["pk_column"] == "entity_id"


# ===========================================================================
# Test: HookResult dataclass
# ===========================================================================


class TestHookResult:
    def test_success_factory(self) -> None:
        r = HookResult.success("st_epi", "ep-1", summary=True, centroid=True, time_ms=5.0)
        assert r.layer == "st_epi"
        assert r.record_id == "ep-1"
        assert r.summary_regenerated is True
        assert r.centroid_recomputed is True
        assert r.failed is False
        assert r.time_ms == 5.0

    def test_failure_factory(self) -> None:
        r = HookResult.failure("st_sem", "sem-1", "boom")
        assert r.failed is True
        assert r.error_message == "boom"
        assert r.summary_regenerated is False
        assert r.centroid_recomputed is False


# ===========================================================================
# Test: HookBatchResult defaults
# ===========================================================================


class TestHookBatchResult:
    def test_defaults(self) -> None:
        b = HookBatchResult()
        assert b.total == 0
        assert b.summary_regen_count == 0
        assert b.centroid_recompute_count == 0
        assert b.skipped == 0
        assert b.failed == 0
        assert b.total_time_ms == 0.0
        assert b.per_record == []
