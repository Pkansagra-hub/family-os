# R5 Dream Phase Algorithms - Full I/O Results

**Generated:** 2026-01-12 10:22:08

---

## Summary

| Algorithm | Status | Outputs |
|-----------|--------|--------:|
| CPN | ✅ OK | 43 |
| MCTS | ✅ OK | 6 |
| BGT-SM | ✅ OK | 1 |
| SPC-UQ | ✅ OK | 1 |

---

## 1. CPN (Causal Perturbation Network)

**Purpose:** Generate 'what-if' counterfactual scenarios from regretful events

**Total Counterfactuals Generated:** 43

### DOWNWARD Scenarios (16)

#### Counterfactual 1

- **Base Episode ID:** `01HWQR5X7KJMN3P4Q8R9S0T1V2`
- **Scenario ID:** `cf_f6050ad5b8450802`
- **Intervention Node:** `ENT_TOMMY`
- **Perturbation Target:** `ENT_TOMMY`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_TOMMY had also gone wrong, outcome would be worse
- **Original Sentiment:** +0.8000
- **Predicted Sentiment:** +0.2382
- **Plausibility:** 1.0000
- **Success Probability:** 0.2191
- **Utility Delta:** -0.5618
- **Causal Path Length:** 0

#### Counterfactual 2

- **Base Episode ID:** `01HWQR5XBOQRS7T8U2V3W4X5Z6`
- **Scenario ID:** `cf_d32d45f74acf3fb0`
- **Intervention Node:** `ENT_HOMEWORK`
- **Perturbation Target:** `ENT_HOMEWORK`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_HOMEWORK had also gone wrong, outcome would be worse
- **Original Sentiment:** +0.7000
- **Predicted Sentiment:** +0.2109
- **Plausibility:** 1.0000
- **Success Probability:** 0.2555
- **Utility Delta:** -0.4891
- **Causal Path Length:** 0

#### Counterfactual 3

- **Base Episode ID:** `01HWQR5X9MLOP5R6S0T1U2V3X4`
- **Scenario ID:** `cf_f7dd37d9ff9d836f`
- **Intervention Node:** `ENT_FAMILY_TIME`
- **Perturbation Target:** `ENT_FAMILY_TIME`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_FAMILY_TIME had also gone wrong, outcome would be worse
- **Original Sentiment:** +0.9000
- **Predicted Sentiment:** +0.4900
- **Plausibility:** 1.0000
- **Success Probability:** 0.2950
- **Utility Delta:** -0.4100
- **Causal Path Length:** 0

#### Counterfactual 4

- **Base Episode ID:** `01HWQR5XBOQRS7T8U2V3W4X5Z6`
- **Scenario ID:** `cf_45a72b56c66c738e`
- **Intervention Node:** `ENT_FRACTIONS`
- **Perturbation Target:** `ENT_FRACTIONS`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_FRACTIONS had also gone wrong, outcome would be worse
- **Original Sentiment:** +0.7000
- **Predicted Sentiment:** +0.3031
- **Plausibility:** 1.0000
- **Success Probability:** 0.3016
- **Utility Delta:** -0.3969
- **Causal Path Length:** 0

#### Counterfactual 5

- **Base Episode ID:** `01HWQR5X7KJMN3P4Q8R9S0T1V2`
- **Scenario ID:** `cf_0b8fefb3c521ac77`
- **Intervention Node:** `ENT_BREAKFAST`
- **Perturbation Target:** `ENT_BREAKFAST`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_BREAKFAST had also gone wrong, outcome would be worse
- **Original Sentiment:** +0.8000
- **Predicted Sentiment:** +0.4336
- **Plausibility:** 1.0000
- **Success Probability:** 0.3168
- **Utility Delta:** -0.3664
- **Causal Path Length:** 0

#### Counterfactual 6

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_cdb9d0d7d03d5f40`
- **Intervention Node:** `ENT_BUDGET`
- **Perturbation Target:** `ENT_BUDGET`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_BUDGET had also gone wrong, outcome would be worse
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -1.0000
- **Plausibility:** 1.0000
- **Success Probability:** 0.3250
- **Utility Delta:** -0.3500
- **Causal Path Length:** 0

#### Counterfactual 7

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_649643b0ff753af1`
- **Intervention Node:** `ENT_STRESS`
- **Perturbation Target:** `ENT_STRESS`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_STRESS had also gone wrong, outcome would be worse
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -1.0000
- **Plausibility:** 1.0000
- **Success Probability:** 0.3250
- **Utility Delta:** -0.3500
- **Causal Path Length:** 0

