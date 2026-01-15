"""Coverage validation framework for R5 benchmarks.

Defines validator classes to enforce pack-specific coverage thresholds
across CPN, MCTS, BGT-SM, and SPC-UQ algorithms. Computes metrics
(counts, distributions, variance) and returns pass/fail results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Coverage Result Dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CoverageResult:
    """Result of validating a single algorithm against thresholds."""

    pack_name: str
    algorithm: str
    passed: bool
    metrics: Dict[str, Any]
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)  # Raw input data summary
    outputs: List[Any] = field(default_factory=list)  # Raw algorithm outputs

    def summary(self) -> str:
        """Return a concise summary string."""
        status = "PASS" if self.passed else "FAIL"
        failure_str = f" ({len(self.failures)} failures)" if self.failures else ""
        warning_str = f" ({len(self.warnings)} warnings)" if self.warnings else ""
        return f"[{status}] {self.pack_name}/{self.algorithm}{failure_str}{warning_str}"


# ─────────────────────────────────────────────────────────────────────────────
# Default Thresholds per Algorithm
# ─────────────────────────────────────────────────────────────────────────────


DEFAULT_CPN_THRESHOLDS = {
    "min_counterfactuals": 5,
    "path_length_ge_1_ratio": 0.0,
    "path_length_ge_2_ratio": 0.0,
    "path_length_ge_3_count": 0,
    "max_path_length": 1,
    "plausibility_variance_min": 0.0,
    "scenario_type_count": 2,
}

DEFAULT_MCTS_THRESHOLDS = {
    "min_scenarios": 1,
    "budget_consumption_ratio": 0.1,
    "max_visit_count": 1,
    "visit_count_variance": False,
    "reward_spread": 0.0,
}

DEFAULT_BGT_THRESHOLDS = {
    "min_insights": 1,
    "pmi_variance": False,
    "semantic_distance_min": 0.0,
    "semantic_distance_max": 1.0,
    "cross_cluster_ratio": 0.0,
    "false_positive_rate_max": 1.0,
}

DEFAULT_SPC_THRESHOLDS = {
    "min_reconstructions": 1,
    "provenance_types_min": 1,
    "confidence_variance_min": 0.0,
    "uncertainty_on_conflict_min": 0.0,
    "schema_boost_detected": False,
}


# ─────────────────────────────────────────────────────────────────────────────
# Coverage Validator
# ─────────────────────────────────────────────────────────────────────────────


class CoverageValidator:
    """Validate algorithm outputs against coverage thresholds."""

    def __init__(self, pack_name: str = "unknown"):
        self.pack_name = pack_name

    def validate_cpn(
        self,
        counterfactuals: List[Any],
        thresholds: Optional[Dict[str, Any]] = None,
    ) -> CoverageResult:
        """Validate CPN counterfactual outputs.

        Args:
            counterfactuals: List of counterfactual scenario objects.
            thresholds: Coverage thresholds (uses defaults if None).

        Returns:
            CoverageResult with pass/fail and metrics.
        """
        thresholds = {**DEFAULT_CPN_THRESHOLDS, **(thresholds or {})}
        failures: List[str] = []
        warnings: List[str] = []

        # Handle empty input
        if not counterfactuals:
            return CoverageResult(
                pack_name=self.pack_name,
                algorithm="CPN",
                passed=False,
                metrics={"total_counterfactuals": 0},
                failures=["No counterfactuals generated"],
                warnings=[],
            )

        # Extract path lengths
        path_lengths = []
        plausibilities = []
        scenario_types: Set[str] = set()

        for cf in counterfactuals:
            # Support both object and dict formats
            if hasattr(cf, "causal_path_length"):
                path_lengths.append(cf.causal_path_length)
                plausibilities.append(cf.plausibility)
                scenario_types.add(str(cf.scenario_type))
            elif isinstance(cf, dict):
                path_lengths.append(cf.get("causal_path_length", 0))
                plausibilities.append(cf.get("plausibility", 0.0))
                scenario_types.add(str(cf.get("scenario_type", "UNKNOWN")))

        total = len(counterfactuals)
        path_lengths_arr = np.array(path_lengths)
        plausibilities_arr = np.array(plausibilities)

        # Compute metrics
        metrics = {
            "total_counterfactuals": total,
            "path_length_distribution": {
                int(k): int(v)
                for k, v in zip(*np.unique(path_lengths_arr, return_counts=True))
            },
            "path_length_ge_1_ratio": float(np.sum(path_lengths_arr >= 1) / total) if total else 0,
            "path_length_ge_2_ratio": float(np.sum(path_lengths_arr >= 2) / total) if total else 0,
            "path_length_ge_3_count": int(np.sum(path_lengths_arr >= 3)),
            "max_path_length": int(np.max(path_lengths_arr)) if len(path_lengths_arr) else 0,
            "plausibility_mean": float(np.mean(plausibilities_arr)) if len(plausibilities_arr) else 0,
            "plausibility_variance": float(np.var(plausibilities_arr)) if len(plausibilities_arr) else 0,
            "scenario_types": list(scenario_types),
            "scenario_type_count": len(scenario_types),
        }

        # Validate against thresholds
        if metrics["total_counterfactuals"] < thresholds["min_counterfactuals"]:
            failures.append(
                f"Too few counterfactuals: {metrics['total_counterfactuals']} < {thresholds['min_counterfactuals']}"
            )

        if metrics["path_length_ge_1_ratio"] < thresholds.get("path_length_ge_1_ratio", 0):
            failures.append(
                f"Path length >= 1 ratio too low: {metrics['path_length_ge_1_ratio']:.2f} < {thresholds['path_length_ge_1_ratio']}"
            )

        if metrics["path_length_ge_2_ratio"] < thresholds.get("path_length_ge_2_ratio", 0):
            failures.append(
                f"Path length >= 2 ratio too low: {metrics['path_length_ge_2_ratio']:.2f} < {thresholds['path_length_ge_2_ratio']}"
            )

        if metrics["path_length_ge_3_count"] < thresholds.get("path_length_ge_3_count", 0):
            failures.append(
                f"Path length >= 3 count too low: {metrics['path_length_ge_3_count']} < {thresholds['path_length_ge_3_count']}"
            )

        if metrics["max_path_length"] < thresholds.get("max_path_length", 1):
            failures.append(
                f"Max path length too short: {metrics['max_path_length']} < {thresholds['max_path_length']}"
            )

        if metrics["plausibility_variance"] < thresholds.get("plausibility_variance_min", 0):
            warnings.append(
                f"Low plausibility variance: {metrics['plausibility_variance']:.4f}"
            )

        if metrics["scenario_type_count"] < thresholds.get("scenario_type_count", 1):
            failures.append(
                f"Too few scenario types: {metrics['scenario_type_count']} < {thresholds['scenario_type_count']}"
            )

        return CoverageResult(
            pack_name=self.pack_name,
            algorithm="CPN",
            passed=len(failures) == 0,
            metrics=metrics,
            failures=failures,
            warnings=warnings,
        )

    def validate_mcts(
        self,
        scenarios: List[Any],
        thresholds: Optional[Dict[str, Any]] = None,
        budget: int = 100,
    ) -> CoverageResult:
        """Validate MCTS scenario outputs.

        Args:
            scenarios: List of projected scenario objects.
            thresholds: Coverage thresholds (uses defaults if None).
            budget: Total rollout budget for consumption ratio.

        Returns:
            CoverageResult with pass/fail and metrics.
        """
        thresholds = {**DEFAULT_MCTS_THRESHOLDS, **(thresholds or {})}
        failures: List[str] = []
        warnings: List[str] = []

        if not scenarios:
            return CoverageResult(
                pack_name=self.pack_name,
                algorithm="MCTS",
                passed=False,
                metrics={"total_scenarios": 0},
                failures=["No scenarios generated"],
                warnings=[],
            )

        # Extract visit counts and rewards
        visit_counts = []
        rewards = []

        for scenario in scenarios:
            if hasattr(scenario, "visit_count"):
                visit_counts.append(scenario.visit_count)
                rewards.append(scenario.expected_reward)
            elif isinstance(scenario, dict):
                visit_counts.append(scenario.get("visit_count", 0))
                rewards.append(scenario.get("expected_reward", 0.0))

        visit_counts_arr = np.array(visit_counts)
        rewards_arr = np.array(rewards)
        total_visits = int(np.sum(visit_counts_arr))

        metrics = {
            "total_scenarios": len(scenarios),
            "total_visits": total_visits,
            "max_visit_count": int(np.max(visit_counts_arr)) if len(visit_counts_arr) else 0,
            "visit_count_variance": float(np.var(visit_counts_arr)) if len(visit_counts_arr) else 0,
            "budget_consumption_ratio": total_visits / budget if budget > 0 else 0,
            "reward_mean": float(np.mean(rewards_arr)) if len(rewards_arr) else 0,
            "reward_max": float(np.max(rewards_arr)) if len(rewards_arr) else 0,
            "reward_min": float(np.min(rewards_arr)) if len(rewards_arr) else 0,
            "reward_spread": float(np.max(rewards_arr) - np.min(rewards_arr)) if len(rewards_arr) else 0,
        }

        # Validate
        if metrics["total_scenarios"] < thresholds.get("min_scenarios", 1):
            failures.append(f"Too few scenarios: {metrics['total_scenarios']}")

        if metrics["budget_consumption_ratio"] < thresholds.get("budget_consumption_ratio", 0):
            warnings.append(
                f"Budget underutilized: {metrics['budget_consumption_ratio']:.2%} < {thresholds['budget_consumption_ratio']:.2%}"
            )

        if metrics["max_visit_count"] < thresholds.get("max_visit_count", 1):
            failures.append(
                f"Max visit count too low: {metrics['max_visit_count']} < {thresholds['max_visit_count']}"
            )

        if thresholds.get("visit_count_variance", False) and metrics["visit_count_variance"] < 0.01:
            warnings.append("Visit counts are nearly constant (low variance)")

        if metrics["reward_spread"] < thresholds.get("reward_spread", 0):
            warnings.append(
                f"Reward spread too narrow: {metrics['reward_spread']:.3f} < {thresholds['reward_spread']}"
            )

        return CoverageResult(
            pack_name=self.pack_name,
            algorithm="MCTS",
            passed=len(failures) == 0,
            metrics=metrics,
            failures=failures,
            warnings=warnings,
        )

    def validate_bgt(
        self,
        insights: List[Any],
        thresholds: Optional[Dict[str, Any]] = None,
        entity_clusters: Optional[Dict[str, str]] = None,
    ) -> CoverageResult:
        """Validate BGT-SM insight outputs.

        Args:
            insights: List of insight objects.
            thresholds: Coverage thresholds (uses defaults if None).
            entity_clusters: Mapping of entity_id -> cluster_name for cross-cluster validation.

        Returns:
            CoverageResult with pass/fail and metrics.
        """
        thresholds = {**DEFAULT_BGT_THRESHOLDS, **(thresholds or {})}
        failures: List[str] = []
        warnings: List[str] = []

        if not insights:
            return CoverageResult(
                pack_name=self.pack_name,
                algorithm="BGT-SM",
                passed=False,
                metrics={"total_insights": 0},
                failures=["No insights discovered"],
                warnings=[],
            )

        # Extract metrics from insights
        pmi_scores = []
        semantic_distances = []
        novelty_scores = []
        cross_cluster_count = 0
        spurious_count = 0

        for insight in insights:
            if hasattr(insight, "pmi_score"):
                pmi_scores.append(insight.pmi_score)
                semantic_distances.append(insight.semantic_distance)
                novelty_scores.append(insight.novelty_score)
                # Check cross-cluster if entity_clusters provided
                if entity_clusters and hasattr(insight, "entity_a") and hasattr(insight, "entity_b"):
                    cluster_a = entity_clusters.get(insight.entity_a)
                    cluster_b = entity_clusters.get(insight.entity_b)
                    if cluster_a and cluster_b and cluster_a != cluster_b:
                        cross_cluster_count += 1
                # Check for spurious/false positive flag
                if hasattr(insight, "is_spurious") and insight.is_spurious:
                    spurious_count += 1
            elif isinstance(insight, dict):
                pmi_scores.append(insight.get("pmi_score", 0.0))
                semantic_distances.append(insight.get("semantic_distance", 0.0))
                novelty_scores.append(insight.get("novelty_score", 0.0))
                if insight.get("is_spurious"):
                    spurious_count += 1

        pmi_arr = np.array(pmi_scores)
        dist_arr = np.array(semantic_distances)
        total = len(insights)

        metrics = {
            "total_insights": total,
            "pmi_mean": float(np.mean(pmi_arr)) if len(pmi_arr) else 0,
            "pmi_variance": float(np.var(pmi_arr)) if len(pmi_arr) else 0,
            "pmi_min": float(np.min(pmi_arr)) if len(pmi_arr) else 0,
            "pmi_max": float(np.max(pmi_arr)) if len(pmi_arr) else 0,
            "semantic_distance_mean": float(np.mean(dist_arr)) if len(dist_arr) else 0,
            "semantic_distance_min": float(np.min(dist_arr)) if len(dist_arr) else 0,
            "semantic_distance_max": float(np.max(dist_arr)) if len(dist_arr) else 0,
            "novelty_mean": float(np.mean(novelty_scores)) if novelty_scores else 0,
            "cross_cluster_count": cross_cluster_count,
            "cross_cluster_ratio": cross_cluster_count / total if total else 0,
            "spurious_count": spurious_count,
            "false_positive_rate": spurious_count / total if total else 0,
        }

        # Validate
        if metrics["total_insights"] < thresholds.get("min_insights", 1):
            failures.append(f"Too few insights: {metrics['total_insights']}")

        if thresholds.get("pmi_variance", False) and metrics["pmi_variance"] < 0.01:
            warnings.append("PMI scores are nearly constant (low variance)")

        if metrics["semantic_distance_min"] < thresholds.get("semantic_distance_min", 0):
            warnings.append(
                f"Semantic distance too low: {metrics['semantic_distance_min']:.3f}"
            )

        if metrics["semantic_distance_max"] > thresholds.get("semantic_distance_max", 1.0):
            warnings.append(
                f"Semantic distance too high: {metrics['semantic_distance_max']:.3f}"
            )

        if metrics["cross_cluster_ratio"] < thresholds.get("cross_cluster_ratio", 0):
            failures.append(
                f"Cross-cluster ratio too low: {metrics['cross_cluster_ratio']:.2%} < {thresholds['cross_cluster_ratio']:.2%}"
            )

        if metrics["false_positive_rate"] > thresholds.get("false_positive_rate_max", 1.0):
            failures.append(
                f"False positive rate too high: {metrics['false_positive_rate']:.2%}"
            )

        return CoverageResult(
            pack_name=self.pack_name,
            algorithm="BGT-SM",
            passed=len(failures) == 0,
            metrics=metrics,
            failures=failures,
            warnings=warnings,
        )

    def validate_spc(
        self,
        reconstructions: List[Any],
        thresholds: Optional[Dict[str, Any]] = None,
        fragments: Optional[List[Any]] = None,
    ) -> CoverageResult:
        """Validate SPC-UQ reconstruction outputs.

        Args:
            reconstructions: List of reconstructed episode objects.
            thresholds: Coverage thresholds (uses defaults if None).
            fragments: Original fragments for provenance analysis.

        Returns:
            CoverageResult with pass/fail and metrics.
        """
        thresholds = {**DEFAULT_SPC_THRESHOLDS, **(thresholds or {})}
        failures: List[str] = []
        warnings: List[str] = []

        if not reconstructions:
            return CoverageResult(
                pack_name=self.pack_name,
                algorithm="SPC-UQ",
                passed=False,
                metrics={"total_reconstructions": 0},
                failures=["No reconstructions generated"],
                warnings=[],
            )

        # Extract metrics
        confidence_scores = []
        uncertainty_scores = []
        provenance_types: Set[str] = set()
        schema_matches = 0
        conflict_detected = 0
        high_uncertainty_on_conflict = 0

        for recon in reconstructions:
            if hasattr(recon, "confidence_score"):
                confidence_scores.append(recon.confidence_score)
                uncertainty_scores.append(recon.uncertainty_score)

                # Extract provenance types from reconstruction.provenance dict
                prov_dict = getattr(recon, "provenance", {})
                if isinstance(prov_dict, dict):
                    # Get provenance_types_used from the provenance dict
                    prov_types_used = prov_dict.get("provenance_types_used", [])
                    for pt in prov_types_used:
                        provenance_types.add(str(pt))

                    # Get conflicts_detected count
                    conflicts_in_episode = prov_dict.get("conflicts_detected", 0)
                    conflict_detected += conflicts_in_episode

                    # If conflicts detected and uncertainty is high, count it
                    if conflicts_in_episode > 0 and recon.uncertainty_score >= 0.7:
                        high_uncertainty_on_conflict += 1

                # Also check reconstructed_fields for provenance
                if hasattr(recon, "reconstructed_fields"):
                    fields = recon.reconstructed_fields
                    if isinstance(fields, (list, tuple)):
                        for field_info in fields:
                            if hasattr(field_info, "provenance"):
                                provenance_types.add(str(field_info.provenance))
                            if hasattr(field_info, "schema_id") and field_info.schema_id:
                                schema_matches += 1
                    elif isinstance(fields, dict):
                        for field_info in fields.values():
                            if hasattr(field_info, "provenance"):
                                provenance_types.add(str(field_info.provenance))
                            if hasattr(field_info, "schema_id") and field_info.schema_id:
                                schema_matches += 1

            elif isinstance(recon, dict):
                confidence_scores.append(recon.get("confidence_score", 0.0))
                uncertainty_scores.append(recon.get("uncertainty_score", 0.0))

                # Extract from dict provenance
                prov_dict = recon.get("provenance", {})
                if isinstance(prov_dict, dict):
                    prov_types_used = prov_dict.get("provenance_types_used", [])
                    for pt in prov_types_used:
                        provenance_types.add(str(pt))
                    conflicts_in_episode = prov_dict.get("conflicts_detected", 0)
                    conflict_detected += conflicts_in_episode
                    if conflicts_in_episode > 0 and recon.get("uncertainty_score", 0) >= 0.7:
                        high_uncertainty_on_conflict += 1

                fields = recon.get("reconstructed_fields", {})
                if isinstance(fields, (list, tuple)):
                    for field_info in fields:
                        if isinstance(field_info, dict) and "provenance" in field_info:
                            provenance_types.add(str(field_info["provenance"]))
                elif isinstance(fields, dict):
                    for field_info in fields.values():
                        if isinstance(field_info, dict) and "provenance" in field_info:
                            provenance_types.add(str(field_info["provenance"]))

        # Also analyze fragment provenance types if provided (for validation)
        fragment_provenance_types: Set[str] = set()
        if fragments:
            for frag in fragments:
                if hasattr(frag, "provenance_type"):
                    fragment_provenance_types.add(frag.provenance_type)
                elif isinstance(frag, dict) and "provenance_type" in frag:
                    fragment_provenance_types.add(frag["provenance_type"])

        conf_arr = np.array(confidence_scores)
        unc_arr = np.array(uncertainty_scores)

        metrics = {
            "total_reconstructions": len(reconstructions),
            "confidence_mean": float(np.mean(conf_arr)) if len(conf_arr) else 0,
            "confidence_variance": float(np.var(conf_arr)) if len(conf_arr) else 0,
            "uncertainty_mean": float(np.mean(unc_arr)) if len(unc_arr) else 0,
            "uncertainty_variance": float(np.var(unc_arr)) if len(unc_arr) else 0,
            "provenance_types": list(provenance_types),
            "provenance_types_count": len(provenance_types),
            "fragment_provenance_types": list(fragment_provenance_types),
            "schema_matches": schema_matches,
            "conflict_fragments": conflict_detected,
            "high_uncertainty_on_conflict": high_uncertainty_on_conflict,
        }

        # Validate minimum reconstructions
        if metrics["total_reconstructions"] < thresholds.get("min_reconstructions", 1):
            failures.append(f"Too few reconstructions: {metrics['total_reconstructions']}")

        # Validate provenance diversity (STRICT for multi_prov packs)
        min_prov_types = thresholds.get("provenance_types_min", 1)
        if metrics["provenance_types_count"] < min_prov_types:
            failures.append(
                f"Too few provenance types: {metrics['provenance_types_count']} < {min_prov_types}"
            )

        # Validate conflicts detected (STRICT for conflict packs)
        min_conflicts = thresholds.get("min_conflicts", 0)
        if min_conflicts > 0 and metrics["conflict_fragments"] < min_conflicts:
            failures.append(
                f"Conflicts not detected: {metrics['conflict_fragments']} < {min_conflicts} required"
            )

        # Validate high uncertainty on conflict (STRICT for conflict packs)
        if thresholds.get("require_high_uncertainty_on_conflict", False):
            if conflict_detected > 0 and high_uncertainty_on_conflict == 0:
                failures.append(
                    f"Conflicts detected but no high uncertainty: {high_uncertainty_on_conflict}"
                )

        if metrics["confidence_variance"] < thresholds.get("confidence_variance_min", 0):
            warnings.append(
                f"Low confidence variance: {metrics['confidence_variance']:.4f}"
            )

        # If conflicts detected, check uncertainty
        if conflict_detected > 0:
            if metrics["uncertainty_mean"] < thresholds.get("uncertainty_on_conflict_min", 0):
                failures.append(
                    f"Uncertainty on conflict too low: {metrics['uncertainty_mean']:.3f}"
                )

        return CoverageResult(
            pack_name=self.pack_name,
            algorithm="SPC-UQ",
            passed=len(failures) == 0,
            metrics=metrics,
            failures=failures,
            warnings=warnings,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate Validation
# ─────────────────────────────────────────────────────────────────────────────


def validate_all(
    pack_name: str,
    cpn_results: Optional[List[Any]] = None,
    mcts_results: Optional[List[Any]] = None,
    bgt_results: Optional[List[Any]] = None,
    spc_results: Optional[List[Any]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, CoverageResult]:
    """Validate all algorithm outputs for a pack.

    Args:
        pack_name: Name of the scenario pack.
        cpn_results: CPN counterfactual outputs.
        mcts_results: MCTS scenario outputs.
        bgt_results: BGT-SM insight outputs.
        spc_results: SPC-UQ reconstruction outputs.
        thresholds: Pack-specific thresholds dict with algorithm prefixes.
        **kwargs: Additional kwargs (fragments, entity_clusters, etc.)

    Returns:
        Dict mapping algorithm name to CoverageResult.
    """
    validator = CoverageValidator(pack_name)
    thresholds = thresholds or {}
    results = {}

    if cpn_results is not None:
        cpn_thresholds = {
            k.replace("cpn_", ""): v
            for k, v in thresholds.items()
            if k.startswith("cpn_")
        }
        results["CPN"] = validator.validate_cpn(cpn_results, cpn_thresholds)

    if mcts_results is not None:
        mcts_thresholds = {
            k.replace("mcts_", ""): v
            for k, v in thresholds.items()
            if k.startswith("mcts_")
        }
        results["MCTS"] = validator.validate_mcts(
            mcts_results,
            mcts_thresholds,
            budget=kwargs.get("mcts_budget", 100),
        )

    if bgt_results is not None:
        bgt_thresholds = {
            k.replace("bgt_", ""): v
            for k, v in thresholds.items()
            if k.startswith("bgt_")
        }
        results["BGT-SM"] = validator.validate_bgt(
            bgt_results,
            bgt_thresholds,
            entity_clusters=kwargs.get("entity_clusters"),
        )

    if spc_results is not None:
        spc_thresholds = {
            k.replace("spc_", ""): v
            for k, v in thresholds.items()
            if k.startswith("spc_")
        }
        results["SPC-UQ"] = validator.validate_spc(
            spc_results,
            spc_thresholds,
            fragments=kwargs.get("fragments"),
        )

    return results


def aggregate_results(
    results: Union[Dict[str, CoverageResult], List[CoverageResult]],
) -> List[CoverageResult]:
    """Aggregate multiple coverage results by algorithm.

    Args:
        results: Either a Dict mapping algorithm name to CoverageResult,
                 or a List of CoverageResult objects.

    Returns:
        List of aggregated CoverageResult objects (one per algorithm).
    """
    # Normalize to list
    if isinstance(results, dict):
        results_list = list(results.values())
    else:
        results_list = list(results)

    if not results_list:
        return []

    # Group by algorithm
    by_algo: Dict[str, List[CoverageResult]] = {}
    for result in results_list:
        if result.algorithm not in by_algo:
            by_algo[result.algorithm] = []
        by_algo[result.algorithm].append(result)

    # Aggregate each algorithm
    aggregated = []
    for algo, algo_results in by_algo.items():
        all_failures = []
        all_warnings = []
        all_metrics: Dict[str, List[float]] = {}

        for result in algo_results:
            all_failures.extend(result.failures)
            all_warnings.extend(result.warnings)

            # Collect numeric metrics for averaging
            for key, value in result.metrics.items():
                if isinstance(value, (int, float)):
                    if key not in all_metrics:
                        all_metrics[key] = []
                    all_metrics[key].append(float(value))

        # Average numeric metrics
        averaged_metrics = {
            key: sum(vals) / len(vals) for key, vals in all_metrics.items()
        }

        pack_name = algo_results[0].pack_name if algo_results else "aggregate"

        aggregated.append(CoverageResult(
            pack_name=pack_name,
            algorithm=algo,
            passed=all(r.passed for r in algo_results),
            metrics=averaged_metrics,
            failures=list(set(all_failures)),  # Dedupe
            warnings=list(set(all_warnings)),
        ))

    return aggregated
