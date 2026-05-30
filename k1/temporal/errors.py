"""Error hierarchy for the k1.temporal kernel module."""

from __future__ import annotations


class TemporalError(Exception):
    """Base error for temporal grounding failures."""


class InvalidTimezoneError(TemporalError):
    """Raised when a timezone name cannot be resolved."""


class StaleAnchorError(TemporalError):
    """Raised when a consumer requires a fresh anchor but only stale data exists."""


class AmbiguousExpressionError(TemporalError):
    """Raised when a temporal expression requires clarification."""


class UnavailableClockError(TemporalError):
    """Raised when no trusted clock source is available."""


class UnsupportedLocaleError(TemporalError):
    """Raised when locale-specific date rules are unavailable."""