#### Counterfactual 8

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_b7c942307ae133d0`
- **Intervention Node:** `ENT_WORK_MEETING`
- **Perturbation Target:** `ENT_WORK_MEETING`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_WORK_MEETING had also gone wrong, outcome would be worse
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -1.0000
- **Plausibility:** 0.5000
- **Success Probability:** 0.1625
- **Utility Delta:** -0.3500
- **Causal Path Length:** 1

#### Counterfactual 9

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_10c1908dcd6f3d98`
- **Intervention Node:** `ENT_SOCCER`
- **Perturbation Target:** `ENT_SOCCER`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_SOCCER had also gone wrong, outcome would be worse
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -1.0000
- **Plausibility:** 0.5000
- **Success Probability:** 0.1625
- **Utility Delta:** -0.3500
- **Causal Path Length:** 1

#### Counterfactual 10

- **Base Episode ID:** `01HWQR5XBOQRS7T8U2V3W4X5Z6`
- **Scenario ID:** `cf_ed4cbd5da0448a14`
- **Intervention Node:** `ENT_SARAH`
- **Perturbation Target:** `ENT_SARAH`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_SARAH had also gone wrong, outcome would be worse
- **Original Sentiment:** +0.7000
- **Predicted Sentiment:** +0.3542
- **Plausibility:** 1.0000
- **Success Probability:** 0.3271
- **Utility Delta:** -0.3458
- **Causal Path Length:** 0

#### Counterfactual 11

- **Base Episode ID:** `01HWQR5X9MLOP5R6S0T1U2V3X4`
- **Scenario ID:** `cf_3707c9b044ffd9b9`
- **Intervention Node:** `ENT_MOVIE`
- **Perturbation Target:** `ENT_MOVIE`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_MOVIE had also gone wrong, outcome would be worse
- **Original Sentiment:** +0.9000
- **Predicted Sentiment:** +0.5772
- **Plausibility:** 1.0000
- **Success Probability:** 0.3386
- **Utility Delta:** -0.3228
- **Causal Path Length:** 0

#### Counterfactual 12

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_91765805f40cc9d7`
- **Intervention Node:** `ENT_SPOUSE`
- **Perturbation Target:** `ENT_SPOUSE`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_SPOUSE had also gone wrong, outcome would be worse
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.9704
- **Plausibility:** 1.0000
- **Success Probability:** 0.3398
- **Utility Delta:** -0.3204
- **Causal Path Length:** 0

#### Counterfactual 13

- **Base Episode ID:** `01HWQR5X7KJMN3P4Q8R9S0T1V2`
- **Scenario ID:** `cf_fc1ace2b22d0a6e5`
- **Intervention Node:** `ENT_SARAH`
- **Perturbation Target:** `ENT_SARAH`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_SARAH had also gone wrong, outcome would be worse
- **Original Sentiment:** +0.8000
- **Predicted Sentiment:** +0.4859
- **Plausibility:** 1.0000
- **Success Probability:** 0.3430
- **Utility Delta:** -0.3141
- **Causal Path Length:** 0

#### Counterfactual 14

- **Base Episode ID:** `01HWQR5X8LKNO4Q5R9S0T1U2W3`
- **Scenario ID:** `cf_db8a4efc7233ef7d`
- **Intervention Node:** `ENT_WORK_MEETING`
- **Perturbation Target:** `ENT_WORK_MEETING`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_WORK_MEETING had also gone wrong, outcome would be worse
- **Original Sentiment:** -0.7000
- **Predicted Sentiment:** -1.0000
- **Plausibility:** 1.0000
- **Success Probability:** 0.3500
- **Utility Delta:** -0.3000
- **Causal Path Length:** 0

#### Counterfactual 15

- **Base Episode ID:** `01HWQR5X8LKNO4Q5R9S0T1U2W3`
- **Scenario ID:** `cf_ee713f5c3f786519`
- **Intervention Node:** `ENT_SOCCER`
- **Perturbation Target:** `ENT_SOCCER`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_SOCCER had also gone wrong, outcome would be worse
- **Original Sentiment:** -0.7000
- **Predicted Sentiment:** -1.0000
- **Plausibility:** 1.0000
- **Success Probability:** 0.3500
- **Utility Delta:** -0.3000
- **Causal Path Length:** 0

#### Counterfactual 16

- **Base Episode ID:** `01HWQR5X8LKNO4Q5R9S0T1U2W3`
- **Scenario ID:** `cf_78af1b68b249a61b`
- **Intervention Node:** `ENT_TOMMY`
- **Perturbation Target:** `ENT_TOMMY`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_TOMMY had also gone wrong, outcome would be worse
- **Original Sentiment:** -0.7000
- **Predicted Sentiment:** -1.0000
- **Plausibility:** 1.0000
- **Success Probability:** 0.3500
- **Utility Delta:** -0.3000
- **Causal Path Length:** 0

### UPWARD Scenarios (11)

#### Counterfactual 1

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_2e9f18647374b304`
- **Intervention Node:** `ENT_WORK_MEETING`
- **Perturbation Target:** `ENT_WORK_MEETING`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_WORK_MEETING had been different, outcome would be better
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.2168
- **Plausibility:** 0.5000
- **Success Probability:** 0.3583
- **Utility Delta:** +0.4332
- **Causal Path Length:** 1
- **Mitigation:** Next time, consider changing ENT_WORK_MEETING earlier

