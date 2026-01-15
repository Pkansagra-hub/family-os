# R5 Benchmark Report

**Generated**: 2026-01-12T10:27:19.566932

## Summary

- Total packs: 11
- Passed: 11
- Failed: 0
- Total duration: 2.25s

## Details

### toy ✅ PASSED

- Seed: 42
- Duration: 2.18s

#### CPN ✅

**Inputs:**

```json
{
  "episodes_count": 5,
  "episodes": [
    {
      "id": "01HWQR5X7KJMN3P4Q8R9S0T1V2",
      "summary": "Had breakfast with kids before school. Sarah was excited about her science project.",
      "emotional_valence": 0.8,
      "participants": [
        "self",
        "Sarah",
        "Tommy"
      ],
      "location": "home_kitchen",
      "activity": "family_meal"
    },
    {
      "id": "01HWQR5X8LKNO4Q5R9S0T1U2W3",
      "summary": "Missed Tommy's soccer practice because of work meeting that ran late.",
      "emotional_valence": -0.7,
      "participants": [
        "self",
        "Tommy"
      ],
      "location": "office",
      "activity": "work_conflict"
    },
    {
      "id": "01HWQR5X9MLOP5R6S0T1U2V3X4",
      "summary": "Family movie night - watched kids' favorite animated film together.",
      "emotional_valence": 0.9,
      "participants": [
        "self",
        "Sarah",
        "Tommy",
        "spouse"
      ],
      "location": "home_living_room",
      "activity": "family_entertainment"
    },
    {
      "id": "01HWQR5XANMPQ6S7T1U2V3W4Y5",
      "summary": "Argued with spouse about household budget. Felt stressed and frustrated.",
      "emotional_valence": -0.65,
      "participants": [
        "self",
        "spouse"
      ],
      "location": "home_bedroom",
      "activity": "relationship_conflict"
    },
    {
      "id": "01HWQR5XBOQRS7T8U2V3W4X5Z6",
      "summary": "Helped Sarah with homework. She understood fractions after my explanation.",
      "emotional_valence": 0.7,
      "participants": [
        "self",
        "Sarah"
      ],
      "location": "home_study",
      "activity": "parenting"
    }
  ],
  "kg_edges_count": 4,
  "kg_edges": [
    {
      "source": "ENT_WORK_MEETING",
      "target": "ENT_STRESS",
      "relation": "CAUSES",
      "weight": 0.8
    },
    {
      "source": "ENT_SOCCER",
      "target": "ENT_STRESS",
      "relation": "CAUSES",
      "weight": 0.7
    },
    {
      "source": "ENT_STRESS",
      "target": "ENT_BUDGET",
      "relation": "CAUSES",
      "weight": 0.75
    },
    {
      "source": "ENT_WORK_MEETING",
      "target": "ENT_SOCCER",
      "relation": "CAUSES",
      "weight": 0.9
    }
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "scenario_id": "cf_f6050ad5b8450802",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01HWQR5X7KJMN3P4Q8R9S0T1V2",
  "intervention_node_id": "ENT_TOMMY",
  "perturbation_target": "ENT_TOMMY",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_TOMMY had also gone wrong, outcome would be worse",
  "original_sentiment": 0.8,
  "predicted_sentiment": 0.23823999258099682,
  "plausibility": 1.0,
  "success_probability": 0.2191199962904984,
  "utility_delta": -0.5617600074190032,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239475
}
[2] {
  "scenario_id": "cf_d32d45f74acf3fb0",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01HWQR5XBOQRS7T8U2V3W4X5Z6",
  "intervention_node_id": "ENT_HOMEWORK",
  "perturbation_target": "ENT_HOMEWORK",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_HOMEWORK had also gone wrong, outcome would be worse",
  "original_sentiment": 0.7,
  "predicted_sentiment": 0.21093291917760038,
  "plausibility": 1.0,
  "success_probability": 0.2554664595888002,
  "utility_delta": -0.4890670808223996,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239475
}
[3] {
  "scenario_id": "cf_2e9f18647374b304",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01HWQR5XANMPQ6S7T1U2V3W4Y5",
  "intervention_node_id": "ENT_WORK_MEETING",
  "perturbation_target": "ENT_WORK_MEETING",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_WORK_MEETING had been different, outcome would be better",
  "original_sentiment": -0.65,
  "predicted_sentiment": -0.2167814923696123,
  "plausibility": 0.5,
  "success_probability": 0.3583046269075969,
  "utility_delta": 0.4332185076303877,
  "mitigation": "Next time, consider changing ENT_WORK_MEETING earlier",
  "causal_path_length": 1,
  "created_at_ms": 1768235239475
}
[4] {
  "scenario_id": "cf_f7dd37d9ff9d836f",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01HWQR5X9MLOP5R6S0T1U2V3X4",
  "intervention_node_id": "ENT_FAMILY_TIME",
  "perturbation_target": "ENT_FAMILY_TIME",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_FAMILY_TIME had also gone wrong, outcome would be worse",
  "original_sentiment": 0.9,
  "predicted_sentiment": 0.48995509746408056,
  "plausibility": 1.0,
  "success_probability": 0.2949775487320403,
  "utility_delta": -0.41004490253591946,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239475
}
[5] {
  "scenario_id": "cf_45a72b56c66c738e",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01HWQR5XBOQRS7T8U2V3W4X5Z6",
  "intervention_node_id": "ENT_FRACTIONS",
  "perturbation_target": "ENT_FRACTIONS",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_FRACTIONS had also gone wrong, outcome would be worse",
  "original_sentiment": 0.7,
  "predicted_sentiment": 0.30314461459103614,
  "plausibility": 1.0,
  "success_probability": 0.3015723072955181,
  "utility_delta": -0.3968553854089638,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239475
}
[6] {
  "scenario_id": "cf_169211515826c55a",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01HWQR5X8LKNO4Q5R9S0T1U2W3",
  "intervention_node_id": "ENT_TOMMY",
  "perturbation_target": "ENT_TOMMY",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_TOMMY had been different, outcome would be better",
  "original_sentiment": -0.7,
  "predicted_sentiment": -0.3241571697984264,
  "plausibility": 1.0,
  "success_probability": 0.6879214151007867,
  "utility_delta": 0.37584283020157355,
  "mitigation": "Next time, consider changing ENT_TOMMY earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239475
}
[7] {
  "scenario_id": "cf_f16edf10e8085d09",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01HWQR5XANMPQ6S7T1U2V3W4Y5",
  "intervention_node_id": "ENT_SPOUSE",
  "perturbation_target": "ENT_SPOUSE",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_SPOUSE had been different, outcome would be better",
  "original_sentiment": -0.65,
  "predicted_sentiment": -0.2810385829979449,
  "plausibility": 1.0,
  "success_probability": 0.6844807085010276,
  "utility_delta": 0.36896141700205515,
  "mitigation": "Next time, consider changing ENT_SPOUSE earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239475
}
[8] {
  "scenario_id": "cf_7d4e3cdec9b261e8",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01HWQR5X8LKNO4Q5R9S0T1U2W3",
  "intervention_node_id": "ENT_SOCCER",
  "perturbation_target": "ENT_SOCCER",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_SOCCER had been different, outcome would be better",
  "original_sentiment": -0.7,
  "predicted_sentiment": -0.33158436144540226,
  "plausibility": 1.0,
  "success_probability": 0.6842078192772989,
  "utility_delta": 0.3684156385545977,
  "mitigation": "Next time, consider changing ENT_SOCCER earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239475
}
[9] {
  "scenario_id": "cf_0b8fefb3c521ac77",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01HWQR5X7KJMN3P4Q8R9S0T1V2",
  "intervention_node_id": "ENT_BREAKFAST",
  "perturbation_target": "ENT_BREAKFAST",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_BREAKFAST had also gone wrong, outcome would be worse",
  "original_sentiment": 0.8,
  "predicted_sentiment": 0.43360097508214973,
  "plausibility": 1.0,
  "success_probability": 0.3168004875410748,
  "utility_delta": -0.3663990249178503,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239475
}
[10] {
  "scenario_id": "cf_e2411e4497f19cfc",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01HWQR5XANMPQ6S7T1U2V3W4Y5",
  "intervention_node_id": "ENT_SOCCER",
  "perturbation_target": "ENT_SOCCER",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_SOCCER had been different, outcome would be better",
  "original_sentiment": -0.65,
  "predicted_sentiment": -0.2907782137201201,
  "plausibility": 0.5,
  "success_probability": 0.33980544656996997,
  "utility_delta": 0.35922178627987994,
  "mitigation": "Next time, consider changing ENT_SOCCER earlier",
  "causal_path_length": 1,
  "created_at_ms": 1768235239475
}
```

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
| scenario_types | ScenarioType.SEMIFACTUAL, ScenarioType.UPWARD, ScenarioType.DOWNWARD |
| scenario_type_count | 3 |

#### MCTS ✅

**Inputs:**

```json
{
  "initial_state": {
    "time_of_day": "morning",
    "day": "Saturday",
    "family_mood": "neutral",
    "pending_tasks": "['grocery shopping', 'kids homework help', 'exercise']"
  },
  "actions_count": 6,
  "actions_sample": [
    "ToyAction(action_id='ACT001', name='Take kids to park', duration_hours=2.0, goal_alignment=0.9, expected_reward=0.85)",
    "ToyAction(action_id='ACT002', name='Go grocery shopping', duration_hours=1.0, goal_alignment=0.3, expected_reward=0.4)",
    "ToyAction(action_id='ACT003', name='Family grocery trip', duration_hours=1.5, goal_alignment=0.7, expected_reward=0.65)",
    "ToyAction(action_id='ACT004', name='Help with homework', duration_hours=1.0, goal_alignment=0.8, expected_reward=0.75)",
    "ToyAction(action_id='ACT005', name='Exercise', duration_hours=1.0, goal_alignment=0.5, expected_reward=0.6)"
  ],
  "goals": [
    "ToyGoal(goal_id='GOAL001', description='Be more present with family', priority=0.9, target_value=1.0)",
    "ToyGoal(goal_id='GOAL002', description='Help kids with school success', priority=0.8, target_value=1.0)",
    "ToyGoal(goal_id='GOAL003', description='Improve work-life balance', priority=0.7, target_value=1.0)"
  ]
}
```

**Outputs (6 shown):**

```json
[1] {
  "scenario_id": "98F08F77A89BCF99ED60F3376A",
  "action_sequence": "('ACT001',)",
  "predicted_outcome": "Action ACT001 outcome",
  "success_probability": 0.2,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 4,
  "depth": 1,
  "created_at_ms": 1768235239480
}
[2] {
  "scenario_id": "70204559073A4FCAEA8C4828E1",
  "action_sequence": "('ACT002',)",
  "predicted_outcome": "Action ACT002 outcome",
  "success_probability": 0.2,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 4,
  "depth": 1,
  "created_at_ms": 1768235239480
}
[3] {
  "scenario_id": "510E6BCF6BCECAF0AB886DA6DC",
  "action_sequence": "('ACT003',)",
  "predicted_outcome": "Action ACT003 outcome",
  "success_probability": 0.15,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 3,
  "depth": 1,
  "created_at_ms": 1768235239480
}
[4] {
  "scenario_id": "730B639B622534791E45CE795E",
  "action_sequence": "('ACT004',)",
  "predicted_outcome": "Action ACT004 outcome",
  "success_probability": 0.15,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 3,
  "depth": 1,
  "created_at_ms": 1768235239480
}
[5] {
  "scenario_id": "2AE337FA4CD2D69A94F17E7F7A",
  "action_sequence": "('ACT005',)",
  "predicted_outcome": "Action ACT005 outcome",
  "success_probability": 0.15,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 3,
  "depth": 1,
  "created_at_ms": 1768235239480
}
[6] {
  "scenario_id": "ECFDC072C76EAF4F25698633A6",
  "action_sequence": "('ACT006',)",
  "predicted_outcome": "Action ACT006 outcome",
  "success_probability": 0.15,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 3,
  "depth": 1,
  "created_at_ms": 1768235239480
}
```

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

**Inputs:**

```json
{
  "entities_count": 10,
  "entities_sample": [
    {
      "id": "ENT001",
      "category": "family"
    },
    {
      "id": "ENT002",
      "category": "family"
    },
    {
      "id": "ENT003",
      "category": "family"
    },
    {
      "id": "ENT004",
      "category": "education"
    },
    {
      "id": "ENT005",
      "category": "sports"
    }
  ],
  "semantic_edges_count": 10,
  "semantic_edges_sample": [
    [
      "ENT001",
      "ENT004",
      0.8
    ],
    [
      "ENT001",
      "ENT008",
      0.9
    ],
    [
      "ENT001",
      "ENT010",
      0.7
    ],
    [
      "ENT002",
      "ENT005",
      0.9
    ],
    [
      "ENT003",
      "ENT007",
      0.6
    ]
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "insight_id": "01KESGH21WH3HXPD37QFE7SWM6",
  "source_entity_id": "ENT005",
  "target_entity_id": "ENT002",
  "source_entity_name": "soccer",
  "target_entity_name": "Tommy",
  "semantic_distance": 0.7796211685010044,
  "pmi_score": 7.603214205277379,
  "novelty_score": 0.3704766714426116,
  "insight_text": "Discovered surprising connection between 'soccer' and 'Tommy' (PMI: 7.60, distance: 0.78).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT005', 'ENT002')",
  "supporting_evidence": "('ENT005', 'ENT002')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239484
}
[2] {
  "insight_id": "01KESGH21V2DW0N2TSW6EAH340",
  "source_entity_id": "ENT001",
  "target_entity_id": "ENT004",
  "source_entity_name": "Sarah",
  "target_entity_name": "homework",
  "semantic_distance": 0.7951048084217934,
  "pmi_score": 7.321928094887363,
  "novelty_score": 0.26462273796198016,
  "insight_text": "Discovered surprising connection between 'Sarah' and 'homework' (PMI: 7.32, distance: 0.80).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.BEHAVIORAL",
  "connection_path": "('ENT001', 'ENT004')",
  "supporting_evidence": "('ENT001', 'ENT004')",
  "confidence": 0.95,
  "relevance_score": 0.75,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239483
}
[3] {
  "insight_id": "01KESGH21Y9Z569MKB8R6D1TF7",
  "source_entity_id": "ENT009",
  "target_entity_id": "ENT002",
  "source_entity_name": "movie_night",
  "target_entity_name": "Tommy",
  "semantic_distance": 0.5966793315745833,
  "pmi_score": 7.643856189774724,
  "novelty_score": 0.1628903929273937,
  "insight_text": "Discovered surprising connection between 'movie_night' and 'Tommy' (PMI: 7.64, distance: 0.60).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT009', 'ENT007', 'ENT009', 'ENT002')",
  "supporting_evidence": "('ENT009', 'ENT002')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239486
}
[4] {
  "insight_id": "01KESGH21XJRN31K8HXPS9EG11",
  "source_entity_id": "ENT007",
  "target_entity_id": "ENT003",
  "source_entity_name": "budget",
  "target_entity_name": "spouse",
  "semantic_distance": 0.7618951411985466,
  "pmi_score": 7.643856189774724,
  "novelty_score": 0.1386623069288047,
  "insight_text": "Discovered surprising connection between 'budget' and 'spouse' (PMI: 7.64, distance: 0.76).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT007', 'ENT009', 'ENT007', 'ENT003')",
  "supporting_evidence": "('ENT007', 'ENT003')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239485
}
[5] {
  "insight_id": "01KESGH21VA533FPK940KRN9F2",
  "source_entity_id": "ENT001",
  "target_entity_id": "ENT008",
  "source_entity_name": "Sarah",
  "target_entity_name": "science_project",
  "semantic_distance": 0.7703304122142816,
  "pmi_score": 7.643856189774724,
  "novelty_score": 0.10330341911536581,
  "insight_text": "Discovered surprising connection between 'Sarah' and 'science_project' (PMI: 7.64, distance: 0.77).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT001', 'ENT010', 'ENT001', 'ENT008')",
  "supporting_evidence": "('ENT001', 'ENT008')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239483
}
[6] {
  "insight_id": "01KESGH21VTEYZ6BND56VQST9X",
  "source_entity_id": "ENT001",
  "target_entity_id": "ENT009",
  "source_entity_name": "Sarah",
  "target_entity_name": "movie_night",
  "semantic_distance": 0.714087136565591,
  "pmi_score": 7.321928094887363,
  "novelty_score": 0.08861855368503846,
  "insight_text": "Discovered surprising connection between 'Sarah' and 'movie_night' (PMI: 7.32, distance: 0.71).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT001', 'ENT010', 'ENT001', 'ENT009')",
  "supporting_evidence": "('ENT001', 'ENT009')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239483
}
[7] {
  "insight_id": "01KESGH21VM6B7MVVZHH0ZS2VS",
  "source_entity_id": "ENT001",
  "target_entity_id": "ENT010",
  "source_entity_name": "Sarah",
  "target_entity_name": "fractions",
  "semantic_distance": 0.8116528639026311,
  "pmi_score": 7.643856189774724,
  "novelty_score": 0.07659454034185813,
  "insight_text": "Discovered surprising connection between 'Sarah' and 'fractions' (PMI: 7.64, distance: 0.81).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT001', 'ENT010')",
  "supporting_evidence": "('ENT001', 'ENT010')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239483
}
[8] {
  "insight_id": "01KESGH21WECKGXQDT97BEZP27",
  "source_entity_id": "ENT005",
  "target_entity_id": "ENT006",
  "source_entity_name": "soccer",
  "target_entity_name": "work_meeting",
  "semantic_distance": 0.6283004107292861,
  "pmi_score": 6.643856189774724,
  "novelty_score": 0.05963339389802527,
  "insight_text": "Discovered surprising connection between 'soccer' and 'work_meeting' (PMI: 6.64, distance: 0.63).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT005', 'ENT006')",
  "supporting_evidence": "('ENT005', 'ENT006')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239484
}
[9] {
  "insight_id": "01KESGH21XWXMEXRVJMJCZ7KQ1",
  "source_entity_id": "ENT007",
  "target_entity_id": "ENT009",
  "source_entity_name": "budget",
  "target_entity_name": "movie_night",
  "semantic_distance": 0.7210943000387576,
  "pmi_score": 7.643856189774724,
  "novelty_score": 0.04835036077861868,
  "insight_text": "Discovered surprising connection between 'budget' and 'movie_night' (PMI: 7.64, distance: 0.72).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT007', 'ENT009')",
  "supporting_evidence": "('ENT007', 'ENT009')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239485
}
[10] {
  "insight_id": "01KESGH21WSFVD7XAGF4RQWNTA",
  "source_entity_id": "ENT004",
  "target_entity_id": "ENT005",
  "source_entity_name": "homework",
  "target_entity_name": "soccer",
  "semantic_distance": 0.867428957962897,
  "pmi_score": 6.380821783940931,
  "novelty_score": 0.03416610858636318,
  "insight_text": "Discovered surprising connection between 'homework' and 'soccer' (PMI: 6.38, distance: 0.87).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT004', 'ENT005')",
  "supporting_evidence": "('ENT004', 'ENT005')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239484
}
```

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

