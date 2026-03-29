"""Contract validation tests for truth layer YAML contracts (M9.1 D11).

Validates structural integrity, cross-contract consistency, and schema
correctness of all 7 truth layer YAML contracts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from k0.modules.consolidation.truth_layer_registry import (
    _TRUTH_LAYER_SCHEMAS,
    MergeRule,
    TruthLayerRegistry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "k0" / "contracts" / "schemas"


@pytest.fixture(scope="module")
def registry() -> TruthLayerRegistry:
    return TruthLayerRegistry.from_contracts()


@pytest.fixture(scope="module")
def all_contracts() -> dict[str, dict]:
    """Load raw YAML data for all truth layer contracts."""
    result = {}
    for path in sorted(CONTRACTS_DIR.glob("*.columns.yaml")):
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if data["schema"] in _TRUTH_LAYER_SCHEMAS:
            result[data["schema"]] = data
    return result


# ---------------------------------------------------------------------------
# YAML Structural Integrity
# ---------------------------------------------------------------------------


class TestYamlStructure:

    def test_all_seven_contracts_exist(self, all_contracts: dict[str, dict]) -> None:
        assert set(all_contracts.keys()) == _TRUTH_LAYER_SCHEMAS

    @pytest.mark.parametrize("schema", sorted(_TRUTH_LAYER_SCHEMAS))
    def test_required_top_level_keys(self, all_contracts: dict[str, dict], schema: str) -> None:
        data = all_contracts[schema]
        for key in ("schema", "version", "migrations", "column_count", "layer_metadata", "columns"):
            assert key in data, f"{schema} missing top-level key: {key}"

    @pytest.mark.parametrize("schema", sorted(_TRUTH_LAYER_SCHEMAS))
    def test_required_metadata_keys(self, all_contracts: dict[str, dict], schema: str) -> None:
        meta = all_contracts[schema]["layer_metadata"]
        required = [
            "pk",
            "version_column",
            "supersedes_column",
            "canonical_column",
            "observation_count_column",
            "confidence_column",
            "confidence_boost_strategy",
            "archival_status_column",
            "active_status_value",
            "decay_lambda",
            "supports_embedding_match",
            "supports_key_match",
            "identity_columns",
            "write_order",
            "temporal",
            "thresholds",
        ]
        for key in required:
            assert key in meta, f"{schema} metadata missing: {key}"

    @pytest.mark.parametrize("schema", sorted(_TRUTH_LAYER_SCHEMAS))
    def test_column_count_matches_columns(
        self, all_contracts: dict[str, dict], schema: str
    ) -> None:
        data = all_contracts[schema]
        declared = data["column_count"]
        actual = len(data["columns"])
        assert actual == declared, (
            f"{schema}: declared column_count={declared}, " f"actual columns={actual}"
        )

    @pytest.mark.parametrize("schema", sorted(_TRUTH_LAYER_SCHEMAS))
    def test_each_column_has_required_fields(
        self, all_contracts: dict[str, dict], schema: str
    ) -> None:
        for col_name, col_data in all_contracts[schema]["columns"].items():
            for field in ("type", "nullable", "merge"):
                assert field in col_data, f"{schema}.{col_name} missing field: {field}"


# ---------------------------------------------------------------------------
# Merge Rule Validity
# ---------------------------------------------------------------------------


class TestMergeRuleValidity:

    @pytest.mark.parametrize("schema", sorted(_TRUTH_LAYER_SCHEMAS))
    def test_all_merge_rules_are_valid(self, all_contracts: dict[str, dict], schema: str) -> None:
        valid_values = {r.value for r in MergeRule}
        for col_name, col_data in all_contracts[schema]["columns"].items():
            assert col_data["merge"] in valid_values, (
                f"{schema}.{col_name} has invalid merge rule: " f"{col_data['merge']!r}"
            )

    @pytest.mark.parametrize("schema", sorted(_TRUTH_LAYER_SCHEMAS))
    def test_ema_columns_have_alpha(self, all_contracts: dict[str, dict], schema: str) -> None:
        for col_name, col_data in all_contracts[schema]["columns"].items():
            if col_data["merge"] == "ema":
                assert (
                    "ema_alpha" in col_data and col_data["ema_alpha"] is not None
                ), f"{schema}.{col_name} is EMA but missing ema_alpha"

    @pytest.mark.parametrize("schema", sorted(_TRUTH_LAYER_SCHEMAS))
    def test_capped_columns_have_cap(self, all_contracts: dict[str, dict], schema: str) -> None:
        for col_name, col_data in all_contracts[schema]["columns"].items():
            if col_data["merge"] == "appendable_capped":
                assert (
                    "cap" in col_data and col_data["cap"] is not None
                ), f"{schema}.{col_name} is appendable_capped but missing cap"


# ---------------------------------------------------------------------------
# Cross-Contract Consistency
# ---------------------------------------------------------------------------


class TestCrossContractConsistency:

    def test_write_orders_are_unique(self, registry: TruthLayerRegistry) -> None:
        orders = [s.write_order for s in registry.all_layers()]
        assert len(orders) == len(set(orders)), "Duplicate write_order values"

    def test_pk_columns_in_columns_dict(self, registry: TruthLayerRegistry) -> None:
        for spec in registry.all_layers():
            assert spec.pk_column in spec.columns, (
                f"{spec.layer_name}: pk_column {spec.pk_column!r} " f"not in columns dict"
            )

    def test_pk_columns_are_immutable(self, registry: TruthLayerRegistry) -> None:
        for spec in registry.all_layers():
            pk_col = spec.columns[spec.pk_column]
            assert pk_col.merge == MergeRule.IMMUTABLE, (
                f"{spec.layer_name}: pk {spec.pk_column} merge "
                f"is {pk_col.merge}, expected IMMUTABLE"
            )

    def test_version_columns_are_counter(self, registry: TruthLayerRegistry) -> None:
        for spec in registry.all_layers():
            ver_col = spec.columns[spec.version_column]
            assert ver_col.merge == MergeRule.COUNTER, (
                f"{spec.layer_name}: version column merge is " f"{ver_col.merge}, expected COUNTER"
            )

    def test_archival_status_columns_are_status(self, registry: TruthLayerRegistry) -> None:
        for spec in registry.all_layers():
            arch_col = spec.columns[spec.archival_status_column]
            assert arch_col.merge == MergeRule.STATUS, (
                f"{spec.layer_name}: archival_status merge is " f"{arch_col.merge}, expected STATUS"
            )

    def test_identity_columns_exist_in_columns(self, registry: TruthLayerRegistry) -> None:
        for spec in registry.all_layers():
            for ic in spec.identity_columns:
                assert ic in spec.columns, (
                    f"{spec.layer_name}: identity column {ic!r} " f"not in columns dict"
                )

    def test_temporal_columns_exist_in_columns(self, registry: TruthLayerRegistry) -> None:
        for spec in registry.all_layers():
            t = spec.temporal
            for attr_name in ("start", "end", "last_observed", "first_observed"):
                col_name = getattr(t, attr_name)
                if col_name is not None:
                    assert col_name in spec.columns, (
                        f"{spec.layer_name}: temporal.{attr_name}={col_name!r} "
                        f"not in columns dict"
                    )

    def test_thresholds_are_ordered(self, registry: TruthLayerRegistry) -> None:
        for spec in registry.all_layers():
            th = spec.thresholds
            assert th.reinforce > th.extend > th.evolve, (
                f"{spec.layer_name}: thresholds not ordered: "
                f"reinforce={th.reinforce}, extend={th.extend}, evolve={th.evolve}"
            )

    def test_decay_lambdas_are_positive(self, registry: TruthLayerRegistry) -> None:
        for spec in registry.all_layers():
            assert spec.decay_lambda > 0, (
                f"{spec.layer_name}: decay_lambda must be positive, " f"got {spec.decay_lambda}"
            )
