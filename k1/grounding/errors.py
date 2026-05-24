"""Error hierarchy for the k1.grounding kernel module."""

from __future__ import annotations


class GroundingError(Exception):
    """Base error for grounding envelope failures."""


class ProjectionDeniedError(GroundingError):
    """Raised when policy denies a requested projection precision."""


class StaleEnvelopeError(GroundingError):
    """Raised when an envelope must be refreshed before use."""


class GroundingSourceUnavailableError(GroundingError):
    """Raised when a required grounding source is unavailable."""


class EnvelopeBuildError(GroundingError):
    """Raised when a grounding envelope cannot be built."""


class GroundingPolicyError(GroundingError):
    """Raised when grounding policy evaluation fails."""


class GroundingStateError(GroundingError):
    """Raised when grounding state cannot be read or written."""


class InvalidGroundingPayloadError(GroundingError):
    """Raised when serialized grounding payload data is malformed."""


class LeaseDeniedError(GroundingError):
    """Raised when an agent grounding lease cannot be issued."""


class GroundingLeaseExpiredError(GroundingError):
    """Raised when an agent grounding lease is no longer usable."""


class LeaseExpiredError(GroundingLeaseExpiredError):
    """Backward-compatible alias for expired grounding leases."""


__all__ = [
    "EnvelopeBuildError",
    "GroundingError",
    "GroundingLeaseExpiredError",
    "GroundingPolicyError",
    "GroundingSourceUnavailableError",
    "GroundingStateError",
    "InvalidGroundingPayloadError",
    "LeaseDeniedError",
    "LeaseExpiredError",
    "ProjectionDeniedError",
    "StaleEnvelopeError",
]
