"""Salience Module - Attention and Priority Scoring | Version: 0.1.0 | ADR: K006"""

from .salience_scorer import SalienceScorer
from .salience_types import SalienceBand, SalienceConfig, SalienceScore

__version__ = "0.1.0"
__all__ = ["SalienceScorer", "SalienceScore", "SalienceConfig", "SalienceBand"]