#### Counterfactual 2

- **Base Episode ID:** `01HWQR5X8LKNO4Q5R9S0T1U2W3`
- **Scenario ID:** `cf_169211515826c55a`
- **Intervention Node:** `ENT_TOMMY`
- **Perturbation Target:** `ENT_TOMMY`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_TOMMY had been different, outcome would be better
- **Original Sentiment:** -0.7000
- **Predicted Sentiment:** -0.3242
- **Plausibility:** 1.0000
- **Success Probability:** 0.6879
- **Utility Delta:** +0.3758
- **Causal Path Length:** 0
- **Mitigation:** Next time, consider changing ENT_TOMMY earlier

#### Counterfactual 3

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_f16edf10e8085d09`
- **Intervention Node:** `ENT_SPOUSE`
- **Perturbation Target:** `ENT_SPOUSE`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_SPOUSE had been different, outcome would be better
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.2810
- **Plausibility:** 1.0000
- **Success Probability:** 0.6845
- **Utility Delta:** +0.3690
- **Causal Path Length:** 0
- **Mitigation:** Next time, consider changing ENT_SPOUSE earlier

#### Counterfactual 4

- **Base Episode ID:** `01HWQR5X8LKNO4Q5R9S0T1U2W3`
- **Scenario ID:** `cf_7d4e3cdec9b261e8`
- **Intervention Node:** `ENT_SOCCER`
- **Perturbation Target:** `ENT_SOCCER`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_SOCCER had been different, outcome would be better
- **Original Sentiment:** -0.7000
- **Predicted Sentiment:** -0.3316
- **Plausibility:** 1.0000
- **Success Probability:** 0.6842
- **Utility Delta:** +0.3684
- **Causal Path Length:** 0
- **Mitigation:** Next time, consider changing ENT_SOCCER earlier

#### Counterfactual 5

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_e2411e4497f19cfc`
- **Intervention Node:** `ENT_SOCCER`
- **Perturbation Target:** `ENT_SOCCER`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_SOCCER had been different, outcome would be better
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.2908
- **Plausibility:** 0.5000
- **Success Probability:** 0.3398
- **Utility Delta:** +0.3592
- **Causal Path Length:** 1
- **Mitigation:** Next time, consider changing ENT_SOCCER earlier

#### Counterfactual 6

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_8c39e71e6e1cb3fa`
- **Intervention Node:** `ENT_STRESS`
- **Perturbation Target:** `ENT_STRESS`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_STRESS had been different, outcome would be better
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.3041
- **Plausibility:** 1.0000
- **Success Probability:** 0.6729
- **Utility Delta:** +0.3459
- **Causal Path Length:** 0
- **Mitigation:** Next time, consider changing ENT_STRESS earlier

#### Counterfactual 7

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_5e4a8988333b4743`
- **Intervention Node:** `ENT_BUDGET`
- **Perturbation Target:** `ENT_BUDGET`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_BUDGET had been different, outcome would be better
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.3336
- **Plausibility:** 1.0000
- **Success Probability:** 0.6582
- **Utility Delta:** +0.3164
- **Causal Path Length:** 0
- **Mitigation:** Next time, consider changing ENT_BUDGET earlier

