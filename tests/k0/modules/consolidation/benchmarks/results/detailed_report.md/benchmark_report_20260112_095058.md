# R5 Benchmark Report

**Generated**: 2026-01-12T09:50:58.317665

## Summary

- Total packs: 1
- Passed: 1
- Failed: 0
- Total duration: 2.19s

## Details

### toy ✅ PASSED

- Seed: 42
- Duration: 2.19s

#### CPN ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_counterfactuals | 43 |
| path_length_distribution | 0:37, 1:6 |
| path_length_ge_1_ratio | 0.1395 |
| path_length_ge_2_ratio | 0.0000 |
| path_length_ge_3_count | 0 |
| max_path_length | 1 |
| plausibility_mean | 0.9302 |
| plausibility_variance | 0.0300 |
| scenario_types | ScenarioType.DOWNWARD, ScenarioType.SEMIFACTUAL, ScenarioType.UPWARD |
| scenario_type_count | 3 |

#### MCTS ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_scenarios | 6 |
| total_visits | 20 |
| max_visit_count | 4 |
| visit_count_variance | 0.2222 |
| budget_consumption_ratio | 0.2000 |
| reward_mean | 0.0000 |
| reward_max | 0.0000 |
| reward_min | 0.0000 |
| reward_spread | 0.0000 |

#### BGT-SM ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_insights | 10 |
| pmi_mean | 7.3491 |
| pmi_variance | 0.1935 |
| pmi_min | 6.3808 |
| pmi_max | 7.6439 |
| semantic_distance_mean | 0.7446 |
| semantic_distance_min | 0.5967 |
| semantic_distance_max | 0.8674 |
| novelty_mean | 0.1347 |
| cross_cluster_count | 0 |
| cross_cluster_ratio | 0.0000 |
| spurious_count | 0 |
| false_positive_rate | 0.0000 |

#### SPC-UQ ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_reconstructions | 1 |
| confidence_mean | 0.3750 |
| confidence_variance | 0.0000 |
| uncertainty_mean | 0.6250 |
| uncertainty_variance | 0.0000 |
| provenance_types | ReconstructionProvenance.CONTEXT_PROPAGATION |
| provenance_types_count | 1 |
| schema_matches | 0 |
| conflict_fragments | 0 |
| high_uncertainty_on_conflict | 0 |
