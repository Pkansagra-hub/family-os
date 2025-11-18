"""
M06: Salience Scoring Module

Attention priority scoring for episodic memories in P02 write path.
"""

from k0.modules.salience.score import (
    ComponentScores,
    SalienceResult,
    classify_salience_band,
    compute_affect_amplification,
    compute_recency_score,
    compute_salience,
    compute_social_importance,
    generate_salience_reasons,
    get_metrics,
    reset_metrics,
    run,
)

__all__ = [
    "run",
    "compute_salience",
    "compute_social_importance",
    "compute_recency_score",
    "compute_affect_amplification",
    "classify_salience_band",
    "generate_salience_reasons",
    "get_metrics",
    "reset_metrics",
    "SalienceResult",
    "ComponentScores",
]

__version__ = "1.0.0"
