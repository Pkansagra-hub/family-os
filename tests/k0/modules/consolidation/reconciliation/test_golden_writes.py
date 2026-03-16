"""Golden write tests -- end-to-end ReconciliationResult -> StagedWrite (M9.5).

Covers validation criteria V22-V23 from the M9.5 spec.
Verifies that WriteDecisionRouter produces correct StagedWrites for
known scenarios across st_epi and st_sem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.reconciliation.router import WriteDecisionRouter
from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry, TruthLayerSpec
from k0.modules.consolidation.types import ReconciliationCandidate
from k0.pipelines.p03.event_state import ReconciliationAction
from k0.pipelines.p03.staged_writes import WriteOperation

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "k0" / "contracts" / "schemas"
_CYCLE = "01J0000000GOLDEN0000000TEST"


@pytest.fixture()
def registry() -> TruthLayerRegistry:
    return TruthLayerRegistry.from_contracts(_CONTRACTS_DIR)


@pytest.fixture()
def epi_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_epi")


@pytest.fixture()
def sem_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_sem")


@pytest.fixture()
def proc_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_procedural")


@pytest.fixture()
def social_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_social")


@pytest.fixture()
def kg_dom_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_kg_dom")


@pytest.fixture()
def kg_edge_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_kg_edges")


@pytest.fixture()
def prosp_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_prospective")


def _candidate(
    layer: str,
    metadata: dict[str, Any] | None = None,
    source_event_ids: tuple[str, ...] = ("evt-g1", "evt-g2"),
) -> ReconciliationCandidate:
    return ReconciliationCandidate(
        candidate_id="golden-cand",
        layer=layer,
        source_phase="R2",
        metadata=metadata or {},
        source_event_ids=source_event_ids,
        cycle_id=_CYCLE,
        tenant_id="golden-tenant",
        space_id="golden-space",
    )


def _result(
    action: ReconciliationAction,
    match_id: str | None = None,
    match_layer: str = "st_epi",
    similarity: float = 0.9,
    confidence: float = 0.85,
) -> ReconciliationResult:
    return ReconciliationResult(
        action=action,
        tier=2,
        match_id=match_id,
        match_layer=match_layer,
        similarity=similarity,
        identity_match=False,
        confidence=confidence,
        reason="golden test",
        candidate_id="golden-cand",
        layer=match_layer,
        cycle_id=_CYCLE,
    )


# =========================================================================
# V22: Golden writes for st_epi
# =========================================================================


class TestEpiGolden:
    def test_epi_create_golden(self, epi_spec: TruthLayerSpec) -> None:
        meta = {
            "episode_summary": "Family dinner at home",
            "start_time_ms": 1700000000000,
            "end_time_ms": 1700003600000,
        }
        result = _result(ReconciliationAction.CREATE)
        cand = _candidate("st_epi", metadata=meta)
        writes = WriteDecisionRouter.build(result, cand, epi_spec, _CYCLE)

        assert len(writes) == 1
        w = writes[0]
        assert w.operation == WriteOperation.INSERT
        assert w.layer == "st_epi"
        assert w.record_data["episode_summary"] == "Family dinner at home"
        assert w.record_data[epi_spec.version_column] == 1
        assert w.record_data[epi_spec.observation_count_column] == 1
        assert w.record_data[epi_spec.canonical_column] is True
        assert w.record_data[epi_spec.archival_status_column] == epi_spec.active_status_value

    def test_epi_reinforce_golden(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.REINFORCE, match_id="epi-001")
        cand = _candidate("st_epi")
        writes = WriteDecisionRouter.build(result, cand, epi_spec, _CYCLE)

        assert len(writes) == 1
        w = writes[0]
        assert w.operation == WriteOperation.UPDATE
        assert w.record_id == "epi-001"
        assert w.record_data[epi_spec.observation_count_column] == 1
        # st_epi has "none" boost
        assert "_confidence_boost" not in w.record_data
        assert "_confidence_boost_factor" not in w.record_data

    def test_epi_prune_golden(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.PRUNE, match_id="epi-old")
        cand = _candidate("st_epi", metadata={"prune_reason": "decay"})
        writes = WriteDecisionRouter.build(result, cand, epi_spec, _CYCLE)

        assert len(writes) == 1
        w = writes[0]
        assert w.operation == WriteOperation.ARCHIVE
        assert w.record_id == "epi-old"
        assert w.record_data[epi_spec.archival_status_column] == "ARCHIVED"
        assert w.record_data["archived_reason"] == "decay"

    def test_epi_skip_golden(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.SKIP)
        writes = WriteDecisionRouter.build(
            result,
            _candidate("st_epi"),
            epi_spec,
            _CYCLE,
        )
        assert writes == []


# =========================================================================
# V23: Golden writes for st_sem
# =========================================================================


class TestSemGolden:
    def test_sem_create_golden(self, sem_spec: TruthLayerSpec) -> None:
        meta = {
            "pattern_label": "morning exercise routine",
            "description": "Goes for a run every morning",
        }
        result = _result(ReconciliationAction.CREATE, match_layer="st_sem")
        cand = _candidate("st_sem", metadata=meta)
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)

        assert len(writes) == 1
        w = writes[0]
        assert w.operation == WriteOperation.INSERT
        assert w.layer == "st_sem"
        assert w.record_data["pattern_label"] == "morning exercise routine"
        assert w.record_data[sem_spec.version_column] == 1

    def test_sem_reinforce_golden(self, sem_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.REINFORCE,
            match_id="sem-001",
            match_layer="st_sem",
        )
        cand = _candidate("st_sem")
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)

        assert len(writes) == 1
        w = writes[0]
        assert w.operation == WriteOperation.UPDATE
        assert w.record_id == "sem-001"
        assert w.record_data["_confidence_boost"] == pytest.approx(0.05)

    def test_sem_extend_golden(self, sem_spec: TruthLayerSpec) -> None:
        meta = {
            "source_texts_json": ["new observation text"],
            "pattern_name": "updated label",
        }
        result = _result(
            ReconciliationAction.EXTEND,
            match_id="sem-001",
            match_layer="st_sem",
        )
        cand = _candidate("st_sem", metadata=meta)
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)

        assert len(writes) == 1
        w = writes[0]
        assert w.operation == WriteOperation.UPDATE
        assert w.record_id == "sem-001"
        # Both columns should be in record_data (REPLACED and APPENDABLE_DISTINCT)
        assert "source_texts_json" in w.record_data
        assert "pattern_name" in w.record_data
        # observation_count always bumped
        assert w.record_data[sem_spec.observation_count_column] == 1

    def test_sem_evolve_golden(self, sem_spec: TruthLayerSpec) -> None:
        meta = {"pattern_label": "evolved morning routine"}
        result = _result(
            ReconciliationAction.EVOLVE,
            match_id="sem-old",
            match_layer="st_sem",
        )
        cand = _candidate("st_sem", metadata=meta)
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)

        assert len(writes) == 2
        archive, insert = writes
        # Archive old
        assert archive.operation == WriteOperation.UPDATE
        assert archive.record_id == "sem-old"
        assert archive.record_data[sem_spec.canonical_column] is False
        assert archive.record_data[sem_spec.archival_status_column] == "SUPERSEDED"
        # Insert new
        assert insert.operation == WriteOperation.INSERT
        assert insert.record_data[sem_spec.supersedes_column] == "sem-old"
        assert insert.record_data[sem_spec.canonical_column] is True
        assert insert.record_data.get("pattern_label") == "evolved morning routine"


# =========================================================================
# Golden writes for other layers
# =========================================================================


class TestOtherLayersGolden:
    def test_procedural_create_golden(self, proc_spec: TruthLayerSpec) -> None:
        meta = {"procedure_name": "bedtime routine"}
        result = _result(ReconciliationAction.CREATE, match_layer="st_procedural")
        cand = _candidate("st_procedural", metadata=meta)
        writes = WriteDecisionRouter.build(result, cand, proc_spec, _CYCLE)
        assert len(writes) == 1
        assert writes[0].layer == "st_procedural"
        assert writes[0].record_data["procedure_name"] == "bedtime routine"

    def test_social_reinforce_golden(self, social_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.REINFORCE,
            match_id="soc-1",
            match_layer="st_social",
        )
        cand = _candidate("st_social")
        writes = WriteDecisionRouter.build(result, cand, social_spec, _CYCLE)
        assert len(writes) == 1
        assert writes[0].record_data.get("_confidence_boost_factor") == pytest.approx(1.1)

    def test_kg_dom_create_golden(self, kg_dom_spec: TruthLayerSpec) -> None:
        meta = {"entity_name": "John", "entity_type": "PERSON"}
        result = _result(ReconciliationAction.CREATE, match_layer="st_kg_dom")
        cand = _candidate("st_kg_dom", metadata=meta)
        writes = WriteDecisionRouter.build(result, cand, kg_dom_spec, _CYCLE)
        assert len(writes) == 1
        assert writes[0].layer == "st_kg_dom"
        assert writes[0].record_data["entity_name"] == "John"

    def test_kg_edges_extend_golden(self, kg_edge_spec: TruthLayerSpec) -> None:
        meta = {"edge_weight": 0.9}
        result = _result(
            ReconciliationAction.EXTEND,
            match_id="edge-1",
            match_layer="st_kg_edges",
        )
        cand = _candidate("st_kg_edges", metadata=meta)
        writes = WriteDecisionRouter.build(result, cand, kg_edge_spec, _CYCLE)
        assert len(writes) == 1
        assert writes[0].operation == WriteOperation.UPDATE

    def test_prospective_create_golden(self, prosp_spec: TruthLayerSpec) -> None:
        meta = {"intention_label": "plan family trip"}
        result = _result(ReconciliationAction.CREATE, match_layer="st_prospective")
        cand = _candidate("st_prospective", metadata=meta)
        writes = WriteDecisionRouter.build(result, cand, prosp_spec, _CYCLE)
        assert len(writes) == 1
        assert writes[0].layer == "st_prospective"


# =========================================================================
# Idempotency golden
# =========================================================================


class TestIdempotencyGolden:
    def test_same_inputs_same_keys(self, sem_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.CREATE,
            match_layer="st_sem",
        )
        meta = {sem_spec.pk_column: "fixed-pk"}
        cand = _candidate("st_sem", metadata=meta)

        w1 = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)
        w2 = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)
        assert w1[0].idempotency_key == w2[0].idempotency_key

    def test_different_cycles_different_keys(self, sem_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.CREATE,
            match_layer="st_sem",
        )
        meta = {sem_spec.pk_column: "fixed-pk"}
        cand = _candidate("st_sem", metadata=meta)

        w1 = WriteDecisionRouter.build(result, cand, sem_spec, "CYCLE_A")
        w2 = WriteDecisionRouter.build(result, cand, sem_spec, "CYCLE_B")
        assert w1[0].idempotency_key != w2[0].idempotency_key