**Inputs:**

```json
{
  "incomplete_episodes_count": 1,
  "incomplete_episodes": [
    {
      "id": "01INCOMPLETE00000000000001",
      "summary": "Something happened with Sarah in the morning... can't quite remember",
      "location": null,
      "participants": null,
      "activity": null,
      "ambiguity": 0.7
    }
  ],
  "fragments_count": 2,
  "fragments": [
    {
      "id": "FRAG001",
      "content": "making breakfast",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG002",
      "content": "Sarah mentioned school",
      "provenance_type": null,
      "confidence": null
    }
  ],
  "schemas_count": 0,
  "context_keys": [
    "time_of_day",
    "day",
    "nearby_locations",
    "known_locations",
    "frequent_contacts"
  ]
}
```

**Outputs (1 shown):**

```json
[1] {
  "episode_id": "B8771F5DFB769ACE5ECD80B4E0",
  "original_episode_id": "01INCOMPLETE00000000000001",
  "summary": "Something happened with Sarah in the morning... can't quite remember [Reconstructed: location_name, participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='location_name', value='school', confidence=0.4, uncertainty=0.6, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239490), ReconstructedValue(attribute_name='participants', value=['Sarah', 'spouse'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239490))",
  "confidence_score": 0.375,
  "uncertainty_score": 0.625,
  "temporal_coherence_score": 1.0,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG001', 'FRAG002'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239490
}
```

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
| fragment_provenance_types |  |
| schema_matches | 0 |
| conflict_fragments | 0 |
| high_uncertainty_on_conflict | 0 |

### causal_deep ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### CPN ✅

**Inputs:**

```json
{
  "episodes_count": 8,
  "episodes": [
    {
      "id": "01CAUSAL_DEEP_001",
      "summary": "Took on too many projects at work. Ended up working through lunch and missing a key deadline.",
      "emotional_valence": -0.8,
      "participants": [
        "self"
      ],
      "location": "office",
      "activity": "work_overload"
    },
    {
      "id": "01CAUSAL_DEEP_002",
      "summary": "Boss expressed disappointment about missed deadline. Mentioned upcoming performance review.",
      "emotional_valence": -0.75,
      "participants": [
        "self",
        "boss"
      ],
      "location": "office",
      "activity": "work_conflict"
    },
    {
      "id": "01CAUSAL_DEEP_003",
      "summary": "Felt exhausted and unfocused all day. Made several errors in the report.",
      "emotional_valence": -0.6,
      "participants": [
        "self"
      ],
      "location": "office",
      "activity": "work_struggle"
    },
    {
      "id": "01CAUSAL_DEEP_004",
      "summary": "Came home stressed and snapped at spouse over small things. Kids saw the argument.",
      "emotional_valence": -0.85,
      "participants": [
        "self",
        "spouse",
        "kids"
      ],
      "location": "home",
      "activity": "family_conflict"
    },
    {
      "id": "01CAUSAL_DEEP_005",
      "summary": "Missed Tommy's school play because I was late leaving the office. He was sad.",
      "emotional_valence": -0.9,
      "participants": [
        "self",
        "Tommy"
      ],
      "location": "school",
      "activity": "missed_event"
    },
    {
      "id": "01CAUSAL_DEEP_006",
      "summary": "Feeling overwhelmed by guilt. Everything seems connected to that overload decision.",
      "emotional_valence": -0.7,
      "participants": [
        "self"
      ],
      "location": "home",
      "activity": "reflection"
    },
    {
      "id": "01CAUSAL_DEEP_007",
      "summary": "Apologized to spouse and kids. Had a good conversation about boundaries.",
      "emotional_valence": 0.6,
      "participants": [
        "self",
        "spouse",
        "kids"
      ],
      "location": "home",
      "activity": "repair"
    },
    {
      "id": "01CAUSAL_DEEP_008",
      "summary": "Went for a long run to clear my head. Felt much better afterward.",
      "emotional_valence": 0.7,
      "participants": [
        "self"
      ],
      "location": "park",
      "activity": "self_care"
    }
  ],
  "kg_edges_count": 24,
  "kg_edges": [
    {
      "source": "ENT_WORK_OVERLOAD",
      "target": "ENT_MISSED_DEADLINE",
      "relation": "CAUSES",
      "weight": 0.9
    },
    {
      "source": "ENT_MISSED_DEADLINE",
      "target": "ENT_BOSS_DISAPPOINTED",
      "relation": "CAUSES",
      "weight": 0.85
    },
    {
      "source": "ENT_BOSS_DISAPPOINTED",
      "target": "ENT_PERFORMANCE_REVIEW",
      "relation": "CAUSES",
      "weight": 0.7
    },
    {
      "source": "ENT_PERFORMANCE_REVIEW",
      "target": "ENT_STRESS",
      "relation": "CAUSES",
      "weight": 0.8
    },
    {
      "source": "ENT_STRESS",
      "target": "ENT_FAMILY_ARGUMENT",
      "relation": "CAUSES",
      "weight": 0.75
    },
    {
      "source": "ENT_WORK_OVERLOAD",
      "target": "ENT_SKIPPED_LUNCH",
      "relation": "CAUSES",
      "weight": 0.7
    },
    {
      "source": "ENT_SKIPPED_LUNCH",
      "target": "ENT_FATIGUE",
      "relation": "CAUSES",
      "weight": 0.85
    },
    {
      "source": "ENT_FATIGUE",
      "target": "ENT_POOR_FOCUS",
      "relation": "CAUSES",
      "weight": 0.8
    },
    {
      "source": "ENT_POOR_FOCUS",
      "target": "ENT_WORK_ERRORS",
      "relation": "CAUSES",
      "weight": 0.75
    },
    {
      "source": "ENT_WORK_ERRORS",
      "target": "ENT_FRUSTRATION",
      "relation": "CAUSES",
      "weight": 0.8
    }
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "scenario_id": "cf_85bee25f8caacd70",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01CAUSAL_DEEP_001",
  "intervention_node_id": "ENT_SKIPPED_LUNCH",
  "perturbation_target": "ENT_SKIPPED_LUNCH",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_SKIPPED_LUNCH had been different, outcome would be better",
  "original_sentiment": -0.8,
  "predicted_sentiment": -0.2720670172294861,
  "plausibility": 1.0,
  "success_probability": 0.763966491385257,
  "utility_delta": 0.5279329827705139,
  "mitigation": "Next time, consider changing ENT_SKIPPED_LUNCH earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239492
}
[2] {
  "scenario_id": "cf_9eb81f3def78414a",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01CAUSAL_DEEP_004",
  "intervention_node_id": "ENT_PERFORMANCE_REVIEW",
  "perturbation_target": "ENT_PERFORMANCE_REVIEW",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_PERFORMANCE_REVIEW had been different, outcome would be better",
  "original_sentiment": -0.85,
  "predicted_sentiment": -0.33342632804996586,
  "plausibility": 0.5,
  "success_probability": 0.3791434179875085,
  "utility_delta": 0.5165736719500341,
  "mitigation": "Next time, consider changing ENT_PERFORMANCE_REVIEW earlier",
  "causal_path_length": 1,
  "created_at_ms": 1768235239492
}
[3] {
  "scenario_id": "cf_ac5173b438275033",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01CAUSAL_DEEP_007",
  "intervention_node_id": "ENT_FAMILY_ARGUMENT",
  "perturbation_target": "ENT_FAMILY_ARGUMENT",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_FAMILY_ARGUMENT had also gone wrong, outcome would be worse",
  "original_sentiment": 0.6,
  "predicted_sentiment": 0.08949721322758364,
  "plausibility": 0.5,
  "success_probability": 0.12237430330689592,
  "utility_delta": -0.5105027867724163,
  "mitigation": null,
  "causal_path_length": 2,
  "created_at_ms": 1768235239491
}
[4] {
  "scenario_id": "cf_98f8802758db15d0",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01CAUSAL_DEEP_002",
  "intervention_node_id": "ENT_PERFORMANCE_REVIEW",
  "perturbation_target": "ENT_PERFORMANCE_REVIEW",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_PERFORMANCE_REVIEW had been different, outcome would be better",
  "original_sentiment": -0.75,
  "predicted_sentiment": -0.26858116594000225,
  "plausibility": 1.0,
  "success_probability": 0.7407094170299988,
  "utility_delta": 0.48141883405999775,
  "mitigation": "Next time, consider changing ENT_PERFORMANCE_REVIEW earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239492
}
[5] {
  "scenario_id": "cf_4d2e6b822dae8dd2",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01CAUSAL_DEEP_004",
  "intervention_node_id": "ENT_MISSED_DEADLINE",
  "perturbation_target": "ENT_MISSED_DEADLINE",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_MISSED_DEADLINE had been different, outcome would be better",
  "original_sentiment": -0.85,
  "predicted_sentiment": -0.3696831761346895,
  "plausibility": 0.5,
  "success_probability": 0.3700792059663276,
  "utility_delta": 0.4803168238653105,
  "mitigation": "Next time, consider changing ENT_MISSED_DEADLINE earlier",
  "causal_path_length": 3,
  "created_at_ms": 1768235239492
}
[6] {
  "scenario_id": "cf_a6182db6bac2f8cb",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01CAUSAL_DEEP_006",
  "intervention_node_id": "ENT_MISSED_EVENT",
  "perturbation_target": "ENT_MISSED_EVENT",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_MISSED_EVENT had been different, outcome would be better",
  "original_sentiment": -0.7,
  "predicted_sentiment": -0.2319084061979036,
  "plausibility": 0.5,
  "success_probability": 0.3670228984505241,
  "utility_delta": 0.46809159380209636,
  "mitigation": "Next time, consider changing ENT_MISSED_EVENT earlier",
  "causal_path_length": 2,
  "created_at_ms": 1768235239491
}
[7] {
  "scenario_id": "cf_4e8480c6abafcfe8",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01CAUSAL_DEEP_003",
  "intervention_node_id": "ENT_FATIGUE",
  "perturbation_target": "ENT_FATIGUE",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_FATIGUE had been different, outcome would be better",
  "original_sentiment": -0.6,
  "predicted_sentiment": -0.15115576548471987,
  "plausibility": 1.0,
  "success_probability": 0.72442211725764,
  "utility_delta": 0.4488442345152801,
  "mitigation": "Next time, consider changing ENT_FATIGUE earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239492
}
[8] {
  "scenario_id": "cf_72d5c60022030298",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01CAUSAL_DEEP_008",
  "intervention_node_id": "ENT_STRESS",
  "perturbation_target": "ENT_STRESS",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_STRESS had also gone wrong, outcome would be worse",
  "original_sentiment": 0.7,
  "predicted_sentiment": 0.2546454701991322,
  "plausibility": 0.5,
  "success_probability": 0.13866136754978306,
  "utility_delta": -0.44535452980086776,
  "mitigation": null,
  "causal_path_length": 1,
  "created_at_ms": 1768235239491
}
[9] {
  "scenario_id": "cf_0e50fa689794ed78",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01CAUSAL_DEEP_008",
  "intervention_node_id": "ENT_WORK_OVERLOAD",
  "perturbation_target": "ENT_WORK_OVERLOAD",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_WORK_OVERLOAD had also gone wrong, outcome would be worse",
  "original_sentiment": 0.7,
  "predicted_sentiment": 0.2578150018656534,
  "plausibility": 0.5,
  "success_probability": 0.13945375046641337,
  "utility_delta": -0.44218499813434653,
  "mitigation": null,
  "causal_path_length": 4,
  "created_at_ms": 1768235239491
}
[10] {
  "scenario_id": "cf_814d0cd9323cf8e5",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01CAUSAL_DEEP_007",
  "intervention_node_id": "ENT_LATE_ARRIVAL",
  "perturbation_target": "ENT_LATE_ARRIVAL",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_LATE_ARRIVAL had also gone wrong, outcome would be worse",
  "original_sentiment": 0.6,
  "predicted_sentiment": 0.16005203653794453,
  "plausibility": 0.5,
  "success_probability": 0.14001300913448614,
  "utility_delta": -0.43994796346205545,
  "mitigation": null,
  "causal_path_length": 4,
  "created_at_ms": 1768235239492
}
```

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
| scenario_types | ScenarioType.SEMIFACTUAL, ScenarioType.UPWARD, ScenarioType.DOWNWARD |
| scenario_type_count | 3 |

### causal_fork_join ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### CPN ✅

**Inputs:**

