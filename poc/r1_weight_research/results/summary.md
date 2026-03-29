# R1 Weight Research -- Results Summary

> Generated: 2026-03-02 20:48

## Score Distribution

| Config | Mean | Std | P10 | P25 | P50 | P75 | P90 |
| - | - | - | - | - | - | - | - |
| A_balanced | 0.408 | 0.231 | 0.167 | 0.223 | 0.383 | 0.488 | 0.679 |
| B_emotion_heavy | 0.435 | 0.231 | 0.179 | 0.253 | 0.417 | 0.535 | 0.702 |
| C_social_identity | 0.408 | 0.228 | 0.167 | 0.230 | 0.382 | 0.489 | 0.659 |
| D_novelty_surprise | 0.391 | 0.234 | 0.155 | 0.202 | 0.361 | 0.455 | 0.682 |

## Tier Mean Scores (higher proxy tier should have higher mean score)

| Tier | A_balanced | B_emotion_heavy | C_social_identity | D_novelty_surprise |
| - | - | - | - | - |
| CRITICAL | 0.564 | 0.579 | 0.525 | 0.570 |
| HIGH | 0.432 | 0.462 | 0.419 | 0.417 |
| MEDIUM_HIGH | 0.529 | 0.550 | 0.537 | 0.508 |
| MEDIUM | 0.411 | 0.442 | 0.412 | 0.390 |
| LOW_MEDIUM | 0.424 | 0.453 | 0.417 | 0.410 |
| LOW | 0.181 | 0.176 | 0.181 | 0.181 |

## Cohen's d (Adjacent Tier Separation)

Target: d >= 0.5 for each pair (medium effect size).

| Pair | A_balanced | B_emotion_heavy | C_social_identity | D_novelty_surprise |
| - | - | - | - | - |
| CRITICAL_vs_HIGH | 1.008 (GOOD) | 0.936 (GOOD) | 0.834 (GOOD) | 1.128 (GOOD) |
| HIGH_vs_MEDIUM_HIGH | -0.502 (POOR) | -0.467 (POOR) | -0.631 (POOR) | -0.448 (POOR) |
| MEDIUM_HIGH_vs_MEDIUM | 0.529 (GOOD) | 0.487 (WEAK) | 0.567 (GOOD) | 0.510 (GOOD) |
| MEDIUM_vs_LOW_MEDIUM | -0.057 (POOR) | -0.047 (POOR) | -0.023 (POOR) | -0.081 (POOR) |
| LOW_MEDIUM_vs_LOW | 1.280 (GOOD) | 1.472 (GOOD) | 1.264 (GOOD) | 1.186 (GOOD) |

## Misclassification Rates

| Config | FP (>0.8, LOW) | FN (<0.3, HIGH/CRIT) | Tier Agreement |
| - | - | - | - |
| A_balanced | 0.007 | 0.275 | 0.331 |
| B_emotion_heavy | 0.005 | 0.264 | 0.276 |
| C_social_identity | 0.005 | 0.288 | 0.311 |
| D_novelty_surprise | 0.008 | 0.288 | 0.365 |

## Winner Selection

- **A_balanced**: avg Cohen's d = 0.452, monotonic tier ordering = NO, FP = 0.007, FN = 0.275
- **B_emotion_heavy**: avg Cohen's d = 0.476, monotonic tier ordering = NO, FP = 0.005, FN = 0.264
- **C_social_identity**: avg Cohen's d = 0.402, monotonic tier ordering = NO, FP = 0.005, FN = 0.288
- **D_novelty_surprise**: avg Cohen's d = 0.459, monotonic tier ordering = NO, FP = 0.008, FN = 0.288

**Recommended config: B_emotion_heavy** (highest average Cohen's d = 0.476)
