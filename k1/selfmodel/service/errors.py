"""Service-layer exception types for ``k1.selfmodel``.

Defined here (separate from contracts/) because they belong to the
service surface and would otherwise create an import cycle between
contract dataclasses and the services that raise them.
"""

from __future__ import annotations

__all__ = [
    "SelfModelError",
    "UnknownActorError",
    "ConstitutionUnavailableError",
    "ConstitutionSafeModeError",
    "InvariantViolationError",
    "UnknownSituationError",
]


class SelfModelError(RuntimeError):
    """Base class for every service-layer error in ``k1.selfmodel``."""


class UnknownActorError(SelfModelError, LookupError):
    """Raised when an actor id has no entry in the projection store."""


class ConstitutionUnavailableError(SelfModelError):
    """Raised when ``ConstitutionService.get_active()`` is called but no
    constitution row exists in the projection store."""


class ConstitutionSafeModeError(SelfModelError):
    """Raised when an amendment-mutating call is made while the active
    constitution is in safe-mode (signature chain broken).

    Read paths still work in safe-mode; only writes raise this.
    """


class InvariantViolationError(SelfModelError):
    """Raised when an Empty-Set Invariant (E1..E6) would be violated by
    proceeding. The composer raises this when its own invariants would
    break — not for normal default-deny outcomes (those return empty
    projections, not exceptions)."""


class UnknownSituationError(SelfModelError, ValueError):
    """``situation_kind`` is not in the canonical V0 set."""