```json
{
  "episodes_count": 8,
  "episodes": [
    {
      "id": "01FORK_JOIN_001",
      "summary": "Said yes to too many projects. Ended up working late AND forgot anniversary dinner.",
      "emotional_valence": -0.85,
      "participants": [
        "self",
        "spouse"
      ],
      "location": "office",
      "activity": "overcommitment"
    },
    {
      "id": "01FORK_JOIN_002",
      "summary": "Spouse was really hurt about the forgotten anniversary. Tension is building.",
      "emotional_valence": -0.75,
      "participants": [
        "self",
        "spouse"
      ],
      "location": "home",
      "activity": "relationship_conflict"
    },
    {
      "id": "01FORK_JOIN_003",
      "summary": "Haven't been sleeping well due to relationship stress. Feeling irritable and tired.",
      "emotional_valence": -0.6,
      "participants": [
        "self"
      ],
      "location": "home",
      "activity": "health_impact"
    },
    {
      "id": "01FORK_JOIN_004",
      "summary": "Made a bad call at work due to being tired. Now regretting the whole cascade.",
      "emotional_valence": -0.7,
      "participants": [
        "self"
      ],
      "location": "office",
      "activity": "poor_judgment"
    },
    {
      "id": "01FORK_JOIN_005",
      "summary": "Started planning Tommy's birthday party. Lots of tasks to coordinate.",
      "emotional_valence": 0.7,
      "participants": [
        "self",
        "spouse",
        "Tommy"
      ],
      "location": "home",
      "activity": "event_planning"
    },
    {
      "id": "01FORK_JOIN_006",
      "summary": "The party was a success! Everything came together perfectly.",
      "emotional_valence": 0.9,
      "participants": [
        "self",
        "spouse",
        "Tommy",
        "guests"
      ],
      "location": "venue",
      "activity": "celebration"
    },
    {
      "id": "01FORK_JOIN_007",
      "summary": "Made a mistake at work and tried to hide it. External audit discovered it.",
      "emotional_valence": -0.8,
      "participants": [
        "self",
        "boss"
      ],
      "location": "office",
      "activity": "work_crisis"
    },
    {
      "id": "01FORK_JOIN_008",
      "summary": "Had an honest conversation with spouse about everything. Starting to rebuild trust.",
      "emotional_valence": 0.5,
      "participants": [
        "self",
        "spouse"
      ],
      "location": "home",
      "activity": "reconciliation"
    }
  ],
  "kg_edges_count": 29,
  "kg_edges": [
    {
      "source": "ENT_OVERCOMMITMENT",
      "target": "ENT_WORK_LATE",
      "relation": "CAUSES",
      "weight": 0.85
    },
    {
      "source": "ENT_OVERCOMMITMENT",
      "target": "ENT_FORGOT_PROMISE",
      "relation": "CAUSES",
      "weight": 0.7
    },
    {
      "source": "ENT_WORK_LATE",
      "target": "ENT_SPOUSE_UPSET",
      "relation": "CAUSES",
      "weight": 0.75
    },
    {
      "source": "ENT_FORGOT_PROMISE",
      "target": "ENT_SPOUSE_UPSET",
      "relation": "CAUSES",
      "weight": 0.8
    },
    {
      "source": "ENT_SPOUSE_UPSET",
      "target": "ENT_RELATIONSHIP_TENSION",
      "relation": "CAUSES",
      "weight": 0.85
    },
    {
      "source": "ENT_POOR_SLEEP",
      "target": "ENT_IRRITABLE",
      "relation": "CAUSES",
      "weight": 0.8
    },
    {
      "source": "ENT_POOR_SLEEP",
      "target": "ENT_LOW_ENERGY",
      "relation": "CAUSES",
      "weight": 0.85
    },
    {
      "source": "ENT_IRRITABLE",
      "target": "ENT_POOR_DECISIONS",
      "relation": "CAUSES",
      "weight": 0.6
    },
    {
      "source": "ENT_LOW_ENERGY",
      "target": "ENT_POOR_DECISIONS",
      "relation": "CAUSES",
      "weight": 0.65
    },
    {
      "source": "ENT_POOR_DECISIONS",
      "target": "ENT_REGRET",
      "relation": "CAUSES",
      "weight": 0.75
    }
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "scenario_id": "cf_a4b6fa8d913cdd98",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01FORK_JOIN_004",
  "intervention_node_id": "ENT_POOR_DECISIONS",
  "perturbation_target": "ENT_POOR_DECISIONS",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_POOR_DECISIONS had been different, outcome would be better",
  "original_sentiment": -0.7,
  "predicted_sentiment": -0.17436827038920855,
  "plausibility": 1.0,
  "success_probability": 0.7628158648053958,
  "utility_delta": 0.5256317296107914,
  "mitigation": "Next time, consider changing ENT_POOR_DECISIONS earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239493
}
[2] {
  "scenario_id": "cf_11c6d5835c0a806e",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01FORK_JOIN_007",
  "intervention_node_id": "ENT_EXTERNAL_PRESSURE",
  "perturbation_target": "ENT_EXTERNAL_PRESSURE",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_EXTERNAL_PRESSURE had been different, outcome would be better",
  "original_sentiment": -0.8,
  "predicted_sentiment": -0.29193004666566624,
  "plausibility": 0.5,
  "success_probability": 0.37701748833358345,
  "utility_delta": 0.5080699533343338,
  "mitigation": "Next time, consider changing ENT_EXTERNAL_PRESSURE earlier",
  "causal_path_length": 1,
  "created_at_ms": 1768235239493
}
[3] {
  "scenario_id": "cf_61d415c18ac8b080",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01FORK_JOIN_004",
  "intervention_node_id": "ENT_RELATIONSHIP_TENSION",
  "perturbation_target": "ENT_RELATIONSHIP_TENSION",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_RELATIONSHIP_TENSION had been different, outcome would be better",
  "original_sentiment": -0.7,
  "predicted_sentiment": -0.21463754574866956,
  "plausibility": 0.5,
  "success_probability": 0.3713406135628326,
  "utility_delta": 0.4853624542513304,
  "mitigation": "Next time, consider changing ENT_RELATIONSHIP_TENSION earlier",
  "causal_path_length": 3,
  "created_at_ms": 1768235239493
}
[4] {
  "scenario_id": "cf_57b899e324aef9c2",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01FORK_JOIN_007",
  "intervention_node_id": "ENT_DISCOVERED",
  "perturbation_target": "ENT_DISCOVERED",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_DISCOVERED had been different, outcome would be better",
  "original_sentiment": -0.8,
  "predicted_sentiment": -0.3191003212241474,
  "plausibility": 1.0,
  "success_probability": 0.7404498393879263,
  "utility_delta": 0.48089967877585266,
  "mitigation": "Next time, consider changing ENT_DISCOVERED earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239493
}
[5] {
  "scenario_id": "cf_e06f2a2eca6738da",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01FORK_JOIN_005",
  "intervention_node_id": "ENT_CAKE",
  "perturbation_target": "ENT_CAKE",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_CAKE had also gone wrong, outcome would be worse",
  "original_sentiment": 0.7,
  "predicted_sentiment": 0.2242040574638513,
  "plausibility": 1.0,
  "success_probability": 0.2621020287319257,
  "utility_delta": -0.47579594253614865,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239493
}
[6] {
  "scenario_id": "cf_6e18adadd7953f2e",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01FORK_JOIN_002",
  "intervention_node_id": "ENT_OVERCOMMITMENT",
  "perturbation_target": "ENT_OVERCOMMITMENT",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_OVERCOMMITMENT had been different, outcome would be better",
  "original_sentiment": -0.75,
  "predicted_sentiment": -0.2858063783776062,
  "plausibility": 0.5,
  "success_probability": 0.36604840540559846,
  "utility_delta": 0.4641936216223938,
  "mitigation": "Next time, consider changing ENT_OVERCOMMITMENT earlier",
  "causal_path_length": 2,
  "created_at_ms": 1768235239493
}
[7] {
  "scenario_id": "cf_57887ec1e149960b",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01FORK_JOIN_004",
  "intervention_node_id": "ENT_POOR_SLEEP",
  "perturbation_target": "ENT_POOR_SLEEP",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_POOR_SLEEP had been different, outcome would be better",
  "original_sentiment": -0.7,
  "predicted_sentiment": -0.2610620152549139,
  "plausibility": 0.5,
  "success_probability": 0.3597344961862715,
  "utility_delta": 0.43893798474508605,
  "mitigation": "Next time, consider changing ENT_POOR_SLEEP earlier",
  "causal_path_length": 2,
  "created_at_ms": 1768235239493
}
[8] {
  "scenario_id": "cf_706b8cc3cc8889fe",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01FORK_JOIN_006",
  "intervention_node_id": "ENT_CAKE",
  "perturbation_target": "ENT_CAKE",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_CAKE had also gone wrong, outcome would be worse",
  "original_sentiment": 0.9,
  "predicted_sentiment": 0.4619215066258893,
  "plausibility": 0.5,
  "success_probability": 0.14048037665647234,
  "utility_delta": -0.4380784933741107,
  "mitigation": null,
  "causal_path_length": 1,
  "created_at_ms": 1768235239493
}
[9] {
  "scenario_id": "cf_7a68c9cfb94719a3",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "01FORK_JOIN_003",
  "intervention_node_id": "ENT_LOW_ENERGY",
  "perturbation_target": "ENT_LOW_ENERGY",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_LOW_ENERGY had been different, outcome would be better",
  "original_sentiment": -0.6,
  "predicted_sentiment": -0.16436628863814495,
  "plausibility": 1.0,
  "success_probability": 0.7178168556809275,
  "utility_delta": 0.435633711361855,
  "mitigation": "Next time, consider changing ENT_LOW_ENERGY earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239493
}
[10] {
  "scenario_id": "cf_3dd576d56b1913c9",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "01FORK_JOIN_005",
  "intervention_node_id": "ENT_VENUE",
  "perturbation_target": "ENT_VENUE",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_VENUE had also gone wrong, outcome would be worse",
  "original_sentiment": 0.7,
  "predicted_sentiment": 0.2716469855541356,
  "plausibility": 1.0,
  "success_probability": 0.2858234927770678,
  "utility_delta": -0.4283530144458644,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239493
}
```

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
| scenario_types | ScenarioType.SEMIFACTUAL, ScenarioType.UPWARD, ScenarioType.DOWNWARD |
| scenario_type_count | 3 |

### mcts_delayed ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### MCTS ✅

**Inputs:**

```json
{
  "initial_state": {
    "time_of_day": "afternoon",
    "day": "Saturday",
    "time_remaining_hours": "6.0",
    "energy": "0.7",
    "stress": "0.5",
    "family_mood": "neutral",
    "spouse_mood": "frustrated",
    "relationship_debt": "0.4",
    "spouse_appreciation": "0.0",
    "family_happiness": "0.3",
    "pending_tasks": "['apologize', 'family_time']"
  },
  "actions_count": 9,
  "actions_sample": [
    "DelayedAction(action_id='ACT_WATCH_TV', name='Watch TV alone', duration_hours=2.0, goal_alignment=0.2, expected_reward=0.3, preconditions=[], unlocks=[], effects={'stress': -0.1})",
    "DelayedAction(action_id='ACT_SOLO_RUN', name='Go for a solo run', duration_hours=1.0, goal_alignment=0.4, expected_reward=0.4, preconditions=[], unlocks=[], effects={'stress': -0.2, 'energy': 0.1})",
    "DelayedAction(action_id='ACT_BROWSE_PHONE', name='Browse phone', duration_hours=1.0, goal_alignment=0.1, expected_reward=0.2, preconditions=[], unlocks=[], effects={})",
    "DelayedAction(action_id='ACT_APOLOGIZE', name='Apologize to spouse', duration_hours=0.5, goal_alignment=0.7, expected_reward=0.1, preconditions=[], unlocks=['ACT_CONVERSATION'], effects={'spouse_mood': 'open'})",
    "DelayedAction(action_id='ACT_CONVERSATION', name='Have meaningful conversation', duration_hours=1.0, goal_alignment=0.8, expected_reward=0.2, preconditions=['spouse_mood == open'], unlocks=['ACT_FAMILY_ACTIVITY'], effects={'spouse_mood': 'receptive', 'relationship_debt': -0.2})"
  ],
  "goals": [
    "DelayedGoal(goal_id='GOAL001', description='Repair relationship with spouse', priority=0.95, target_value=1.0)",
    "DelayedGoal(goal_id='GOAL002', description='Spend quality time with family', priority=0.9, target_value=1.0)",
    "DelayedGoal(goal_id='GOAL003', description='Reduce personal stress', priority=0.6, target_value=1.0)"
  ]
}
```

**Outputs (9 shown):**

```json
[1] {
  "scenario_id": "E819F8404E72282F8C1FEB6868",
  "action_sequence": "('ACT_WATCH_TV',)",
  "predicted_outcome": "Action ACT_WATCH_TV outcome",
  "success_probability": 0.15,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 3,
  "depth": 1,
  "created_at_ms": 1768235239494
}
[2] {
  "scenario_id": "498D129B6ACA0C55E9847CF07B",
  "action_sequence": "('ACT_SOLO_RUN',)",
  "predicted_outcome": "Action ACT_SOLO_RUN outcome",
  "success_probability": 0.15,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 3,
  "depth": 1,
  "created_at_ms": 1768235239494
}
[3] {
  "scenario_id": "164B65BC9565D56BF37EB5E208",
  "action_sequence": "('ACT_BROWSE_PHONE',)",
  "predicted_outcome": "Action ACT_BROWSE_PHONE outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239494
}
[4] {
  "scenario_id": "5DBEA219A647B9D0F98DBB3699",
  "action_sequence": "('ACT_APOLOGIZE',)",
  "predicted_outcome": "Action ACT_APOLOGIZE outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239494
}
[5] {
  "scenario_id": "F2FE6FFE788D865AB6F99AC91F",
  "action_sequence": "('ACT_CONVERSATION',)",
  "predicted_outcome": "Action ACT_CONVERSATION outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239494
}
[6] {
  "scenario_id": "F8A8CE7391E118288BA3BE455B",
  "action_sequence": "('ACT_FAMILY_ACTIVITY',)",
  "predicted_outcome": "Action ACT_FAMILY_ACTIVITY outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239494
}
[7] {
  "scenario_id": "FAE6B98F14DB573B95E0D8ABF3",
  "action_sequence": "('ACT_FAMILY_DINNER',)",
  "predicted_outcome": "Action ACT_FAMILY_DINNER outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239494
}
[8] {
  "scenario_id": "D91703448257E05B5A65F4481B",
  "action_sequence": "('ACT_HELP_CHORES',)",
  "predicted_outcome": "Action ACT_HELP_CHORES outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239494
}
[9] {
  "scenario_id": "67B16230F27E1ACD15C046EEE4",
  "action_sequence": "('ACT_THANK_YOU',)",
  "predicted_outcome": "Action ACT_THANK_YOU outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239494
}
```

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

**Inputs:**

```json
{
  "initial_state": {
    "current_hour": "10",
    "end_hour": "17",
    "time_remaining_hours": "7.0",
    "energy": "0.7",
    "budget_remaining": "100.0",
    "location": "home",
    "family_mood": "excited",
    "activities_done": "[]"
  },
  "actions_count": 10,
  "actions_sample": [
    "ConstrainedAction(action_id='ACT_AMUSEMENT_PARK', name='Go to amusement park', duration_hours=5.0, goal_alignment=0.95, expected_reward=0.9, energy_cost=0.4, money_cost=80.0, min_energy=0.3, time_window=None, location_required=None)",
    "ConstrainedAction(action_id='ACT_FANCY_DINNER', name='Fancy restaurant dinner', duration_hours=2.5, goal_alignment=0.85, expected_reward=0.8, energy_cost=0.1, money_cost=60.0, min_energy=0.2, time_window=(17, 21), location_required=None)",
    "ConstrainedAction(action_id='ACT_PARK_PICNIC', name='Picnic in the park', duration_hours=2.0, goal_alignment=0.8, expected_reward=0.7, energy_cost=0.2, money_cost=15.0, min_energy=0.2, time_window=None, location_required=None)",
    "ConstrainedAction(action_id='ACT_MOVIE', name='Go to movies', duration_hours=3.0, goal_alignment=0.7, expected_reward=0.65, energy_cost=0.1, money_cost=40.0, min_energy=0.1, time_window=None, location_required=None)",
    "ConstrainedAction(action_id='ACT_GYM', name='Family gym session', duration_hours=1.5, goal_alignment=0.6, expected_reward=0.5, energy_cost=0.25, money_cost=0.0, min_energy=0.4, time_window=None, location_required=None)"
  ],
  "goals": [
    "ConstrainedGoal(goal_id='GOAL001', description='Maximize family fun', priority=0.9, target_value=1.0)",
    "ConstrainedGoal(goal_id='GOAL002', description='Stay within budget', priority=0.8, target_value=1.0)",
    "ConstrainedGoal(goal_id='GOAL003', description='Not exhaust everyone', priority=0.7, target_value=1.0)"
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "scenario_id": "71995912DC677451F798CB3F3A",
  "action_sequence": "('ACT_AMUSEMENT_PARK',)",
  "predicted_outcome": "Action ACT_AMUSEMENT_PARK outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239495
}
[2] {
  "scenario_id": "62363F2061503E16DECA06383D",
  "action_sequence": "('ACT_FANCY_DINNER',)",
  "predicted_outcome": "Action ACT_FANCY_DINNER outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239495
}
[3] {
  "scenario_id": "573861081F38382070B3BED9F3",
  "action_sequence": "('ACT_PARK_PICNIC',)",
  "predicted_outcome": "Action ACT_PARK_PICNIC outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239495
}
[4] {
  "scenario_id": "69B873B9DC48C06E722E8044A0",
  "action_sequence": "('ACT_MOVIE',)",
  "predicted_outcome": "Action ACT_MOVIE outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239495
}
[5] {
  "scenario_id": "09B4BB6AA3DFF243C524FA5F5B",
  "action_sequence": "('ACT_GYM',)",
  "predicted_outcome": "Action ACT_GYM outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239495
}
[6] {
  "scenario_id": "CF671EA8E007A572B72C6DD060",
  "action_sequence": "('ACT_BOARD_GAMES',)",
  "predicted_outcome": "Action ACT_BOARD_GAMES outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239495
}
[7] {
  "scenario_id": "62D65AC97665E863886E9F1419",
  "action_sequence": "('ACT_BACKYARD_PLAY',)",
  "predicted_outcome": "Action ACT_BACKYARD_PLAY outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239495
}
[8] {
  "scenario_id": "D83769D54874DB8A6F09742F73",
  "action_sequence": "('ACT_NAP',)",
  "predicted_outcome": "Action ACT_NAP outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239495
}
[9] {
  "scenario_id": "503EFCE02405DE89A5F9B18EF4",
  "action_sequence": "('ACT_ICE_CREAM',)",
  "predicted_outcome": "Action ACT_ICE_CREAM outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239495
}
[10] {
  "scenario_id": "B5A89651286DB8F02D4501C50F",
  "action_sequence": "('ACT_LIBRARY',)",
  "predicted_outcome": "Action ACT_LIBRARY outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239495
}
```

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

