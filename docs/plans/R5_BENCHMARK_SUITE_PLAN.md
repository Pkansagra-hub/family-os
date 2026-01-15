# R5 Dream Phase Benchmark Suite - Implementation Plan

**Status:** DRAFT
**Created:** 2026-01-12
**Target:** World-class algorithmic benchmarking for CPN, MCTS, BGT-SM, SPC-UQ

---

## Executive Summary

Transform the current single-world demo (`show_io.py`) into a **production-grade benchmark harness** with:
- Multiple scenario packs (toy, stress, adversarial, real-world)
- Real embeddings via UltraBERT
- Statistical rigor (confidence intervals, effect sizes)
- Coverage gates (pass/fail thresholds)
- Performance profiling (latency, memory, throughput)
- Regression detection across commits
- Visualization and reporting

---

## 1. Architecture Overview

```
tests/k0/modules/consolidation/benchmarks/
├── __init__.py
├── show_io.py                    # Current demo (will import from factory)
├── run_benchmarks.py             # Main benchmark runner with CLI
├── r5_data_factory.py            # World generator (scenario packs)
├── r5_embeddings.py              # UltraBERT embedding service
├── r5_coverage.py                # Coverage thresholds and validation
├── r5_statistics.py              # Statistical analysis utilities
├── r5_report.py                  # HTML/Markdown report generator
├── r5_baseline.py                # Baseline comparisons (random, greedy, etc.)
├── packs/                        # Scenario pack definitions
│   ├── __init__.py
│   ├── toy.py                    # Current small world (baseline)
│   ├── causal_deep.py            # CPN: deep causal chains
│   ├── causal_fork_join.py       # CPN: diamond patterns
│   ├── mcts_delayed.py           # MCTS: delayed reward
│   ├── mcts_constrained.py       # MCTS: time/resource budgets
│   ├── bgt_clustered.py          # BGT: semantic clusters
│   ├── bgt_adversarial.py        # BGT: hard negatives
│   ├── spc_multi_prov.py         # SPC: multiple provenance
│   ├── spc_conflict.py           # SPC: conflicting fragments
│   ├── mixed_stress.py           # All algorithms: stress test
│   └── real_world.py             # Realistic family scenarios
├── schemas/                      # SPC-UQ schema library
│   ├── morning_routine.json
│   ├── weekend_family.json
│   ├── work_conflict.json
│   └── school_event.json
├── results/                      # Benchmark outputs (gitignored)
│   ├── .gitkeep
│   └── [timestamp]_[pack]_results.json
└── baselines/                    # Golden baselines for regression
    ├── v1.0_toy_baseline.json
    └── v1.0_coverage_thresholds.json
```

---

## 2. Component Specifications

### 2.1 Data Factory (`r5_data_factory.py`)

Central world generator that produces consistent test data across packs.

```python
@dataclass
class World:
    """Complete test world for R5 algorithms."""
    pack_name: str
    seed: int

    # CPN inputs
    episodes: List[DemoEpisode]
    kg_edges: List[DemoEdge]           # CAUSES edges

    # BGT-SM inputs
    entities: List[DemoEntity]
    semantic_edges: List[DemoEdge]     # Non-causal edges
    embeddings: Dict[str, List[float]] # entity_id -> embedding

    # MCTS inputs
    initial_state: Dict[str, Any]
    actions: List[DemoAction]
    goals: List[DemoGoal]
    constraints: Optional[Dict[str, Any]]  # Time budget, preconditions

    # SPC-UQ inputs
    incomplete_episodes: List[Any]
    fragments: List[EpisodeFragment]
    schemas: Optional[List[Dict]]
    context: Dict[str, Any]

    # Metadata
    expected_properties: Dict[str, Any]  # Coverage expectations
    difficulty: str                       # easy, medium, hard, adversarial

def make_world(pack: str, seed: int = 42) -> World:
    """Factory function to create worlds from pack names."""
    ...
```

**Pack Registry:**

