"""Statistical utilities for R5 benchmarks.

Provides confidence intervals, effect sizes, significance tests,
stability scores, and regression detection for benchmark analysis.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Statistical Result Dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ConfidenceInterval:
    """Confidence interval for a metric."""

    mean: float
    lower: float
    upper: float
    confidence: float
    n: int

    def __str__(self) -> str:
        return f"{self.mean:.4f} [{self.lower:.4f}, {self.upper:.4f}] ({self.confidence:.0%} CI, n={self.n})"


@dataclass
class EffectSizeResult:
    """Result of effect size calculation."""

    cohens_d: float
    interpretation: str  # negligible, small, medium, large
    baseline_mean: float
    treatment_mean: float
    pooled_std: float

    def __str__(self) -> str:
        return f"Cohen's d = {self.cohens_d:.3f} ({self.interpretation})"


@dataclass
class SignificanceTestResult:
    """Result of significance test."""

    statistic: float
    p_value: float
    is_significant: bool
    test_name: str
    effect_size: Optional[EffectSizeResult] = None

    def __str__(self) -> str:
        sig = "significant" if self.is_significant else "not significant"
        return f"{self.test_name}: t={self.statistic:.3f}, p={self.p_value:.4f} ({sig})"


@dataclass
class RegressionAlert:
    """Alert for detected regression."""

    metric: str
    current_value: float
    baseline_value: float
    change_pct: float
    threshold_pct: float
    severity: str  # warning, critical

    def __str__(self) -> str:
        direction = "↓" if self.change_pct < 0 else "↑"
        return f"[{self.severity.upper()}] {self.metric}: {self.baseline_value:.4f} → {self.current_value:.4f} ({direction}{abs(self.change_pct):.1%})"


@dataclass
class StabilityReport:
    """Report on metric stability across seeds."""

    metric: str
    values: List[float]
    mean: float
    std: float
    cv: float  # coefficient of variation
    is_stable: bool
    stability_score: float  # 0-1, higher is more stable

    def __str__(self) -> str:
        status = "stable" if self.is_stable else "unstable"
        return f"{self.metric}: {status} (CV={self.cv:.3f}, stability={self.stability_score:.2f})"


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Statistics Class
# ─────────────────────────────────────────────────────────────────────────────


class BenchmarkStatistics:
    """Statistical analysis helpers for benchmark results."""

    def __init__(self, alpha: float = 0.05, stability_threshold: float = 0.1):
        """Initialize statistics helper.

        Args:
            alpha: Significance level for hypothesis tests (default 0.05).
            stability_threshold: CV threshold for stability (default 0.1 = 10%).
        """
        self.alpha = alpha
        self.stability_threshold = stability_threshold

    def confidence_interval(
        self,
        values: List[float],
        confidence: float = 0.95,
    ) -> ConfidenceInterval:
        """Calculate confidence interval for a metric.

        Uses t-distribution for small samples, z-distribution for large.

        Args:
            values: List of metric values across runs.
            confidence: Confidence level (default 0.95).

        Returns:
            ConfidenceInterval with mean, lower, upper bounds.
        """
        arr = np.array(values)
        if arr.size == 0:
            return ConfidenceInterval(
                mean=0.0, lower=0.0, upper=0.0, confidence=confidence, n=0
            )

        n = len(arr)
        mean = float(np.mean(arr))

        if n < 2:
            return ConfidenceInterval(
                mean=mean, lower=mean, upper=mean, confidence=confidence, n=n
            )

        std_err = float(stats.sem(arr))

        # Use t-distribution for small samples
        if n < 30:
            t_crit = stats.t.ppf((1 + confidence) / 2, df=n - 1)
            margin = t_crit * std_err
        else:
            z_crit = stats.norm.ppf((1 + confidence) / 2)
            margin = z_crit * std_err

        return ConfidenceInterval(
            mean=mean,
            lower=mean - margin,
            upper=mean + margin,
            confidence=confidence,
            n=n,
        )

    def effect_size(
        self,
        baseline: List[float],
        treatment: List[float],
    ) -> EffectSizeResult:
        """Calculate Cohen's d effect size between baseline and treatment.

        Args:
            baseline: Metric values from baseline condition.
            treatment: Metric values from treatment condition.

        Returns:
            EffectSizeResult with Cohen's d and interpretation.
        """
        baseline_arr = np.array(baseline)
        treatment_arr = np.array(treatment)

        if baseline_arr.size == 0 or treatment_arr.size == 0:
            return EffectSizeResult(
                cohens_d=0.0,
                interpretation="undefined",
                baseline_mean=0.0,
                treatment_mean=0.0,
                pooled_std=0.0,
            )

        n1, n2 = len(baseline_arr), len(treatment_arr)
        mean1, mean2 = np.mean(baseline_arr), np.mean(treatment_arr)
        var1, var2 = np.var(baseline_arr, ddof=1), np.var(treatment_arr, ddof=1)

        # Pooled standard deviation
        pooled_std = math.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))

        if pooled_std == 0:
            cohens_d = 0.0
        else:
            cohens_d = (mean2 - mean1) / pooled_std

        # Interpret effect size (Cohen's conventions)
        abs_d = abs(cohens_d)
        if abs_d < 0.2:
            interpretation = "negligible"
        elif abs_d < 0.5:
            interpretation = "small"
        elif abs_d < 0.8:
            interpretation = "medium"
        else:
            interpretation = "large"

        return EffectSizeResult(
            cohens_d=float(cohens_d),
            interpretation=interpretation,
            baseline_mean=float(mean1),
            treatment_mean=float(mean2),
            pooled_std=float(pooled_std),
        )

    def significance_test(
        self,
        baseline: List[float],
        treatment: List[float],
        test: str = "welch",
    ) -> SignificanceTestResult:
        """Perform significance test between baseline and treatment.

        Args:
            baseline: Metric values from baseline condition.
            treatment: Metric values from treatment condition.
            test: Test type - 'welch' (default), 'student', 'mannwhitney'.

        Returns:
            SignificanceTestResult with statistic, p-value, and significance.
        """
        if len(baseline) < 2 or len(treatment) < 2:
            return SignificanceTestResult(
                statistic=0.0,
                p_value=1.0,
                is_significant=False,
                test_name=test,
            )

        baseline_arr = np.array(baseline)
        treatment_arr = np.array(treatment)

        if test == "welch":
            stat, p_value = stats.ttest_ind(
                treatment_arr, baseline_arr, equal_var=False
            )
            test_name = "Welch's t-test"
        elif test == "student":
            stat, p_value = stats.ttest_ind(
                treatment_arr, baseline_arr, equal_var=True
            )
            test_name = "Student's t-test"
        elif test == "mannwhitney":
            stat, p_value = stats.mannwhitneyu(
                treatment_arr, baseline_arr, alternative="two-sided"
            )
            test_name = "Mann-Whitney U"
        else:
            raise ValueError(f"Unknown test type: {test}")

        effect = self.effect_size(baseline, treatment)

        return SignificanceTestResult(
            statistic=float(stat),
            p_value=float(p_value),
            is_significant=p_value < self.alpha,
            test_name=test_name,
            effect_size=effect,
        )

    def stability_score(
        self,
        results: List[Dict[str, Any]],
        metric: str,
        across_seeds: Optional[List[int]] = None,
    ) -> StabilityReport:
        """Measure result stability across different seeds.

        Args:
            results: List of result dicts from different runs.
            metric: Metric name to analyze (dot notation for nested).
            across_seeds: Optional list of seed values used.

        Returns:
            StabilityReport with CV and stability assessment.
        """
        values = []
        for result in results:
            # Support dot notation for nested metrics
            value = result
            for key in metric.split("."):
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = None
                    break
            if value is not None and isinstance(value, (int, float)):
                values.append(float(value))

        if not values:
            return StabilityReport(
                metric=metric,
                values=[],
                mean=0.0,
                std=0.0,
                cv=float("inf"),
                is_stable=False,
                stability_score=0.0,
            )

        arr = np.array(values)
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0

        # Coefficient of variation (handle zero mean)
        cv = std / abs(mean) if mean != 0 else (float("inf") if std > 0 else 0.0)

        # Stability score: 1 - normalized CV (capped at 1)
        stability_score = max(0.0, 1.0 - min(cv / self.stability_threshold, 1.0))
        is_stable = cv <= self.stability_threshold

        return StabilityReport(
            metric=metric,
            values=values,
            mean=mean,
            std=std,
            cv=cv,
            is_stable=is_stable,
            stability_score=stability_score,
        )

    def regression_check(
        self,
        current: Dict[str, Any],
        baseline: Dict[str, Any],
        threshold: float = 0.1,
        metrics: Optional[List[str]] = None,
        higher_is_better: Optional[Dict[str, bool]] = None,
    ) -> List[RegressionAlert]:
        """Check for performance regressions against baseline.

        Args:
            current: Current run metrics.
            baseline: Baseline metrics to compare against.
            threshold: Percentage change threshold for alerting (default 10%).
            metrics: List of metric paths to check (all if None).
            higher_is_better: Dict indicating direction for each metric.

        Returns:
            List of RegressionAlert for detected regressions.
        """
        alerts = []
        higher_is_better = higher_is_better or {}

        def extract_metrics(d: Dict, prefix: str = "") -> Dict[str, float]:
            """Flatten nested dict to metric paths."""
            result = {}
            for key, value in d.items():
                path = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    result.update(extract_metrics(value, path))
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    result[path] = float(value)
            return result

        current_flat = extract_metrics(current)
        baseline_flat = extract_metrics(baseline)

        # Filter to requested metrics if specified
        if metrics:
            current_flat = {k: v for k, v in current_flat.items() if k in metrics}
            baseline_flat = {k: v for k, v in baseline_flat.items() if k in metrics}

        for metric, current_value in current_flat.items():
            if metric not in baseline_flat:
                continue

            baseline_value = baseline_flat[metric]
            if baseline_value == 0:
                continue

            change_pct = (current_value - baseline_value) / abs(baseline_value)

            # Determine if this change is a regression
            is_higher_better = higher_is_better.get(metric, True)  # Default: higher is better
            is_regression = (
                (is_higher_better and change_pct < -threshold)
                or (not is_higher_better and change_pct > threshold)
            )

            if is_regression:
                severity = "critical" if abs(change_pct) > threshold * 2 else "warning"
                alerts.append(
                    RegressionAlert(
                        metric=metric,
                        current_value=current_value,
                        baseline_value=baseline_value,
                        change_pct=change_pct,
                        threshold_pct=threshold,
                        severity=severity,
                    )
                )

        return alerts


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Seed Run Aggregation
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MultiSeedResult:
    """Aggregated result from multiple seed runs."""

    pack_name: str
    seeds: List[int]
    per_seed_results: List[Dict[str, Any]]
    aggregated_metrics: Dict[str, ConfidenceInterval]
    stability_reports: List[StabilityReport]
    overall_pass_rate: float

    def summary(self) -> str:
        """Return summary string."""
        stable_count = sum(1 for r in self.stability_reports if r.is_stable)
        return (
            f"{self.pack_name}: {len(self.seeds)} seeds, "
            f"{self.overall_pass_rate:.0%} pass rate, "
            f"{stable_count}/{len(self.stability_reports)} stable metrics"
        )


def run_multi_seed(
    run_fn,
    pack_name: str,
    seeds: List[int],
    metrics_to_aggregate: List[str],
) -> MultiSeedResult:
    """Run benchmark across multiple seeds and aggregate results.

    Args:
        run_fn: Function(seed) -> Dict with benchmark results.
        pack_name: Name of the pack being benchmarked.
        seeds: List of seed values to test.
        metrics_to_aggregate: Metric paths to aggregate with CIs.

    Returns:
        MultiSeedResult with aggregated statistics.
    """
    stats_helper = BenchmarkStatistics()
    per_seed_results = []
    pass_count = 0

    for seed in seeds:
        try:
            result = run_fn(seed)
            per_seed_results.append(result)
            if result.get("passed", True):
                pass_count += 1
        except Exception as e:
            logger.error(f"Seed {seed} failed: {e}")
            per_seed_results.append({"error": str(e), "passed": False})

    # Aggregate metrics
    aggregated_metrics = {}
    for metric in metrics_to_aggregate:
        values = []
        for result in per_seed_results:
            value = result
            for key in metric.split("."):
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = None
                    break
            if value is not None and isinstance(value, (int, float)):
                values.append(float(value))

        if values:
            aggregated_metrics[metric] = stats_helper.confidence_interval(values)

    # Stability reports
    stability_reports = [
        stats_helper.stability_score(per_seed_results, metric)
        for metric in metrics_to_aggregate
    ]

    return MultiSeedResult(
        pack_name=pack_name,
        seeds=seeds,
        per_seed_results=per_seed_results,
        aggregated_metrics=aggregated_metrics,
        stability_reports=stability_reports,
        overall_pass_rate=pass_count / len(seeds) if seeds else 0.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Baseline Management
# ─────────────────────────────────────────────────────────────────────────────


def save_baseline(
    metrics: Dict[str, Any],
    path: Path,
    version: str = "v1.0",
    pack_name: str = "unknown",
) -> None:
    """Save baseline metrics to JSON file.

    Args:
        metrics: Metrics dict to save as baseline.
        path: Path to save file.
        version: Version label.
        pack_name: Pack name for metadata.
    """
    baseline = {
        "version": version,
        "pack_name": pack_name,
        "metrics": metrics,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, default=str)
    logger.info(f"Saved baseline to {path}")


def load_baseline(path: Path) -> Optional[Dict[str, Any]]:
    """Load baseline metrics from JSON file.

    Args:
        path: Path to baseline file.

    Returns:
        Metrics dict or None if file doesn't exist.
    """
    if not path.exists():
        logger.warning(f"Baseline not found: {path}")
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("metrics", {})