**Inputs:**

```json
{
  "entities_count": 48,
  "entities_sample": [
    {
      "id": "ENT_SARAH",
      "category": "family"
    },
    {
      "id": "ENT_TOMMY",
      "category": "family"
    },
    {
      "id": "ENT_SPOUSE",
      "category": "family"
    },
    {
      "id": "ENT_GRANDMA",
      "category": "family"
    },
    {
      "id": "ENT_UNCLE",
      "category": "family"
    }
  ],
  "semantic_edges_count": 28,
  "semantic_edges_sample": [
    [
      "ENT_SARAH",
      "ENT_TOMMY",
      0.9
    ],
    [
      "ENT_SPOUSE",
      "ENT_FAMILY_DINNER",
      0.8
    ],
    [
      "ENT_GRANDMA",
      "ENT_FAMILY_VACATION",
      0.7
    ],
    [
      "ENT_SARAH",
      "ENT_FAMILY_MOOD",
      0.6
    ],
    [
      "ENT_HOMEWORK",
      "ENT_SCHOOL",
      0.9
    ]
  ]
}
```

**Outputs (7 shown):**

```json
[1] {
  "insight_id": "01KESGH22ADAYSKZCD9SVH29D1",
  "source_entity_id": "ENT_BUDGET",
  "target_entity_id": "ENT_VACATION",
  "source_entity_name": "Budget",
  "target_entity_name": "Vacation",
  "semantic_distance": 0.6725236489119981,
  "pmi_score": 5.210896782498619,
  "novelty_score": 0.0250317951304983,
  "insight_text": "Discovered surprising connection between 'Budget' and 'Vacation' (PMI: 5.21, distance: 0.67).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_BUDGET', 'ENT_VACATION')",
  "supporting_evidence": "('ENT_BUDGET', 'ENT_VACATION')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239498
}
[2] {
  "insight_id": "01KESGH229NH3A8D3XF9NE66ZD",
  "source_entity_id": "ENT_MEETING",
  "target_entity_id": "ENT_STRESS",
  "source_entity_name": "Meeting",
  "target_entity_name": "Stress",
  "semantic_distance": 0.7568116673837146,
  "pmi_score": 3.243318260190996,
  "novelty_score": 0.024302783171794018,
  "insight_text": "Discovered surprising connection between 'Meeting' and 'Stress' (PMI: 3.24, distance: 0.76).",
  "category": "InsightCategory.PATTERN",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_MEETING', 'ENT_STRESS')",
  "supporting_evidence": "('ENT_MEETING', 'ENT_STRESS')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.7,
  "created_at_ms": 1768235239497
}
[3] {
  "insight_id": "01KESGH229HAQQ66AQ9KSB5ZVG",
  "source_entity_id": "ENT_HOMEWORK",
  "target_entity_id": "ENT_STRESS",
  "source_entity_name": "Homework",
  "target_entity_name": "Stress",
  "semantic_distance": 0.6444169749952035,
  "pmi_score": 3.7641504234924366,
  "novelty_score": 0.023781200287587352,
  "insight_text": "Discovered surprising connection between 'Homework' and 'Stress' (PMI: 3.76, distance: 0.64).",
  "category": "InsightCategory.PATTERN",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_HOMEWORK', 'ENT_FRACTIONS', 'ENT_HOMEWORK', 'ENT_STRESS')",
  "supporting_evidence": "('ENT_HOMEWORK', 'ENT_STRESS')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.7,
  "created_at_ms": 1768235239497
}
[4] {
  "insight_id": "01KESGH22BWS9RJCT4GD6EBMGC",
  "source_entity_id": "ENT_EXERCISE",
  "target_entity_id": "ENT_FAMILY_MOOD",
  "source_entity_name": "Exercise",
  "target_entity_name": "Family Mood",
  "semantic_distance": 0.6225402606852652,
  "pmi_score": 3.4884307580275276,
  "novelty_score": 0.023605310798749505,
  "insight_text": "Discovered surprising connection between 'Exercise' and 'Family Mood' (PMI: 3.49, distance: 0.62).",
  "category": "InsightCategory.PATTERN",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_EXERCISE', 'ENT_ENERGY', 'ENT_EXERCISE', 'ENT_FAMILY_MOOD')",
  "supporting_evidence": "('ENT_EXERCISE', 'ENT_FAMILY_MOOD')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.7,
  "created_at_ms": 1768235239499
}
[5] {
  "insight_id": "01KESGH229EQS0TQ2BH712RNY8",
  "source_entity_id": "ENT_HOMEWORK",
  "target_entity_id": "ENT_SCHOOL",
  "source_entity_name": "Homework",
  "target_entity_name": "School",
  "semantic_distance": 0.17084473746988804,
  "pmi_score": 4.857259827883918,
  "novelty_score": 0.01455854877399757,
  "insight_text": "'Homework' may have downstream effects on 'School'.",
  "category": "InsightCategory.WARNING",
  "connection_type": "ConnectionType.CAUSAL",
  "connection_path": "('ENT_HOMEWORK', 'ENT_STRESS', 'ENT_MEETING', 'ENT_BOSS', 'ENT_MEETING', 'ENT_STRESS', 'ENT_HOMEWORK', 'ENT_SCHOOL')",
  "supporting_evidence": "('ENT_HOMEWORK', 'ENT_SCHOOL')",
  "confidence": 0.95,
  "relevance_score": 0.9,
  "actionability_score": 0.85,
  "created_at_ms": 1768235239497
}
[6] {
  "insight_id": "01KESGH229BJDVF2E9PE2K5WAM",
  "source_entity_id": "ENT_HOMEWORK",
  "target_entity_id": "ENT_FRACTIONS",
  "source_entity_name": "Homework",
  "target_entity_name": "Fractions",
  "semantic_distance": 0.16120959185416983,
  "pmi_score": 4.063710705351345,
  "novelty_score": 0.01310218288446222,
  "insight_text": "Discovered surprising connection between 'Homework' and 'Fractions' (PMI: 4.06, distance: 0.16).",
  "category": "InsightCategory.PATTERN",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_HOMEWORK', 'ENT_FRACTIONS')",
  "supporting_evidence": "('ENT_HOMEWORK', 'ENT_FRACTIONS')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.7,
  "created_at_ms": 1768235239497
}
[7] {
  "insight_id": "01KESGH22AFKAKGTJWCDHVNSQW",
  "source_entity_id": "ENT_BUDGET",
  "target_entity_id": "ENT_INCOME",
  "source_entity_name": "Budget",
  "target_entity_name": "Income",
  "semantic_distance": 0.161068429882412,
  "pmi_score": 6.058893689053568,
  "novelty_score": 0.010724137289234211,
  "insight_text": "Discovered surprising connection between 'Budget' and 'Income' (PMI: 6.06, distance: 0.16).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_BUDGET', 'ENT_VACATION', 'ENT_PARK', 'ENT_VACATION', 'ENT_BUDGET', 'ENT_INCOME')",
  "supporting_evidence": "('ENT_BUDGET', 'ENT_INCOME')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239498
}
```

**Metrics:**

| Metric | Value |
|--------|-------|
| total_insights | 7 |
| pmi_mean | 4.3838 |
| pmi_variance | 0.9004 |
| pmi_min | 3.2433 |
| pmi_max | 6.0589 |
| semantic_distance_mean | 0.4556 |
| semantic_distance_min | 0.1611 |
| semantic_distance_max | 0.7568 |
| novelty_mean | 0.0193 |
| cross_cluster_count | 0 |
| cross_cluster_ratio | 0.0000 |
| spurious_count | 0 |
| false_positive_rate | 0.0000 |

### bgt_adversarial ✅ PASSED

- Seed: 42
- Duration: 0.01s

#### BGT-SM ✅

**Inputs:**

```json
{
  "entities_count": 23,
  "entities_sample": [
    {
      "id": "ENT_WORK_STRESS",
      "category": "health"
    },
    {
      "id": "ENT_FAMILY_TIME",
      "category": "family"
    },
    {
      "id": "ENT_EXERCISE",
      "category": "health"
    },
    {
      "id": "ENT_SLEEP_QUALITY",
      "category": "health"
    },
    {
      "id": "ENT_PRODUCTIVITY",
      "category": "work"
    }
  ],
  "semantic_edges_count": 17,
  "semantic_edges_sample": [
    [
      "ENT_WORK_STRESS",
      "ENT_SLEEP_QUALITY",
      0.7
    ],
    [
      "ENT_EXERCISE",
      "ENT_SLEEP_QUALITY",
      0.75
    ],
    [
      "ENT_SLEEP_QUALITY",
      "ENT_PRODUCTIVITY",
      0.8
    ],
    [
      "ENT_FAMILY_TIME",
      "ENT_WORK_STRESS",
      0.6
    ],
    [
      "ENT_BANK_FINANCIAL",
      "ENT_SAVINGS",
      0.9
    ]
  ]
}
```

**Outputs (6 shown):**

```json
[1] {
  "insight_id": "01KESGH22CJMYSCTBHQ9P3QB9R",
  "source_entity_id": "ENT_WORK_STRESS",
  "target_entity_id": "ENT_FAMILY_TIME",
  "source_entity_name": "Work Stress",
  "target_entity_name": "Family Time",
  "semantic_distance": 0.6034284346001724,
  "pmi_score": 3.0588936890535687,
  "novelty_score": 0.03766986592640697,
  "insight_text": "Discovered surprising connection between 'Work Stress' and 'Family Time' (PMI: 3.06, distance: 0.60).",
  "category": "InsightCategory.PATTERN",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_WORK_STRESS', 'ENT_FAMILY_TIME')",
  "supporting_evidence": "('ENT_WORK_STRESS', 'ENT_FAMILY_TIME')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.7,
  "created_at_ms": 1768235239500
}
[2] {
  "insight_id": "01KESGH22EWQJ6A3DZK6RRNHQG",
  "source_entity_id": "ENT_BANK_FINANCIAL",
  "target_entity_id": "ENT_BANK_RIVER",
  "source_entity_name": "Bank",
  "target_entity_name": "Bank",
  "semantic_distance": 0.4726799348640387,
  "pmi_score": 5.965784284662087,
  "novelty_score": 0.03168434300097732,
  "insight_text": "Discovered surprising connection between 'Bank' and 'Bank' (PMI: 5.97, distance: 0.47).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_BANK_FINANCIAL', 'ENT_BANK_RIVER')",
  "supporting_evidence": "('ENT_BANK_FINANCIAL', 'ENT_BANK_RIVER')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239502
}
[3] {
  "insight_id": "01KESGH22D514H8AD9RB13862J",
  "source_entity_id": "ENT_PRODUCTIVITY",
  "target_entity_id": "ENT_SLEEP_QUALITY",
  "source_entity_name": "Productivity",
  "target_entity_name": "Sleep Quality",
  "semantic_distance": 0.7823343501792608,
  "pmi_score": 3.3510744405468786,
  "novelty_score": 0.016805516954151105,
  "insight_text": "Discovered surprising connection between 'Productivity' and 'Sleep Quality' (PMI: 3.35, distance: 0.78).",
  "category": "InsightCategory.PATTERN",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_PRODUCTIVITY', 'ENT_SLEEP_QUALITY')",
  "supporting_evidence": "('ENT_PRODUCTIVITY', 'ENT_SLEEP_QUALITY')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.7,
  "created_at_ms": 1768235239501
}
[4] {
  "insight_id": "01KESGH22CSRC61QTS4KCWVGSK",
  "source_entity_id": "ENT_WORK_STRESS",
  "target_entity_id": "ENT_NEWS",
  "source_entity_name": "Work Stress",
  "target_entity_name": "News",
  "semantic_distance": 0.36877071119207716,
  "pmi_score": 2.473931188332412,
  "novelty_score": 0.01658751570475644,
  "insight_text": "Discovered surprising connection between 'Work Stress' and 'News' (PMI: 2.47, distance: 0.37).",
  "category": "InsightCategory.PATTERN",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_WORK_STRESS', 'ENT_FAMILY_TIME', 'ENT_WORK_STRESS', 'ENT_NEWS')",
  "supporting_evidence": "('ENT_WORK_STRESS', 'ENT_NEWS')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.7,
  "created_at_ms": 1768235239500
}
[5] {
  "insight_id": "01KESGH22ET074HZJTVAMXN971",
  "source_entity_id": "ENT_BANK_FINANCIAL",
  "target_entity_id": "ENT_LOAN",
  "source_entity_name": "Bank",
  "target_entity_name": "Loan",
  "semantic_distance": 0.1509226071598988,
  "pmi_score": 5.380821783940931,
  "novelty_score": 0.015617070236445058,
  "insight_text": "Discovered surprising connection between 'Bank' and 'Loan' (PMI: 5.38, distance: 0.15).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_BANK_FINANCIAL', 'ENT_LOAN')",
  "supporting_evidence": "('ENT_BANK_FINANCIAL', 'ENT_LOAN')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239502
}
[6] {
  "insight_id": "01KESGH22E90HCDCH9A29TPDPX",
  "source_entity_id": "ENT_BANK_FINANCIAL",
  "target_entity_id": "ENT_SAVINGS",
  "source_entity_name": "Bank",
  "target_entity_name": "Savings Account",
  "semantic_distance": 0.19645539550033175,
  "pmi_score": 5.058893689053568,
  "novelty_score": 0.013614341924344535,
  "insight_text": "Discovered surprising connection between 'Bank' and 'Savings Account' (PMI: 5.06, distance: 0.20).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_BANK_FINANCIAL', 'ENT_SAVINGS')",
  "supporting_evidence": "('ENT_BANK_FINANCIAL', 'ENT_SAVINGS')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239502
}
```

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

**Inputs:**

```json
{
  "incomplete_episodes_count": 4,
  "incomplete_episodes": [
    {
      "id": "episode_soccer_saturday",
      "summary": "Saturday morning soccer activity... something with the kids",
      "location": null,
      "participants": [
        "Emma"
      ],
      "activity": null,
      "ambiguity": 0.75
    },
    {
      "id": "episode_school_play",
      "summary": "Evening event at school, someone was performing",
      "location": "Elementary School",
      "participants": null,
      "activity": null,
      "ambiguity": 0.8
    },
    {
      "id": "episode_grocery",
      "summary": "Went shopping for food with family",
      "location": null,
      "participants": [
        "Mom",
        "Dad",
        "Emma",
        "Jack"
      ],
      "activity": "shopping",
      "ambiguity": 0.6
    },
    {
      "id": "episode_work_conflict",
      "summary": "Had to deal with conflicting schedules...",
      "location": null,
      "participants": null,
      "activity": null,
      "ambiguity": 0.9
    }
  ],
  "fragments_count": 20,
  "fragments": [
    {
      "id": "frag_cal_01",
      "content": "Soccer game at 10:00 AM - Emma",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_msg_01",
      "content": "Coach Mike: Don't forget shin guards for tmrw!",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_sens_01",
      "content": "Saw Emma putting soccer gear in car trunk",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_rout_01",
      "content": "Typical Saturday: breakfast, prep, drive to field",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_inf_01",
      "content": "Likely stopped for coffee on way (based on usual pattern)",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_cal_02",
      "content": "School Play - Emma performing, 6 PM Friday",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_msg_02",
      "content": "Ms. Johnson: Please arrive 30 min early for costume",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_sens_02",
      "content": "Emma practicing lines in her room before dinner",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_rout_02",
      "content": "Evening school events typically: early dinner, drive, attend, home by 9",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_inf_02",
      "content": "Jack probably attended too (family support pattern)",
      "provenance_type": null,
      "confidence": null
    }
  ],
  "schemas_count": 0,
  "context_keys": [
    "current_date",
    "day_of_week",
    "family_size",
    "active_activities",
    "provenance_weights",
    "nearby_locations",
    "known_locations",
    "frequent_contacts"
  ]
}
```

