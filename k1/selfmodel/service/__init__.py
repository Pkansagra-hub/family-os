"""Service layer for k1.selfmodel.

Composes ports/adapters into typed snapshots. Filled in across M1–M4.
"""

from __future__ import annotations

from k1.selfmodel.service.constitution import (
    ConstitutionReadResult,
    ConstitutionService,
    SignatureChainValidator,
    stub_signature_validator,
)
from k1.selfmodel.service.errors import (
    ConstitutionSafeModeError,
    ConstitutionUnavailableError,
    InvariantViolationError,
    SelfModelError,
    UnknownActorError,
    UnknownSituationError,
)
from k1.selfmodel.service.family_model import (
    FamilyModelService,
    FamilyViewResult,
)
from k1.selfmodel.service.self_model import (
    SelfModelReadResult,
    SelfModelService,
)
from k1.selfmodel.service.situation_composer import SituationFrameComposer

__all__ = [
    "ConstitutionReadResult",
    "ConstitutionSafeModeError",
    "ConstitutionService",
    "ConstitutionUnavailableError",
    "FamilyModelService",
    "FamilyViewResult",
    "InvariantViolationError",
    "SelfModelError",
    "SelfModelReadResult",
    "SelfModelService",
    "SignatureChainValidator",
    "SituationFrameComposer",
    "UnknownActorError",
    "UnknownSituationError",
    "stub_signature_validator",
]
