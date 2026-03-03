"""Phase 4: Weight Configuration Scoring -- batch runner + metrics.

Runs all events through the R1 formula with 4 weight configurations,
computes tier separation metrics, and writes results.

Usage:
    python -m poc.r1_weight_research.run_matrix [--shards N] [--output-dir DIR]

Default: processes all 113 shards, writes to poc/r1_weight_research/results/
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .config import ALL_CONFIGS, WeightConfig
from .proxy_labels import assign_proxy_tier
from .scorer import compute_importance, score_to_tier
from .signal_derive import R1SignalVector, derive_signal_vector

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(r"D:\Modeling_studio\data\familyos\unified\output_healed_merged")
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# Scored event record
# ---------------------------------------------------------------------------


@dataclass
class ScoredRecord:
    """One event scored by one config."""

    event_id: str
    proxy_tier: str
    score: float
    computed_tier: str
    config_name: str


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------


def cohens_d(group_a: list[float], group_b: list[float]) -> float:
    """Compute Cohen's d effect size between two groups.

    Returns 0.0 if either group has < 2 elements or zero variance.
    """
    if len(group_a) < 2 or len(group_b) < 2:
        return 0.0
    mean_a = statistics.mean(group_a)
    mean_b = statistics.mean(group_b)
    var_a = statistics.variance(group_a)
    var_b = statistics.variance(group_b)
    pooled_std = math.sqrt((var_a + var_b) / 2)
    if pooled_std == 0:
        return 0.0
    return (mean_a - mean_b) / pooled_std


@dataclass
class ConfigMetrics:
    """Aggregate metrics for one weight configuration."""

    config_name: str
    total_events: int

    # Mean score per proxy tier
    tier_means: Dict[str, float]
    tier_stds: Dict[str, float]
    tier_counts: Dict[str, int]

    # Cohen's d between adjacent tiers (higher is better)
    cohens_d_pairs: Dict[str, float]

    # Misclassification rates
    false_positive_rate: float  # scored > 0.8 but proxy = LOW
    false_negative_rate: float  # scored < 0.3 but proxy = HIGH/CRITICAL

    # Score distribution stats
    score_mean: float
    score_std: float
    score_p10: float
    score_p25: float
    score_p50: float
    score_p75: float
    score_p90: float

    # Tier agreement: what % of events match proxy tier
    tier_agreement_rate: float


def compute_metrics(
    scores_by_tier: Dict[str, list[float]],
    all_scores: list[float],
    all_proxy_tiers: list[str],
    all_computed_tiers: list[str],
    config_name: str,
) -> ConfigMetrics:
    """Compute all metrics for one weight configuration."""
    total = len(all_scores)

    # Tier means and stds
    tier_means = {}
    tier_stds = {}
    tier_counts = {}
    tier_order_list = ["CRITICAL", "HIGH", "MEDIUM_HIGH", "MEDIUM", "LOW_MEDIUM", "LOW"]
    for tier in tier_order_list:
        scores = scores_by_tier.get(tier, [])
        tier_counts[tier] = len(scores)
        if scores:
            tier_means[tier] = statistics.mean(scores)
            tier_stds[tier] = statistics.stdev(scores) if len(scores) > 1 else 0.0
        else:
            tier_means[tier] = 0.0
            tier_stds[tier] = 0.0

    # Cohen's d between adjacent tiers
    cohens_pairs = {}
    for i in range(len(tier_order_list) - 1):
        high_tier = tier_order_list[i]
        low_tier = tier_order_list[i + 1]
        pair_key = f"{high_tier}_vs_{low_tier}"
        high_scores = scores_by_tier.get(high_tier, [])
        low_scores = scores_by_tier.get(low_tier, [])
        cohens_pairs[pair_key] = cohens_d(high_scores, low_scores)

    # Misclassification
    false_positives = sum(
        1 for s, pt in zip(all_scores, all_proxy_tiers) if s > 0.80 and pt == "LOW"
    )
    false_negatives = sum(
        1 for s, pt in zip(all_scores, all_proxy_tiers) if s < 0.30 and pt in ("HIGH", "CRITICAL")
    )
    fp_low_count = all_proxy_tiers.count("LOW")
    fn_high_count = sum(1 for pt in all_proxy_tiers if pt in ("HIGH", "CRITICAL"))
    fp_rate = false_positives / max(1, fp_low_count)
    fn_rate = false_negatives / max(1, fn_high_count)

    # Score distribution percentiles
    sorted_scores = sorted(all_scores)
    n = len(sorted_scores)

    def percentile(p: float) -> float:
        idx = int(p / 100 * (n - 1))
        return sorted_scores[idx]

    # Tier agreement
    matches = sum(1 for pt, ct in zip(all_proxy_tiers, all_computed_tiers) if pt == ct)
    agreement = matches / max(1, total)

    return ConfigMetrics(
        config_name=config_name,
        total_events=total,
        tier_means=tier_means,
        tier_stds=tier_stds,
        tier_counts=tier_counts,
        cohens_d_pairs=cohens_pairs,
        false_positive_rate=fp_rate,
        false_negative_rate=fn_rate,
        score_mean=statistics.mean(all_scores),
        score_std=statistics.stdev(all_scores) if n > 1 else 0.0,
        score_p10=percentile(10),
        score_p25=percentile(25),
        score_p50=percentile(50),
        score_p75=percentile(75),
        score_p90=percentile(90),
        tier_agreement_rate=agreement,
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def load_shards(data_dir: Path, max_shards: int = 0) -> list[Dict[str, Any]]:
    """Load all JSONL shards into memory. Returns list of raw event dicts."""
    shard_files = sorted(data_dir.glob("shard_*.jsonl"))
    if max_shards > 0:
        shard_files = shard_files[:max_shards]

    events = []
    for shard_path in shard_files:
        with open(shard_path, encoding="utf-8") as f:
            for line in f:
                events.append(json.loads(line))
    return events


def run_matrix(
    events: list[Dict[str, Any]],
    configs: list[WeightConfig],
    output_dir: Path,
) -> Dict[str, ConfigMetrics]:
    """Score all events with all configs. Returns metrics per config."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: derive signal vectors + Phase 2: proxy labels (once)
    print(f"Deriving signal vectors for {len(events)} events...")
    t0 = time.perf_counter()
    vectors: list[R1SignalVector] = []
    proxy_tiers: list[str] = []
    derive_errors = 0
    for event in events:
        try:
            vec = derive_signal_vector(event)
            tier = assign_proxy_tier(event)
            vec.proxy_tier = tier
            vectors.append(vec)
            proxy_tiers.append(tier)
        except Exception:
            derive_errors += 1

    t1 = time.perf_counter()
    print(
        f"  Derived {len(vectors)} vectors in {t1 - t0:.1f}s "
        f"({len(vectors) / max(0.01, t1 - t0):.0f}/sec), "
        f"errors: {derive_errors}"
    )

    # Phase 4: score with each config
    all_metrics: Dict[str, ConfigMetrics] = {}

    for cfg in configs:
        print(f"\nScoring with config {cfg.name} (total={cfg.total:.2f})...")
        t2 = time.perf_counter()

        scores_by_tier: Dict[str, list[float]] = defaultdict(list)
        all_scores: list[float] = []
        all_computed_tiers: list[str] = []
        csv_rows: list[list] = []

        for vec in vectors:
            score = compute_importance(vec, cfg)
            computed_tier = score_to_tier(score)
            all_scores.append(score)
            all_computed_tiers.append(computed_tier)
            scores_by_tier[vec.proxy_tier].append(score)
            csv_rows.append(
                [
                    vec.event_id,
                    vec.proxy_tier,
                    f"{score:.4f}",
                    computed_tier,
                ]
            )

        t3 = time.perf_counter()
        print(f"  Scored {len(all_scores)} events in {t3 - t2:.1f}s")

        # Write CSV
        csv_path = output_dir / f"scores_{cfg.name}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["event_id", "proxy_tier", "score", "computed_tier"])
            writer.writerows(csv_rows)
        print(f"  Wrote {csv_path}")

        # Compute metrics
        metrics = compute_metrics(
            scores_by_tier=scores_by_tier,
            all_scores=all_scores,
            all_proxy_tiers=proxy_tiers,
            all_computed_tiers=all_computed_tiers,
            config_name=cfg.name,
        )
        all_metrics[cfg.name] = metrics

        # Print summary
        print(f"\n  --- {cfg.name} Summary ---")
        print(
            f"  Score: mean={metrics.score_mean:.3f}, std={metrics.score_std:.3f}, "
            f"p10={metrics.score_p10:.3f}, p50={metrics.score_p50:.3f}, p90={metrics.score_p90:.3f}"
        )
        print("  Tier means:")
        for tier in ["CRITICAL", "HIGH", "MEDIUM_HIGH", "MEDIUM", "LOW_MEDIUM", "LOW"]:
            n = metrics.tier_counts[tier]
            m = metrics.tier_means[tier]
            s = metrics.tier_stds[tier]
            print(f"    {tier:13s}: n={n:6d}, mean={m:.3f}, std={s:.3f}")
        print("  Cohen's d (adjacent tiers):")
        for pair, d in metrics.cohens_d_pairs.items():
            status = "GOOD" if d >= 0.5 else "WEAK" if d >= 0.2 else "POOR"
            print(f"    {pair}: d={d:.3f} [{status}]")
        print(f"  False positive rate (scored>0.8, proxy=LOW): {metrics.false_positive_rate:.3f}")
        print(
            f"  False negative rate (scored<0.3, proxy=HIGH/CRITICAL): {metrics.false_negative_rate:.3f}"
        )
        print(f"  Tier agreement rate: {metrics.tier_agreement_rate:.3f}")

    # Write summary comparison
    write_summary(all_metrics, output_dir)

    return all_metrics