| Pack | Algorithm Focus | Difficulty | Key Property Tested |
|------|-----------------|------------|---------------------|
| `toy` | All | Easy | Baseline sanity |
| `causal_deep` | CPN | Medium | path_length >= 3 |
| `causal_fork_join` | CPN | Hard | Diamond DAG patterns |
| `mcts_delayed` | MCTS | Medium | Delayed reward discovery |
| `mcts_constrained` | MCTS | Hard | Budget/precondition handling |
| `bgt_clustered` | BGT-SM | Medium | Cross-cluster insights |
| `bgt_adversarial` | BGT-SM | Hard | Reject false positives |
| `spc_multi_prov` | SPC-UQ | Medium | Multiple provenance types |
| `spc_conflict` | SPC-UQ | Hard | Conflicting fragment handling |
| `mixed_stress` | All | Hard | 1000+ entities, 100+ episodes |
| `real_world` | All | Medium | Realistic family scenarios |

---

### 2.2 UltraBERT Embeddings (`r5_embeddings.py`)

Replace random embeddings with real semantic embeddings.

```python
class EmbeddingService:
    """UltraBERT-based embedding service for BGT-SM."""

    def __init__(self, model_name: str = "ultra-bert-base"):
        self.model = load_ultrabert(model_name)
        self.cache: Dict[str, List[float]] = {}

    def embed_entity(self, entity: DemoEntity) -> List[float]:
        """Generate embedding from entity name + type + category."""
        text = f"{entity.name} ({entity.entity_type}, {entity.category})"
        return self._embed(text)

    def embed_batch(self, entities: List[DemoEntity]) -> Dict[str, List[float]]:
        """Batch embedding for efficiency."""
        ...

    def _embed(self, text: str) -> List[float]:
        """Core embedding with caching."""
        if text in self.cache:
            return self.cache[text]
        embedding = self.model.encode(text)
        self.cache[text] = embedding.tolist()
        return self.cache[text]

# Fallback for CI without GPU
class ClusteredEmbeddingService:
    """Deterministic clustered embeddings (no ML required)."""

    CLUSTER_CENTERS = {
        "family": [1.0, 0.0, 0.0, ...],      # 64-dim
        "education": [0.0, 1.0, 0.0, ...],
        "work": [0.0, 0.0, 1.0, ...],
        "entertainment": [0.5, 0.5, 0.0, ...],
        "finance": [0.0, 0.0, 0.5, ...],
        "sports": [0.3, 0.0, 0.7, ...],
    }

    def embed_entity(self, entity: DemoEntity) -> List[float]:
        """Cluster center + small noise based on entity_id."""
        center = self.CLUSTER_CENTERS.get(entity.category, [0.5] * 64)
        noise = self._deterministic_noise(entity.entity_id)
        return [c + n * 0.1 for c, n in zip(center, noise)]
```

**Integration:**
- Use UltraBERT when `--real-embeddings` flag is set
- Fall back to clustered embeddings in CI/fast mode
- Cache embeddings to disk for reproducibility

---

### 2.3 Scenario Pack Specifications

#### Pack: `causal_deep` (CPN Focus)

**Goal:** Force `causal_path_length >= 3` in generated counterfactuals.

**Data Design:**
```
Causal Chain (depth 4):
  WORK_OVERLOAD
    -> MISSED_DEADLINE
      -> BOSS_DISAPPOINTED
        -> PERFORMANCE_REVIEW
          -> STRESS
            -> FAMILY_ARGUMENT

Fork Pattern:
  WORK_OVERLOAD -> MISSED_DEADLINE
  WORK_OVERLOAD -> SKIPPED_LUNCH -> FATIGUE
  FATIGUE -> STRESS
  MISSED_DEADLINE -> STRESS

Join Pattern:
  STRESS + FAMILY_ARGUMENT -> GUILT
```

**Entities (15+):**
- ENT_WORK_OVERLOAD, ENT_MISSED_DEADLINE, ENT_BOSS_DISAPPOINTED
- ENT_PERFORMANCE_REVIEW, ENT_STRESS, ENT_FAMILY_ARGUMENT
- ENT_SKIPPED_LUNCH, ENT_FATIGUE, ENT_GUILT
- ENT_APOLOGY, ENT_REPAIR_TALK, ENT_QUALITY_TIME
- ENT_LATE_ARRIVAL, ENT_MISSED_EVENT, ENT_CHILD_SAD

**Episodes (8+):**
- 4 regret episodes (valence < -0.6) with deep causal chains
- 4 positive episodes for contrast

**CAUSES Edges (20+):**
- Linear chains (depth 4-5)
- Fork patterns (1 cause -> 2 effects)
- Join patterns (2 causes -> 1 effect)