**Outputs (4 shown):**

```json
[1] {
  "episode_id": "0AF9410E9634BAED8AE734D49D",
  "original_episode_id": "episode_soccer_saturday",
  "summary": "Saturday morning soccer activity... something with the kids [Reconstructed: location_name]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='location_name', value='loc_home', confidence=0.4, uncertainty=0.6, provenance=<ReconstructionProvenance.CALENDAR: 'calendar'>, schema_id=None, created_at_ms=1768235239506),)",
  "confidence_score": 0.4,
  "uncertainty_score": 0.6,
  "temporal_coherence_score": 0.85,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['frag_cal_01', 'frag_msg_01', 'frag_sens_01', 'frag_rout_01', 'frag_inf_01'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.MESSAGE', 'ReconstructionProvenance.SENSOR', 'ReconstructionProvenance.INFERRED_PRIOR', 'ReconstructionProvenance.ROUTINE_PRIOR', 'ReconstructionProvenance.CALENDAR'], 'reconstruction_provenance': ['ReconstructionProvenance.CALENDAR'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239506
}
[2] {
  "episode_id": "A150B0A43B8BBC653ABEECE137",
  "original_episode_id": "episode_school_play",
  "summary": "Evening event at school, someone was performing [Reconstructed: participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='participants', value=['Mom', 'Jack'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CALENDAR: 'calendar'>, schema_id=None, created_at_ms=1768235239506),)",
  "confidence_score": 0.35,
  "uncertainty_score": 0.65,
  "temporal_coherence_score": 0.725,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['frag_cal_02', 'frag_msg_02', 'frag_sens_02', 'frag_rout_02', 'frag_inf_02'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.MESSAGE', 'ReconstructionProvenance.SENSOR', 'ReconstructionProvenance.INFERRED_PRIOR', 'ReconstructionProvenance.ROUTINE_PRIOR', 'ReconstructionProvenance.CALENDAR'], 'reconstruction_provenance': ['ReconstructionProvenance.CALENDAR'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239506
}
[3] {
  "episode_id": "A679326108A23F96456B27C926",
  "original_episode_id": "episode_grocery",
  "summary": "Went shopping for food with family [Reconstructed: location_name]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='location_name', value='loc_home', confidence=0.4, uncertainty=0.6, provenance=<ReconstructionProvenance.CALENDAR: 'calendar'>, schema_id=None, created_at_ms=1768235239506),)",
  "confidence_score": 0.4,
  "uncertainty_score": 0.6,
  "temporal_coherence_score": 0.77,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['frag_cal_03', 'frag_msg_03', 'frag_sens_03', 'frag_msg_04', 'frag_sens_04', 'frag_rout_03'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.SENSOR', 'ReconstructionProvenance.MESSAGE', 'ReconstructionProvenance.ROUTINE_PRIOR', 'ReconstructionProvenance.CALENDAR'], 'reconstruction_provenance': ['ReconstructionProvenance.CALENDAR'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239506
}
[4] {
  "episode_id": "61791BE3D5941E7DDBEC20A617",
  "original_episode_id": "episode_work_conflict",
  "summary": "Had to deal with conflicting schedules... [Reconstructed: location_name, participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='location_name', value='loc_home', confidence=0.4, uncertainty=0.6, provenance=<ReconstructionProvenance.CALENDAR: 'calendar'>, schema_id=None, created_at_ms=1768235239506), ReconstructedValue(attribute_name='participants', value=['Coach Mike', 'Dad'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CALENDAR: 'calendar'>, schema_id=None, created_at_ms=1768235239506))",
  "confidence_score": 0.275,
  "uncertainty_score": 0.725,
  "temporal_coherence_score": 0.8,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['frag_cal_04', 'frag_cal_05', 'frag_msg_05', 'frag_inf_03'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.INFERRED_PRIOR', 'ReconstructionProvenance.MESSAGE', 'ReconstructionProvenance.CALENDAR'], 'reconstruction_provenance': ['ReconstructionProvenance.CALENDAR'], 'conflicts_detected': 1, 'conflict_details': [{'attribute': 'temporal', 'values': ['5 PM', '6 PM'], 'severity': 0.7}]}",
  "is_canonical": false,
  "created_at_ms": 1768235239506
}
```

**Metrics:**

| Metric | Value |
|--------|-------|
| total_reconstructions | 4 |
| confidence_mean | 0.3562 |
| confidence_variance | 0.0026 |
| uncertainty_mean | 0.6438 |
| uncertainty_variance | 0.0026 |
| provenance_types | ReconstructionProvenance.SENSOR, ReconstructionProvenance.INFERRED_PRIOR, ReconstructionProvenance.MESSAGE, ReconstructionProvenance.CALENDAR, ReconstructionProvenance.ROUTINE_PRIOR |
| provenance_types_count | 5 |
| fragment_provenance_types |  |
| schema_matches | 0 |
| conflict_fragments | 1 |
| high_uncertainty_on_conflict | 1 |

### spc_conflict ✅ PASSED

- Seed: 42
- Duration: 0.00s

#### SPC-UQ ✅

**Inputs:**

```json
{
  "incomplete_episodes_count": 6,
  "incomplete_episodes": [
    {
      "id": "episode_cluster_temporal_arrival",
      "summary": "Conflicting information about temporal details...",
      "location": "Unknown Location",
      "participants": [
        "Unknown"
      ],
      "activity": "conflicted_activity",
      "ambiguity": 0.75
    },
    {
      "id": "episode_cluster_spatial_saturday",
      "summary": "Conflicting information about spatial details...",
      "location": null,
      "participants": [
        "Unknown"
      ],
      "activity": "conflicted_activity",
      "ambiguity": 0.65
    },
    {
      "id": "episode_cluster_factual_meeting",
      "summary": "Conflicting information about factual details...",
      "location": "Unknown Location",
      "participants": [
        "Unknown"
      ],
      "activity": null,
      "ambiguity": 0.65
    },
    {
      "id": "episode_cluster_attribution_pickup",
      "summary": "Conflicting information about attribution details...",
      "location": "Unknown Location",
      "participants": null,
      "activity": "conflicted_activity",
      "ambiguity": 0.75
    },
    {
      "id": "episode_cluster_pizza_night",
      "summary": "Conflicting information about temporal details...",
      "location": "Unknown Location",
      "participants": [
        "Unknown"
      ],
      "activity": "conflicted_activity",
      "ambiguity": 0.65
    }
  ],
  "fragments_count": 18,
  "fragments": [
    {
      "id": "frag_temp_1a",
      "content": "Charlie came home at 3:30 PM",
      "provenance_type": null,
      "confidence": null,
      "conflict_type": "temporal"
    },
    {
      "id": "frag_temp_1b",
      "content": "Saw Charlie arrive around 4:15 PM, was watering plants",
      "provenance_type": null,
      "confidence": null,
      "conflict_type": "temporal"
    },
    {
      "id": "frag_temp_1c",
      "content": "School bus dropped Charlie at 3:45 PM",
      "provenance_type": null,
      "confidence": null,
      "conflict_type": "temporal"
    },
    {
      "id": "frag_temp_1d",
      "content": "Bus tracking shows arrival at Oak Street stop 3:42 PM",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_spat_2a",
      "content": "We went to the mall on Saturday afternoon",
      "provenance_type": null,
      "confidence": null,
      "conflict_type": "spatial"
    },
    {
      "id": "frag_spat_2b",
      "content": "Saturday was park day, remember the picnic?",
      "provenance_type": null,
      "confidence": null,
      "conflict_type": "spatial"
    },
    {
      "id": "frag_spat_2c",
      "content": "Photo EXIF: GPS coordinates match Central Park, 2:15 PM",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "frag_fact_3a",
      "content": "Diana got an award at the school meeting",
      "provenance_type": null,
      "confidence": null,
      "conflict_type": "factual"
    },
    {
      "id": "frag_fact_3b",
      "content": "Diana's class performed a song, no awards given",
      "provenance_type": null,
      "confidence": null,
      "conflict_type": "factual"
    },
    {
      "id": "frag_fact_3c",
      "content": "Official: 3rd grade performed 'Spring Song', attendance certificates distributed",
      "provenance_type": null,
      "confidence": null
    }
  ],
  "schemas_count": 0,
  "context_keys": [
    "current_date",
    "day_of_week",
    "family_members",
    "source_reliability",
    "conflict_clusters",
    "nearby_locations",
    "known_locations",
    "frequent_contacts"
  ]
}
```

**Outputs (1 shown):**

```json
[1] {
  "episode_id": "0EC77F25C46CF5C2A9AAA6F469",
  "original_episode_id": "episode_cluster_attribution_pickup",
  "summary": "Conflicting information about attribution details... [Reconstructed: participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='participants', value=['Alice', 'Charlie'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.MESSAGE: 'message'>, schema_id=None, created_at_ms=1768235239507),)",
  "confidence_score": 0.24999999999999997,
  "uncertainty_score": 0.75,
  "temporal_coherence_score": 0.7,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['frag_attr_4a', 'frag_attr_4b', 'frag_attr_4c'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.MESSAGE', 'ReconstructionProvenance.SENSOR'], 'reconstruction_provenance': ['ReconstructionProvenance.MESSAGE'], 'conflicts_detected': 1, 'conflict_details': [{'attribute': 'attribution', 'values': ['I picked up Diana from library at 5', 'Got Diana from library, she was reading Harry Pott'], 'severity': 0.7}]}",
  "is_canonical": false,
  "created_at_ms": 1768235239507
}
```

**Metrics:**

| Metric | Value |
|--------|-------|
| total_reconstructions | 1 |
| confidence_mean | 0.2500 |
| confidence_variance | 0.0000 |
| uncertainty_mean | 0.7500 |
| uncertainty_variance | 0.0000 |
| provenance_types | ReconstructionProvenance.SENSOR, ReconstructionProvenance.MESSAGE |
| provenance_types_count | 2 |
| fragment_provenance_types |  |
| schema_matches | 0 |
| conflict_fragments | 1 |
| high_uncertainty_on_conflict | 1 |

### mixed_stress ✅ PASSED

- Seed: 42
- Duration: 0.05s

#### CPN ✅

**Inputs:**

```json
{
  "episodes_count": 150,
  "episodes": [
    {
      "id": "EP_00000",
      "summary": "Episode 0 involving 6 entities",
      "emotional_valence": -0.3599149336817078,
      "participants": [
        "work_person_630"
      ],
      "location": "mall",
      "activity": "entertainment"
    },
    {
      "id": "EP_00001",
      "summary": "Episode 1 involving 3 entities",
      "emotional_valence": 0.18746298336839418,
      "participants": [
        "finance_person_549",
        "family_person_400"
      ],
      "location": "hospital",
      "activity": "work_meeting"
    },
    {
      "id": "EP_00002",
      "summary": "Episode 2 involving 3 entities",
      "emotional_valence": -0.15837920109179937,
      "participants": [
        "self"
      ],
      "location": "home_living_room",
      "activity": "social_event"
    },
    {
      "id": "EP_00003",
      "summary": "Episode 3 involving 6 entities",
      "emotional_valence": 0.39877890512878866,
      "participants": [
        "entertainment_person_759"
      ],
      "location": "home_bedroom",
      "activity": "work_meeting"
    },
    {
      "id": "EP_00004",
      "summary": "Episode 4 involving 2 entities",
      "emotional_valence": 0.21663125204559586,
      "participants": [
        "self"
      ],
      "location": "mall",
      "activity": "healthcare"
    },
    {
      "id": "EP_00005",
      "summary": "Episode 5 involving 4 entities",
      "emotional_valence": 0.01727520709360703,
      "participants": [
        "social_person_380"
      ],
      "location": "library",
      "activity": "work_meeting"
    },
    {
      "id": "EP_00006",
      "summary": "Episode 6 involving 5 entities",
      "emotional_valence": 0.013108321159747886,
      "participants": [
        "health_person_536"
      ],
      "location": "hospital",
      "activity": "work_meeting"
    },
    {
      "id": "EP_00007",
      "summary": "Episode 7 involving 5 entities",
      "emotional_valence": -0.09676165564951059,
      "participants": [
        "self"
      ],
      "location": "home_bedroom",
      "activity": "travel"
    }
  ],
  "kg_edges_count": 373,
  "kg_edges": [
    {
      "source": "ENT_00371",
      "target": "ENT_00312",
      "relation": "CAUSES",
      "weight": 0.8550591822710512
    },
    {
      "source": "ENT_00312",
      "target": "ENT_00946",
      "relation": "CAUSES",
      "weight": 0.8948455285228256
    },
    {
      "source": "ENT_00946",
      "target": "ENT_00221",
      "relation": "CAUSES",
      "weight": 0.9142942416238851
    },
    {
      "source": "ENT_00221",
      "target": "ENT_00882",
      "relation": "CAUSES",
      "weight": 0.6675092028243814
    },
    {
      "source": "ENT_00882",
      "target": "ENT_00798",
      "relation": "CAUSES",
      "weight": 0.669045404146811
    },
    {
      "source": "ENT_00773",
      "target": "ENT_00108",
      "relation": "CAUSES",
      "weight": 0.8917344415063095
    },
    {
      "source": "ENT_00108",
      "target": "ENT_00546",
      "relation": "CAUSES",
      "weight": 0.6672010593322901
    },
    {
      "source": "ENT_00546",
      "target": "ENT_00187",
      "relation": "CAUSES",
      "weight": 0.778888851917098
    },
    {
      "source": "ENT_00187",
      "target": "ENT_00361",
      "relation": "CAUSES",
      "weight": 0.7644756620785682
    },
    {
      "source": "ENT_00901",
      "target": "ENT_00184",
      "relation": "CAUSES",
      "weight": 0.6678108238962857
    }
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "scenario_id": "cf_1b9d27c1ef99d01f",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "EP_00042",
  "intervention_node_id": "ENT_00921",
  "perturbation_target": "ENT_00921",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_00921 had been different, outcome would be better",
  "original_sentiment": -1.0,
  "predicted_sentiment": -0.3977833763632941,
  "plausibility": 0.5,
  "success_probability": 0.4005541559091765,
  "utility_delta": 0.6022166236367059,
  "mitigation": "Next time, consider changing ENT_00921 earlier",
  "causal_path_length": 4,
  "created_at_ms": 1768235239534
}
[2] {
  "scenario_id": "cf_95d216e8af715f2b",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "EP_00062",
  "intervention_node_id": "ENT_00775",
  "perturbation_target": "ENT_00775",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_00775 had been different, outcome would be better",
  "original_sentiment": -0.8178354292440885,
  "predicted_sentiment": -0.2472667674439082,
  "plausibility": 0.5,
  "success_probability": 0.39264216545004504,
  "utility_delta": 0.5705686618001803,
  "mitigation": "Next time, consider changing ENT_00775 earlier",
  "causal_path_length": 2,
  "created_at_ms": 1768235239536
}
[3] {
  "scenario_id": "cf_bf4c4e987856789a",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "EP_00042",
  "intervention_node_id": "ENT_00233",
  "perturbation_target": "ENT_00233",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_00233 had been different, outcome would be better",
  "original_sentiment": -1.0,
  "predicted_sentiment": -0.4382399925809968,
  "plausibility": 0.5,
  "success_probability": 0.3904400018547508,
  "utility_delta": 0.5617600074190032,
  "mitigation": "Next time, consider changing ENT_00233 earlier",
  "causal_path_length": 2,
  "created_at_ms": 1768235239534
}
[4] {
  "scenario_id": "cf_e92cb5415dcc0d22",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "EP_00011",
  "intervention_node_id": "ENT_00510",
  "perturbation_target": "ENT_00510",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_00510 had also gone wrong, outcome would be worse",
  "original_sentiment": 0.9166971385639319,
  "predicted_sentiment": 0.36149525118046943,
  "plausibility": 0.5,
  "success_probability": 0.11119952815413439,
  "utility_delta": -0.5552018873834624,
  "mitigation": null,
  "causal_path_length": 1,
  "created_at_ms": 1768235239534
}
[5] {
  "scenario_id": "cf_5adbc5f90210a631",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "EP_00029",
  "intervention_node_id": "ENT_00563",
  "perturbation_target": "ENT_00563",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_00563 had been different, outcome would be better",
  "original_sentiment": -1.0,
  "predicted_sentiment": -0.4723351650888279,
  "plausibility": 1.0,
  "success_probability": 0.763832417455586,
  "utility_delta": 0.5276648349111721,
  "mitigation": "Next time, consider changing ENT_00563 earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239535
}
[6] {
  "scenario_id": "cf_71a84e207eba50f5",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "EP_00096",
  "intervention_node_id": "ENT_00080",
  "perturbation_target": "ENT_00080",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_00080 had been different, outcome would be better",
  "original_sentiment": -0.7440476608450417,
  "predicted_sentiment": -0.2178864824136102,
  "plausibility": 0.5,
  "success_probability": 0.3815402946078579,
  "utility_delta": 0.5261611784314315,
  "mitigation": "Next time, consider changing ENT_00080 earlier",
  "causal_path_length": 3,
  "created_at_ms": 1768235239536
}
[7] {
  "scenario_id": "cf_4e808c8f8f7de84e",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "EP_00011",
  "intervention_node_id": "ENT_00401",
  "perturbation_target": "ENT_00401",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_00401 had also gone wrong, outcome would be worse",
  "original_sentiment": 0.9166971385639319,
  "predicted_sentiment": 0.3943603912337642,
  "plausibility": 0.5,
  "success_probability": 0.11941581316745808,
  "utility_delta": -0.5223367473301677,
  "mitigation": null,
  "causal_path_length": 2,
  "created_at_ms": 1768235239534
}
[8] {
  "scenario_id": "cf_b1462ec8572fd1f1",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "EP_00042",
  "intervention_node_id": "ENT_00606",
  "perturbation_target": "ENT_00606",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_00606 had been different, outcome would be better",
  "original_sentiment": -1.0,
  "predicted_sentiment": -0.5010198527676575,
  "plausibility": 0.5,
  "success_probability": 0.37474503680808563,
  "utility_delta": 0.4989801472323425,
  "mitigation": "Next time, consider changing ENT_00606 earlier",
  "causal_path_length": 3,
  "created_at_ms": 1768235239534
}
[9] {
  "scenario_id": "cf_b78dd37a5c859ccb",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "EP_00042",
  "intervention_node_id": "ENT_00785",
  "perturbation_target": "ENT_00785",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_00785 had been different, outcome would be better",
  "original_sentiment": -1.0,
  "predicted_sentiment": -0.5042713090995847,
  "plausibility": 0.5,
  "success_probability": 0.3739321727251038,
  "utility_delta": 0.49572869090041527,
  "mitigation": "Next time, consider changing ENT_00785 earlier",
  "causal_path_length": 3,
  "created_at_ms": 1768235239534
}
[10] {
  "scenario_id": "cf_d774544234a4eb3a",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "EP_00029",
  "intervention_node_id": "ENT_00067",
  "perturbation_target": "ENT_00067",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_00067 had been different, outcome would be better",
  "original_sentiment": -1.0,
  "predicted_sentiment": -0.5062079480402736,
  "plausibility": 0.5,
  "success_probability": 0.3734480129899316,
  "utility_delta": 0.4937920519597264,
  "mitigation": "Next time, consider changing ENT_00067 earlier",
  "causal_path_length": 3,
  "created_at_ms": 1768235239535
}
```

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
| scenario_types | ScenarioType.SEMIFACTUAL, ScenarioType.UPWARD, ScenarioType.DOWNWARD |
| scenario_type_count | 3 |

