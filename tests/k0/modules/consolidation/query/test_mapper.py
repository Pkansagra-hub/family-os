"""Tests for TruthCandidateMapper -- M9.3 D9.

Row-to-TruthRecord mapping: vector decoding, metadata extraction,
confidence normalisation, null handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k0.modules.consolidation.query.builder import EXTRA_COLUMNS
from k0.modules.consolidation.query.mapper import (
    TruthCandidateMapper,
    _parse_json_column,
    _safe_get,
    decode_vector,
)
from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry
from k0.modules.consolidation.types import TruthRecord

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "k0" / "contracts" / "schemas"


@pytest.fixture(scope="module")
def registry() -> TruthLayerRegistry:
    return TruthLayerRegistry.from_contracts(CONTRACTS_DIR)


@pytest.fixture(scope="module")
def mapper(registry: TruthLayerRegistry) -> TruthCandidateMapper:
    return TruthCandidateMapper(registry)


def _fake_row(layer: str, **overrides) -> dict:
    """Build a dict mimicking an asyncpg Record for a given layer."""
    base = {
        "record_id": "rec_001",
        "layer": layer,
        "similarity": 0.87,
        "confidence": 0.75,
        "version": 3,
        "observation_count": 12,
        "last_observed_ms": 1700000000000,
    }
    # Add dummy extra columns for the layer
    for col in EXTRA_COLUMNS.get(layer, ()):
        if col.endswith("_json"):
            base[col] = '{"key": "value"}'
        else:
            base[col] = f"test_{col}"
    base.update(overrides)
    return base


# ===========================================================================
# decode_vector
# ===========================================================================


class TestDecodeVector:
    def test_none_returns_none(self):
        assert decode_vector(None) is None

    def test_string_pgvector_format(self):
        raw = "[0.1,0.2,0.3]"
        result = decode_vector(raw)
        assert result == [0.1, 0.2, 0.3]

    def test_string_768_dim(self):
        vals = [float(i) / 768 for i in range(768)]
        raw = "[" + ",".join(str(v) for v in vals) + "]"
        result = decode_vector(raw)
        assert len(result) == 768
        assert abs(result[0] - vals[0]) < 1e-10

    def test_list_passthrough(self):
        raw = [0.1, 0.2, 0.3]
        result = decode_vector(raw)
        assert result == [0.1, 0.2, 0.3]

    def test_tuple_to_list(self):
        raw = (0.5, 0.6)
        result = decode_vector(raw)
        assert result == [0.5, 0.6]

    def test_bytes_legacy(self):
        import struct

        vals = [0.1, 0.2, 0.3]
        raw = struct.pack(f"<{len(vals)}f", *vals)
        result = decode_vector(raw)
        assert len(result) == 3
        assert abs(result[0] - 0.1) < 1e-6

    def test_unknown_type_returns_none(self):
        assert decode_vector(42) is None
        assert decode_vector(object()) is None


# ===========================================================================
# _safe_get
# ===========================================================================


class TestSafeGet:
    def test_dict_hit(self):
        assert _safe_get({"a": 1}, "a") == 1

    def test_dict_miss(self):
        assert _safe_get({"a": 1}, "b") is None

    def test_index_error(self):
        # list with string key raises TypeError, caught as None
        assert _safe_get({}, "x") is None


# ===========================================================================
# _parse_json_column
# ===========================================================================


class TestParseJsonColumn:
    def test_json_suffix_parses(self):
        result = _parse_json_column("participants_json", '["Alice","Bob"]')
        assert result == ["Alice", "Bob"]

    def test_json_suffix_invalid_returns_raw(self):
        result = _parse_json_column("aliases_json", "not-json")
        assert result == "not-json"

    def test_non_json_suffix_passthrough(self):
        result = _parse_json_column("entity_type", "PERSON")
        assert result == "PERSON"

    def test_none_returns_none(self):
        assert _parse_json_column("any_json", None) is None


# ===========================================================================
# TruthCandidateMapper.map_row
# ===========================================================================


class TestMapRow:
    @pytest.mark.parametrize("layer", list(EXTRA_COLUMNS.keys()))
    def test_map_row_produces_truth_record(self, mapper, layer):
        row = _fake_row(layer)
        result = mapper.map_row(row, layer)
        assert isinstance(result, TruthRecord)
        assert result.record_id == "rec_001"
        assert result.layer == layer
        assert result.confidence == 0.75
        assert result.version == 3
        assert result.observation_count == 12
        assert result.last_observed_ms == 1700000000000

    @pytest.mark.parametrize("layer", list(EXTRA_COLUMNS.keys()))
    def test_map_row_metadata_contains_similarity(self, mapper, layer):
        row = _fake_row(layer, similarity=0.92)
        result = mapper.map_row(row, layer)
        assert result.metadata["similarity"] == pytest.approx(0.92)

    @pytest.mark.parametrize("layer", list(EXTRA_COLUMNS.keys()))
    def test_map_row_metadata_contains_extra_columns(self, mapper, layer):
        row = _fake_row(layer)
        result = mapper.map_row(row, layer)
        for col in EXTRA_COLUMNS[layer]:
            assert col in result.metadata

    def test_map_row_json_columns_parsed(self, mapper):
        row = _fake_row("st_epi", participants_json='["Alice","Bob"]')
        result = mapper.map_row(row, "st_epi")
        assert result.metadata["participants_json"] == ["Alice", "Bob"]

    def test_map_row_null_confidence(self, mapper):
        row = _fake_row("st_epi", confidence=None)
        result = mapper.map_row(row, "st_epi")
        assert result.confidence == 0.0

    def test_map_row_null_version(self, mapper):
        row = _fake_row("st_epi", version=None)
        result = mapper.map_row(row, "st_epi")
        assert result.version == 0

    def test_map_row_null_observation_count(self, mapper):
        row = _fake_row("st_epi", observation_count=None)
        result = mapper.map_row(row, "st_epi")
        assert result.observation_count == 0

    def test_map_row_null_last_observed_ms(self, mapper):
        row = _fake_row("st_epi", last_observed_ms=None)
        result = mapper.map_row(row, "st_epi")
        assert result.last_observed_ms == 0

    def test_map_row_null_similarity(self, mapper):
        row = _fake_row("st_epi", similarity=None)
        result = mapper.map_row(row, "st_epi")
        assert result.metadata["similarity"] == 0.0

    def test_map_row_zero_similarity(self, mapper):
        row = _fake_row("st_kg_edges", similarity=0.0)
        result = mapper.map_row(row, "st_kg_edges")
        assert result.metadata["similarity"] == 0.0

    def test_map_row_embedding_is_none(self, mapper):
        """Mapper does NOT fetch embeddings (pgvector does similarity in SQL)."""
        row = _fake_row("st_epi")
        result = mapper.map_row(row, "st_epi")
        assert result.embedding is None

    def test_map_row_record_is_frozen(self, mapper):
        row = _fake_row("st_epi")
        result = mapper.map_row(row, "st_epi")
        with pytest.raises(AttributeError):
            result.record_id = "new_id"  # type: ignore
