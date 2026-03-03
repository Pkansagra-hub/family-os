"""Phase 5: Lambda + Reliability Floor Calibration.

Part A -- Lambda grid on full dataset:
  Score 562K events at simulated ages [1h, 6h, 24h, 72h, 168h] with
  lambda values [0.005, 0.01, 0.02, 0.05] using the winning config.
  Find the lambda where tier boundaries remain stable.

Part B -- Reliability floor on hand-crafted scenarios:
  Scenarios 6, 13, 15 from Section 16.6.4 with floor values
  [0.0, 0.3, 0.5, 0.7].

Usage:
    python -m poc.r1_weight_research.calibrate [--shards N] [--all-configs]
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
from typing import Dict

from .config import ALL_CONFIGS, CONFIG_B, LAMBDA_VALUES, RELIABILITY_FLOORS, WeightConfig
from .proxy_labels import assign_proxy_tier
from .scorer import compute_importance, score_to_tier
from .signal_derive import R1SignalVector, derive_signal_vector

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(r"D:\Modeling_studio\data\familyos\unified\output_healed_merged")
OUTPUT_DIR = Path(__file__).parent / "results"

SIMULATED_AGES_H = [1, 6, 24, 72, 168]  # hours
TIER_ORDER = ["CRITICAL", "HIGH", "MEDIUM_HIGH", "MEDIUM", "LOW_MEDIUM", "LOW"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def recency_factor(lam: float, age_h: float) -> float:
    """exp(-lambda * age_hours)."""
    return math.exp(-lam * age_h)


def cohens_d(a: list[float], b: list[float]) -> float:
    if len(a) < 2 or len(b) < 2:
        return 0.0
    va = statistics.variance(a)
    vb = statistics.variance(b)
    pooled = math.sqrt((va + vb) / 2)
    if pooled == 0:
        return 0.0
    return (statistics.mean(a) - statistics.mean(b)) / pooled


@dataclass
class TierMetrics:
    """Compact tier-separation metrics for one scoring pass."""

    config_name: str
    lam: float
    age_h: int
    rf: float  # recency_factor applied
    total: int
    tier_means: Dict[str, float]
    tier_counts: Dict[str, int]
    cohens_pairs: Dict[str, float]
    avg_cohens_d: float
    is_monotonic: bool
    fp_rate: float  # scored > 0.80 but proxy LOW
    fn_rate: float  # scored < 0.30 but proxy HIGH/CRITICAL
    score_mean: float
    score_p50: float


# ---------------------------------------------------------------------------
# Part A: Lambda grid
# ---------------------------------------------------------------------------


def score_pass(
    vectors: list[R1SignalVector],
    proxy_tiers: list[str],
    cfg: WeightConfig,
    rf: float,
) -> TierMetrics:
    """Score all vectors with one config + recency_factor. Return metrics."""
    scores_by_tier: Dict[str, list[float]] = defaultdict(list)
    all_scores: list[float] = []

    for vec, pt in zip(vectors, proxy_tiers):
        s = compute_importance(vec, cfg, recency_factor=rf)
        all_scores.append(s)
        scores_by_tier[pt].append(s)

    # Tier means
    tier_means: Dict[str, float] = {}
    tier_counts: Dict[str, int] = {}
    for t in TIER_ORDER:
        vals = scores_by_tier.get(t, [])
        tier_counts[t] = len(vals)
        tier_means[t] = statistics.mean(vals) if vals else 0.0

    # Cohen's d
    cohens_pairs: Dict[str, float] = {}
    for i in range(len(TIER_ORDER) - 1):
        hi, lo = TIER_ORDER[i], TIER_ORDER[i + 1]
        cohens_pairs[f"{hi}_vs_{lo}"] = cohens_d(
            scores_by_tier.get(hi, []), scores_by_tier.get(lo, [])
        )

    avg_d = statistics.mean(cohens_pairs.values()) if cohens_pairs else 0.0
    monotonic = all(
        tier_means.get(TIER_ORDER[i], 0) >= tier_means.get(TIER_ORDER[i + 1], 0)
        for i in range(len(TIER_ORDER) - 1)
    )

    # Misclassification
    fp_low = sum(1 for s, pt in zip(all_scores, proxy_tiers) if s > 0.80 and pt == "LOW")
    fn_high = sum(
        1 for s, pt in zip(all_scores, proxy_tiers) if s < 0.30 and pt in ("HIGH", "CRITICAL")
    )
    low_count = proxy_tiers.count("LOW")
    high_count = sum(1 for pt in proxy_tiers if pt in ("HIGH", "CRITICAL"))

    n = len(all_scores)
    sorted_scores = sorted(all_scores)

    return TierMetrics(
        config_name=cfg.name,
        lam=0.0,
        age_h=0,
        rf=rf,
        total=n,
        tier_means=tier_means,
        tier_counts=tier_counts,
        cohens_pairs=cohens_pairs,
        avg_cohens_d=avg_d,
        is_monotonic=monotonic,
        fp_rate=fp_low / max(1, low_count),
        fn_rate=fn_high / max(1, high_count),
        score_mean=statistics.mean(all_scores),
        score_p50=sorted_scores[n // 2] if n else 0.0,
    )


def run_lambda_grid(
    vectors: list[R1SignalVector],
    proxy_tiers: list[str],
    configs: list[WeightConfig],
    output_dir: Path,
) -> list[TierMetrics]:
    """Score all vectors at every lambda x age_h combo. Returns metrics list."""
    results: list[TierMetrics] = []

    for cfg in configs:
        print(f"\n=== Lambda grid for {cfg.name} ===")
        for lam in LAMBDA_VALUES:
            for age_h in SIMULATED_AGES_H:
                rf = recency_factor(lam, age_h)
                m = score_pass(vectors, proxy_tiers, cfg, rf)
                m.lam = lam
                m.age_h = age_h
                results.append(m)

    # Write CSV
    csv_path = output_dir / "lambda_grid.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "config",
                "lambda",
                "age_h",
                "recency_factor",
                "score_mean",
                "score_p50",
                "CRITICAL_mean",
                "HIGH_mean",
                "MEDIUM_HIGH_mean",
                "MEDIUM_mean",
                "LOW_MEDIUM_mean",
                "LOW_mean",
                "d_CRIT_HIGH",
                "d_HIGH_MHIGH",
                "d_MHIGH_MED",
                "d_MED_LMED",
                "d_LMED_LOW",
                "avg_cohens_d",
                "monotonic",
                "fp_rate",
                "fn_rate",
            ]
        )
        for m in results:
            w.writerow(
                [
                    m.config_name,
                    m.lam,
                    m.age_h,
                    f"{m.rf:.4f}",
                    f"{m.score_mean:.4f}",
                    f"{m.score_p50:.4f}",
                    *[f"{m.tier_means.get(t, 0):.4f}" for t in TIER_ORDER],
                    *[f"{v:.4f}" for v in m.cohens_pairs.values()],
                    f"{m.avg_cohens_d:.4f}",
                    m.is_monotonic,
                    f"{m.fp_rate:.4f}",
                    f"{m.fn_rate:.4f}",
                ]
            )

    print(f"\nWrote lambda grid CSV: {csv_path}")
    return results


# ---------------------------------------------------------------------------
# Part B: Hand-crafted scenarios for reliability floor + recency
# ---------------------------------------------------------------------------


def build_scenario_vectors() -> list[R1SignalVector]:
    """Build signal vectors for scenarios 6, 13, 15 from Section 16.6.4."""
    return [
        # Scenario 6: System infers grocery trip from location
        R1SignalVector(
            event_id="scenario_06_grocery",
            sentiment_score=0.0,
            affect_valence=0.0,
            affect_arousal=0.0,
            affect_dominance=0.5,
            surprise_level=0.0,
            num_participants=1,
            social_intimacy="LOW",
            activity_type="location",
            intent="other",
            novelty="ROUTINE",
            elaboration_depth="MENTION",
            temporal_orientation="ONGOING",
            identity_relevance=0.0,
            source_type="device_observed",
            source_reliability=0.70,
            narrative_is_goal_event=False,
            narrative_arc_position="EXPOSITION",
            memory_tier="routine",
            proxy_tier="LOW_MEDIUM",
            word_count=5,
        ),
        # Scenario 13: Moderate family event (used for recency comparison)
        R1SignalVector(
            event_id="scenario_13_recency_test",
            sentiment_score=0.50,
            affect_valence=0.50,
            affect_arousal=0.50,
            affect_dominance=0.50,
            surprise_level=0.0,
            num_participants=3,
            social_intimacy="HIGH",
            activity_type="message",
            intent="share_news",
            novelty="EXPECTED",
            elaboration_depth="DISCUSSED",
            temporal_orientation="PAST",
            identity_relevance=0.30,
            source_type="user_stated",
            source_reliability=0.95,
            narrative_is_goal_event=False,
            narrative_arc_position="EXPOSITION",
            memory_tier="routine",
            proxy_tier="MEDIUM_HIGH",
            word_count=15,
        ),
        # Scenario 15: Low-confidence system inference, old event
        R1SignalVector(
            event_id="scenario_15_low_confidence",
            sentiment_score=0.0,
            affect_valence=0.0,
            affect_arousal=0.0,
            affect_dominance=0.5,
            surprise_level=0.0,
            num_participants=1,
            social_intimacy="LOW",
            activity_type="routine",
            intent="other",
            novelty="ROUTINE",
            elaboration_depth="MENTION",
            temporal_orientation="PAST",
            identity_relevance=0.0,
            source_type="system_inferred",
            source_reliability=0.35,
            narrative_is_goal_event=False,
            narrative_arc_position="EXPOSITION",
            memory_tier="routine",
            proxy_tier="LOW",
            word_count=3,
        ),
    ]


def run_reliability_floor_test(
    scenarios: list[R1SignalVector],
    cfg: WeightConfig,
    output_dir: Path,
) -> None:
    """Test scenarios 6 + 15 with different reliability floors."""
    print("\n=== Reliability Floor Test (Scenarios 6, 15) ===")
    print(f"Config: {cfg.name}")

    floor_scenarios = [
        s for s in scenarios if s.event_id in ("scenario_06_grocery", "scenario_15_low_confidence")
    ]

    rows: list[list] = []
    for vec in floor_scenarios:
        raw_reliability = vec.source_reliability
        print(f"\n  {vec.event_id} (raw reliability={raw_reliability:.2f}):")
        for floor in RELIABILITY_FLOORS:
            # Apply floor: effective = max(floor, raw)
            effective = max(floor, raw_reliability)
            # Temporarily set reliability on vector
            original = vec.source_reliability
            vec.source_reliability = effective
            score = compute_importance(vec, cfg, recency_factor=1.0)
            tier = score_to_tier(score)
            vec.source_reliability = original  # restore
            print(
                f"    floor={floor:.1f} -> reliability={effective:.2f}, "
                f"score={score:.4f}, tier={tier}"
            )
            rows.append([vec.event_id, raw_reliability, floor, effective, f"{score:.4f}", tier])

    csv_path = output_dir / "reliability_floor.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["scenario", "raw_reliability", "floor", "effective_reliability", "score", "tier"]
        )
        w.writerows(rows)
    print(f"\n  Wrote: {csv_path}")


def run_recency_scenario_test(
    scenarios: list[R1SignalVector],
    cfg: WeightConfig,
) -> None:
    """Test scenario 13 at different ages with different lambdas."""
    print("\n=== Recency Scenario Test (Scenario 13) ===")
    print(f"Config: {cfg.name}")

    vec = next(s for s in scenarios if s.event_id == "scenario_13_recency_test")
    base_score = compute_importance(vec, cfg, recency_factor=1.0)
    base_tier = score_to_tier(base_score)
    print(f"  Base (fresh): score={base_score:.4f}, tier={base_tier}")

    test_ages = [1, 6, 24, 48, 72, 168]
    print(f"\n  {'Lambda':<8} | ", end="")
    for age in test_ages:
        print(f"{age:>5}h", end="  ")
    print()
    print(f"  {'------':<8}-+-", end="")
    print("-------" * len(test_ages))

    for lam in LAMBDA_VALUES:
        print(f"  {lam:<8.3f} | ", end="")
        for age in test_ages:
            rf = recency_factor(lam, age)
            score = compute_importance(vec, cfg, recency_factor=rf)
            tier = score_to_tier(score)
            # Show abbreviated tier + score
            abbrev = {
                "CRITICAL": "CR",
                "HIGH": "HI",
                "MEDIUM_HIGH": "MH",
                "MEDIUM": "ME",
                "LOW_MEDIUM": "LM",
                "LOW": "LO",
            }
            print(f" {score:.2f}{abbrev[tier]}", end="")
        print()

    # Also show recency_factor values for reference
    print("\n  Recency factors (exp(-lambda * age)):")
    for lam in LAMBDA_VALUES:
        factors = [f"{recency_factor(lam, a):.3f}" for a in test_ages]
        print(f"    lambda={lam:.3f}: {factors}")


# ---------------------------------------------------------------------------
# Part C: Summary analysis
# ---------------------------------------------------------------------------


def write_phase5_summary(
    lambda_results: list[TierMetrics],
    configs_tested: list[str],
    output_dir: Path,
) -> None:
    """Write Phase 5 summary with lambda + floor recommendations."""
    lines = [
        "# Phase 5: Lambda + Floor Calibration Results",
        "",
        f"> Generated: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # Lambda decay reference table
    lines += [
        "## Recency Decay Reference",
        "",
        "recency_factor = exp(-lambda * age_hours)",
        "",
        "| Lambda | 1h | 6h | 24h | 72h | 168h |",
        "| - | - | - | - | - | - |",
    ]
    for lam in LAMBDA_VALUES:
        vals = [f"{recency_factor(lam, a):.3f}" for a in SIMULATED_AGES_H]
        lines.append(f"| {lam} | {' | '.join(vals)} |")

    # Per-config lambda analysis
    for cfg_name in configs_tested:
        cfg_results = [r for r in lambda_results if r.config_name == cfg_name]
        lines += [
            "",
            f"## Config: {cfg_name}",
            "",
            "### Tier Means at Each Lambda x Age",
            "",
            "| Lambda | Age | RF | CRITICAL | HIGH | MED_HIGH | MEDIUM | LOW_MED | LOW | Avg d | Mono |",
            "| - | - | - | - | - | - | - | - | - | - | - |",
        ]
        for m in cfg_results:
            mono = "Y" if m.is_monotonic else "N"
            lines.append(
                f"| {m.lam} | {m.age_h}h | {m.rf:.3f} | "
                f"{m.tier_means.get('CRITICAL', 0):.3f} | "
                f"{m.tier_means.get('HIGH', 0):.3f} | "
                f"{m.tier_means.get('MEDIUM_HIGH', 0):.3f} | "
                f"{m.tier_means.get('MEDIUM', 0):.3f} | "
                f"{m.tier_means.get('LOW_MEDIUM', 0):.3f} | "
                f"{m.tier_means.get('LOW', 0):.3f} | "
                f"{m.avg_cohens_d:.3f} | {mono} |"
            )

        # Find best lambda: highest avg_d at age=24h
        at_24h = [r for r in cfg_results if r.age_h == 24]
        if at_24h:
            best_24h = max(at_24h, key=lambda r: r.avg_cohens_d)
            lines += [
                "",
                f"**Best lambda at 24h**: {best_24h.lam} "
                f"(avg Cohen's d = {best_24h.avg_cohens_d:.3f}, "
                f"monotonic = {best_24h.is_monotonic})",
            ]

        # Find lambda where CRITICAL still > 0.60 at 72h
        at_72h = [r for r in cfg_results if r.age_h == 72]
        safe_72h = [r for r in at_72h if r.tier_means.get("CRITICAL", 0) >= 0.40]
        if safe_72h:
            best_safe = max(safe_72h, key=lambda r: r.avg_cohens_d)
            lines += [
                f"**Safest lambda at 72h** (CRITICAL mean >= 0.40): {best_safe.lam} "
                f"(CRITICAL mean = {best_safe.tier_means.get('CRITICAL', 0):.3f})",
            ]

    # Recommendations
    lines += [
        "",
        "## Recommendations",
        "",
        "### Lambda Selection Criteria",
        "",
        "1. CRITICAL events at 24h must still score above MEDIUM_HIGH threshold (0.45)",
        "2. LOW events at 1h must still score below MEDIUM threshold (0.30)",
        "3. Tier separation (avg Cohen's d) should remain > 0.3 at 24h",
        "4. At 72h, CRITICAL events should still be distinguishable (mean > 0.40)",
        "",
    ]

    # Auto-determine best lambda across configs
    all_at_24h = [r for r in lambda_results if r.age_h == 24]
    if all_at_24h:
        # Group by lambda, pick lambda with best average across configs
        by_lam: Dict[float, list[TierMetrics]] = defaultdict(list)
        for r in all_at_24h:
            by_lam[r.lam].append(r)
        best_lam = 0.0
        best_avg_d = -1.0
        for lam, group in by_lam.items():
            avg = statistics.mean(r.avg_cohens_d for r in group)
            if avg > best_avg_d:
                best_avg_d = avg
                best_lam = lam
        lines += [
            f"**Recommended lambda: {best_lam}** (highest avg Cohen's d at 24h = {best_avg_d:.3f})",
            "",
        ]

    lines += [
        "### Reliability Floor",
        "",
        "See reliability_floor.csv for scenario-level results.",
        "Floor recommendation depends on scenario 6 + 15 outcomes:",
        "- If floor=0.0 already keeps scenario 15 LOW -> no floor needed",
        "- If floor=0.3 prevents important device_observed events from being zeroed -> use 0.3",
        "- Higher floors reduce scoring discrimination for untrusted sources",
        "",
    ]

    summary_path = output_dir / "phase5_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nWrote Phase 5 summary: {summary_path}")


# ---------------------------------------------------------------------------
# Data loading (shared with run_matrix.py)
# ---------------------------------------------------------------------------


def load_and_derive(
    data_dir: Path,
    max_shards: int = 0,
) -> tuple[list[R1SignalVector], list[str]]:
    """Load shards, derive signal vectors + proxy tiers."""
    shard_files = sorted(data_dir.glob("shard_*.jsonl"))
    if max_shards > 0:
        shard_files = shard_files[:max_shards]

    events: list[dict] = []
    for sp in shard_files:
        with open(sp, encoding="utf-8") as f:
            for line in f:
                events.append(json.loads(line))

    vectors: list[R1SignalVector] = []
    proxy_tiers: list[str] = []
    errors = 0
    for ev in events:
        try:
            vec = derive_signal_vector(ev)
            tier = assign_proxy_tier(ev)
            vec.proxy_tier = tier
            vectors.append(vec)
            proxy_tiers.append(tier)
        except Exception:
            errors += 1

    return vectors, proxy_tiers


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5: Lambda + Floor Calibration")
    parser.add_argument("--shards", type=int, default=0, help="Max shards (0 = all)")
    parser.add_argument(
        "--all-configs", action="store_true", help="Test all 4 configs (default: winner B only)"
    )
    args = parser.parse_args()

    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Select configs
    configs = ALL_CONFIGS if args.all_configs else [CONFIG_B]
    config_names = [c.name for c in configs]

    # Load data
    print(f"Loading shards from {DATA_DIR}...")
    t0 = time.perf_counter()
    vectors, proxy_tiers = load_and_derive(DATA_DIR, max_shards=args.shards)
    t1 = time.perf_counter()
    print(f"Loaded + derived {len(vectors)} vectors in {t1 - t0:.1f}s")

    # Part A: Lambda grid
    print("\n" + "=" * 60)
    print("PART A: Lambda Grid on Full Dataset")
    print("=" * 60)
    t2 = time.perf_counter()
    lambda_results = run_lambda_grid(vectors, proxy_tiers, configs, output_dir)
    t3 = time.perf_counter()
    print(f"\nLambda grid completed in {t3 - t2:.1f}s " f"({len(lambda_results)} scoring passes)")

    # Print compact lambda summary for winner config
    print("\n--- Lambda Impact Summary (B_emotion_heavy) ---")
    b_results = [r for r in lambda_results if r.config_name == "B_emotion_heavy"]
    if not b_results:
        b_results = [r for r in lambda_results if r.config_name == configs[0].name]
    print(
        f"  {'Lam':<6} {'Age':>4} {'RF':>6} {'CRITm':>7} {'HIGHm':>7} "
        f"{'LOWm':>7} {'Avg_d':>7} {'Mono':>5} {'FN':>6}"
    )
    for m in b_results:
        mono = "Y" if m.is_monotonic else "N"
        print(
            f"  {m.lam:<6.3f} {m.age_h:>4}h {m.rf:>6.3f} "
            f"{m.tier_means.get('CRITICAL', 0):>7.3f} "
            f"{m.tier_means.get('HIGH', 0):>7.3f} "
            f"{m.tier_means.get('LOW', 0):>7.3f} "
            f"{m.avg_cohens_d:>7.3f} {mono:>5} "
            f"{m.fn_rate:>6.3f}"
        )

    # Part B: Reliability floor + recency scenarios
    print("\n" + "=" * 60)
    print("PART B: Reliability Floor + Recency Scenarios")
    print("=" * 60)
    scenarios = build_scenario_vectors()
    winning_cfg = CONFIG_B
    run_reliability_floor_test(scenarios, winning_cfg, output_dir)
    run_recency_scenario_test(scenarios, winning_cfg)

    # Part C: Summary
    print("\n" + "=" * 60)
    print("PART C: Summary")
    print("=" * 60)
    write_phase5_summary(lambda_results, config_names, output_dir)

    print("\nPhase 5 complete.")


if __name__ == "__main__":
    main()
