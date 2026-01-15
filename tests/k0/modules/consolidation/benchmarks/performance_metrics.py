"""
Performance Metrics for R5 Benchmarking.

This module provides metrics collection and analysis utilities for
benchmarking the R5 Dream Phase algorithms.

Metrics Categories:
1. Timing Metrics: Execution time, throughput
2. Quality Metrics: Accuracy, precision, recall
3. Efficiency Metrics: Memory usage, iterations
4. Output Metrics: Count, distribution statistics

References:
- M8_EXECUTION.md: Issue 8.1.* for algorithm specifications
- Dossier Section 4.6: R5 Dream-Like Exploration
"""

from __future__ import annotations

import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

# =============================================================================
# TIMING UTILITIES
# =============================================================================


@contextmanager
def timer() -> Generator[Dict[str, float], None, None]:
    """
    Context manager for timing code execution.

    Usage:
        with timer() as t:
            result = expensive_operation()
        print(f"Elapsed: {t['elapsed_ms']:.2f}ms")
    """
    result: Dict[str, float] = {}
    start_ns = time.perf_counter_ns()
    try:
        yield result
    finally:
        end_ns = time.perf_counter_ns()
        result["elapsed_ns"] = end_ns - start_ns
        result["elapsed_ms"] = result["elapsed_ns"] / 1_000_000
        result["elapsed_s"] = result["elapsed_ns"] / 1_000_000_000


class StopwatchTimer:
    """
    Reusable stopwatch for multi-lap timing.

    Usage:
        sw = StopwatchTimer()
        sw.start()
        # ... first operation ...
        sw.lap("operation_1")
        # ... second operation ...
        sw.lap("operation_2")
        sw.stop()
        print(sw.summary())
    """

    def __init__(self) -> None:
        """Initialize stopwatch."""
        self._start_ns: Optional[int] = None
        self._laps: List[tuple[str, int]] = []
        self._end_ns: Optional[int] = None

    def start(self) -> "StopwatchTimer":
        """Start the stopwatch."""
        self._start_ns = time.perf_counter_ns()
        self._laps = []
        self._end_ns = None
        return self

    def lap(self, name: str) -> int:
        """Record a lap time and return elapsed ns since start."""
        if self._start_ns is None:
            raise RuntimeError("Stopwatch not started")
        elapsed = time.perf_counter_ns() - self._start_ns
        self._laps.append((name, elapsed))
        return elapsed

    def stop(self) -> int:
        """Stop the stopwatch and return total elapsed ns."""
        if self._start_ns is None:
            raise RuntimeError("Stopwatch not started")
        self._end_ns = time.perf_counter_ns()
        return self._end_ns - self._start_ns

    @property
    def elapsed_ms(self) -> float:
        """Get total elapsed time in milliseconds."""
        if self._start_ns is None:
            return 0.0
        end = self._end_ns or time.perf_counter_ns()
        return (end - self._start_ns) / 1_000_000

    def get_lap_times_ms(self) -> Dict[str, float]:
        """Get lap times as dictionary in milliseconds."""
        result: Dict[str, float] = {}
        prev_ns = 0
        for name, elapsed_ns in self._laps:
            result[name] = (elapsed_ns - prev_ns) / 1_000_000
            prev_ns = elapsed_ns
        return result

    def summary(self) -> str:
        """Get human-readable summary of timing."""
        lines = [f"Total: {self.elapsed_ms:.2f}ms"]
        for name, elapsed_ms in self.get_lap_times_ms().items():
            lines.append(f"  {name}: {elapsed_ms:.2f}ms")
        return "\n".join(lines)


# =============================================================================
# BENCHMARK RESULT DATACLASSES
# =============================================================================


@dataclass
class TimingResult:
    """Timing metrics for a single benchmark run."""

    elapsed_ms: float
    throughput_per_sec: float
    items_processed: int

    @classmethod
    def from_timer(
        cls,
        elapsed_ms: float,
        items_processed: int,
    ) -> "TimingResult":
        """Create from timer result and item count."""
        throughput = items_processed / (elapsed_ms / 1000) if elapsed_ms > 0 else 0
        return cls(
            elapsed_ms=elapsed_ms,
            throughput_per_sec=throughput,
            items_processed=items_processed,
        )


