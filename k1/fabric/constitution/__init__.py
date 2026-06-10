"""k1.fabric.constitution — Epic 5.

Constitution schema validation (5.1) and the single load path (5.2).
"""

from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.constitution.schema import (
    CONSTITUTION_JSON_SCHEMA,
    KNOWN_HIL_TRIGGERS,
    KNOWN_VERIFIER_METHODS,
    CompanionResourceRole,
    ConflictRule,
    ConstitutionArtifact,
    ConstitutionValidationError,
    HILGate,
    MutationStep,
    PrerequisiteRead,
    VerificationRequirement,
    validate_constitution,
    validate_constitution_semantics,
)

__all__ = [
    # Epic 5.1 — schema
    "ConstitutionArtifact",
    "PrerequisiteRead",
    "ConflictRule",
    "CompanionResourceRole",
    "HILGate",
    "MutationStep",
    "VerificationRequirement",
    "ConstitutionValidationError",
    "CONSTITUTION_JSON_SCHEMA",
    "KNOWN_VERIFIER_METHODS",
    "KNOWN_HIL_TRIGGERS",
    "validate_constitution",
    "validate_constitution_semantics",
    # Epic 5.2 — loader
    "ConstitutionLoader",
]