#### Counterfactual 8

- **Base Episode ID:** `01HWQR5X8LKNO4Q5R9S0T1U2W3`
- **Scenario ID:** `cf_9140795e86e16186`
- **Intervention Node:** `ENT_WORK_MEETING`
- **Perturbation Target:** `ENT_WORK_MEETING`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** If action at ENT_WORK_MEETING had been different, outcome would be better
- **Original Sentiment:** -0.7000
- **Predicted Sentiment:** -0.3883
- **Plausibility:** 1.0000
- **Success Probability:** 0.6559
- **Utility Delta:** +0.3117
- **Causal Path Length:** 0
- **Mitigation:** Next time, consider changing ENT_WORK_MEETING earlier

#### Counterfactual 9

- **Base Episode ID:** `01HWQR5XBOQRS7T8U2V3W4X5Z6`
- **Scenario ID:** `cf_39c721c8ca5be171`
- **Intervention Node:** `ENT_HOMEWORK`
- **Perturbation Target:** `ENT_HOMEWORK`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_HOMEWORK had been different, outcome would be better
- **Original Sentiment:** +0.7000
- **Predicted Sentiment:** +1.0000
- **Plausibility:** 1.0000
- **Success Probability:** 0.6500
- **Utility Delta:** +0.3000
- **Causal Path Length:** 0
- **Mitigation:** Next time, consider changing ENT_HOMEWORK earlier

#### Counterfactual 10

- **Base Episode ID:** `01HWQR5XBOQRS7T8U2V3W4X5Z6`
- **Scenario ID:** `cf_8d64cef2ec972054`
- **Intervention Node:** `ENT_SARAH`
- **Perturbation Target:** `ENT_SARAH`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_SARAH had been different, outcome would be better
- **Original Sentiment:** +0.7000
- **Predicted Sentiment:** +1.0000
- **Plausibility:** 1.0000
- **Success Probability:** 0.6500
- **Utility Delta:** +0.3000
- **Causal Path Length:** 0
- **Mitigation:** Next time, consider changing ENT_SARAH earlier

#### Counterfactual 11

- **Base Episode ID:** `01HWQR5XBOQRS7T8U2V3W4X5Z6`
- **Scenario ID:** `cf_56f4fe2a3d7a158a`
- **Intervention Node:** `ENT_FRACTIONS`
- **Perturbation Target:** `ENT_FRACTIONS`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** If action at ENT_FRACTIONS had been different, outcome would be better
- **Original Sentiment:** +0.7000
- **Predicted Sentiment:** +1.0000
- **Plausibility:** 1.0000
- **Success Probability:** 0.6500
- **Utility Delta:** +0.3000
- **Causal Path Length:** 0
- **Mitigation:** Next time, consider changing ENT_FRACTIONS earlier

### SEMIFACTUAL Scenarios (16)

#### Counterfactual 1

- **Base Episode ID:** `01HWQR5X7KJMN3P4Q8R9S0T1V2`
- **Scenario ID:** `cf_2382d0ed4643fd47`
- **Intervention Node:** `ENT_BREAKFAST`
- **Perturbation Target:** `ENT_BREAKFAST`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** Even if action at ENT_BREAKFAST changed, outcome would be similar
- **Original Sentiment:** +0.8000
- **Predicted Sentiment:** +0.9021
- **Plausibility:** 1.0000
- **Success Probability:** 0.5510
- **Utility Delta:** +0.1021
- **Causal Path Length:** 0

#### Counterfactual 2

- **Base Episode ID:** `01HWQR5XBOQRS7T8U2V3W4X5Z6`
- **Scenario ID:** `cf_06a3211b6bdfec91`
- **Intervention Node:** `ENT_SARAH`
- **Perturbation Target:** `ENT_SARAH`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** Even if action at ENT_SARAH changed, outcome would be similar
- **Original Sentiment:** +0.7000
- **Predicted Sentiment:** +0.7412
- **Plausibility:** 1.0000
- **Success Probability:** 0.5206
- **Utility Delta:** +0.0412
- **Causal Path Length:** 0