**Coverage Thresholds:**
```python
{
    "min_counterfactuals": 10,
    "path_length_ge_2_ratio": 0.5,    # 50% have path >= 2
    "path_length_ge_3_count": 3,       # At least 3 with path >= 3
    "max_path_length": 4,              # Should see depth 4
    "plausibility_variance": 0.01,     # Not constant
    "scenario_type_count": 3,          # UPWARD, DOWNWARD, SEMIFACTUAL
}
```

---

#### Pack: `mcts_delayed` (MCTS Focus)

**Goal:** Prove MCTS can find delayed-reward strategies.

**State Design:**
```python
initial_state = {
    "time_remaining_hours": 4.0,
    "energy": 0.7,
    "family_mood": "neutral",
    "spouse_mood": "frustrated",  # Requires repair first
    "pending_tasks": ["groceries", "homework_help", "exercise"],
    "relationship_debt": 0.3,     # Accumulated from past conflicts
}
```

**Actions with Preconditions:**
```python
actions = [
    # Immediate reward actions
    {"name": "Watch TV", "reward": 0.3, "duration": 1.0, "preconditions": []},

    # Delayed reward actions
    {"name": "Apologize to spouse", "reward": 0.1, "duration": 0.5,
     "preconditions": [], "unlocks": ["Family activity"]},

    {"name": "Family activity", "reward": 0.9, "duration": 2.0,
     "preconditions": ["spouse_mood >= neutral"]},

    # Sequential chains
    {"name": "Help with homework", "reward": 0.4, "duration": 1.0,
     "effect": {"pending_tasks": "remove:homework_help"}},

    {"name": "Quality family dinner", "reward": 0.8, "duration": 1.5,
     "preconditions": ["pending_tasks.length <= 1"]},
]
```

**Coverage Thresholds:**
```python
{
    "budget_consumption_ratio": 0.7,   # Use 70%+ of budget
    "max_visit_count": 10,             # Some node visited 10+ times
    "visit_count_variance": True,      # Not all equal
    "top_scenario_has_delayed_action": True,  # Finds "Apologize -> Family"
    "reward_spread": 0.3,              # Top - bottom reward >= 0.3
}
```

---

#### Pack: `bgt_clustered` (BGT-SM Focus)

**Goal:** Meaningful semantic distances + cross-cluster insights.

**Cluster Design (6 clusters, 50+ entities):**

| Cluster | Entities | Base Embedding |
|---------|----------|----------------|
| Family | Sarah, Tommy, spouse, grandma, uncle | [1,0,0,0,0,0] |
| Education | homework, school, fractions, teacher, grades | [0,1,0,0,0,0] |
| Work | meeting, boss, deadline, project, email | [0,0,1,0,0,0] |
| Entertainment | movie, game, park, birthday, vacation | [0,0,0,1,0,0] |
| Finance | budget, savings, bills, grocery, expenses | [0,0,0,0,1,0] |
| Health | exercise, sleep, stress, doctor, medicine | [0,0,0,0,0,1] |

**Bisociative Bridges (rare cross-cluster edges):**
- `homework` <-> `stress` (education-health)
- `deadline` <-> `family_argument` (work-family)
- `budget` <-> `vacation` (finance-entertainment)
- `exercise` <-> `family_mood` (health-family)

**Coverage Thresholds:**
```python
{
    "insights_discovered": 3,
    "min_semantic_distance": 0.4,      # Cross-cluster
    "max_semantic_distance": 0.9,      # Not completely unrelated
    "pmi_variance": True,              # Not constant
    "cross_cluster_insight_count": 2,  # At least 2 bridge insights
    "no_same_cluster_insights": True,  # Reject trivial same-cluster
}
```

---

#### Pack: `spc_multi_prov` (SPC-UQ Focus)

**Goal:** Multiple provenance types with varied confidence.

**Fragment Design:**
```python
fragments = [
    # Calendar provenance (high confidence)
    EpisodeFragment(
        content="Doctor appointment at 10am",
        attributes=(("prov", "calendar"), ("confidence", 0.95)),
    ),

    # Message provenance (medium confidence)
    EpisodeFragment(
        content="Sarah texted about science project",
        attributes=(("prov", "message"), ("confidence", 0.7)),
    ),

    # Sensory provenance (low confidence)
    EpisodeFragment(
        content="Heard kids laughing",
        attributes=(("prov", "sensory"), ("confidence", 0.4)),
    ),

    # Inferred provenance (uncertain)
    EpisodeFragment(
        content="Probably had breakfast",
        attributes=(("prov", "inferred"), ("confidence", 0.3)),
    ),
]
```

