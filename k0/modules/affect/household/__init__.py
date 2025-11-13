"""
Household-Level Affect Dynamics

Aggregate individual affect into household state with conflict/family moment detection.

Reference: ADR-0012g (Household-Level Affect Dynamics)
"""

from .engine import HouseholdDynamicsEngine

__all__ = ["HouseholdDynamicsEngine"]
