"""Truth Layer Registry -- M9.1 (Universal Reconciliation Engine).

Single source of truth for every truth layer's metadata, column inventory,
and merge rules.  Loads from YAML contracts in ``k0/contracts/schemas/``.
Replaces 9+ scattered registries across the codebase.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts" / "schemas"

# Only these tables are truth layers (excludes st_vec, st_hipp_events, etc.)
_TRUTH_LAYER_SCHEMAS: frozenset[str] = frozenset(
    {
        "st_epi",
        "st_sem",
        "st_procedural",
        "st_social",
        "st_prospective",
        "st_kg_dom",
        "st_kg_edges",
    }
)


# ---------------------------------------------------------------------------
# MergeRule Enum (16 types)
# ---------------------------------------------------------------------------


class MergeRule(enum.Enum):
    """Taxonomy of column-level merge behaviours across all truth writers."""

    IMMUTABLE = "immutable"
    COUNTER = "counter"
    REPLACED = "replaced"
    COALESCE = "coalesce"
    APPENDABLE_DISTINCT = "appendable_distinct"
    APPENDABLE_ALL = "appendable_all"
    APPENDABLE_CAPPED = "appendable_capped"
    ADDITIVE_MERGE = "additive_merge"
    SHALLOW_MERGE = "shallow_merge"
    TEMPORAL_MIN = "temporal_min"
    TEMPORAL_MAX = "temporal_max"
    EMA = "ema"
    TREND = "trend"
    DERIVED = "derived"
    PG_ARRAY_CONCAT = "pg_array_concat"
    STATUS = "status"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciliationThresholds:
    """Score thresholds that determine reconciliation action."""

    reinforce: float
    extend: float
    evolve: float


@dataclass(frozen=True)
class TemporalSpec:
    """Temporal column mapping for EXTEND / REINFORCE merge paths."""

    start: str | None
    end: str | None
    last_observed: str | None
    first_observed: str | None


@dataclass(frozen=True)
class ColumnSpec:
    """Schema and merge metadata for a single column."""

    name: str
    sql_type: str
    nullable: bool
    merge: MergeRule
    cap: int | None = None
    ema_alpha: float | None = None
    trend_alpha: float | None = None
    description: str = ""


@dataclass(frozen=True)
class TruthLayerSpec:
    """Complete metadata for one truth layer, built from its YAML contract."""

    # Identity
    layer_name: str
    pk_column: str

    # Version control
    version_column: str
    supersedes_column: str
    canonical_column: str

    # Observation tracking
    observation_count_column: str
    confidence_column: str
    confidence_boost_strategy: str

    # Lifecycle
    archival_status_column: str
    active_status_value: str

    # Decay
    decay_lambda: float

    # Matching capabilities
    embedding_fk_column: str | None
    supports_embedding_match: bool
    supports_key_match: bool
    identity_columns: tuple[str, ...]

    # Write ordering
    write_order: int

    # Temporal
    temporal: TemporalSpec

    # Thresholds
    thresholds: ReconciliationThresholds

    # All columns with merge rules
    columns: dict[str, ColumnSpec] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# YAML -> Dataclass Parsing
# ---------------------------------------------------------------------------


def _parse_merge_rule(raw: str) -> MergeRule:
    """Convert a YAML merge string to the ``MergeRule`` enum."""
    try:
        return MergeRule(raw)
    except ValueError:
        raise ValueError(f"Unknown merge rule: {raw!r}") from None


def _parse_column(name: str, raw: dict[str, Any]) -> ColumnSpec:
    merge = _parse_merge_rule(raw["merge"])
    return ColumnSpec(
        name=name,
        sql_type=raw["type"],
        nullable=raw["nullable"],
        merge=merge,
        cap=raw.get("cap"),
        ema_alpha=raw.get("ema_alpha"),
        trend_alpha=raw.get("trend_alpha"),
        description=raw.get("description", ""),
    )


def _parse_contract(path: Path) -> TruthLayerSpec | None:
    """Load a single ``*.columns.yaml`` and return a ``TruthLayerSpec``.

    Returns ``None`` when the file describes a non-truth-layer schema
    (e.g. ``st_vec``).
    """
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    schema: str = data["schema"]
    if schema not in _TRUTH_LAYER_SCHEMAS:
        return None

    meta = data["layer_metadata"]

    temporal = TemporalSpec(
        start=meta["temporal"].get("start"),
        end=meta["temporal"].get("end"),
        last_observed=meta["temporal"].get("last_observed"),
        first_observed=meta["temporal"].get("first_observed"),
    )

    thresholds = ReconciliationThresholds(
        reinforce=meta["thresholds"]["reinforce"],
        extend=meta["thresholds"]["extend"],
        evolve=meta["thresholds"]["evolve"],
    )

    columns: dict[str, ColumnSpec] = {}
    for col_name, col_raw in data["columns"].items():
        columns[col_name] = _parse_column(col_name, col_raw)

    identity_raw = meta.get("identity_columns") or []

    return TruthLayerSpec(
        layer_name=schema,
        pk_column=meta["pk"],
        version_column=meta["version_column"],
        supersedes_column=meta["supersedes_column"],
        canonical_column=meta["canonical_column"],
        observation_count_column=meta["observation_count_column"],
        confidence_column=meta["confidence_column"],
        confidence_boost_strategy=meta["confidence_boost_strategy"],
        archival_status_column=meta["archival_status_column"],
        active_status_value=meta["active_status_value"],
        decay_lambda=meta["decay_lambda"],
        embedding_fk_column=meta.get("embedding_fk_column"),
        supports_embedding_match=meta["supports_embedding_match"],
        supports_key_match=meta["supports_key_match"],
        identity_columns=tuple(identity_raw),
        write_order=meta["write_order"],
        temporal=temporal,
        thresholds=thresholds,
        columns=columns,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TruthLayerRegistry:
    """Single source of truth for all truth layer metadata.

    Loads from YAML contracts in ``k0/contracts/schemas/``.
    Replaces scattered registries across the codebase.
    """

    def __init__(self) -> None:
        self._layers: dict[str, TruthLayerSpec] = {}

    # -- Construction -------------------------------------------------------

    @classmethod
    def from_contracts(cls, contracts_dir: Path | None = None) -> TruthLayerRegistry:
        """Load all ``*.columns.yaml`` from *contracts_dir*.

        Only files whose ``schema`` key is in :data:`_TRUTH_LAYER_SCHEMAS` are
        loaded.  Defaults to ``k0/contracts/schemas/``.
        """
        directory = contracts_dir or _CONTRACTS_DIR
        registry = cls()

        for path in sorted(directory.glob("*.columns.yaml")):
            spec = _parse_contract(path)
            if spec is not None:
                registry._layers[spec.layer_name] = spec

        return registry

    # -- Queries ------------------------------------------------------------

    def get(self, layer_name: str) -> TruthLayerSpec:
        """Return spec for a layer.  Raises ``KeyError`` if not registered."""
        try:
            return self._layers[layer_name]
        except KeyError:
            raise KeyError(
                f"Unknown truth layer: {layer_name!r}. " f"Registered: {sorted(self._layers)}"
            ) from None

    def all_layers(self) -> list[TruthLayerSpec]:
        """All registered layer specs, sorted by ``write_order``."""
        return sorted(self._layers.values(), key=lambda s: s.write_order)

    def truth_layer_names(self) -> frozenset[str]:
        """All registered layer names."""
        return frozenset(self._layers)

    def merge_rules_for(self, layer_name: str) -> dict[str, MergeRule]:
        """Column -> MergeRule mapping for *layer_name*."""
        spec = self.get(layer_name)
        return {name: col.merge for name, col in spec.columns.items()}

    def appendable_columns(self, layer_name: str) -> list[str]:
        """Columns with ``APPENDABLE_*`` merge rules (JSON union targets)."""
        spec = self.get(layer_name)
        return [
            name
            for name, col in spec.columns.items()
            if col.merge
            in (
                MergeRule.APPENDABLE_DISTINCT,
                MergeRule.APPENDABLE_ALL,
                MergeRule.APPENDABLE_CAPPED,
            )
        ]

    def __len__(self) -> int:
        return len(self._layers)

    def __contains__(self, layer_name: str) -> bool:
        return layer_name in self._layers

    def __repr__(self) -> str:
        return f"TruthLayerRegistry(layers={sorted(self._layers)})"