**Schema Library:**
```json
{
    "morning_routine": {
        "typical_sequence": ["wake", "breakfast", "school_prep", "commute"],
        "locations": ["bedroom", "kitchen", "car"],
        "participants": ["self", "kids"],
        "confidence_boost": 0.2
    }
}
```

**Coverage Thresholds:**
```python
{
    "provenance_types_count": 3,       # At least 3 different types
    "confidence_variance": 0.1,        # Varied confidence scores
    "uncertainty_correlates_provenance": True,  # Low-conf prov = high uncertainty
    "schema_match_boost": True,        # Schema matching improves confidence
}
```

---

### 2.4 Coverage Framework (`r5_coverage.py`)

```python
@dataclass
class CoverageResult:
    """Result of coverage validation."""
    pack_name: str
    algorithm: str
    passed: bool
    metrics: Dict[str, Any]
    failures: List[str]
    warnings: List[str]

class CoverageValidator:
    """Validate algorithm outputs against coverage thresholds."""

    def validate_cpn(self, counterfactuals: List, thresholds: Dict) -> CoverageResult:
        metrics = {
            "total_counterfactuals": len(counterfactuals),
            "path_length_distribution": self._path_length_dist(counterfactuals),
            "max_path_length": max(cf.causal_path_length for cf in counterfactuals),
            "plausibility_variance": np.var([cf.plausibility for cf in counterfactuals]),
            "scenario_types": set(str(cf.scenario_type) for cf in counterfactuals),
        }

        failures = []
        if metrics["total_counterfactuals"] < thresholds["min_counterfactuals"]:
            failures.append(f"Too few counterfactuals: {metrics['total_counterfactuals']}")
        if metrics["max_path_length"] < thresholds.get("max_path_length", 2):
            failures.append(f"Max path length too short: {metrics['max_path_length']}")

        return CoverageResult(
            pack_name=...,
            algorithm="CPN",
            passed=len(failures) == 0,
            metrics=metrics,
            failures=failures,
            warnings=[],
        )

    def validate_mcts(self, scenarios: List, thresholds: Dict) -> CoverageResult:
        ...

    def validate_bgt(self, insights: List, thresholds: Dict) -> CoverageResult:
        ...

    def validate_spc(self, reconstructions: List, thresholds: Dict) -> CoverageResult:
        ...
```

---

### 2.5 Statistical Analysis (`r5_statistics.py`)

```python
class BenchmarkStatistics:
    """Statistical analysis for benchmark results."""

    def confidence_interval(self, values: List[float], confidence: float = 0.95) -> Tuple[float, float]:
        """Calculate confidence interval for a metric."""
        ...

    def effect_size(self, baseline: List[float], treatment: List[float]) -> float:
        """Cohen's d effect size between baseline and treatment."""
        ...

    def significance_test(self, baseline: List[float], treatment: List[float]) -> Tuple[float, bool]:
        """Welch's t-test for significance."""
        ...

    def stability_score(self, results: List[Dict], metric: str, across_seeds: List[int]) -> float:
        """Measure result stability across different seeds."""
        ...

    def regression_check(self, current: Dict, baseline: Dict, threshold: float = 0.1) -> List[str]:
        """Check for performance regressions."""
        ...
```

---

### 2.6 Baseline Comparisons (`r5_baseline.py`)

Compare algorithm outputs against naive baselines.

```python
class BaselineComparator:
    """Compare algorithm performance against baselines."""

    # CPN Baselines
    def random_counterfactual(self, episodes: List, kg_edges: List) -> List:
        """Random perturbation without causal reasoning."""
        ...

    # MCTS Baselines
    def greedy_action_selection(self, state: Dict, actions: List) -> List:
        """Always pick highest immediate reward."""
        ...

    def random_action_selection(self, state: Dict, actions: List) -> List:
        """Random action sequence."""
        ...

    # BGT-SM Baselines
    def random_walk_no_pmi(self, entities: List, edges: List) -> List:
        """Random insights without PMI filtering."""
        ...

    def nearest_neighbor(self, seed: str, embeddings: Dict) -> List:
        """Just return semantically closest entities."""
        ...

    # SPC-UQ Baselines
    def mode_imputation(self, fragments: List) -> List:
        """Fill gaps with most common values."""
        ...

def compare_to_baselines(algorithm_results: Dict, baseline_results: Dict) -> Dict:
    """Calculate improvement over baselines."""
    return {
        "cpn_vs_random": {
            "plausibility_improvement": ...,
            "path_coherence_improvement": ...,
        },
        "mcts_vs_greedy": {
            "reward_improvement": ...,
            "finds_delayed_reward": ...,
        },
        ...
    }
```