#### Counterfactual 3

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_4ad0cadcd58f2488`
- **Intervention Node:** `ENT_BUDGET`
- **Perturbation Target:** `ENT_BUDGET`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** Even if action at ENT_BUDGET changed, outcome would be similar
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.6904
- **Plausibility:** 1.0000
- **Success Probability:** 0.4798
- **Utility Delta:** -0.0404
- **Causal Path Length:** 0

#### Counterfactual 4

- **Base Episode ID:** `01HWQR5X8LKNO4Q5R9S0T1U2W3`
- **Scenario ID:** `cf_d35675ca3d1e9a8b`
- **Intervention Node:** `ENT_SOCCER`
- **Perturbation Target:** `ENT_SOCCER`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** Even if action at ENT_SOCCER changed, outcome would be similar
- **Original Sentiment:** -0.7000
- **Predicted Sentiment:** -0.6598
- **Plausibility:** 1.0000
- **Success Probability:** 0.5201
- **Utility Delta:** +0.0402
- **Causal Path Length:** 0

#### Counterfactual 5

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_de590e8caa4b8845`
- **Intervention Node:** `ENT_SOCCER`
- **Perturbation Target:** `ENT_SOCCER`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** Even if action at ENT_SOCCER changed, outcome would be similar
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.6795
- **Plausibility:** 0.5000
- **Success Probability:** 0.2426
- **Utility Delta:** -0.0295
- **Causal Path Length:** 1

#### Counterfactual 6

- **Base Episode ID:** `01HWQR5X9MLOP5R6S0T1U2V3X4`
- **Scenario ID:** `cf_eb0f0451684f01ee`
- **Intervention Node:** `ENT_FAMILY_TIME`
- **Perturbation Target:** `ENT_FAMILY_TIME`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** Even if action at ENT_FAMILY_TIME changed, outcome would be similar
- **Original Sentiment:** +0.9000
- **Predicted Sentiment:** +0.9288
- **Plausibility:** 1.0000
- **Success Probability:** 0.5144
- **Utility Delta:** +0.0288
- **Causal Path Length:** 0

