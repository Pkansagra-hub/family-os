"""Signal taxonomy for the feedback subsystem.

Story: FEEDBACK-002
Related ADR: K020

This file defines the canonical set of feedback signal classes and their
recommended priority bands.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SignalClass(str, Enum):
    """High-level taxonomy for feedback signals."""

    OUTCOME = "OUTCOME"
    CORRECTION = "CORRECTION"
    IMPLICIT = "IMPLICIT"
    EXPLICIT = "EXPLICIT"
    VALIDATION = "VALIDATION"


class SignalSource(str, Enum):
    """Attribution for where the signal originated."""

    K1 = "K1"
    USER = "USER"
    SYSTEM = "SYSTEM"
    AGENT = "AGENT"


@dataclass(frozen=True, slots=True)
class SignalPriorityBand:
    """Recommended priority band for a signal class.

    Priority is a continuous scalar in [0.0, 1.0] used for routing/scheduling.
    We also keep a coarse tier label (P0/P1/P2) to align with FEEDBACK.md.
    """

    min_priority: float
    max_priority: float
    tier: str  # "P0" | "P1" | "P2"


_SIGNAL_CLASS_PRIORITY: dict[SignalClass, SignalPriorityBand] = {
    # P0: user asserts something is wrong or confirms/denies truth.
    SignalClass.CORRECTION: SignalPriorityBand(min_priority=0.85, max_priority=1.00, tier="P0"),
    SignalClass.VALIDATION: SignalPriorityBand(min_priority=0.80, max_priority=1.00, tier="P0"),
    # P1: direct user feedback, but typically less specific than corrections.
    SignalClass.EXPLICIT: SignalPriorityBand(min_priority=0.65, max_priority=0.95, tier="P1"),
    # P2: derived/system signals; useful but noisier.
    SignalClass.IMPLICIT: SignalPriorityBand(min_priority=0.35, max_priority=0.80, tier="P2"),
    SignalClass.OUTCOME: SignalPriorityBand(min_priority=0.35, max_priority=0.80, tier="P2"),
}


def priority_band_for(signal_class: SignalClass) -> SignalPriorityBand:
    """Return the recommended priority band for a feedback signal class."""

    return _SIGNAL_CLASS_PRIORITY[signal_class]
