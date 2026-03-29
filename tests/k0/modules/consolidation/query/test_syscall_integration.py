"""Tests for truth_candidates_query syscall -- M9.3 D12.

End-to-end: syscall -> capability gate -> builder -> SQL -> mapper -> TruthRecord.
Uses mock UoW/connection so we can run without a real database.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from k0.modules.consolidation.query import (
    QueryMode,
    TruthCandidateRequest,
    TruthCandidateResponse,
    resolve_query_mode,
)
from k0.modules.consolidation.query.builder import EXTRA_COLUMNS
from k0.modules.consolidation.types import TruthRecord

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "k0" / "contracts" / "schemas"


def _make_fake_row(layer: str, record_id: str = "rec_001", similarity: float = 0.85) -> dict:
    """Build a dict mimicking an asyncpg Record."""
    base = {
        "record_id": record_id,
        "layer": layer,
        "similarity": similarity,
        "confidence": 0.75,
        "version": 3,
        "observation_count": 12,
        "last_observed_ms": 1700000000000,
    }
    for col in EXTRA_COLUMNS.get(layer, ()):
        if col.endswith("_json"):
            base[col] = "{}"
        else:
            base[col] = f"test_{col}"
    return base


class _FakeConn:
    """Fake asyncpg connection that returns pre-configured rows."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    async def fetch(self, sql: str, *params: Any) -> list[dict]:
        return self._rows


class _FakeUoW:
    """Fake UnitOfWork context manager."""

    def __init__(self, conn):
        self._connection = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _make_syscalls(
    granted_caps: set[str],
    rows_per_layer: dict[str, list[dict]] | None = None,
) -> Any:
    """Create a Syscalls instance with fake UoW."""
    from k0.kernel.syscalls import Syscalls

    default_rows = rows_per_layer or {}

    # The conn will track which SQL was called
    call_log: list[tuple[str, tuple]] = []

    class TrackingConn:
        async def fetch(self, sql: str, *params: Any) -> list[dict]:
            call_log.append((sql, params))
            # Figure out which layer from the SQL
            for layer in EXTRA_COLUMNS:
                if f"FROM {layer} t" in sql:
                    return default_rows.get(layer, [])
            return []

    conn = TrackingConn()
    uow = _FakeUoW(conn)
    syscalls = Syscalls(
        pipeline_id="P03_test",
        granted_caps=granted_caps,
        uow_factory=lambda: uow,
    )
    return syscalls, call_log


def _make_request(**overrides) -> TruthCandidateRequest:
    defaults = {
        "tenant_id": "t1",
        "space_id": "s1",
        "layers": ("st_epi",),
        "query_embedding": [0.1] * 768,
        "top_k": 10,
        "min_similarity": 0.35,
    }
    defaults.update(overrides)
    return TruthCandidateRequest(**defaults)


# ===========================================================================
# Capability enforcement
# ===========================================================================


class TestCapabilityEnforcement:
    def test_missing_capability_raises_permission_error(self):
        from k0.kernel.syscalls import PermissionError as SyscallPermError

        syscalls, _ = _make_syscalls(granted_caps=set())
        req = _make_request()
        with pytest.raises(SyscallPermError):
            asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))

    def test_granted_capability_allows_query(self):
        rows = {"st_epi": [_make_fake_row("st_epi")]}
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer=rows,
        )
        req = _make_request()
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert isinstance(result, TruthCandidateResponse)
        assert result.total_count == 1


# ===========================================================================
# Response structure
# ===========================================================================


class TestResponseStructure:
    def test_response_has_expected_fields(self):
        rows = {"st_epi": [_make_fake_row("st_epi")]}
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer=rows,
        )
        req = _make_request()
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert result.layers_queried == ("st_epi",)
        assert "st_epi" in result.modes_used
        assert result.elapsed_ms > 0
        assert len(result.query_id) > 0
        assert result.errors == {}

    def test_candidates_are_truth_records(self):
        rows = {"st_epi": [_make_fake_row("st_epi", "rec_1"), _make_fake_row("st_epi", "rec_2")]}
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer=rows,
        )
        req = _make_request()
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert result.total_count == 2
        for rec in result.candidates["st_epi"]:
            assert isinstance(rec, TruthRecord)
            assert rec.layer == "st_epi"


# ===========================================================================
# Multi-layer queries
# ===========================================================================


class TestMultiLayer:
    def test_multi_layer_query(self):
        rows = {
            "st_epi": [_make_fake_row("st_epi", "epi_1")],
            "st_sem": [_make_fake_row("st_sem", "sem_1")],
        }
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer=rows,
        )
        req = _make_request(layers=("st_epi", "st_sem"))
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert result.total_count == 2
        assert len(result.candidates["st_epi"]) == 1
        assert len(result.candidates["st_sem"]) == 1

    def test_all_seven_layers(self):
        all_layers = tuple(EXTRA_COLUMNS.keys())
        rows = {layer: [_make_fake_row(layer)] for layer in all_layers}
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer=rows,
        )
        req = _make_request(
            layers=all_layers,
            key_filters={
                "source_entity_id": "e1",
                "target_entity_id": "e2",
                "relation_type": "KNOWS",
                "entity_type": "PERSON",
                "canonical_name": "test",
            },
        )
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert result.total_count == 7
        for layer in all_layers:
            assert layer in result.candidates

    def test_empty_result_for_layer(self):
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer={},
        )
        req = _make_request(layers=("st_epi",))
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert result.total_count == 0
        assert result.candidates.get("st_epi", []) == []