---

### 2.7 Benchmark Runner (`run_benchmarks.py`)

```python
"""
R5 Dream Phase Benchmark Runner

Usage:
    python -m tests.k0.modules.consolidation.benchmarks.run_benchmarks [OPTIONS]

Options:
    --pack PACK          Run specific pack (default: all)
    --algorithm ALG      Run specific algorithm (default: all)
    --seeds N            Number of seeds to test (default: 5)
    --real-embeddings    Use UltraBERT (requires GPU)
    --strict             Exit non-zero on coverage failure
    --output DIR         Output directory for results
    --compare-baseline   Include baseline comparisons
    --profile            Enable performance profiling
    --report FORMAT      Generate report (html, markdown, json)
"""

import argparse
import sys
from typing import List, Dict

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default="all")
    parser.add_argument("--algorithm", default="all")
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--real-embeddings", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", default="results/")
    parser.add_argument("--compare-baseline", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--report", choices=["html", "markdown", "json"], default="markdown")
    args = parser.parse_args()

    # Load packs
    packs = load_packs(args.pack)

    # Run benchmarks
    all_results = []
    for pack in packs:
        for seed in range(args.seeds):
            world = make_world(pack, seed)

            if args.algorithm in ("all", "cpn"):
                results = run_cpn(world)
                coverage = validate_cpn(results, world.expected_properties)
                all_results.append(coverage)

            # ... other algorithms

    # Generate report
    report = generate_report(all_results, args.report)

    # Exit code
    if args.strict:
        failures = [r for r in all_results if not r.passed]
        if failures:
            print(f"FAILED: {len(failures)} coverage failures")
            sys.exit(1)

    sys.exit(0)
```

---

### 2.8 Report Generator (`r5_report.py`)

Generate comprehensive benchmark reports.

**HTML Report Structure:**
```
R5 Benchmark Report
├── Executive Summary
│   ├── Pass/Fail by Pack
│   ├── Coverage Heatmap
│   └── Regression Alerts
├── Per-Algorithm Results
│   ├── CPN
│   │   ├── Counterfactual Distribution
│   │   ├── Path Length Histogram
│   │   ├── Plausibility Box Plot
│   │   └── Scenario Type Breakdown
│   ├── MCTS
│   │   ├── Visit Count Distribution
│   │   ├── Reward vs Baseline
│   │   ├── Budget Utilization
│   │   └── Action Sequence Analysis
│   ├── BGT-SM
│   │   ├── PMI Distribution
│   │   ├── Semantic Distance Scatter
│   │   ├── Cluster Heatmap
│   │   └── Insight Quality Ranking
│   └── SPC-UQ
│       ├── Confidence Distribution
│       ├── Provenance Breakdown
│       ├── Uncertainty Correlation
│       └── Schema Match Analysis
├── Performance Metrics
│   ├── Latency (p50, p95, p99)
│   ├── Memory Usage
│   ├── Throughput (scenarios/sec)
│   └── Scaling Analysis
├── Baseline Comparisons
│   ├── vs Random
│   ├── vs Greedy
│   └── Improvement %
└── Statistical Summary
    ├── Confidence Intervals
    ├── Effect Sizes
    └── Stability Scores
```

---

## 3. Implementation Phases

### Phase 1: Foundation (Week 1)

| Task | Effort | Owner |
|------|--------|-------|
| Create directory structure | 2h | - |
| Implement `r5_data_factory.py` skeleton | 4h | - |
| Implement `World` dataclass | 2h | - |
| Port `toy` pack from current `show_io.py` | 2h | - |
| Add `--pack` CLI argument to `show_io.py` | 1h | - |

**Deliverable:** `show_io.py` works with factory-loaded worlds.

---

### Phase 2: Embeddings (Week 1-2)