#### MCTS ✅

**Inputs:**

```json
{
  "initial_state": {
    "time_of_day": "afternoon",
    "day": "weekend",
    "family_mood": "happy",
    "energy_level": "0.9414148766436616",
    "pending_tasks": "['task_0', 'task_1', 'task_2', 'task_3', 'task_4', 'task_5', 'task_6', 'task_7', 'task_8']",
    "budget_remaining": "154.6868231596248",
    "time_budget_hours": "2.2713329701414824"
  },
  "actions_count": 100,
  "actions_sample": [
    "StressAction(action_id='ACT_00000', name='Educational activity 0', duration_hours=0.6864707220952182, goal_alignment=0.5934053646862711, expected_reward=0.5225857434391984, preconditions=[])",
    "StressAction(action_id='ACT_00001', name='Entertainment 1', duration_hours=2.2412924929129536, goal_alignment=0.4477952619597247, expected_reward=0.3724700283668938, preconditions=[])",
    "StressAction(action_id='ACT_00002', name='Family time with 2', duration_hours=1.6270788941665035, goal_alignment=0.9362230903341933, expected_reward=0.7502911368425058, preconditions=[])",
    "StressAction(action_id='ACT_00003', name='Shopping for 3', duration_hours=1.451972963457084, goal_alignment=0.28360301587984094, expected_reward=0.26808479770110916, preconditions=['ACT_00001'])",
    "StressAction(action_id='ACT_00004', name='Family time with 4', duration_hours=2.727086417851188, goal_alignment=0.9644025954679883, expected_reward=0.7980598584790242, preconditions=[])"
  ],
  "goals": [
    "StressGoal(goal_id='GOAL_000', description='Reduce stress (variant 0)', priority=0.6687892434038949, target_value=1.0)",
    "StressGoal(goal_id='GOAL_001', description='Travel more (variant 1)', priority=0.9041783121636304, target_value=1.0)",
    "StressGoal(goal_id='GOAL_002', description='Maintain health (variant 2)', priority=0.6455850701156756, target_value=1.0)"
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "scenario_id": "8DD226574EDB91E0017BD43E67",
  "action_sequence": "('ACT_00000',)",
  "predicted_outcome": "Action ACT_00000 outcome",
  "success_probability": 0.05,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 1,
  "depth": 1,
  "created_at_ms": 1768235239538
}
[2] {
  "scenario_id": "3E403F2A5179CC8BEFC8BD3691",
  "action_sequence": "('ACT_00001',)",
  "predicted_outcome": "Action ACT_00001 outcome",
  "success_probability": 0.05,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 1,
  "depth": 1,
  "created_at_ms": 1768235239538
}
[3] {
  "scenario_id": "2CF25C9DABEDA1CC95016610EF",
  "action_sequence": "('ACT_00002',)",
  "predicted_outcome": "Action ACT_00002 outcome",
  "success_probability": 0.05,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 1,
  "depth": 1,
  "created_at_ms": 1768235239538
}
[4] {
  "scenario_id": "90788355E9AB05D799A3F25F2D",
  "action_sequence": "('ACT_00003',)",
  "predicted_outcome": "Action ACT_00003 outcome",
  "success_probability": 0.05,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 1,
  "depth": 1,
  "created_at_ms": 1768235239538
}
[5] {
  "scenario_id": "88BF11A20C72E7385C78F4850C",
  "action_sequence": "('ACT_00004',)",
  "predicted_outcome": "Action ACT_00004 outcome",
  "success_probability": 0.05,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 1,
  "depth": 1,
  "created_at_ms": 1768235239538
}
[6] {
  "scenario_id": "18C311BD55D3D6781679B31844",
  "action_sequence": "('ACT_00005',)",
  "predicted_outcome": "Action ACT_00005 outcome",
  "success_probability": 0.05,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 1,
  "depth": 1,
  "created_at_ms": 1768235239538
}
[7] {
  "scenario_id": "0CA388F326E4E6BEB0B0B2D8C8",
  "action_sequence": "('ACT_00006',)",
  "predicted_outcome": "Action ACT_00006 outcome",
  "success_probability": 0.05,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 1,
  "depth": 1,
  "created_at_ms": 1768235239538
}
[8] {
  "scenario_id": "3909110890CC69A2F7D09CAF3E",
  "action_sequence": "('ACT_00007',)",
  "predicted_outcome": "Action ACT_00007 outcome",
  "success_probability": 0.05,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 1,
  "depth": 1,
  "created_at_ms": 1768235239538
}
[9] {
  "scenario_id": "61EA69D9D7DB635DC4FB0CA503",
  "action_sequence": "('ACT_00008',)",
  "predicted_outcome": "Action ACT_00008 outcome",
  "success_probability": 0.05,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 1,
  "depth": 1,
  "created_at_ms": 1768235239538
}
[10] {
  "scenario_id": "05B4942AD1B1D992C4F7666FCD",
  "action_sequence": "('ACT_00009',)",
  "predicted_outcome": "Action ACT_00009 outcome",
  "success_probability": 0.05,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 1,
  "depth": 1,
  "created_at_ms": 1768235239538
}
```

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

**Inputs:**

```json
{
  "entities_count": 1000,
  "entities_sample": [
    {
      "id": "ENT_00000",
      "category": "entertainment"
    },
    {
      "id": "ENT_00001",
      "category": "work"
    },
    {
      "id": "ENT_00002",
      "category": "health"
    },
    {
      "id": "ENT_00003",
      "category": "education"
    },
    {
      "id": "ENT_00004",
      "category": "work"
    }
  ],
  "semantic_edges_count": 3000,
  "semantic_edges_sample": [
    [
      "ENT_00864",
      "ENT_00465",
      0.6921055915742477
    ],
    [
      "ENT_00721",
      "ENT_00156",
      0.8315239657553819
    ],
    [
      "ENT_00944",
      "ENT_00472",
      0.6653895606228951
    ],
    [
      "ENT_00546",
      "ENT_00168",
      0.37487305386366326
    ],
    [
      "ENT_00520",
      "ENT_00264",
      0.8771879005953243
    ]
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "insight_id": "01KESGH23S79VDS0S650AMCJS0",
  "source_entity_id": "ENT_00002",
  "target_entity_id": "ENT_00021",
  "source_entity_name": "health_object_2",
  "target_entity_name": "entertainment_object_21",
  "semantic_distance": 0.7838046402428889,
  "pmi_score": 15.988152097690541,
  "novelty_score": 3.132896950769731,
  "insight_text": "Discovered surprising connection between 'health_object_2' and 'entertainment_object_21' (PMI: 15.99, distance: 0.78).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_00002', 'ENT_00021')",
  "supporting_evidence": "('ENT_00002', 'ENT_00021')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239545
}
[2] {
  "insight_id": "01KESGH23P1XP2Y7VW0FZ2JZ1A",
  "source_entity_id": "ENT_00000",
  "target_entity_id": "ENT_00257",
  "source_entity_name": "entertainment_person_0",
  "target_entity_name": "family_person_257",
  "semantic_distance": 0.7987564862704175,
  "pmi_score": 16.28771237954945,
  "novelty_score": 1.30099159096721,
  "insight_text": "Discovered surprising connection between 'entertainment_person_0' and 'family_person_257' (PMI: 16.29, distance: 0.80).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_00000', 'ENT_00727', 'ENT_00000', 'ENT_00257')",
  "supporting_evidence": "('ENT_00000', 'ENT_00257')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239542
}
[3] {
  "insight_id": "01KESGH23QMQ9ARM6TRK5C0F8R",
  "source_entity_id": "ENT_00001",
  "target_entity_id": "ENT_00099",
  "source_entity_name": "work_activity_1",
  "target_entity_name": "social_location_99",
  "semantic_distance": 0.8238568032414424,
  "pmi_score": 16.095067301607052,
  "novelty_score": 1.105002557921488,
  "insight_text": "Discovered surprising connection between 'work_activity_1' and 'social_location_99' (PMI: 16.10, distance: 0.82).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_00001', 'ENT_00045', 'ENT_00001', 'ENT_00099')",
  "supporting_evidence": "('ENT_00001', 'ENT_00099')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239543
}
[4] {
  "insight_id": "01KESGH23S8F555GFPN5K4QZAE",
  "source_entity_id": "ENT_00002",
  "target_entity_id": "ENT_00974",
  "source_entity_name": "health_object_2",
  "target_entity_name": "health_person_974",
  "semantic_distance": 0.17589077371181894,
  "pmi_score": 16.872674880270605,
  "novelty_score": 0.7419369598196922,
  "insight_text": "Discovered surprising connection between 'health_object_2' and 'health_person_974' (PMI: 16.87, distance: 0.18).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_00002', 'ENT_00974')",
  "supporting_evidence": "('ENT_00002', 'ENT_00974')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239545
}
[5] {
  "insight_id": "01KESGH23PZN3QV47RV7Q5XTZ0",
  "source_entity_id": "ENT_00000",
  "target_entity_id": "ENT_00139",
  "source_entity_name": "entertainment_person_0",
  "target_entity_name": "social_event_139",
  "semantic_distance": 0.7598503871486595,
  "pmi_score": 15.287712379549449,
  "novelty_score": 0.7260233856386252,
  "insight_text": "Discovered surprising connection between 'entertainment_person_0' and 'social_event_139' (PMI: 15.29, distance: 0.76).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_00000', 'ENT_00139')",
  "supporting_evidence": "('ENT_00000', 'ENT_00139')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239542
}
[6] {
  "insight_id": "01KESGH23P7B3TY069HH8DE631",
  "source_entity_id": "ENT_00000",
  "target_entity_id": "ENT_00720",
  "source_entity_name": "entertainment_person_0",
  "target_entity_name": "work_object_720",
  "semantic_distance": 0.856565391432485,
  "pmi_score": 15.872674880270605,
  "novelty_score": 0.7155781037841875,
  "insight_text": "Discovered surprising connection between 'entertainment_person_0' and 'work_object_720' (PMI: 15.87, distance: 0.86).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_00000', 'ENT_00720')",
  "supporting_evidence": "('ENT_00000', 'ENT_00720')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239542
}
[7] {
  "insight_id": "01KESGH23SXQC5BMQT9CKJMZJF",
  "source_entity_id": "ENT_00002",
  "target_entity_id": "ENT_00960",
  "source_entity_name": "health_object_2",
  "target_entity_name": "finance_topic_960",
  "semantic_distance": 0.6506540341344276,
  "pmi_score": 14.287712379549449,
  "novelty_score": 0.6640255498790179,
  "insight_text": "Discovered surprising connection between 'health_object_2' and 'finance_topic_960' (PMI: 14.29, distance: 0.65).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_00002', 'ENT_00960')",
  "supporting_evidence": "('ENT_00002', 'ENT_00960')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239545
}
[8] {
  "insight_id": "01KESGH242MK0H0ATC2K5GQ774",
  "source_entity_id": "ENT_00007",
  "target_entity_id": "ENT_00188",
  "source_entity_name": "social_person_7",
  "target_entity_name": "education_topic_188",
  "semantic_distance": 0.638161529974961,
  "pmi_score": 16.095067301607052,
  "novelty_score": 0.6419532983902202,
  "insight_text": "Discovered surprising connection between 'social_person_7' and 'education_topic_188' (PMI: 16.10, distance: 0.64).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_00007', 'ENT_00188')",
  "supporting_evidence": "('ENT_00007', 'ENT_00188')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239554
}
[9] {
  "insight_id": "01KESGH23PHYF7AY56D6TBQY0R",
  "source_entity_id": "ENT_00000",
  "target_entity_id": "ENT_00771",
  "source_entity_name": "entertainment_person_0",
  "target_entity_name": "entertainment_person_771",
  "semantic_distance": 0.21779714620078872,
  "pmi_score": 16.535639892993036,
  "novelty_score": 0.45017689741222483,
  "insight_text": "Discovered surprising connection between 'entertainment_person_0' and 'entertainment_person_771' (PMI: 16.54, distance: 0.22).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_00000', 'ENT_00727', 'ENT_00421', 'ENT_00450', 'ENT_00421', 'ENT_00159', 'ENT_00807', 'ENT_00467', 'ENT_00807', 'ENT_00021', 'ENT_00329', 'ENT_00771')",
  "supporting_evidence": "('ENT_00000', 'ENT_00771')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239542
}
[10] {
  "insight_id": "01KESGH23PYQ9VKB3P7PJGH7CS",
  "source_entity_id": "ENT_00000",
  "target_entity_id": "ENT_00237",
  "source_entity_name": "entertainment_person_0",
  "target_entity_name": "entertainment_object_237",
  "semantic_distance": 0.232923521454377,
  "pmi_score": 16.194602975157967,
  "novelty_score": 0.37721039535293244,
  "insight_text": "Discovered surprising connection between 'entertainment_person_0' and 'entertainment_object_237' (PMI: 16.19, distance: 0.23).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_00000', 'ENT_00237')",
  "supporting_evidence": "('ENT_00000', 'ENT_00237')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239542
}
```

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

**Inputs:**