# ===========================================================================
# Query mode detection
# ===========================================================================


class TestQueryModeDetection:
    def test_embedding_layers_use_expected_mode(self):
        expected = {
            "st_epi": "embedding",
            "st_sem": "embedding",
            "st_procedural": "hybrid",  # has identity_columns
            "st_social": "hybrid",  # has identity_columns
            "st_prospective": "embedding",
        }
        layers = tuple(expected.keys())
        rows = {layer: [] for layer in layers}
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer=rows,
        )
        req = _make_request(layers=layers)
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        for layer, mode_str in expected.items():
            assert (
                result.modes_used[layer] == mode_str
            ), f"{layer}: expected {mode_str}, got {result.modes_used[layer]}"

    def test_kg_edges_uses_key_mode(self):
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer={"st_kg_edges": []},
        )
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={"source_entity_id": "e1"},
        )
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert result.modes_used["st_kg_edges"] == "key"

    def test_kg_dom_uses_hybrid_mode(self):
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer={"st_kg_dom": []},
        )
        req = _make_request(
            layers=("st_kg_dom",),
            key_filters={"entity_type": "PERSON"},
        )
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert result.modes_used["st_kg_dom"] == "hybrid"


# ===========================================================================
# SQL verification (via call log)
# ===========================================================================


class TestSqlVerification:
    def test_embedding_query_uses_pgvector(self):
        syscalls, call_log = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer={"st_epi": []},
        )
        req = _make_request(layers=("st_epi",))
        asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert len(call_log) == 1
        sql, params = call_log[0]
        assert "<=> $1::vector" in sql
        assert "ORDER BY v.vector <=> $1::vector ASC" in sql

    def test_key_query_has_where_clause(self):
        syscalls, call_log = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer={"st_kg_edges": []},
        )
        req = _make_request(
            layers=("st_kg_edges",),
            query_embedding=None,
            key_filters={"source_entity_id": "ent_1"},
        )
        asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        sql, params = call_log[0]
        assert "source_entity_id = $" in sql
        assert "ent_1" in params

    def test_no_python_cosine(self):
        """V12: No Python-side cosine computation in query module."""
        import inspect

        from k0.modules.consolidation.query import builder, mapper

        for mod in [builder, mapper]:
            src = inspect.getsource(mod)
            assert "np.dot" not in src
            assert "numpy.dot" not in src
            assert "cosine_similarity" not in src


# ===========================================================================
# Error handling
# ===========================================================================


class TestErrorHandling:
    def test_unknown_layer_records_error(self):
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer={},
        )
        req = _make_request(layers=("st_nonexistent",))
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert "st_nonexistent" in result.errors
        assert result.total_count == 0

    def test_partial_success(self):
        """One layer succeeds, another fails."""
        rows = {"st_epi": [_make_fake_row("st_epi")]}
        syscalls, _ = _make_syscalls(
            granted_caps={"truth.reconcile.read"},
            rows_per_layer=rows,
        )
        req = _make_request(layers=("st_epi", "st_nonexistent"))
        result = asyncio.get_event_loop().run_until_complete(syscalls.truth_candidates_query(req))
        assert result.total_count == 1
        assert "st_epi" in result.candidates
        assert "st_nonexistent" in result.errors


# ===========================================================================
# resolve_query_mode
# ===========================================================================


class TestResolveQueryMode:
    def test_embedding_only(self):
        assert resolve_query_mode(True, False) == QueryMode.EMBEDDING

    def test_key_only(self):
        assert resolve_query_mode(False, True) == QueryMode.KEY

    def test_both_is_hybrid(self):
        assert resolve_query_mode(True, True) == QueryMode.HYBRID

    def test_neither_defaults_to_key(self):
        assert resolve_query_mode(False, False) == QueryMode.KEY

    def test_override_takes_precedence(self):
        assert resolve_query_mode(True, False, QueryMode.KEY) == QueryMode.KEY
        assert resolve_query_mode(False, True, QueryMode.EMBEDDING) == QueryMode.EMBEDDING


# ===========================================================================
# TruthCandidateRequest / TruthCandidateResponse
# ===========================================================================


class TestRequestResponse:
    def test_request_frozen(self):
        req = _make_request()
        with pytest.raises(AttributeError):
            req.tenant_id = "new"  # type: ignore

    def test_response_frozen(self):
        resp = TruthCandidateResponse(
            candidates={},
            total_count=0,
            layers_queried=(),
            modes_used={},
            elapsed_ms=0.0,
            query_id="q1",
        )
        with pytest.raises(AttributeError):
            resp.total_count = 5  # type: ignore

    def test_request_defaults(self):
        req = TruthCandidateRequest(
            tenant_id="t1",
            space_id="s1",
            layers=("st_epi",),
        )
        assert req.query_embedding is None
        assert req.key_filters == {}
        assert req.top_k == 10
        assert req.min_similarity == 0.0
        assert req.mode is None
        assert req.timeout_ms == 5000

    def test_response_errors_default(self):
        resp = TruthCandidateResponse(
            candidates={},
            total_count=0,
            layers_queried=(),
            modes_used={},
            elapsed_ms=0.0,
            query_id="q1",
        )
        assert resp.errors == {}
