"""k1.grounding -- policy-filtered identity, time, and place envelope.

Top-level imports stay inert: types, configuration, constants, and errors only.
Runtime services, adapters, factories, and kernel handles live in submodules.
"""

from __future__ import annotations

from k1.grounding.config import GroundingConfig
from k1.grounding.errors import (
    EnvelopeBuildError,
    GroundingError,
    GroundingPolicyError,
    GroundingStateError,
    LeaseDeniedError,
    LeaseExpiredError,
    ProjectionDeniedError,
    StaleEnvelopeError,
)
from k1.grounding.types import (
    AgentGroundingLease,
    Consumer,
    ConsumerScope,
    DeviceContextSnapshot,
    GroundingEnvelope,
    GroundingFreshness,
    GroundingProjection,
    GroundingSource,
)

__all__ = [
    "AgentGroundingLease",
    "Consumer",
    "ConsumerScope",
    "DeviceContextSnapshot",
    "EnvelopeBuildError",
    "GroundingConfig",
    "GroundingEnvelope",
    "GroundingError",
    "GroundingFreshness",
    "GroundingPolicyError",
    "GroundingProjection",
    "GroundingSource",
    "GroundingStateError",
    "LeaseDeniedError",
    "LeaseExpiredError",
    "ProjectionDeniedError",
    "StaleEnvelopeError",
]
