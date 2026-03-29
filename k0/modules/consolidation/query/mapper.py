"""TruthCandidateMapper -- M9.3 row-to-TruthRecord mapping.

Maps asyncpg Record rows to TruthRecord (M9.2 type).
Handles pgvector VECTOR(768) decoding, confidence normalisation,
and per-layer metadata extraction.
"""

from __future__ import annotations

import json
import struct
from typing import TYPE_CHECKING, Any

from k0.modules.consolidation.query.builder import EXTRA_COLUMNS
from k0.modules.consolidation.types import TruthRecord

if TYPE_CHECKING:
    from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry


class TruthCandidateMapper:
    """Maps asyncpg Row to TruthRecord (M9.2 type)."""

    def __init__(self, registry: TruthLayerRegistry) -> None:
        self._registry = registry

    def map_row(self, row: Any, layer: str) -> TruthRecord:
        """Map one DB row to a TruthRecord.

        The similarity field comes from the SQL SELECT (computed by pgvector
        for EMBEDDING/HYBRID, 0.0 for KEY mode).
        """
        return TruthRecord(
            record_id=str(row["record_id"]),
            layer=str(row["layer"]),
            embedding=None,  # Not fetched in the query (pgvector does similarity in SQL)
            confidence=float(row["confidence"] or 0.0),
            version=int(row["version"] or 0),
            observation_count=int(row["observation_count"] or 0),
            last_observed_ms=int(row["last_observed_ms"] or 0),
            metadata=self._extract_metadata(row, layer),
        )

    def _extract_metadata(self, row: Any, layer: str) -> dict[str, Any]:
        """Extract layer-specific columns into metadata dict.

        Includes the similarity score (computed by pgvector in SQL)
        and all extra columns declared in EXTRA_COLUMNS for this layer.
        """
        meta: dict[str, Any] = {}

        # Similarity from SQL (always present)
        sim = row.get("similarity") if hasattr(row, "get") else row["similarity"]
        meta["similarity"] = float(sim) if sim is not None else 0.0

        # Extra columns for this layer
        extras = EXTRA_COLUMNS.get(layer, ())
        for col in extras:
            val = _safe_get(row, col)
            if val is not None:
                meta[col] = _parse_json_column(col, val)

        return meta


def decode_vector(raw: Any) -> list[float] | None:
    """Decode pgvector VECTOR(768) from asyncpg.

    asyncpg returns VECTOR columns as strings: "[0.1,0.2,...,0.768]"
    Three-path handling (matching R0 batch selector pattern):
    1. str  -> json.loads  (pgvector native, current)
    2. list/tuple -> direct (pgvector extension codec)
    3. bytes -> struct.unpack (legacy BYTEA, pre-M4)
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, (list, tuple)):
        return [float(x) for x in raw]
    if isinstance(raw, (bytes, bytearray)):
        dim = len(raw) // 4
        return list(struct.unpack(f"<{dim}f", raw))
    return None


def _safe_get(row: Any, col: str) -> Any:
    """Get a column value from an asyncpg Record or dict, returning None on miss."""
    try:
        return row[col]
    except (KeyError, IndexError, TypeError):
        return None


_JSON_SUFFIXES = ("_json",)


def _parse_json_column(col: str, val: Any) -> Any:
    """Parse JSON string columns into dicts/lists when applicable."""
    if val is None:
        return val
    if col.endswith(_JSON_SUFFIXES[0]) and isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val