| Task | Effort | Owner |
|------|--------|-------|
| Implement `ClusteredEmbeddingService` | 4h | - |
| Design cluster centers (6 clusters) | 2h | - |
| Implement `EmbeddingService` with UltraBERT | 6h | - |
| Add embedding caching to disk | 2h | - |
| Update `demo_bgt()` to use embedding service | 2h | - |

**Deliverable:** BGT-SM uses meaningful semantic embeddings.

---

### Phase 3: Deep Packs (Week 2)

| Task | Effort | Owner |
|------|--------|-------|
| Implement `causal_deep` pack | 4h | - |
| Implement `causal_fork_join` pack | 4h | - |
| Implement `mcts_delayed` pack | 4h | - |
| Implement `mcts_constrained` pack | 4h | - |
| Implement `bgt_clustered` pack | 4h | - |
| Implement `bgt_adversarial` pack | 4h | - |

**Deliverable:** 6 new packs testing algorithm edge cases.

---

### Phase 4: SPC-UQ Enhancement (Week 2-3)

| Task | Effort | Owner |
|------|--------|-------|
| Create schema library (4 schemas) | 4h | - |
| Implement `spc_multi_prov` pack | 4h | - |
| Implement `spc_conflict` pack | 4h | - |
| Add provenance type tracking | 2h | - |
| Add uncertainty correlation validation | 2h | - |

**Deliverable:** SPC-UQ benchmarks with schema matching.

---

### Phase 5: Coverage Framework (Week 3)

| Task | Effort | Owner |
|------|--------|-------|
| Implement `CoverageValidator` | 6h | - |
| Define thresholds for each pack | 4h | - |
| Add coverage validation to demo functions | 2h | - |
| Add `--strict` mode with exit codes | 2h | - |

**Deliverable:** Pass/fail coverage gates.

---

### Phase 6: Baselines & Statistics (Week 3-4)

| Task | Effort | Owner |
|------|--------|-------|
| Implement `BaselineComparator` | 6h | - |
| Implement `BenchmarkStatistics` | 4h | - |
| Add multi-seed runs | 2h | - |
| Add confidence interval calculation | 2h | - |
| Add regression detection | 4h | - |

**Deliverable:** Statistical rigor + baseline comparisons.

---

### Phase 7: Runner & Reports (Week 4)

| Task | Effort | Owner |
|------|--------|-------|
| Implement `run_benchmarks.py` CLI | 6h | - |
| Implement HTML report generator | 8h | - |
| Implement Markdown report generator | 4h | - |
| Add performance profiling | 4h | - |
| Add visualization (matplotlib/plotly) | 6h | - |

**Deliverable:** Full benchmark runner with reports.

---

### Phase 8: Stress & Real-World (Week 4-5)

| Task | Effort | Owner |
|------|--------|-------|
| Implement `mixed_stress` pack (1000+ entities) | 6h | - |
| Implement `real_world` pack | 6h | - |
| Performance optimization if needed | 8h | - |
| Memory profiling and optimization | 4h | - |

**Deliverable:** Stress-tested at scale.

---

### Phase 9: CI Integration (Week 5)

| Task | Effort | Owner |
|------|--------|-------|
| Store baseline results in repo | 2h | - |

**Deliverable:** Automated benchmark regression detection.

---

## 4. Coverage Thresholds (All Packs)

### CPN Thresholds

| Metric | toy | causal_deep | causal_fork_join |
|--------|-----|-------------|------------------|
| min_counterfactuals | 5 | 15 | 20 |
| path_length_ge_2_ratio | 0.0 | 0.5 | 0.6 |
| path_length_ge_3_count | 0 | 3 | 5 |
| max_path_length | 1 | 4 | 5 |
| plausibility_variance | 0.001 | 0.01 | 0.02 |
| scenario_type_count | 2 | 3 | 3 |

### MCTS Thresholds

| Metric | toy | mcts_delayed | mcts_constrained |
|--------|-----|--------------|------------------|
| budget_consumption | 0.5 | 0.8 | 0.9 |
| max_visit_count | 5 | 15 | 20 |
| visit_variance | True | True | True |
| finds_delayed_reward | N/A | True | True |
| respects_constraints | N/A | N/A | True |
| reward_spread | 0.1 | 0.4 | 0.5 |

### BGT-SM Thresholds