def write_summary(
    all_metrics: Dict[str, ConfigMetrics],
    output_dir: Path,
) -> None:
    """Write summary.md comparing all configurations."""
    summary_path = output_dir / "summary.md"
    tier_order = ["CRITICAL", "HIGH", "MEDIUM_HIGH", "MEDIUM", "LOW_MEDIUM", "LOW"]

    lines = [
        "# R1 Weight Research -- Results Summary",
        "",
        f"> Generated: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Score Distribution",
        "",
        "| Config | Mean | Std | P10 | P25 | P50 | P75 | P90 |",
        "| - | - | - | - | - | - | - | - |",
    ]
    for name, m in all_metrics.items():
        lines.append(
            f"| {name} | {m.score_mean:.3f} | {m.score_std:.3f} | "
            f"{m.score_p10:.3f} | {m.score_p25:.3f} | {m.score_p50:.3f} | "
            f"{m.score_p75:.3f} | {m.score_p90:.3f} |"
        )

    lines += [
        "",
        "## Tier Mean Scores (higher proxy tier should have higher mean score)",
        "",
        "| Tier | " + " | ".join(all_metrics.keys()) + " |",
        "| - | " + " | ".join(["-"] * len(all_metrics)) + " |",
    ]
    for tier in tier_order:
        row = f"| {tier} |"
        for name, m in all_metrics.items():
            row += f" {m.tier_means[tier]:.3f} |"
        lines.append(row)

    lines += [
        "",
        "## Cohen's d (Adjacent Tier Separation)",
        "",
        "Target: d >= 0.5 for each pair (medium effect size).",
        "",
    ]
    # Get pair keys from first config
    first_metrics = next(iter(all_metrics.values()))
    pair_keys = list(first_metrics.cohens_d_pairs.keys())
    lines.append("| Pair | " + " | ".join(all_metrics.keys()) + " |")
    lines.append("| - | " + " | ".join(["-"] * len(all_metrics)) + " |")
    for pair in pair_keys:
        row = f"| {pair} |"
        for name, m in all_metrics.items():
            d = m.cohens_d_pairs[pair]
            tag = "GOOD" if d >= 0.5 else "WEAK" if d >= 0.2 else "POOR"
            row += f" {d:.3f} ({tag}) |"
        lines.append(row)

    lines += [
        "",
        "## Misclassification Rates",
        "",
        "| Config | FP (>0.8, LOW) | FN (<0.3, HIGH/CRIT) | Tier Agreement |",
        "| - | - | - | - |",
    ]
    for name, m in all_metrics.items():
        lines.append(
            f"| {name} | {m.false_positive_rate:.3f} | "
            f"{m.false_negative_rate:.3f} | {m.tier_agreement_rate:.3f} |"
        )

    # Determine winner
    lines += [
        "",
        "## Winner Selection",
        "",
    ]
    # Score: average Cohen's d across all pairs
    winner_name = ""
    best_avg_d = -1.0
    for name, m in all_metrics.items():
        avg_d = statistics.mean(m.cohens_d_pairs.values())
        monotonic = all(
            m.tier_means[tier_order[i]] >= m.tier_means[tier_order[i + 1]]
            for i in range(len(tier_order) - 1)
        )
        lines.append(
            f"- **{name}**: avg Cohen's d = {avg_d:.3f}, "
            f"monotonic tier ordering = {'YES' if monotonic else 'NO'}, "
            f"FP = {m.false_positive_rate:.3f}, FN = {m.false_negative_rate:.3f}"
        )
        if avg_d > best_avg_d:
            best_avg_d = avg_d
            winner_name = name

    lines += [
        "",
        f"**Recommended config: {winner_name}** (highest average Cohen's d = {best_avg_d:.3f})",
        "",
    ]

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nWrote summary to {summary_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="R1 Weight Research -- Phase 4 matrix scoring")
    parser.add_argument("--shards", type=int, default=0, help="Max shards to process (0 = all)")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory for results",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    print(f"Loading shards from {DATA_DIR}...")
    events = load_shards(DATA_DIR, max_shards=args.shards)
    print(f"Loaded {len(events)} events")

    run_matrix(events, ALL_CONFIGS, output_dir)


if __name__ == "__main__":
    main()
