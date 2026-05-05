"""Canonical topic strings for ``k1.selfmodel`` events (M2.E3.I1).

Topic naming convention: ``k1.<domain>.<event>.<version>`` per
[k1/bus/timing/defaults.py](k1/bus/timing/defaults.py). Selfmodel
publishes under three sub-domains:

* ``k1.selfmodel.policy.*``        — gate verdicts and escalations (M2)
* ``k1.selfmodel.constitution.*``  — amendment lifecycle (M3)
* ``k1.selfmodel.identity.*``      — tier transitions (M3)
"""

from __future__ import annotations

__all__ = [
    "TOPIC_POLICY_VERDICT",
    "TOPIC_POLICY_ESCALATION",
    "TOPIC_POLICY_DEFERRED",
    "TOPIC_CONSTITUTION_AMENDMENT_PROPOSED",
    "TOPIC_CONSTITUTION_AMENDMENT_APPROVED",
    "TOPIC_CONSTITUTION_AMENDMENT_ACTIVE",
    "TOPIC_CONSTITUTION_AMENDMENT_REJECTED",
    "TOPIC_IDENTITY_SESSION_STARTED",
    "TOPIC_IDENTITY_SESSION_PROMOTED",
    "TOPIC_IDENTITY_SESSION_ENDED",
    "TOPIC_SELFMODEL_STARTUP_COMPLETE",
    "TOPIC_RISK_FALLBACK",
    "TOPIC_CAPSULE_UNKNOWN_ACTOR",
    "TOPIC_HIL_REQUEST",
    "TOPIC_KERNEL_SAFE_MODE_ACTIVE",
    "ALL_SELFMODEL_TOPICS",
]

# ---- M2: policy gate ------------------------------------------------
TOPIC_POLICY_VERDICT = "k1.selfmodel.policy.verdict.v1"
TOPIC_POLICY_ESCALATION = "k1.selfmodel.policy.escalation.v1"
TOPIC_POLICY_DEFERRED = "k1.selfmodel.policy.deferred.v1"

# ---- M3: constitution amendments ------------------------------------
TOPIC_CONSTITUTION_AMENDMENT_PROPOSED = "k1.selfmodel.constitution.amendment_proposed.v1"
TOPIC_CONSTITUTION_AMENDMENT_APPROVED = "k1.selfmodel.constitution.amendment_approved.v1"
TOPIC_CONSTITUTION_AMENDMENT_ACTIVE = "k1.selfmodel.constitution.amendment_active.v1"
TOPIC_CONSTITUTION_AMENDMENT_REJECTED = "k1.selfmodel.constitution.amendment_rejected.v1"

# ---- M3: identity sessions ------------------------------------------
TOPIC_IDENTITY_SESSION_STARTED = "k1.selfmodel.identity.session_started.v1"
TOPIC_IDENTITY_SESSION_PROMOTED = "k1.selfmodel.identity.session_promoted.v1"
TOPIC_IDENTITY_SESSION_ENDED = "k1.selfmodel.identity.session_ended.v1"

# ---- M5: lifecycle --------------------------------------------------
TOPIC_SELFMODEL_STARTUP_COMPLETE = "k1.selfmodel.startup.complete.v1"

# ---- M12.E2.I3: risk catalog fallback warning -----------------------
TOPIC_RISK_FALLBACK = "k1.selfmodel.risk.fallback.v1"

# ---- M15.E1.I3: capsule renderer warning when actor is unknown ------
TOPIC_CAPSULE_UNKNOWN_ACTOR = "k1.selfmodel.capsule.unknown_actor.v1"

# ---- M15.E1.I7: kernel-side safe-mode active warning ----------------
TOPIC_KERNEL_SAFE_MODE_ACTIVE = "k1.kernel.safe_mode_active.v1"

# ---- M15.E1.I4: re-export HIL request topic for selfmodel callers ---
# Keeping a single import path avoids string-literal duplication
# between the kernel HIL package and selfmodel-side subscribers.
try:  # pragma: no cover - import shim
    from k1.hil.topics import TOPIC_HIL_REQUEST as _TOPIC_HIL_REQUEST
except Exception:  # noqa: BLE001
    _TOPIC_HIL_REQUEST = "k1.hil.request.v1"
TOPIC_HIL_REQUEST = _TOPIC_HIL_REQUEST


ALL_SELFMODEL_TOPICS: tuple[str, ...] = (
    TOPIC_POLICY_VERDICT,
    TOPIC_POLICY_ESCALATION,
    TOPIC_POLICY_DEFERRED,
    TOPIC_CONSTITUTION_AMENDMENT_PROPOSED,
    TOPIC_CONSTITUTION_AMENDMENT_APPROVED,
    TOPIC_CONSTITUTION_AMENDMENT_ACTIVE,
    TOPIC_CONSTITUTION_AMENDMENT_REJECTED,
    TOPIC_IDENTITY_SESSION_STARTED,
    TOPIC_IDENTITY_SESSION_PROMOTED,
    TOPIC_IDENTITY_SESSION_ENDED,
    TOPIC_SELFMODEL_STARTUP_COMPLETE,
    TOPIC_RISK_FALLBACK,
)