#### Counterfactual 7

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_11c5d6d48b5327b0`
- **Intervention Node:** `ENT_STRESS`
- **Perturbation Target:** `ENT_STRESS`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** Even if action at ENT_STRESS changed, outcome would be similar
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.6283
- **Plausibility:** 1.0000
- **Success Probability:** 0.5108
- **Utility Delta:** +0.0217
- **Causal Path Length:** 0

#### Counterfactual 8

- **Base Episode ID:** `01HWQR5XBOQRS7T8U2V3W4X5Z6`
- **Scenario ID:** `cf_aa9621f1df81e08d`
- **Intervention Node:** `ENT_HOMEWORK`
- **Perturbation Target:** `ENT_HOMEWORK`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** Even if action at ENT_HOMEWORK changed, outcome would be similar
- **Original Sentiment:** +0.7000
- **Predicted Sentiment:** +0.7207
- **Plausibility:** 1.0000
- **Success Probability:** 0.5104
- **Utility Delta:** +0.0207
- **Causal Path Length:** 0

#### Counterfactual 9

- **Base Episode ID:** `01HWQR5X7KJMN3P4Q8R9S0T1V2`
- **Scenario ID:** `cf_8a2c61cd1a2baf2e`
- **Intervention Node:** `ENT_TOMMY`
- **Perturbation Target:** `ENT_TOMMY`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** Even if action at ENT_TOMMY changed, outcome would be similar
- **Original Sentiment:** +0.8000
- **Predicted Sentiment:** +0.7855
- **Plausibility:** 1.0000
- **Success Probability:** 0.4927
- **Utility Delta:** -0.0145
- **Causal Path Length:** 0

#### Counterfactual 10

- **Base Episode ID:** `01HWQR5X9MLOP5R6S0T1U2V3X4`
- **Scenario ID:** `cf_c1bd311bba53d4e8`
- **Intervention Node:** `ENT_MOVIE`
- **Perturbation Target:** `ENT_MOVIE`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** Even if action at ENT_MOVIE changed, outcome would be similar
- **Original Sentiment:** +0.9000
- **Predicted Sentiment:** +0.9113
- **Plausibility:** 1.0000
- **Success Probability:** 0.5057
- **Utility Delta:** +0.0113
- **Causal Path Length:** 0

#### Counterfactual 11

- **Base Episode ID:** `01HWQR5X7KJMN3P4Q8R9S0T1V2`
- **Scenario ID:** `cf_74ac8f543d83249c`
- **Intervention Node:** `ENT_SARAH`
- **Perturbation Target:** `ENT_SARAH`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** Even if action at ENT_SARAH changed, outcome would be similar
- **Original Sentiment:** +0.8000
- **Predicted Sentiment:** +0.7904
- **Plausibility:** 1.0000
- **Success Probability:** 0.4952
- **Utility Delta:** -0.0096
- **Causal Path Length:** 0

#### Counterfactual 12

- **Base Episode ID:** `01HWQR5XBOQRS7T8U2V3W4X5Z6`
- **Scenario ID:** `cf_caf81ef91c5d7dad`
- **Intervention Node:** `ENT_FRACTIONS`
- **Perturbation Target:** `ENT_FRACTIONS`
- **Original Outcome:** Positive outcome
- **Counterfactual Outcome:** Even if action at ENT_FRACTIONS changed, outcome would be similar
- **Original Sentiment:** +0.7000
- **Predicted Sentiment:** +0.6912
- **Plausibility:** 1.0000
- **Success Probability:** 0.4956
- **Utility Delta:** -0.0088
- **Causal Path Length:** 0

#### Counterfactual 13

- **Base Episode ID:** `01HWQR5X8LKNO4Q5R9S0T1U2W3`
- **Scenario ID:** `cf_539e4023f2e4bb05`
- **Intervention Node:** `ENT_TOMMY`
- **Perturbation Target:** `ENT_TOMMY`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** Even if action at ENT_TOMMY changed, outcome would be similar
- **Original Sentiment:** -0.7000
- **Predicted Sentiment:** -0.7032
- **Plausibility:** 1.0000
- **Success Probability:** 0.4984
- **Utility Delta:** -0.0032
- **Causal Path Length:** 0

#### Counterfactual 14

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_d4ec86218e3c49e2`
- **Intervention Node:** `ENT_WORK_MEETING`
- **Perturbation Target:** `ENT_WORK_MEETING`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** Even if action at ENT_WORK_MEETING changed, outcome would be similar
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.6523
- **Plausibility:** 0.5000
- **Success Probability:** 0.2494
- **Utility Delta:** -0.0023
- **Causal Path Length:** 1

#### Counterfactual 15

- **Base Episode ID:** `01HWQR5X8LKNO4Q5R9S0T1U2W3`
- **Scenario ID:** `cf_82b7ee64f230fc21`
- **Intervention Node:** `ENT_WORK_MEETING`
- **Perturbation Target:** `ENT_WORK_MEETING`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** Even if action at ENT_WORK_MEETING changed, outcome would be similar
- **Original Sentiment:** -0.7000
- **Predicted Sentiment:** -0.7023
- **Plausibility:** 1.0000
- **Success Probability:** 0.4989
- **Utility Delta:** -0.0023
- **Causal Path Length:** 0

#### Counterfactual 16

- **Base Episode ID:** `01HWQR5XANMPQ6S7T1U2V3W4Y5`
- **Scenario ID:** `cf_4bc47278ea6f7151`
- **Intervention Node:** `ENT_SPOUSE`
- **Perturbation Target:** `ENT_SPOUSE`
- **Original Outcome:** Negative outcome
- **Counterfactual Outcome:** Even if action at ENT_SPOUSE changed, outcome would be similar
- **Original Sentiment:** -0.6500
- **Predicted Sentiment:** -0.6485
- **Plausibility:** 1.0000
- **Success Probability:** 0.5007
- **Utility Delta:** +0.0015
- **Causal Path Length:** 0

---

## 2. TPN-MCTS (Temporal Projection MCTS)

**Purpose:** Simulate future scenarios via Monte Carlo tree search

**Total Scenarios Generated:** 6

### Scenario 1

- **Scenario ID:** `98F08F77A89BCF99ED60F3376A`
- **Expected Reward:** 0.000000
- **Visit Count:** 4
- **Success Probability:** 0.200000
- **Plausibility:** 0.909091
- **Action Sequence:** `('ACT001',)`

### Scenario 2

