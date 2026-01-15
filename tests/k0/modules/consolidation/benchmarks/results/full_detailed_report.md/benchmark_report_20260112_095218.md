# R5 Benchmark Report

**Generated**: 2026-01-12T09:52:18.201881

## Summary

- Total packs: 11
- Passed: 11
- Failed: 0
- Total duration: 2.29s

## Details

### toy ✅ PASSED

- Seed: 42
- Duration: 2.22s

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
| scenario_types | ScenarioType.UPWARD, ScenarioType.SEMIFACTUAL, ScenarioType.DOWNWARD |
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

### causal_deep ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### CPN ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_counterfactuals | 176 |
| path_length_distribution | 0:49, 1:34, 2:41, 3:34, 4:18 |
| path_length_ge_1_ratio | 0.7216 |
| path_length_ge_2_ratio | 0.5284 |
| path_length_ge_3_count | 52 |
| max_path_length | 4 |
| plausibility_mean | 0.6392 |
| plausibility_variance | 0.0502 |
| scenario_types | ScenarioType.UPWARD, ScenarioType.SEMIFACTUAL, ScenarioType.DOWNWARD |
| scenario_type_count | 3 |

### causal_fork_join ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### CPN ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_counterfactuals | 96 |
| path_length_distribution | 0:48, 1:23, 2:10, 3:9, 4:6 |
| path_length_ge_1_ratio | 0.5000 |
| path_length_ge_2_ratio | 0.2604 |
| path_length_ge_3_count | 15 |
| max_path_length | 4 |
| plausibility_mean | 0.7500 |
| plausibility_variance | 0.0625 |
| scenario_types | ScenarioType.UPWARD, ScenarioType.SEMIFACTUAL, ScenarioType.DOWNWARD |
| scenario_type_count | 3 |

### mcts_delayed ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### MCTS ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_scenarios | 9 |
| total_visits | 20 |
| max_visit_count | 3 |
| visit_count_variance | 0.1728 |
| budget_consumption_ratio | 0.2000 |
| reward_mean | 0.0000 |
| reward_max | 0.0000 |
| reward_min | 0.0000 |
| reward_spread | 0.0000 |

### mcts_constrained ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### MCTS ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_scenarios | 10 |
| total_visits | 20 |
| max_visit_count | 2 |
| visit_count_variance | 0.0000 |
| budget_consumption_ratio | 0.2000 |
| reward_mean | 0.0000 |
| reward_max | 0.0000 |
| reward_min | 0.0000 |
| reward_spread | 0.0000 |

### bgt_clustered ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### BGT-SM ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_insights | 6 |
| pmi_mean | 3.7173 |
| pmi_variance | 0.6717 |
| pmi_min | 2.6915 |
| pmi_max | 5.0023 |
| semantic_distance_mean | 0.5047 |
| semantic_distance_min | 0.1612 |
| semantic_distance_max | 0.7568 |
| novelty_mean | 0.0185 |
| cross_cluster_count | 0 |
| cross_cluster_ratio | 0.0000 |
| spurious_count | 0 |
| false_positive_rate | 0.0000 |

### bgt_adversarial ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### BGT-SM ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_insights | 6 |
| pmi_mean | 4.2149 |
| pmi_variance | 1.7085 |
| pmi_min | 2.4739 |
| pmi_max | 5.9658 |
| semantic_distance_mean | 0.4291 |
| semantic_distance_min | 0.1509 |
| semantic_distance_max | 0.7823 |
| novelty_mean | 0.0220 |
| cross_cluster_count | 0 |
| cross_cluster_ratio | 0.0000 |
| spurious_count | 0 |
| false_positive_rate | 0.0000 |

### spc_multi_prov ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### SPC-UQ ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_reconstructions | 4 |
| confidence_mean | 0.3812 |
| confidence_variance | 0.0004 |
| uncertainty_mean | 0.6188 |
| uncertainty_variance | 0.0004 |
| provenance_types | ReconstructionProvenance.CONTEXT_PROPAGATION |
| provenance_types_count | 1 |
| schema_matches | 0 |
| conflict_fragments | 0 |
| high_uncertainty_on_conflict | 0 |

