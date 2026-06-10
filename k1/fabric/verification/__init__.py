"""k1.fabric.verification — Epic 4.2.

Post-write verification: build a plan from the constitution, run it against
the native provider's readback, and produce a typed observation.
"""

from k1.fabric.verification.runner import (
    VERIFIED_STATUSES,
    BindingLike,
    NativeReadbackPort,
    NativeReadbackResult,
    ObservationLike,
    ReadbackContext,
    ReadbackUnavailableError,
    VerificationObservation,
    VerificationPlan,
    VerificationPlanRunner,
)

__all__ = [
    "VerificationPlanRunner",
    "VerificationPlan",
    "VerificationObservation",
    "ReadbackContext",
    "ReadbackUnavailableError",
    "NativeReadbackPort",
    "NativeReadbackResult",
    "BindingLike",
    "ObservationLike",
    "VERIFIED_STATUSES",
]