@dataclass
class QualityResult:
    """Quality metrics for algorithm outputs."""

    total_outputs: int
    valid_outputs: int
    high_quality_outputs: int  # Exceeds quality threshold

    @property
    def validity_rate(self) -> float:
        """Fraction of valid outputs."""
        return self.valid_outputs / self.total_outputs if self.total_outputs > 0 else 0.0

    @property
    def quality_rate(self) -> float:
        """Fraction of high-quality outputs."""
        return self.high_quality_outputs / self.total_outputs if self.total_outputs > 0 else 0.0


@dataclass
class DistributionStats:
    """Statistics for a numeric distribution."""

    count: int
    min_value: float
    max_value: float
    mean: float
    median: float
    std_dev: float
    p25: float  # 25th percentile
    p75: float  # 75th percentile
    p95: float  # 95th percentile

    @classmethod
    def from_values(cls, values: List[float]) -> "DistributionStats":
        """Calculate statistics from a list of values."""
        if not values:
            return cls(
                count=0, min_value=0, max_value=0, mean=0, median=0, std_dev=0, p25=0, p75=0, p95=0
            )

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        def percentile(p: float) -> float:
            k = (n - 1) * p
            f = int(k)
            c = f + 1 if f < n - 1 else f
            return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)

        return cls(
            count=n,
            min_value=min(values),
            max_value=max(values),
            mean=statistics.mean(values),
            median=statistics.median(values),
            std_dev=statistics.stdev(values) if n > 1 else 0.0,
            p25=percentile(0.25),
            p75=percentile(0.75),
            p95=percentile(0.95),
        )


@dataclass
class AlgorithmBenchmarkResult:
    """Complete benchmark result for an algorithm."""

    algorithm_name: str
    scale: str
    timing: TimingResult
    quality: QualityResult
    output_stats: Dict[str, DistributionStats] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"=== {self.algorithm_name} Benchmark ({self.scale}) ===",
            "Timing:",
            f"  Elapsed: {self.timing.elapsed_ms:.2f}ms",
            f"  Throughput: {self.timing.throughput_per_sec:.1f}/sec",
            f"  Items: {self.timing.items_processed}",
            "Quality:",
            f"  Total: {self.quality.total_outputs}",
            f"  Valid: {self.quality.valid_outputs} ({self.quality.validity_rate:.1%})",
            f"  High Quality: {self.quality.high_quality_outputs} ({self.quality.quality_rate:.1%})",
        ]

        for stat_name, stats in self.output_stats.items():
            lines.append(f"{stat_name}:")
            lines.append(f"  Mean: {stats.mean:.3f} (±{stats.std_dev:.3f})")
            lines.append(f"  Range: [{stats.min_value:.3f}, {stats.max_value:.3f}]")
            lines.append(f"  P50: {stats.median:.3f}, P95: {stats.p95:.3f}")

        return "\n".join(lines)


# =============================================================================
# BENCHMARK COLLECTORS
# =============================================================================