### spc_conflict ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### SPC-UQ ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_reconstructions | 2 |
| confidence_mean | 0.3750 |
| confidence_variance | 0.0006 |
| uncertainty_mean | 0.6250 |
| uncertainty_variance | 0.0006 |
| provenance_types | ReconstructionProvenance.CONTEXT_PROPAGATION |
| provenance_types_count | 1 |
| schema_matches | 0 |
| conflict_fragments | 0 |
| high_uncertainty_on_conflict | 0 |

### mixed_stress ✅ PASSED

- Seed: 42
- Duration: 0.04s

#### CPN ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_counterfactuals | 228 |
| path_length_distribution | 0:74, 1:37, 2:31, 3:42, 4:44 |
| path_length_ge_1_ratio | 0.6754 |
| path_length_ge_2_ratio | 0.5132 |
| path_length_ge_3_count | 86 |
| max_path_length | 4 |
| plausibility_mean | 0.6623 |
| plausibility_variance | 0.0548 |
| scenario_types | ScenarioType.UPWARD, ScenarioType.SEMIFACTUAL, ScenarioType.DOWNWARD |
| scenario_type_count | 3 |

#### MCTS ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_scenarios | 20 |
| total_visits | 20 |
| max_visit_count | 1 |
| visit_count_variance | 0.0000 |
| budget_consumption_ratio | 0.2000 |
| reward_mean | 0.0000 |
| reward_max | 0.0000 |
| reward_min | 0.0000 |
| reward_spread | 0.0000 |

#### BGT-SM ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_insights | 20 |
| pmi_mean | 15.4093 |
| pmi_variance | 1.1061 |
| pmi_min | 13.2877 |
| pmi_max | 16.8727 |
| semantic_distance_mean | 0.5056 |
| semantic_distance_min | 0.1263 |
| semantic_distance_max | 0.8566 |
| novelty_mean | 0.5984 |
| cross_cluster_count | 0 |
| cross_cluster_ratio | 0.0000 |
| spurious_count | 0 |
| false_positive_rate | 0.0000 |

#### SPC-UQ ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_reconstructions | 18 |
| confidence_mean | 0.3681 |
| confidence_variance | 0.0004 |
| uncertainty_mean | 0.6319 |
| uncertainty_variance | 0.0004 |
| provenance_types | ReconstructionProvenance.CONTEXT_PROPAGATION |
| provenance_types_count | 1 |
| schema_matches | 0 |
| conflict_fragments | 0 |
| high_uncertainty_on_conflict | 0 |

### real_world ✅ PASSED

- Seed: 42
- Duration: 0.01s

#### CPN ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_counterfactuals | 134 |
| path_length_distribution | 0:93, 1:16, 2:13, 3:9, 4:3 |
| path_length_ge_1_ratio | 0.3060 |
| path_length_ge_2_ratio | 0.1866 |
| path_length_ge_3_count | 12 |
| max_path_length | 4 |
| plausibility_mean | 0.8470 |
| plausibility_variance | 0.0531 |
| scenario_types | ScenarioType.UPWARD, ScenarioType.SEMIFACTUAL, ScenarioType.DOWNWARD |
| scenario_type_count | 3 |

#### MCTS ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_scenarios | 10 |
| total_visits | 20 |
| max_visit_count | 2 |
| visit_count_variance | 0.0000 |
| budget_consumption_ratio | 0.2000 |
| reward_mean | 0.0000 |
| reward_max | 0.0000 |
| reward_min | 0.0000 |
| reward_spread | 0.0000 |

#### BGT-SM ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_insights | 7 |
| pmi_mean | 7.0494 |
| pmi_variance | 0.1502 |
| pmi_min | 6.3219 |
| pmi_max | 7.6439 |
| semantic_distance_mean | 0.3817 |
| semantic_distance_min | 0.1586 |
| semantic_distance_max | 0.6973 |
| novelty_mean | 0.0309 |
| cross_cluster_count | 0 |
| cross_cluster_ratio | 0.0000 |
| spurious_count | 0 |
| false_positive_rate | 0.0000 |

#### SPC-UQ ✅

**Metrics:**

| Metric | Value |
|--------|-------|
| total_reconstructions | 3 |
| confidence_mean | 0.3833 |
| confidence_variance | 0.0006 |
| uncertainty_mean | 0.6167 |
| uncertainty_variance | 0.0006 |
| provenance_types | ReconstructionProvenance.CONTEXT_PROPAGATION |
| provenance_types_count | 1 |
| schema_matches | 0 |
| conflict_fragments | 0 |
| high_uncertainty_on_conflict | 0 |