| Metric | toy | bgt_clustered | bgt_adversarial |
|--------|-----|---------------|-----------------|
| insights_discovered | 1 | 5 | 3 |
| pmi_variance | True | True | True |
| semantic_distance_range | [0,1] | [0.3, 0.8] | [0.4, 0.9] |
| cross_cluster_ratio | N/A | 0.6 | 0.8 |
| false_positive_rate | N/A | N/A | < 0.1 |

### SPC-UQ Thresholds

| Metric | toy | spc_multi_prov | spc_conflict |
|--------|-----|----------------|--------------|
| reconstructions | 1 | 3 | 2 |
| provenance_types | 1 | 3 | 4 |
| confidence_variance | 0.01 | 0.1 | 0.15 |
| uncertainty_on_conflict | N/A | N/A | > 0.5 |
| schema_boost_detected | N/A | True | True |

---

## 5. Performance Targets

| Algorithm | Metric | Target (p95) | Stress Pack Target |
|-----------|--------|--------------|-------------------|
| CPN | Latency per episode | 50ms | 100ms |
| CPN | Memory (10 episodes) | 50MB | 200MB |
| MCTS | Latency per 100 rollouts | 200ms | 500ms |
| MCTS | Memory (100 rollouts) | 100MB | 500MB |
| BGT-SM | Latency per 50 walks | 100ms | 300ms |
| BGT-SM | Memory (100 entities) | 50MB | 500MB |
| SPC-UQ | Latency per reconstruction | 30ms | 80ms |
| SPC-UQ | Memory (50 simulations) | 30MB | 100MB |

---

## 6. Success Criteria

### Minimum Viable Benchmark (MVP)
- [ ] 4 packs implemented (toy + 1 per algorithm)
- [ ] Clustered embeddings working
- [ ] Coverage validation for all packs
- [ ] Markdown report generation
- [ ] CLI runner with `--pack` and `--strict`

### Full Benchmark Suite
- [ ] 10 packs implemented
- [ ] UltraBERT integration
- [ ] Baseline comparisons
- [ ] Multi-seed statistical analysis
- [ ] HTML report with visualizations
- [ ] Performance profiling
- [ ] CI integration with regression detection

### World-Class Benchmark
- [ ] Real-world family scenarios validated with domain experts
- [ ] Published benchmark methodology
- [ ] Comparison with external baselines (if any exist)
- [ ] Performance optimized for 10,000+ entity graphs
- [ ] Reproducibility verified across environments

---

## 7. Dependencies

| Dependency | Purpose | Install |
|------------|---------|---------|
| numpy | Statistics | `pip install numpy` |
| scipy | Statistical tests | `pip install scipy` |
| matplotlib | Visualizations | `pip install matplotlib` |
| plotly | Interactive charts | `pip install plotly` |
| ultrabert | Real embeddings | `pip install ultrabert` |
| jinja2 | HTML templates | `pip install jinja2` |
| py-spy | Profiling | `pip install py-spy` |
| memory-profiler | Memory profiling | `pip install memory-profiler` |

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| UltraBERT too slow | High | Use ClusteredEmbeddings as default; UltraBERT opt-in |
| Coverage thresholds too strict | Medium | Start loose, tighten after baseline established |
| Pack generation is fragile | Medium | Seed-based determinism; golden file regression |
| Report generation bloated | Low | Modular report sections; lazy loading |
| CI too slow | Medium | Run `toy` pack only in fast path; full suite nightly |

---

## 9. Open Questions

1. **Schema format for SPC-UQ:** JSON or Python dataclass?
2. **Embedding dimension:** 64 (current) vs 384 (BERT) vs 768 (UltraBERT)?
3. **Baseline storage:** Git LFS for large golden files?
4. **Report hosting:** Generate to `docs/` or separate artifact?
5. **Multi-algorithm packs:** One world tests all 4, or separate?

---

## 10. Next Steps

1. **Immediate:** Create `r5_data_factory.py` with `toy` pack ported
2. **This week:** Implement `ClusteredEmbeddingService`
3. **Next week:** Add `causal_deep` and `bgt_clustered` packs
4. **Week 3:** Coverage framework + CLI runner

---

## References

- Current demo: [show_io.py](../../tests/k0/modules/consolidation/benchmarks/show_io.py)
- Algorithm implementations: `k0/modules/consolidation/algorithms/`
- UltraBERT: https://huggingface.co/ultrabert
- Cohen's d: https://en.wikipedia.org/wiki/Effect_size#Cohen's_d
