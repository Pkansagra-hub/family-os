"""
Counterfactual Emotional Safety & Sharing

Simulate affect impact before taking actions (sharing, notifications, recall).

Reference: ADR-0012i (Counterfactual Emotional Safety & Sharing)
"""

from .simulator import CounterfactualSimulator

__all__ = ["CounterfactualSimulator"]