- **Scenario ID:** `70204559073A4FCAEA8C4828E1`
- **Expected Reward:** 0.000000
- **Visit Count:** 4
- **Success Probability:** 0.200000
- **Plausibility:** 0.909091
- **Action Sequence:** `('ACT002',)`

### Scenario 3

- **Scenario ID:** `510E6BCF6BCECAF0AB886DA6DC`
- **Expected Reward:** 0.000000
- **Visit Count:** 3
- **Success Probability:** 0.150000
- **Plausibility:** 0.909091
- **Action Sequence:** `('ACT003',)`

### Scenario 4

- **Scenario ID:** `730B639B622534791E45CE795E`
- **Expected Reward:** 0.000000
- **Visit Count:** 3
- **Success Probability:** 0.150000
- **Plausibility:** 0.909091
- **Action Sequence:** `('ACT004',)`

### Scenario 5

- **Scenario ID:** `2AE337FA4CD2D69A94F17E7F7A`
- **Expected Reward:** 0.000000
- **Visit Count:** 3
- **Success Probability:** 0.150000
- **Plausibility:** 0.909091
- **Action Sequence:** `('ACT005',)`

### Scenario 6

- **Scenario ID:** `ECFDC072C76EAF4F25698633A6`
- **Expected Reward:** 0.000000
- **Visit Count:** 3
- **Success Probability:** 0.150000
- **Plausibility:** 0.909091
- **Action Sequence:** `('ACT006',)`

---

## 3. BGT-SM (Bisociative Graph Traversal)

**Purpose:** Discover unexpected connections between distant concepts

**Total Insights Discovered:** 1

| # | Source | Target | Novelty | PMI | Semantic Distance |
|--:|--------|--------|--------:|----:|------------------:|
| 1 | ENT001 | ENT004 | 0.8135 | 7.3219 | 1.0000 |

### Detailed Insights

#### Insight 1

- **Source Entity:** `ENT001`
- **Target Entity:** `ENT004`
- **Insight Text:** Discovered surprising connection between 'Sarah' and 'homework' (PMI: 7.32, distance: 1.00).
- **Novelty Score:** 0.813548
- **PMI Score:** 7.321928
- **Semantic Distance:** 1.000000

---

## 4. SPC-UQ (Episodic Simulation with Uncertainty)

**Purpose:** Reconstruct incomplete episodic memories with confidence bounds

**Note:** All reconstructions are NON-CANONICAL (never treated as ground truth)

**Total Reconstructions:** 1

### Reconstruction 1

- **New Episode ID:** `B8771F5DFB769ACE5ECD80B4E0`
- **Original Episode ID:** `01INCOMPLETE00000000000001`
- **Summary:** Something happened with Sarah in the morning... can't quite remember [Reconstructed: location_name, participants]
- **Confidence Score:** 0.375000
- **Uncertainty Score:** 0.625000
- **Temporal Coherence:** 1.000000
- **Is Canonical:** False

**Reconstructed Fields:**

| Attribute | Value | Confidence | Uncertainty | Provenance |
|-----------|-------|----------:|------------:|------------|
| location_name | school | 0.4000 | 0.6000 | CONTEXT_PROPAGATION |
| participants | ['Sarah', 'spouse'] | 0.3500 | 0.6500 | CONTEXT_PROPAGATION |

---

## Interpretation Guide

### CPN (Counterfactual)
- Generates "what-if" scenarios from emotionally charged events
- **UPWARD:** What if you had acted differently? (includes mitigation)
- **DOWNWARD:** What if things had gotten worse?
- **SEMIFACTUAL:** Would outcome have changed anyway?
- Requires causal edges (CAUSES relationships) to build DAGs

### MCTS (Forward Simulation)
- Projects future scenarios using Monte Carlo tree search
- Uses UCT selection with exploration constant c=√2
- Higher expected reward = better predicted outcome

### BGT-SM (Insight Generation)
- Finds surprising connections via random walks on knowledge graph
- Uses PMI (Pointwise Mutual Information) for surprise scoring
- Higher novelty = more unexpected connection

### SPC-UQ (Episodic Reconstruction)
- Fills gaps in incomplete memories using pattern completion
- All reconstructions are NON-CANONICAL (never treated as ground truth)
- Lower uncertainty = higher confidence in reconstruction
