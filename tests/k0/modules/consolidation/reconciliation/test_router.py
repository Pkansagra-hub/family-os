"""Per-action StagedWrite tests for WriteDecisionRouter (M9.5).

Covers validation criteria V1, V2, V15-V21, V26 from the M9.5 spec.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from k0.modules.consolidation.reconciliation.idem import RouterIdempotencyKey
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.reconciliation.router import WriteDecisionRouter
from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry, TruthLayerSpec
from k0.modules.consolidation.types import ReconciliationCandidate
from k0.pipelines.p03.event_state import ReconciliationAction
from k0.pipelines.p03.staged_writes import StagedWrite, WriteOperation

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "k0" / "contracts" / "schemas"
_CYCLE = "01J0000000000000000000CYCL"


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
def kg_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_kg_dom")


def _candidate(
    layer: str = "st_epi",
    metadata: dict[str, Any] | None = None,
    source_event_ids: tuple[str, ...] = ("evt-1", "evt-2"),
) -> ReconciliationCandidate:
    return ReconciliationCandidate(
        candidate_id="cand-1",
        layer=layer,
        source_phase="R2",
        metadata=metadata or {},
        source_event_ids=source_event_ids,
        cycle_id=_CYCLE,
        tenant_id="t1",
        space_id="s1",
    )


def _result(
    action: ReconciliationAction,
    match_id: str | None = None,
    match_layer: str = "st_epi",
    similarity: float = 0.9,
    confidence: float = 0.8,
    tier: int = 2,
    contradiction_details: dict[str, Any] | None = None,
) -> ReconciliationResult:
    return ReconciliationResult(
        action=action,
        tier=tier,
        match_id=match_id,
        match_layer=match_layer,
        similarity=similarity,
        identity_match=False,
        confidence=confidence,
        reason="test",
        candidate_id="cand-1",
        layer=match_layer,
        cycle_id=_CYCLE,
        contradiction_details=contradiction_details,
    )


# =========================================================================
# V18: SKIP produces empty list
# =========================================================================


class TestSkip:
    def test_skip_no_writes(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.SKIP)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes == []

    def test_skip_returns_list(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.SKIP)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert isinstance(writes, list)


# =========================================================================
# V1: CREATE produces INSERT
# =========================================================================


class TestCreate:
    def test_create_insert(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert len(writes) == 1
        w = writes[0]
        assert w.operation == WriteOperation.INSERT
        assert w.layer == "st_epi"

    def test_create_version_one(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].record_data[epi_spec.version_column] == 1

    def test_create_observation_count_one(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].record_data[epi_spec.observation_count_column] == 1

    def test_create_canonical_true(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].record_data[epi_spec.canonical_column] is True

    def test_create_active_status(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert (
            writes[0].record_data[epi_spec.archival_status_column] == epi_spec.active_status_value
        )

    def test_create_generates_record_id(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert len(writes[0].record_id) == 26  # ULID

    def test_create_preserves_candidate_pk(self, epi_spec: TruthLayerSpec) -> None:
        pk = "my-custom-pk-12345"
        meta = {epi_spec.pk_column: pk}
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(
            result,
            _candidate(metadata=meta),
            epi_spec,
            _CYCLE,
        )
        assert writes[0].record_id == pk

    def test_create_source_phase(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].source_phase == "R2"

    def test_create_source_event_ids(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].source_event_ids == ["evt-1", "evt-2"]

    def test_create_no_expected_version(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].expected_version is None

    def test_create_metadata_carried(self, epi_spec: TruthLayerSpec) -> None:
        meta = {"episode_summary": "Trip to park", "mood": "happy"}
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(
            result,
            _candidate(metadata=meta),
            epi_spec,
            _CYCLE,
        )
        assert writes[0].record_data["episode_summary"] == "Trip to park"
        assert writes[0].record_data["mood"] == "happy"


# =========================================================================
# V2: REINFORCE produces UPDATE
# =========================================================================


class TestReinforce:
    def test_reinforce_update(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.REINFORCE, match_id="rec-1")
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert len(writes) == 1
        assert writes[0].operation == WriteOperation.UPDATE

    def test_reinforce_record_id(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.REINFORCE, match_id="rec-1")
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].record_id == "rec-1"

    def test_reinforce_observation_count(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.REINFORCE, match_id="rec-1")
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].record_data[epi_spec.observation_count_column] == 1

    def test_reinforce_last_observed_set(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.REINFORCE, match_id="rec-1")
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        last_obs = epi_spec.temporal.last_observed
        if last_obs:
            assert last_obs in writes[0].record_data
            assert isinstance(writes[0].record_data[last_obs], int)

    def test_reinforce_no_expected_version(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.REINFORCE, match_id="rec-1")
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].expected_version is None


# =========================================================================
# V26: Confidence boost per strategy
# =========================================================================


class TestConfidenceBoost:
    def test_reinforce_no_boost_epi(self, epi_spec: TruthLayerSpec) -> None:
        """st_epi has strategy 'none' -> no boost keys."""
        result = _result(ReconciliationAction.REINFORCE, match_id="rec-1")
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        rd = writes[0].record_data
        assert "_confidence_boost" not in rd
        assert "_confidence_boost_factor" not in rd

    def test_reinforce_additive_boost_sem(self, sem_spec: TruthLayerSpec) -> None:
        """st_sem has strategy 'additive_0.05'."""
        result = _result(
            ReconciliationAction.REINFORCE,
            match_id="rec-1",
            match_layer="st_sem",
        )
        cand = _candidate(layer="st_sem")
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)
        assert writes[0].record_data["_confidence_boost"] == pytest.approx(0.05)

    def test_reinforce_multiplicative_boost_proc(self, proc_spec: TruthLayerSpec) -> None:
        """st_procedural has strategy 'multiplicative_1.1'."""
        result = _result(
            ReconciliationAction.REINFORCE,
            match_id="rec-1",
            match_layer="st_procedural",
        )
        cand = _candidate(layer="st_procedural")
        writes = WriteDecisionRouter.build(result, cand, proc_spec, _CYCLE)
        assert writes[0].record_data["_confidence_boost_factor"] == pytest.approx(1.1)

    def test_reinforce_multiplicative_boost_kg(self, kg_spec: TruthLayerSpec) -> None:
        """st_kg_dom has strategy 'multiplicative_1.1'."""
        result = _result(
            ReconciliationAction.REINFORCE,
            match_id="rec-1",
            match_layer="st_kg_dom",
        )
        cand = _candidate(layer="st_kg_dom")
        writes = WriteDecisionRouter.build(result, cand, kg_spec, _CYCLE)
        assert writes[0].record_data["_confidence_boost_factor"] == pytest.approx(1.1)


# =========================================================================
# EXTEND produces UPDATE (via MergeEngine)
# =========================================================================


class TestExtend:
    def test_extend_update(self, sem_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.EXTEND,
            match_id="rec-1",
            match_layer="st_sem",
        )
        cand = _candidate(layer="st_sem", metadata={"pattern_label": "morning routine"})
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)
        assert len(writes) == 1
        assert writes[0].operation == WriteOperation.UPDATE

    def test_extend_record_id(self, sem_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.EXTEND,
            match_id="rec-1",
            match_layer="st_sem",
        )
        cand = _candidate(layer="st_sem", metadata={})
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)
        assert writes[0].record_id == "rec-1"

    def test_extend_observation_count(self, sem_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.EXTEND,
            match_id="rec-1",
            match_layer="st_sem",
        )
        cand = _candidate(layer="st_sem", metadata={})
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)
        assert writes[0].record_data[sem_spec.observation_count_column] == 1


# =========================================================================
# EVOLVE dispatches to EvolveHandler (tested in test_evolve_handler)
# =========================================================================


class TestEvolveDispatch:
    def test_evolve_produces_two_writes(self, sem_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.EVOLVE,
            match_id="rec-1",
            match_layer="st_sem",
        )
        cand = _candidate(layer="st_sem", metadata={"pattern_label": "evolved"})
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)
        assert len(writes) == 2

    def test_evolve_first_is_update(self, sem_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.EVOLVE,
            match_id="rec-1",
            match_layer="st_sem",
        )
        cand = _candidate(layer="st_sem")
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)
        assert writes[0].operation == WriteOperation.UPDATE

    def test_evolve_second_is_insert(self, sem_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.EVOLVE,
            match_id="rec-1",
            match_layer="st_sem",
        )
        cand = _candidate(layer="st_sem")
        writes = WriteDecisionRouter.build(result, cand, sem_spec, _CYCLE)
        assert writes[1].operation == WriteOperation.INSERT


# =========================================================================
# V15: CONTRADICT inserts to st_learning_queue
# =========================================================================


class TestContradict:
    def test_contradict_layer_is_learning_queue(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.CONTRADICT,
            match_id="rec-1",
            tier=1,
            contradiction_details={
                "correction_source": "user",
                "supersedes_concept": "old-concept",
                "session_context_id": "sess-1",
            },
        )
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert len(writes) == 1
        assert writes[0].layer == "st_learning_queue"

    def test_contradict_is_insert(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.CONTRADICT,
            match_id="rec-1",
            tier=1,
        )
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].operation == WriteOperation.INSERT

    def test_contradict_gap_type(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.CONTRADICT,
            match_id="rec-1",
            tier=1,
        )
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].record_data["gap_type"] == "CONTRADICTION"

    def test_contradict_target_id(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.CONTRADICT,
            match_id="rec-1",
            tier=1,
        )
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].record_data["target_id"] == "rec-1"

    def test_contradict_context_json(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.CONTRADICT,
            match_id="rec-1",
            tier=1,
            contradiction_details={"correction_source": "k1"},
        )
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        ctx = json.loads(writes[0].record_data["context_json"])
        assert ctx["contradiction_reason"] == "test"
        assert ctx["correction_source"] == "k1"

    def test_contradict_tenant_space(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(
            ReconciliationAction.CONTRADICT,
            match_id="rec-1",
            tier=1,
        )
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].record_data["tenant_id"] == "t1"
        assert writes[0].record_data["space_id"] == "s1"


# =========================================================================
# V16, V17: PRUNE produces ARCHIVE or TOMBSTONE
# =========================================================================


class TestPrune:
    def test_prune_archive(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.PRUNE, match_id="rec-1")
        cand = _candidate(metadata={"prune_reason": "decay"})
        writes = WriteDecisionRouter.build(result, cand, epi_spec, _CYCLE)
        assert len(writes) == 1
        assert writes[0].operation == WriteOperation.ARCHIVE

    def test_prune_archive_status(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.PRUNE, match_id="rec-1")
        cand = _candidate(metadata={"prune_reason": "decay"})
        writes = WriteDecisionRouter.build(result, cand, epi_spec, _CYCLE)
        assert writes[0].record_data[epi_spec.archival_status_column] == "ARCHIVED"

    def test_prune_archive_reason(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.PRUNE, match_id="rec-1")
        cand = _candidate(metadata={"prune_reason": "duplicate"})
        writes = WriteDecisionRouter.build(result, cand, epi_spec, _CYCLE)
        assert writes[0].record_data["archived_reason"] == "duplicate"

    def test_prune_archive_default_reason(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.PRUNE, match_id="rec-1")
        cand = _candidate(metadata={})
        writes = WriteDecisionRouter.build(result, cand, epi_spec, _CYCLE)
        assert writes[0].record_data["archived_reason"] == "decay"

    def test_prune_tombstone(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.PRUNE, match_id="rec-1")
        cand = _candidate(metadata={"prune_decision": "TOMBSTONE"})
        writes = WriteDecisionRouter.build(result, cand, epi_spec, _CYCLE)
        assert writes[0].operation == WriteOperation.TOMBSTONE

    def test_prune_tombstone_status(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.PRUNE, match_id="rec-1")
        cand = _candidate(metadata={"prune_decision": "TOMBSTONE"})
        writes = WriteDecisionRouter.build(result, cand, epi_spec, _CYCLE)
        assert writes[0].record_data[epi_spec.archival_status_column] == "TOMBSTONE"

    def test_prune_tombstone_no_reason(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.PRUNE, match_id="rec-1")
        cand = _candidate(metadata={"prune_decision": "TOMBSTONE"})
        writes = WriteDecisionRouter.build(result, cand, epi_spec, _CYCLE)
        assert "archived_reason" not in writes[0].record_data

    def test_prune_record_id(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.PRUNE, match_id="rec-1")
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].record_id == "rec-1"


# =========================================================================
# V19, V20: Idempotency
# =========================================================================


class TestIdempotency:
    def test_idempotency_prefix(self) -> None:
        key = RouterIdempotencyKey.for_write(_CYCLE, "st_epi", "rec-1", "create")
        assert key.startswith("p03:reconcile:")

    def test_idempotency_deterministic(self) -> None:
        k1 = RouterIdempotencyKey.for_write(_CYCLE, "st_epi", "rec-1", "create")
        k2 = RouterIdempotencyKey.for_write(_CYCLE, "st_epi", "rec-1", "create")
        assert k1 == k2

    def test_idempotency_different_actions(self) -> None:
        k1 = RouterIdempotencyKey.for_write(_CYCLE, "st_epi", "rec-1", "create")
        k2 = RouterIdempotencyKey.for_write(_CYCLE, "st_epi", "rec-1", "reinforce")
        assert k1 != k2

    def test_idempotency_different_records(self) -> None:
        k1 = RouterIdempotencyKey.for_write(_CYCLE, "st_epi", "rec-1", "create")
        k2 = RouterIdempotencyKey.for_write(_CYCLE, "st_epi", "rec-2", "create")
        assert k1 != k2

    def test_idempotency_key_format(self) -> None:
        key = RouterIdempotencyKey.for_write("CYC", "st_sem", "REC", "extend")
        assert key == "p03:reconcile:CYC:st_sem:REC:extend"

    def test_batch_key_deterministic(self) -> None:
        k1 = RouterIdempotencyKey.for_batch(_CYCLE, "st_epi", ["e1", "e2", "e3"])
        k2 = RouterIdempotencyKey.for_batch(_CYCLE, "st_epi", ["e3", "e1", "e2"])
        assert k1 == k2  # sorted -> deterministic

    def test_batch_key_prefix(self) -> None:
        key = RouterIdempotencyKey.for_batch(_CYCLE, "st_epi", ["e1"])
        assert key.startswith("p03:reconcile:")
        assert ":batch:" in key

    def test_create_write_has_idempotency(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].idempotency_key.startswith("p03:reconcile:")
        assert ":create" in writes[0].idempotency_key


# =========================================================================
# V21: StagedWrite compatibility (R7 shape)
# =========================================================================


class TestR7Compatibility:
    def test_write_has_write_id(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert len(writes[0].write_id) == 26

    def test_write_has_layer(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].layer == "st_epi"

    def test_write_has_record_data(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert isinstance(writes[0].record_data, dict)

    def test_write_is_staged_write(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert isinstance(writes[0], StagedWrite)

    def test_write_has_created_at_ms(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.CREATE)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes[0].created_at_ms > 0


# =========================================================================
# PENDING action -> empty (defensive)
# =========================================================================


class TestPendingFallback:
    def test_pending_no_writes(self, epi_spec: TruthLayerSpec) -> None:
        result = _result(ReconciliationAction.PENDING)
        writes = WriteDecisionRouter.build(result, _candidate(), epi_spec, _CYCLE)
        assert writes == []


# =========================================================================
# Multi-layer exercise
# =========================================================================


class TestMultiLayer:
    def test_create_on_all_layers(self, registry: TruthLayerRegistry) -> None:
        for layer_name in (
            "st_epi",
            "st_sem",
            "st_procedural",
            "st_social",
            "st_prospective",
            "st_kg_dom",
            "st_kg_edges",
        ):
            spec = registry.get(layer_name)
            result = _result(ReconciliationAction.CREATE, match_layer=layer_name)
            cand = _candidate(layer=layer_name)
            writes = WriteDecisionRouter.build(result, cand, spec, _CYCLE)
            assert len(writes) == 1
            assert writes[0].layer == layer_name
            assert writes[0].operation == WriteOperation.INSERT

    def test_reinforce_on_all_layers(self, registry: TruthLayerRegistry) -> None:
        for layer_name in (
            "st_epi",
            "st_sem",
            "st_procedural",
            "st_social",
            "st_prospective",
            "st_kg_dom",
            "st_kg_edges",
        ):
            spec = registry.get(layer_name)
            result = _result(
                ReconciliationAction.REINFORCE,
                match_id="rec-1",
                match_layer=layer_name,
            )
            cand = _candidate(layer=layer_name)
            writes = WriteDecisionRouter.build(result, cand, spec, _CYCLE)
            assert len(writes) == 1
            assert writes[0].operation == WriteOperation.UPDATE