class BenchmarkCollector:
    """
    Collects metrics across multiple benchmark runs.

    Usage:
        collector = BenchmarkCollector("CPN")

        for i in range(10):
            with collector.time_run() as run:
                results = algorithm.generate(...)
                run["outputs"] = results

            collector.record_outputs(
                total=len(results),
                valid=len([r for r in results if r.is_valid]),
                high_quality=len([r for r in results if r.score > 0.7])
            )

        summary = collector.summarize()
    """

    def __init__(self, algorithm_name: str):
        """Initialize collector."""
        self.algorithm_name = algorithm_name
        self._timing_samples: List[float] = []
        self._quality_samples: List[Dict[str, int]] = []
        self._output_samples: Dict[str, List[float]] = {}
        self._metadata: Dict[str, Any] = {}

    @contextmanager
    def time_run(self) -> Generator[Dict[str, Any], None, None]:
        """Context manager to time a single run."""
        result: Dict[str, Any] = {}
        start_ns = time.perf_counter_ns()
        try:
            yield result
        finally:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            self._timing_samples.append(elapsed_ms)
            result["elapsed_ms"] = elapsed_ms

    def record_timing(self, elapsed_ms: float) -> None:
        """Manually record a timing sample."""
        self._timing_samples.append(elapsed_ms)

    def record_quality(
        self,
        total: int,
        valid: int,
        high_quality: int,
    ) -> None:
        """Record quality metrics for a run."""
        self._quality_samples.append(
            {
                "total": total,
                "valid": valid,
                "high_quality": high_quality,
            }
        )

    def record_output_value(self, name: str, value: float) -> None:
        """Record a single output value for distribution analysis."""
        if name not in self._output_samples:
            self._output_samples[name] = []
        self._output_samples[name].append(value)

    def record_output_values(self, name: str, values: List[float]) -> None:
        """Record multiple output values."""
        if name not in self._output_samples:
            self._output_samples[name] = []
        self._output_samples[name].extend(values)

    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata about the benchmark."""
        self._metadata[key] = value

    def summarize(self, scale: str = "unknown") -> AlgorithmBenchmarkResult:
        """Generate summary of collected metrics."""
        # Aggregate timing
        timing_stats = DistributionStats.from_values(self._timing_samples)
        total_items = sum(q["total"] for q in self._quality_samples)

        timing = TimingResult(
            elapsed_ms=timing_stats.mean,
            throughput_per_sec=(
                total_items / (sum(self._timing_samples) / 1000) if self._timing_samples else 0
            ),
            items_processed=total_items,
        )

        # Aggregate quality
        total = sum(q["total"] for q in self._quality_samples)
        valid = sum(q["valid"] for q in self._quality_samples)
        high_quality = sum(q["high_quality"] for q in self._quality_samples)

        quality = QualityResult(
            total_outputs=total,
            valid_outputs=valid,
            high_quality_outputs=high_quality,
        )

        # Compute output stats
        output_stats = {
            name: DistributionStats.from_values(values)
            for name, values in self._output_samples.items()
        }

        # Add timing distribution
        output_stats["timing_ms"] = timing_stats

        return AlgorithmBenchmarkResult(
            algorithm_name=self.algorithm_name,
            scale=scale,
            timing=timing,
            quality=quality,
            output_stats=output_stats,
            metadata=self._metadata,
        )


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================


def validate_insight(insight: Any, thresholds: Dict[str, float]) -> tuple[bool, bool]:
    """
    Validate an insight object.

    Args:
        insight: Insight object to validate
        thresholds: Quality thresholds (novelty, confidence, serendipity)

    Returns:
        Tuple of (is_valid, is_high_quality)
    """
    # Basic validity checks
    try:
        has_id = hasattr(insight, "insight_id") and insight.insight_id
        has_description = hasattr(insight, "description") and insight.description
        has_confidence = hasattr(insight, "confidence") and 0 <= insight.confidence <= 1
        has_novelty = hasattr(insight, "novelty_score") and 0 <= insight.novelty_score <= 1

        is_valid = has_id and has_description and has_confidence and has_novelty
    except Exception:
        return False, False

    if not is_valid:
        return False, False

    # High quality checks
    novelty_threshold = thresholds.get("novelty", 0.5)
    confidence_threshold = thresholds.get("confidence", 0.5)
    serendipity_threshold = thresholds.get("serendipity", 0.6)

    is_high_quality = (
        insight.novelty_score >= novelty_threshold
        and insight.confidence >= confidence_threshold
        and getattr(insight, "serendipity_score", 0) >= serendipity_threshold
    )

    return True, is_high_quality


def validate_counterfactual(
    counterfactual: Any,
    thresholds: Dict[str, float],
) -> tuple[bool, bool]:
    """
    Validate a counterfactual scenario.

    Args:
        counterfactual: Counterfactual object to validate
        thresholds: Quality thresholds (plausibility, utility_delta)

    Returns:
        Tuple of (is_valid, is_high_quality)
    """
    try:
        has_id = hasattr(counterfactual, "scenario_id") and counterfactual.scenario_id
        has_type = hasattr(counterfactual, "scenario_type")
        has_plausibility = (
            hasattr(counterfactual, "plausibility") and 0 <= counterfactual.plausibility <= 1
        )

        is_valid = has_id and has_type and has_plausibility
    except Exception:
        return False, False

    if not is_valid:
        return False, False

    # High quality checks
    plausibility_threshold = thresholds.get("plausibility", 0.3)
    utility_threshold = thresholds.get("utility_delta", 0.3)

    is_high_quality = (
        counterfactual.plausibility >= plausibility_threshold
        and abs(getattr(counterfactual, "utility_delta", 0)) >= utility_threshold
    )

    return True, is_high_quality


def validate_mcts_scenario(
    scenario: Any,
    thresholds: Dict[str, float],
) -> tuple[bool, bool]:
    """
    Validate an MCTS scenario.

    Args:
        scenario: MCTSScenario object to validate
        thresholds: Quality thresholds

    Returns:
        Tuple of (is_valid, is_high_quality)
    """
    try:
        has_id = hasattr(scenario, "scenario_id") and scenario.scenario_id
        has_actions = hasattr(scenario, "action_sequence") and len(scenario.action_sequence) > 0
        has_probability = (
            hasattr(scenario, "success_probability") and 0 <= scenario.success_probability <= 1
        )

        is_valid = has_id and has_actions and has_probability
    except Exception:
        return False, False

    if not is_valid:
        return False, False

    # High quality checks
    probability_threshold = thresholds.get("success_probability", 0.3)
    visit_threshold = thresholds.get("min_visits", 5)

    is_high_quality = (
        scenario.success_probability >= probability_threshold
        and getattr(scenario, "visit_count", 0) >= visit_threshold
    )

    return True, is_high_quality


# =============================================================================
# REPORT GENERATION
# =============================================================================


def generate_benchmark_report(
    results: List[AlgorithmBenchmarkResult],
    output_format: str = "text",
) -> str:
    """
    Generate a comprehensive benchmark report.

    Args:
        results: List of benchmark results
        output_format: "text" or "markdown"

    Returns:
        Formatted report string
    """
    if output_format == "markdown":
        return _generate_markdown_report(results)
    else:
        return _generate_text_report(results)


def _generate_text_report(results: List[AlgorithmBenchmarkResult]) -> str:
    """Generate plain text report."""
    lines = [
        "=" * 70,
        "R5 DREAM PHASE ALGORITHM BENCHMARK REPORT",
        "=" * 70,
        "",
    ]

    for result in results:
        lines.append(result.summary())
        lines.append("")

    # Summary table
    lines.append("-" * 70)
    lines.append("SUMMARY")
    lines.append("-" * 70)
    lines.append(f"{'Algorithm':<20} {'Time (ms)':<12} {'Outputs':<10} {'Quality':<10}")
    lines.append("-" * 70)

    for result in results:
        lines.append(
            f"{result.algorithm_name:<20} "
            f"{result.timing.elapsed_ms:<12.2f} "
            f"{result.quality.total_outputs:<10} "
            f"{result.quality.quality_rate:<10.1%}"
        )

    return "\n".join(lines)


def _generate_markdown_report(results: List[AlgorithmBenchmarkResult]) -> str:
    """Generate Markdown report."""
    lines = [
        "# R5 Dream Phase Algorithm Benchmark Report",
        "",
        "## Summary",
        "",
        "| Algorithm | Time (ms) | Outputs | Valid Rate | Quality Rate |",
        "|-----------|-----------|---------|------------|--------------|",
    ]

    for result in results:
        lines.append(
            f"| {result.algorithm_name} "
            f"| {result.timing.elapsed_ms:.2f} "
            f"| {result.quality.total_outputs} "
            f"| {result.quality.validity_rate:.1%} "
            f"| {result.quality.quality_rate:.1%} |"
        )

    lines.append("")
    lines.append("## Detailed Results")

    for result in results:
        lines.append("")
        lines.append(f"### {result.algorithm_name}")
        lines.append("")
        lines.append("```")
        lines.append(result.summary())
        lines.append("```")

    return "\n".join(lines)
