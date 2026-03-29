"""EVOLVE handler tests -- 2-write pair, version chain, supersedes linking (M9.5).

Covers validation criteria V12-V14 from the M9.5 spec.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from k0.modules.consolidation.reconciliation.evolve_handler import EvolveHandler
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry, TruthLayerSpec
from k0.modules.consolidation.types import ReconciliationCandidate
from k0.pipelines.p03.event_state import ReconciliationAction
from k0.pipelines.p03.staged_writes import WriteOperation

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "k0" / "contracts" / "schemas"
_CYCLE = "01J0000000000000000000CYCL"


@pytest.fixture()
def registry() -> TruthLayerRegistry:
    return TruthLayerRegistry.from_contracts(_CONTRACTS_DIR)


@pytest.fixture()
def sem_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_sem")


@pytest.fixture()
def epi_spec(registry: TruthLayerRegistry) -> TruthLayerSpec:
    return registry.get("st_epi")


def _candidate(
    layer: str = "st_sem",
    metadata: dict[str, Any] | None = None,
) -> ReconciliationCandidate:
    return ReconciliationCandidate(
        candidate_id="cand-1",
        layer=layer,
        source_phase="R3",
        metadata=metadata or {"pattern_label": "evolved pattern"},
        source_event_ids=("evt-1", "evt-2"),
        cycle_id=_CYCLE,
        tenant_id="t1",
        space_id="s1",
    )


def _result(
    match_id: str = "old-rec-1",
    match_layer: str = "st_sem",
) -> ReconciliationResult:
    return ReconciliationResult(
        action=ReconciliationAction.EVOLVE,
        tier=2,
        match_id=match_id,
        match_layer=match_layer,
        similarity=0.45,
        identity_match=True,
        confidence=0.7,
        reason="schema evolution detected",
        candidate_id="cand-1",
        layer=match_layer,
        cycle_id=_CYCLE,
    )


# =========================================================================
# V12: EVOLVE produces exactly 2 StagedWrites
# =========================================================================


class TestEvolveCount:
    def test_evolve_count(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert len(writes) == 2

    def test_evolve_on_epi(self, epi_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(match_layer="st_epi"),
            _candidate(layer="st_epi"),
            epi_spec,
            _CYCLE,
        )
        assert len(writes) == 2


# =========================================================================
# V13: Write 1 -- old record archived to SUPERSEDED
# =========================================================================


class TestEvolveArchiveOld:
    def test_evolve_archive_operation(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[0].operation == WriteOperation.UPDATE

    def test_evolve_archive_record_id(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(match_id="old-rec-99"),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[0].record_id == "old-rec-99"

    def test_evolve_archive_canonical_false(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[0].record_data[sem_spec.canonical_column] is False

    def test_evolve_archive_status_superseded(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[0].record_data[sem_spec.archival_status_column] == "SUPERSEDED"

    def test_evolve_archive_valid_to(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert "valid_to" in writes[0].record_data
        assert isinstance(writes[0].record_data["valid_to"], int)

    def test_evolve_archive_version_counter(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[0].record_data[sem_spec.version_column] == 1

    def test_evolve_archive_idempotency(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert "evolve_archive" in writes[0].idempotency_key

    def test_evolve_archive_layer(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[0].layer == "st_sem"


# =========================================================================
# V14: Write 2 -- new canonical record with supersedes link
# =========================================================================


class TestEvolveInsertNew:
    def test_evolve_insert_operation(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[1].operation == WriteOperation.INSERT

    def test_evolve_insert_new_record_id(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert len(writes[1].record_id) == 26  # ULID

    def test_evolve_insert_supersedes_id(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(match_id="old-rec-1"),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[1].record_data[sem_spec.supersedes_column] == "old-rec-1"

    def test_evolve_insert_canonical_true(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[1].record_data[sem_spec.canonical_column] is True

    def test_evolve_insert_version_one(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[1].record_data[sem_spec.version_column] == 1

    def test_evolve_insert_observation_one(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[1].record_data[sem_spec.observation_count_column] == 1

    def test_evolve_insert_active_status(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert (
            writes[1].record_data[sem_spec.archival_status_column] == sem_spec.active_status_value
        )

    def test_evolve_insert_idempotency(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert "evolve_create" in writes[1].idempotency_key

    def test_evolve_insert_carries_metadata(self, sem_spec: TruthLayerSpec) -> None:
        cand = _candidate(metadata={"pattern_label": "new pattern"})
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            cand,
            sem_spec,
            _CYCLE,
        )
        assert writes[1].record_data.get("pattern_label") == "new pattern"


# =========================================================================
# Version chain linking
# =========================================================================


class TestVersionChain:
    def test_supersedes_links_old_to_new(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(match_id="old-rec-1"),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        old_id = writes[0].record_id
        new_supersedes = writes[1].record_data[sem_spec.supersedes_column]
        assert new_supersedes == old_id

    def test_new_pk_in_record_data(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        assert writes[1].record_data[sem_spec.pk_column] == writes[1].record_id

    def test_custom_pk_from_candidate(self, sem_spec: TruthLayerSpec) -> None:
        cand = _candidate(metadata={sem_spec.pk_column: "custom-pk"})
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            cand,
            sem_spec,
            _CYCLE,
        )
        assert writes[1].record_id == "custom-pk"


# =========================================================================
# Source provenance
# =========================================================================


class TestProvenance:
    def test_evolve_source_phase(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        for w in writes:
            assert w.source_phase == "R3"

    def test_evolve_source_event_ids(self, sem_spec: TruthLayerSpec) -> None:
        writes = EvolveHandler.build_evolve_pair(
            _result(),
            _candidate(),
            sem_spec,
            _CYCLE,
        )
        for w in writes:
            assert w.source_event_ids == ["evt-1", "evt-2"]