```json
{
  "incomplete_episodes_count": 30,
  "incomplete_episodes": [
    {
      "id": "INC_00000",
      "summary": "Incomplete episode 0 - details missing",
      "location": "library",
      "participants": null,
      "activity": "healthcare",
      "ambiguity": 0.5116694175839305
    },
    {
      "id": "INC_00001",
      "summary": "Incomplete episode 1 - details missing",
      "location": "theater",
      "participants": [
        "person_0"
      ],
      "activity": null,
      "ambiguity": 0.7339867129116744
    },
    {
      "id": "INC_00002",
      "summary": "Incomplete episode 2 - details missing",
      "location": null,
      "participants": [
        "person_0"
      ],
      "activity": "social_event",
      "ambiguity": 0.6981883230983873
    },
    {
      "id": "INC_00003",
      "summary": "Incomplete episode 3 - details missing",
      "location": "airport",
      "participants": [
        "person_0",
        "person_1",
        "person_2",
        "person_3"
      ],
      "activity": null,
      "ambiguity": 0.5363679890954322
    },
    {
      "id": "INC_00004",
      "summary": "Incomplete episode 4 - details missing",
      "location": "mall",
      "participants": null,
      "activity": null,
      "ambiguity": 0.5946202986292276
    }
  ],
  "fragments_count": 123,
  "fragments": [
    {
      "id": "FRAG_INC_00000_00",
      "content": "Fragment content for inferred provenance",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_00000_01",
      "content": "Fragment content for calendar provenance",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_00000_02",
      "content": "Fragment content for calendar provenance",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_00000_03",
      "content": "Fragment content for message provenance",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_00000_04",
      "content": "Fragment content for voice provenance",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_00001_00",
      "content": "Fragment content for voice provenance",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_00001_01",
      "content": "Fragment content for voice provenance",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_00001_02",
      "content": "Fragment content for voice provenance",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_00001_03",
      "content": "Fragment content for photo provenance",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_00002_00",
      "content": "Fragment content for calendar provenance",
      "provenance_type": null,
      "confidence": null
    }
  ],
  "schemas_count": 0,
  "context_keys": [
    "time_of_day",
    "day",
    "nearby_locations",
    "known_locations",
    "frequent_contacts",
    "recent_activities"
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "episode_id": "7846911C27A1C33B5DC793ECC0",
  "original_episode_id": "INC_00000",
  "summary": "Incomplete episode 0 - details missing [Reconstructed: participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='participants', value=['contact_10', 'contact_1'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239555),)",
  "confidence_score": 0.35,
  "uncertainty_score": 0.65,
  "temporal_coherence_score": 0.775,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_00000_00', 'FRAG_INC_00000_01', 'FRAG_INC_00000_02', 'FRAG_INC_00000_03', 'FRAG_INC_00000_04'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239555
}
[2] {
  "episode_id": "A1301BC335AEA7EEC00D6D09E0",
  "original_episode_id": "INC_00002",
  "summary": "Incomplete episode 2 - details missing [Reconstructed: location_name]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='location_name', value='home_living_room', confidence=0.4, uncertainty=0.6, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239555),)",
  "confidence_score": 0.4,
  "uncertainty_score": 0.6,
  "temporal_coherence_score": 0.775,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_00002_00', 'FRAG_INC_00002_01', 'FRAG_INC_00002_02', 'FRAG_INC_00002_03', 'FRAG_INC_00002_04'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239555
}
[3] {
  "episode_id": "4004A8833118ABA5285ADCB310",
  "original_episode_id": "INC_00004",
  "summary": "Incomplete episode 4 - details missing [Reconstructed: participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='participants', value=['contact_2', 'contact_11'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239555),)",
  "confidence_score": 0.35,
  "uncertainty_score": 0.65,
  "temporal_coherence_score": 0.9,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_00004_00', 'FRAG_INC_00004_01', 'FRAG_INC_00004_02', 'FRAG_INC_00004_03'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239555
}
[4] {
  "episode_id": "6FC944D482214BEF47FAFDEAD6",
  "original_episode_id": "INC_00005",
  "summary": "Incomplete episode 5 - details missing [Reconstructed: location_name, participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='location_name', value='hospital', confidence=0.4, uncertainty=0.6, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239555), ReconstructedValue(attribute_name='participants', value=['contact_1', 'contact_9'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239555))",
  "confidence_score": 0.375,
  "uncertainty_score": 0.625,
  "temporal_coherence_score": 0.7,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_00005_00', 'FRAG_INC_00005_01', 'FRAG_INC_00005_02', 'FRAG_INC_00005_03'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239555
}
[5] {
  "episode_id": "EEA9A0D8E10E8EE0CEA7C3F34A",
  "original_episode_id": "INC_00006",
  "summary": "Incomplete episode 6 - details missing [Reconstructed: location_name]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='location_name', value='home_bedroom', confidence=0.4, uncertainty=0.6, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239555),)",
  "confidence_score": 0.4,
  "uncertainty_score": 0.6,
  "temporal_coherence_score": 0.85,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_00006_00', 'FRAG_INC_00006_01', 'FRAG_INC_00006_02', 'FRAG_INC_00006_03', 'FRAG_INC_00006_04'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239555
}
[6] {
  "episode_id": "D9929CE558D26E2CE5EC53E235",
  "original_episode_id": "INC_00007",
  "summary": "Incomplete episode 7 - details missing [Reconstructed: participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='participants', value=['contact_3', 'contact_8'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239555),)",
  "confidence_score": 0.35,
  "uncertainty_score": 0.65,
  "temporal_coherence_score": 0.7,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_00007_00', 'FRAG_INC_00007_01', 'FRAG_INC_00007_02', 'FRAG_INC_00007_03', 'FRAG_INC_00007_04'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239555
}
[7] {
  "episode_id": "DF26FB77A4E0FDBC6B75EA925F",
  "original_episode_id": "INC_00008",
  "summary": "Incomplete episode 8 - details missing [Reconstructed: participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='participants', value=['contact_8', 'contact_3'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239555),)",
  "confidence_score": 0.35,
  "uncertainty_score": 0.65,
  "temporal_coherence_score": 0.775,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_00008_00', 'FRAG_INC_00008_01', 'FRAG_INC_00008_02', 'FRAG_INC_00008_03', 'FRAG_INC_00008_04'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239555
}
[8] {
  "episode_id": "D353D44F9AF1392714A84EEDBE",
  "original_episode_id": "INC_00009",
  "summary": "Incomplete episode 9 - details missing [Reconstructed: participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='participants', value=['contact_11', 'contact_8'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239556),)",
  "confidence_score": 0.35,
  "uncertainty_score": 0.65,
  "temporal_coherence_score": 0.7,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_00009_00', 'FRAG_INC_00009_01', 'FRAG_INC_00009_02', 'FRAG_INC_00009_03', 'FRAG_INC_00009_04'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239556
}
[9] {
  "episode_id": "099D07B6D76A61BF77FEECCB41",
  "original_episode_id": "INC_00011",
  "summary": "Incomplete episode 11 - details missing [Reconstructed: participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='participants', value=['contact_7', 'contact_9'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239556),)",
  "confidence_score": 0.35,
  "uncertainty_score": 0.65,
  "temporal_coherence_score": 0.7,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_00011_00', 'FRAG_INC_00011_01', 'FRAG_INC_00011_02', 'FRAG_INC_00011_03'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239556
}
[10] {
  "episode_id": "956345718A6DF3F879D0646D4E",
  "original_episode_id": "INC_00012",
  "summary": "Incomplete episode 12 - details missing [Reconstructed: location_name, participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='location_name', value='home_bedroom', confidence=0.4, uncertainty=0.6, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239556), ReconstructedValue(attribute_name='participants', value=['contact_12', 'contact_2'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239556))",
  "confidence_score": 0.375,
  "uncertainty_score": 0.625,
  "temporal_coherence_score": 0.775,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_00012_00', 'FRAG_INC_00012_01', 'FRAG_INC_00012_02', 'FRAG_INC_00012_03', 'FRAG_INC_00012_04'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239556
}
```

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
| fragment_provenance_types |  |
| schema_matches | 0 |
| conflict_fragments | 0 |
| high_uncertainty_on_conflict | 0 |

### real_world ✅ PASSED

- Seed: 42
- Duration: 0.01s

#### CPN ✅

**Inputs:**

```json
{
  "episodes_count": 17,
  "episodes": [
    {
      "id": "EP_REAL_000",
      "summary": "Rushed breakfast before school. Sarah couldn't find her homework and everyone was stressed.",
      "emotional_valence": -0.4,
      "participants": [
        "self",
        "sarah",
        "tommy"
      ],
      "location": "home_kitchen",
      "activity": "morning_routine"
    },
    {
      "id": "EP_REAL_001",
      "summary": "Peaceful morning routine. Everyone got ready on time and had a nice family breakfast.",
      "emotional_valence": 0.7,
      "participants": [
        "self",
        "spouse",
        "sarah",
        "tommy"
      ],
      "location": "home_kitchen",
      "activity": "family_meal"
    },
    {
      "id": "EP_REAL_002",
      "summary": "Tommy had a stomach ache and didn't want to go to school. Had to stay home with him.",
      "emotional_valence": -0.3,
      "participants": [
        "self",
        "tommy"
      ],
      "location": "home_bedroom",
      "activity": "caregiving"
    },
    {
      "id": "EP_REAL_003",
      "summary": "Important work deadline conflicted with Sarah's school play. Felt guilty missing it.",
      "emotional_valence": -0.7,
      "participants": [
        "self"
      ],
      "location": "office",
      "activity": "work_conflict"
    },
    {
      "id": "EP_REAL_004",
      "summary": "Got a promotion at work. Family celebration dinner to share the good news.",
      "emotional_valence": 0.9,
      "participants": [
        "self",
        "spouse",
        "sarah",
        "tommy"
      ],
      "location": "restaurant",
      "activity": "celebration"
    },
    {
      "id": "EP_REAL_005",
      "summary": "Worked from home to help Tommy with his science fair project. Great bonding time.",
      "emotional_valence": 0.8,
      "participants": [
        "self",
        "tommy"
      ],
      "location": "home_office",
      "activity": "parenting"
    },
    {
      "id": "EP_REAL_006",
      "summary": "Sarah struggled with algebra homework. Spent two hours helping her understand fractions.",
      "emotional_valence": 0.4,
      "participants": [
        "self",
        "sarah"
      ],
      "location": "home_study",
      "activity": "homework_help"
    },
    {
      "id": "EP_REAL_007",
      "summary": "Parent-teacher conference revealed Tommy is falling behind in reading. Need intervention plan.",
      "emotional_valence": -0.5,
      "participants": [
        "self",
        "spouse"
      ],
      "location": "school",
      "activity": "school_meeting"
    }
  ],
  "kg_edges_count": 14,
  "kg_edges": [
    {
      "source": "ENT_WORK_MEETING",
      "target": "ENT_MISSED_EVENT",
      "relation": "CAUSES",
      "weight": 0.8
    },
    {
      "source": "ENT_MISSED_EVENT",
      "target": "ENT_GUILT",
      "relation": "CAUSES",
      "weight": 0.85
    },
    {
      "source": "ENT_GUILT",
      "target": "ENT_STRESS",
      "relation": "CAUSES",
      "weight": 0.7
    },
    {
      "source": "ENT_STRESS",
      "target": "ENT_FRUSTRATION",
      "relation": "CAUSES",
      "weight": 0.65
    },
    {
      "source": "ENT_HOMEWORK",
      "target": "ENT_LEARNING",
      "relation": "CAUSES",
      "weight": 0.9
    },
    {
      "source": "ENT_LEARNING",
      "target": "ENT_ACHIEVEMENT",
      "relation": "CAUSES",
      "weight": 0.8
    },
    {
      "source": "ENT_ACHIEVEMENT",
      "target": "ENT_PRIDE",
      "relation": "CAUSES",
      "weight": 0.9
    },
    {
      "source": "ENT_BUDGET",
      "target": "ENT_STRESS",
      "relation": "CAUSES",
      "weight": 0.7
    },
    {
      "source": "ENT_STRESS",
      "target": "ENT_ARGUMENT",
      "relation": "CAUSES",
      "weight": 0.6
    },
    {
      "source": "ENT_ARGUMENT",
      "target": "ENT_APOLOGY",
      "relation": "CAUSES",
      "weight": 0.5
    }
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "scenario_id": "cf_542f42798e6bb633",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "EP_REAL_001",
  "intervention_node_id": "ENT_DINNER",
  "perturbation_target": "ENT_DINNER",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_DINNER had also gone wrong, outcome would be worse",
  "original_sentiment": 0.7,
  "predicted_sentiment": 0.1380054577781148,
  "plausibility": 0.5,
  "success_probability": 0.10950136444452871,
  "utility_delta": -0.5619945422218852,
  "mitigation": null,
  "causal_path_length": 1,
  "created_at_ms": 1768235239560
}
[2] {
  "scenario_id": "cf_fc20346e3a910b03",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "EP_REAL_010",
  "intervention_node_id": "ENT_MOVIES",
  "perturbation_target": "ENT_MOVIES",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_MOVIES had also gone wrong, outcome would be worse",
  "original_sentiment": 0.75,
  "predicted_sentiment": 0.22339896893491162,
  "plausibility": 1.0,
  "success_probability": 0.2366994844674558,
  "utility_delta": -0.5266010310650884,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239560
}
[3] {
  "scenario_id": "cf_33acc3b94009899f",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "EP_REAL_010",
  "intervention_node_id": "ENT_RELAXATION",
  "perturbation_target": "ENT_RELAXATION",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_RELAXATION had also gone wrong, outcome would be worse",
  "original_sentiment": 0.75,
  "predicted_sentiment": 0.2259056296224432,
  "plausibility": 1.0,
  "success_probability": 0.2379528148112216,
  "utility_delta": -0.5240943703775568,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239560
}
[4] {
  "scenario_id": "cf_1e7e4ff19e051d23",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "EP_REAL_014",
  "intervention_node_id": "ENT_APOLOGY",
  "perturbation_target": "ENT_APOLOGY",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_APOLOGY had also gone wrong, outcome would be worse",
  "original_sentiment": 0.6,
  "predicted_sentiment": 0.08342632804996586,
  "plausibility": 1.0,
  "success_probability": 0.24171316402498294,
  "utility_delta": -0.5165736719500341,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239561
}
[5] {
  "scenario_id": "cf_ccfe83f4ed3db147",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "EP_REAL_011",
  "intervention_node_id": "ENT_COOKING",
  "perturbation_target": "ENT_COOKING",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_COOKING had also gone wrong, outcome would be worse",
  "original_sentiment": 0.8,
  "predicted_sentiment": 0.28734518630495653,
  "plausibility": 1.0,
  "success_probability": 0.24367259315247825,
  "utility_delta": -0.5126548136950435,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239560
}
[6] {
  "scenario_id": "cf_f9d1e927e6549c6e",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "EP_REAL_014",
  "intervention_node_id": "ENT_GUILT",
  "perturbation_target": "ENT_GUILT",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_GUILT had also gone wrong, outcome would be worse",
  "original_sentiment": 0.6,
  "predicted_sentiment": 0.11968317613468948,
  "plausibility": 0.5,
  "success_probability": 0.12992079403367238,
  "utility_delta": -0.4803168238653105,
  "mitigation": null,
  "causal_path_length": 3,
  "created_at_ms": 1768235239561
}
[7] {
  "scenario_id": "cf_6a3cd22d5d5af7cf",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "EP_REAL_008",
  "intervention_node_id": "ENT_SPELLING_BEE",
  "perturbation_target": "ENT_SPELLING_BEE",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_SPELLING_BEE had also gone wrong, outcome would be worse",
  "original_sentiment": 0.95,
  "predicted_sentiment": 0.4819084061979036,
  "plausibility": 1.0,
  "success_probability": 0.2659542030989518,
  "utility_delta": -0.46809159380209636,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239560
}
[8] {
  "scenario_id": "cf_81f2a21d23d449a8",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "EP_REAL_012",
  "intervention_node_id": "ENT_FINANCES",
  "perturbation_target": "ENT_FINANCES",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_FINANCES had been different, outcome would be better",
  "original_sentiment": -0.65,
  "predicted_sentiment": -0.19779872753350602,
  "plausibility": 1.0,
  "success_probability": 0.7261006362332469,
  "utility_delta": 0.452201272466494,
  "mitigation": "Next time, consider changing ENT_FINANCES earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239560
}
[9] {
  "scenario_id": "cf_3b00afd80a10a8a9",
  "scenario_type": "ScenarioType.DOWNWARD",
  "base_episode_id": "EP_REAL_009",
  "intervention_node_id": "ENT_FAMILY_FUN",
  "perturbation_target": "ENT_FAMILY_FUN",
  "original_outcome": "Positive outcome",
  "counterfactual_outcome": "If action at ENT_FAMILY_FUN had also gone wrong, outcome would be worse",
  "original_sentiment": 0.85,
  "predicted_sentiment": 0.4016974729792719,
  "plausibility": 1.0,
  "success_probability": 0.2758487364896359,
  "utility_delta": -0.4483025270207281,
  "mitigation": null,
  "causal_path_length": 0,
  "created_at_ms": 1768235239560
}
[10] {
  "scenario_id": "cf_aeebc360f89f7a44",
  "scenario_type": "ScenarioType.UPWARD",
  "base_episode_id": "EP_REAL_003",
  "intervention_node_id": "ENT_SCHOOL_PLAY",
  "perturbation_target": "ENT_SCHOOL_PLAY",
  "original_outcome": "Negative outcome",
  "counterfactual_outcome": "If action at ENT_SCHOOL_PLAY had been different, outcome would be better",
  "original_sentiment": -0.7,
  "predicted_sentiment": -0.2556321593921711,
  "plausibility": 1.0,
  "success_probability": 0.7221839203039144,
  "utility_delta": 0.44436784060782886,
  "mitigation": "Next time, consider changing ENT_SCHOOL_PLAY earlier",
  "causal_path_length": 0,
  "created_at_ms": 1768235239560
}
```

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
| scenario_types | ScenarioType.SEMIFACTUAL, ScenarioType.UPWARD, ScenarioType.DOWNWARD |
| scenario_type_count | 3 |

