# R5 Pack Benchmark Results

**Generated:** 2026-01-12 00:29:24

---

## Summary

| Pack | Seed | CPN | MCTS | BGT | SPC | Time |
|------|------|-----|------|-----|-----|------|
| toy | 42 | 43 | 6 | 1 | 1 | 2.71s |
| causal_deep | 42 | 58 | 0 | 0 | 1 | 0.00s |
| bgt_clustered | 42 | 0 | 0 | 0 | 1 | 0.00s |
| mcts_delayed | 42 | 0 | 8 | 0 | 1 | 0.00s |

---

## Coverage Validation

**Overall:** 8/9 passed

### [PASS] CPN (toy)

**Metrics:**
```
  total_counterfactuals: 43
  path_length_distribution: {0: 37, 1: 6, 2: 0, '3+': 0}
  path_ge_2_count: 0
  path_ge_2_ratio: 0.0
  path_ge_3_count: 0
  max_path_length: 1
  plausibility_variance: 0.03001622498647918
  plausibility_range: (0.5, 1.0)
  scenario_types: ['ScenarioType.DOWNWARD', 'ScenarioType.UPWARD', 'ScenarioType.SEMIFACTUAL']
  scenario_type_count: 3
```

### [PASS] MCTS (toy)

**Warnings:**
- Budget underutilized: 20.00% < 50.00%

**Metrics:**
```
  scenarios_returned: 6
  total_visits: 20
  max_visit_count: 4
  visit_counts: [4, 4, 3, 3, 3, 3]
  reward_range: (0.0, 0.0)
  reward_spread: 0.0
  visit_variance: True
  budget_consumption_ratio: 0.2
```

### [PASS] BGT-SM (toy)

**Warnings:**
- PMI values are constant (no variance)

**Metrics:**
```
  insights_discovered: 1
  pmi_range: (7.321928094887363, 7.321928094887363)
  pmi_unique_count: 1
  pmi_variance: False
  semantic_distance_range: (1.0, 1.0)
  semantic_distance_unique: 1
  novelty_range: (0.665629826807942, 0.665629826807942)
```

### [PASS] SPC-UQ (toy)

**Metrics:**
```
  reconstructions_returned: 1
  total_fields: 2
  provenance_types: ['ReconstructionProvenance.CONTEXT_PROPAGATION']
  provenance_types_count: 1
  confidence_range: (0.35, 0.4)
  confidence_variance: 0.0006250000000000011
  uncertainty_range: (0.6, 0.65)
```

### [FAIL] CPN (causal_deep)

**Failures:**
- path_length >= 2 ratio too low: 31.03% < 50.00%

**Metrics:**
```
  total_counterfactuals: 58
  path_length_distribution: {0: 32, 1: 8, 2: 10, '3+': 8}
  path_ge_2_count: 18
  path_ge_2_ratio: 0.3103448275862069
  path_ge_3_count: 8
  max_path_length: 4
  plausibility_variance: 0.06183115338882283
  plausibility_range: (0.5, 1.0)
  scenario_types: ['ScenarioType.DOWNWARD', 'ScenarioType.UPWARD', 'ScenarioType.SEMIFACTUAL']
  scenario_type_count: 3
```

### [PASS] SPC-UQ (causal_deep)

**Metrics:**
```
  reconstructions_returned: 1
  total_fields: 2
  provenance_types: ['ReconstructionProvenance.CONTEXT_PROPAGATION']
  provenance_types_count: 1
  confidence_range: (0.35, 0.4)
  confidence_variance: 0.0006250000000000011
  uncertainty_range: (0.6, 0.65)
```

### [PASS] SPC-UQ (bgt_clustered)

**Metrics:**
```
  reconstructions_returned: 1
  total_fields: 2
  provenance_types: ['ReconstructionProvenance.CONTEXT_PROPAGATION']
  provenance_types_count: 1
  confidence_range: (0.35, 0.4)
  confidence_variance: 0.0006250000000000011
  uncertainty_range: (0.6, 0.65)
```

### [PASS] MCTS (mcts_delayed)

**Warnings:**
- max_visit_count below expected: 3 < 10
- Budget underutilized: 20.00% < 80.00%
- Reward spread too narrow: 0.0000 < 0.3

**Metrics:**
```
  scenarios_returned: 8
  total_visits: 20
  max_visit_count: 3
  visit_counts: [3, 3, 3, 3, 2, 2, 2, 2]
  reward_range: (0.0, 0.0)
  reward_spread: 0.0
  visit_variance: True
  budget_consumption_ratio: 0.2
```

### [PASS] SPC-UQ (mcts_delayed)

**Metrics:**
```
  reconstructions_returned: 1
  total_fields: 2
  provenance_types: ['ReconstructionProvenance.CONTEXT_PROPAGATION']
  provenance_types_count: 1
  confidence_range: (0.35, 0.4)
  confidence_variance: 0.0006250000000000011
  uncertainty_range: (0.6, 0.65)
```

