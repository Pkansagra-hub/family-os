"""
Policy Band Rules and P18 Integration

Maps affect (valence, arousal, tags) to policy bands (GREEN/AMBER/RED/BLACK).

Reference: ADR-0012e (Policy Band Rules & P18 Integration)
"""

from .engine import PolicyEngine
from .rules import check_amber_rules, check_black_rules, check_green_rules, check_red_rules

__all__ = [
    "PolicyEngine",
    "check_black_rules",
    "check_red_rules",
    "check_amber_rules",
    "check_green_rules",
]