#### MCTS ✅

**Inputs:**

```json
{
  "initial_state": {
    "time_of_day": "afternoon",
    "day": "Saturday",
    "family_mood": "neutral",
    "spouse_mood": "slightly_frustrated",
    "energy_level": "0.7",
    "pending_tasks": "['grocery_shopping', 'homework_help', 'laundry']",
    "relationship_debt": "0.2",
    "time_budget_hours": "5.0",
    "kids_homework_done": "False",
    "pantry_stocked": "False"
  },
  "actions_count": 10,
  "actions_sample": [
    "RealWorldAction(action_id='ACT_PARK', name='Take kids to the park', duration_hours=2.0, goal_alignment=0.9, expected_reward=0.85, preconditions=[], effects={'family_mood': 0.3, 'energy': -0.2})",
    "RealWorldAction(action_id='ACT_HOMEWORK', name='Help with homework', duration_hours=1.0, goal_alignment=0.8, expected_reward=0.7, preconditions=[], effects={'education_progress': 0.2})",
    "RealWorldAction(action_id='ACT_GROCERY', name='Go grocery shopping', duration_hours=1.0, goal_alignment=0.3, expected_reward=0.35, preconditions=[], effects={'pantry_stocked': True})",
    "RealWorldAction(action_id='ACT_FAMILY_GROCERY', name='Family grocery trip', duration_hours=1.5, goal_alignment=0.6, expected_reward=0.55, preconditions=[], effects={'pantry_stocked': True, 'family_time': 0.1})",
    "RealWorldAction(action_id='ACT_EXERCISE', name='Morning exercise', duration_hours=1.0, goal_alignment=0.6, expected_reward=0.65, preconditions=[], effects={'energy': 0.2, 'stress': -0.1})"
  ],
  "goals": [
    "RealWorldGoal(goal_id='GOAL_PRESENT', description='Be more present with family', priority=0.95, target_value=1.0)",
    "RealWorldGoal(goal_id='GOAL_EDUCATION', description=\"Support kids' education\", priority=0.9, target_value=1.0)",
    "RealWorldGoal(goal_id='GOAL_BALANCE', description='Improve work-life balance', priority=0.85, target_value=1.0)"
  ]
}
```

**Outputs (10 shown):**

```json
[1] {
  "scenario_id": "C5540DDED4AD5439E123C2E9F9",
  "action_sequence": "('ACT_PARK',)",
  "predicted_outcome": "Action ACT_PARK outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239562
}
[2] {
  "scenario_id": "01754AF1E3218B5AE228A683A0",
  "action_sequence": "('ACT_HOMEWORK',)",
  "predicted_outcome": "Action ACT_HOMEWORK outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239562
}
[3] {
  "scenario_id": "32C88A7741B498FB876CF658BF",
  "action_sequence": "('ACT_GROCERY',)",
  "predicted_outcome": "Action ACT_GROCERY outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239562
}
[4] {
  "scenario_id": "890D71EB93883FC15820FDB711",
  "action_sequence": "('ACT_FAMILY_GROCERY',)",
  "predicted_outcome": "Action ACT_FAMILY_GROCERY outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239562
}
[5] {
  "scenario_id": "A17D9BC39C3DD040E440266D48",
  "action_sequence": "('ACT_EXERCISE',)",
  "predicted_outcome": "Action ACT_EXERCISE outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239562
}
[6] {
  "scenario_id": "69B873B9DC48C06E722E8044A0",
  "action_sequence": "('ACT_MOVIE',)",
  "predicted_outcome": "Action ACT_MOVIE outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239562
}
[7] {
  "scenario_id": "2D45925C823FC624FFDE83F491",
  "action_sequence": "('ACT_COOK',)",
  "predicted_outcome": "Action ACT_COOK outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239562
}
[8] {
  "scenario_id": "5DBEA219A647B9D0F98DBB3699",
  "action_sequence": "('ACT_APOLOGIZE',)",
  "predicted_outcome": "Action ACT_APOLOGIZE outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239562
}
[9] {
  "scenario_id": "4E2CE5115967C4AF97D88BFB30",
  "action_sequence": "('ACT_QUALITY_TIME',)",
  "predicted_outcome": "Action ACT_QUALITY_TIME outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239562
}
[10] {
  "scenario_id": "BA268B787C5CA45D918AE92F93",
  "action_sequence": "('ACT_READ_STORY',)",
  "predicted_outcome": "Action ACT_READ_STORY outcome",
  "success_probability": 0.1,
  "expected_reward": 0.0,
  "plausibility": 0.9090909090909091,
  "visit_count": 2,
  "depth": 1,
  "created_at_ms": 1768235239562
}
```

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

**Inputs:**

```json
{
  "entities_count": 29,
  "entities_sample": [
    {
      "id": "ENT_SELF",
      "category": "family"
    },
    {
      "id": "ENT_SPOUSE",
      "category": "family"
    },
    {
      "id": "ENT_SARAH",
      "category": "family"
    },
    {
      "id": "ENT_TOMMY",
      "category": "family"
    },
    {
      "id": "ENT_GRANDMA",
      "category": "family"
    }
  ],
  "semantic_edges_count": 18,
  "semantic_edges_sample": [
    [
      "ENT_SELF",
      "ENT_SPOUSE",
      1.0
    ],
    [
      "ENT_SELF",
      "ENT_SARAH",
      0.95
    ],
    [
      "ENT_SELF",
      "ENT_TOMMY",
      0.95
    ],
    [
      "ENT_SPOUSE",
      "ENT_SARAH",
      0.95
    ],
    [
      "ENT_SPOUSE",
      "ENT_TOMMY",
      0.95
    ]
  ]
}
```

**Outputs (7 shown):**

```json
[1] {
  "insight_id": "01KESGH24CJ1GGE8FQWFA7HDYD",
  "source_entity_id": "ENT_HOMEWORK",
  "target_entity_id": "ENT_SARAH",
  "source_entity_name": "Homework",
  "target_entity_name": "Sarah (12yo)",
  "semantic_distance": 0.6598026214205523,
  "pmi_score": 7.251538766995965,
  "novelty_score": 0.060564358073375915,
  "insight_text": "Discovered surprising connection between 'Homework' and 'Sarah (12yo)' (PMI: 7.25, distance: 0.66).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_HOMEWORK', 'ENT_SARAH')",
  "supporting_evidence": "('ENT_HOMEWORK', 'ENT_SARAH')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239564
}
[2] {
  "insight_id": "01KESGH24DMYPVMQF72WQ01CER",
  "source_entity_id": "ENT_VIDEO_GAMES",
  "target_entity_id": "ENT_TOMMY",
  "source_entity_name": "Video Games",
  "target_entity_name": "Tommy (8yo)",
  "semantic_distance": 0.6973432861562163,
  "pmi_score": 7.643856189774724,
  "novelty_score": 0.057316040798742376,
  "insight_text": "Discovered surprising connection between 'Video Games' and 'Tommy (8yo)' (PMI: 7.64, distance: 0.70).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_VIDEO_GAMES', 'ENT_HAPPINESS', 'ENT_VIDEO_GAMES', 'ENT_TOMMY')",
  "supporting_evidence": "('ENT_VIDEO_GAMES', 'ENT_TOMMY')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239565
}
[3] {
  "insight_id": "01KESGH24DGA33HW6TE9SZ27M4",
  "source_entity_id": "ENT_VIDEO_GAMES",
  "target_entity_id": "ENT_HAPPINESS",
  "source_entity_name": "Video Games",
  "target_entity_name": "Happiness",
  "semantic_distance": 0.37691131217873886,
  "pmi_score": 7.321928094887363,
  "novelty_score": 0.028160382917575198,
  "insight_text": "Discovered surprising connection between 'Video Games' and 'Happiness' (PMI: 7.32, distance: 0.38).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_VIDEO_GAMES', 'ENT_HAPPINESS')",
  "supporting_evidence": "('ENT_VIDEO_GAMES', 'ENT_HAPPINESS')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239565
}
[4] {
  "insight_id": "01KESGH24C1Q12SSNRMXZ4T6VH",
  "source_entity_id": "ENT_HOMEWORK",
  "target_entity_id": "ENT_STRESS",
  "source_entity_name": "Homework",
  "target_entity_name": "Stress",
  "semantic_distance": 0.4045106586229401,
  "pmi_score": 6.836501267717121,
  "novelty_score": 0.025370987435603832,
  "insight_text": "Discovered surprising connection between 'Homework' and 'Stress' (PMI: 6.84, distance: 0.40).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_HOMEWORK', 'ENT_SARAH', 'ENT_HOMEWORK', 'ENT_STRESS')",
  "supporting_evidence": "('ENT_HOMEWORK', 'ENT_STRESS')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239564
}
[5] {
  "insight_id": "01KESGH24BSR1DJW0JQ8Y7T6F3",
  "source_entity_id": "ENT_SELF",
  "target_entity_id": "ENT_SPOUSE",
  "source_entity_name": "Parent",
  "target_entity_name": "Spouse",
  "semantic_distance": 0.19902903167166508,
  "pmi_score": 6.321928094887363,
  "novelty_score": 0.019357649646512712,
  "insight_text": "Discovered surprising connection between 'Parent' and 'Spouse' (PMI: 6.32, distance: 0.20).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_SELF', 'ENT_SPOUSE')",
  "supporting_evidence": "('ENT_SELF', 'ENT_SPOUSE')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239563
}
[6] {
  "insight_id": "01KESGH24B66QB5570NMQ4FDEQ",
  "source_entity_id": "ENT_SELF",
  "target_entity_id": "ENT_SARAH",
  "source_entity_name": "Parent",
  "target_entity_name": "Sarah (12yo)",
  "semantic_distance": 0.1754093263582145,
  "pmi_score": 6.984893107609792,
  "novelty_score": 0.013613504385444099,
  "insight_text": "Discovered surprising connection between 'Parent' and 'Sarah (12yo)' (PMI: 6.98, distance: 0.18).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_SELF', 'ENT_SPOUSE', 'ENT_SARAH')",
  "supporting_evidence": "('ENT_SELF', 'ENT_SARAH')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239563
}
[7] {
  "insight_id": "01KESGH24BXHCJX35JC84RW24Q",
  "source_entity_id": "ENT_SELF",
  "target_entity_id": "ENT_TOMMY",
  "source_entity_name": "Parent",
  "target_entity_name": "Tommy (8yo)",
  "semantic_distance": 0.15864759784207783,
  "pmi_score": 6.984893107609792,
  "novelty_score": 0.011664594870589257,
  "insight_text": "Discovered surprising connection between 'Parent' and 'Tommy (8yo)' (PMI: 6.98, distance: 0.16).",
  "category": "InsightCategory.ANOMALY",
  "connection_type": "ConnectionType.SEMANTIC",
  "connection_path": "('ENT_SELF', 'ENT_TOMMY')",
  "supporting_evidence": "('ENT_SELF', 'ENT_TOMMY')",
  "confidence": 0.95,
  "relevance_score": 0.6,
  "actionability_score": 0.6,
  "created_at_ms": 1768235239563
}
```

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

**Inputs:**

```json
{
  "incomplete_episodes_count": 3,
  "incomplete_episodes": [
    {
      "id": "INC_REAL_001",
      "summary": "Something happened with Sarah this morning... can't quite remember the details",
      "location": null,
      "participants": [
        "sarah"
      ],
      "activity": null,
      "ambiguity": 0.7
    },
    {
      "id": "INC_REAL_002",
      "summary": "There was a conversation with spouse about something important...",
      "location": "home",
      "participants": null,
      "activity": "discussion",
      "ambiguity": 0.6
    },
    {
      "id": "INC_REAL_003",
      "summary": "Tommy said something that made me laugh...",
      "location": null,
      "participants": [
        "tommy"
      ],
      "activity": null,
      "ambiguity": 0.8
    }
  ],
  "fragments_count": 9,
  "fragments": [
    {
      "id": "FRAG_INC_REAL_001_00",
      "content": "Photo shows family at dinner table",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_REAL_001_01",
      "content": "Voice memo: 'Don't forget Tommy's doctor appointment'",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_REAL_001_02",
      "content": "Calendar showed school event at 9am",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_REAL_002_00",
      "content": "Text from spouse: 'Remember to pick up milk'",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_REAL_002_01",
      "content": "Probably had breakfast around 7am",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_REAL_002_02",
      "content": "Heard kids laughing in the backyard",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_REAL_003_00",
      "content": "Heard kids laughing in the backyard",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_REAL_003_01",
      "content": "Voice memo: 'Don't forget Tommy's doctor appointment'",
      "provenance_type": null,
      "confidence": null
    },
    {
      "id": "FRAG_INC_REAL_003_02",
      "content": "Photo shows family at dinner table",
      "provenance_type": null,
      "confidence": null
    }
  ],
  "schemas_count": 4,
  "context_keys": [
    "time_of_day",
    "day",
    "nearby_locations",
    "known_locations",
    "frequent_contacts",
    "typical_weekday_activities"
  ]
}
```

**Outputs (3 shown):**

```json
[1] {
  "episode_id": "5EEEAB81D545065D0106C2E42C",
  "original_episode_id": "INC_REAL_001",
  "summary": "Something happened with Sarah this morning... can't quite remember the details [Reconstructed: location_name]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='location_name', value='home_bedroom', confidence=0.4, uncertainty=0.6, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239566),)",
  "confidence_score": 0.4,
  "uncertainty_score": 0.6,
  "temporal_coherence_score": 0.85,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_REAL_001_00', 'FRAG_INC_REAL_001_01', 'FRAG_INC_REAL_001_02'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239566
}
[2] {
  "episode_id": "97D4A3B7A9E36161090FF878B2",
  "original_episode_id": "INC_REAL_002",
  "summary": "There was a conversation with spouse about something important... [Reconstructed: participants]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='participants', value=['tommy', 'spouse'], confidence=0.35, uncertainty=0.65, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239566),)",
  "confidence_score": 0.35,
  "uncertainty_score": 0.65,
  "temporal_coherence_score": 0.7,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_REAL_002_00', 'FRAG_INC_REAL_002_01', 'FRAG_INC_REAL_002_02'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239566
}
[3] {
  "episode_id": "F51D7DABDA31F29FC7D66A7620",
  "original_episode_id": "INC_REAL_003",
  "summary": "Tommy said something that made me laugh... [Reconstructed: location_name]",
  "reconstructed_fields": "(ReconstructedValue(attribute_name='location_name', value='home_bedroom', confidence=0.4, uncertainty=0.6, provenance=<ReconstructionProvenance.CONTEXT_PROPAGATION: 'context_propagation'>, schema_id=None, created_at_ms=1768235239566),)",
  "confidence_score": 0.4,
  "uncertainty_score": 0.6,
  "temporal_coherence_score": 0.7,
  "provenance": "{'algorithm': 'SPC-UQ', 'source_fragments': ['FRAG_INC_REAL_003_00', 'FRAG_INC_REAL_003_01', 'FRAG_INC_REAL_003_02'], 'schema_id': None, 'simulation_count': 50, 'rng_seed': 42, 'provenance_types_used': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'reconstruction_provenance': ['ReconstructionProvenance.CONTEXT_PROPAGATION'], 'conflicts_detected': 0, 'conflict_details': []}",
  "is_canonical": false,
  "created_at_ms": 1768235239566
}
```

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
| fragment_provenance_types |  |
| schema_matches | 0 |
| conflict_fragments | 0 |
| high_uncertainty_on_conflict | 0 |
