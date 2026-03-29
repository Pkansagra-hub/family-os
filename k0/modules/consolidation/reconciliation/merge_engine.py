"""MergeEngine -- data-driven per-column merge for EXTEND operations (M9.5).

Reads merge rules from TruthLayerSpec.columns and produces the
record_data dict that R7 layer writers execute.  No SQL generation --
the merge rule enum tells R7 *how* to apply each value.
"""

from __future__ import annotations

import time
from typing import Any

from k0.modules.consolidation.truth_layer_registry import ColumnSpec, MergeRule, TruthLayerSpec


def _now_ms() -> int:
    return int(time.time() * 1000)


class MergeEngine:
    """Data-driven per-column merge for EXTEND operations.

    Reads merge rules from ``TruthLayerSpec.columns``.
    Produces ``record_data`` dicts that R7 layer writers consume.
    """

    @staticmethod
    def build_extend_data(
        spec: TruthLayerSpec,
        candidate_data: dict[str, Any],
        existing_record_id: str,
    ) -> dict[str, Any]:
        """Build the UPDATE record_data by applying merge rules.

        Iterates ``spec.columns``; for each column present in
        *candidate_data*, applies the declared ``MergeRule``.

        Returns:
            Dict suitable for ``StagedWrite.record_data``.
        """
        record_data: dict[str, Any] = {}

        for col_name, col_spec in spec.columns.items():
            if col_name not in candidate_data:
                continue

            new_value = candidate_data[col_name]
            merged = _apply_rule(col_spec, new_value, record_data)
            if merged is not _SKIP:
                record_data[col_name] = merged

        # Always include observation bump and last_observed.
        record_data[spec.observation_count_column] = 1  # COUNTER: +1 in R7 SQL
        if spec.temporal.last_observed:
            record_data[spec.temporal.last_observed] = _now_ms()

        return record_data


# Sentinel for "do not include this column".
_SKIP = object()


def _apply_rule(
    col_spec: ColumnSpec,
    new_value: Any,
    record_data: dict[str, Any],
) -> Any:
    """Return the value to set, or ``_SKIP`` to omit."""
    rule = col_spec.merge

    if rule == MergeRule.IMMUTABLE:
        return _SKIP

    if rule == MergeRule.DERIVED:
        return _SKIP

    if rule == MergeRule.COUNTER:
        return new_value

    if rule == MergeRule.REPLACED:
        return new_value

    if rule == MergeRule.COALESCE:
        return new_value

    if rule == MergeRule.APPENDABLE_DISTINCT:
        return new_value

    if rule == MergeRule.APPENDABLE_ALL:
        return new_value

    if rule == MergeRule.APPENDABLE_CAPPED:
        record_data[f"_{col_spec.name}_cap"] = col_spec.cap
        return new_value

    if rule == MergeRule.ADDITIVE_MERGE:
        return new_value

    if rule == MergeRule.SHALLOW_MERGE:
        return new_value

    if rule == MergeRule.TEMPORAL_MIN:
        return new_value

    if rule == MergeRule.TEMPORAL_MAX:
        return new_value

    if rule == MergeRule.EMA:
        record_data[f"_{col_spec.name}_alpha"] = col_spec.ema_alpha
        return new_value

    if rule == MergeRule.TREND:
        return new_value

    if rule == MergeRule.PG_ARRAY_CONCAT:
        return new_value

    if rule == MergeRule.STATUS:
        return new_value

    return _SKIP  # Unknown rule -- safe fallback
