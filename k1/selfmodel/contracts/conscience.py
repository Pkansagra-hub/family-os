"""Conscience digest dataclasses (M6.E2).

Per ``IMPLEMENTATION_PLAN_SELF_MODEL.md`` Part B §A:

The constitution is a **conscience**, not an IAM allowlist. All doors
unlocked by default; the conscience names only the social acts that
are **forbidden**, **must-ask**, or risk-overridden for the actor in
the current situation.

This file is contract-only — no behavior. Composer logic lives in
``k1.selfmodel.service.situation_composer``; gate logic in
``k1.selfmodel.adapters.concierge_policy_gate``.

Renaming map (vs. legacy ``Capabilities``):

* ``Capabilities.can_do``                 → IGNORED (default-allow)
* ``Capabilities.requires_confirmation``  → ``must_ask_acts``
* ``Capabilities.requires_identity_tier`` → ``tier_floor``
* (new)                                   → ``forbidden_acts``
* (new)                                   → ``risk_overrides``
* (new)                                   → ``protections``

Empty-Set Invariants tied to this shape:

* **E6 (restated):**
  ``tool_authority ∩ ConscienceDigest.forbidden_acts = ∅``.
  No tool whose social-act maps to ``forbidden_acts`` may execute.
* **E7 (new):** ``forbidden_acts`` is monotone within a session;
  removing an act mid-session without an amendment leaves the
  enforced set as the prior superset until next refresh.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "SocialAct",
    "ConscienceBucket",
    "ConscienceDigest",
]


@dataclass(frozen=True)
class SocialAct:
    """A social/behavioural act the actor may attempt.

    Tool names NEVER appear here — only social-act ids
    (e.g. ``"share_location_with_family"``, ``"send_message"``,
    ``"prescribe_medication"``). Mapping from social-act → fabric
    tool(s) lives outside ``k1.selfmodel`` (deferred to M9).
    """

    act_id: str
    display_name: str = ""
    category: str = ""  # "communication" | "scheduling" | "medical" | ...


@dataclass(frozen=True)
class ConscienceBucket:
    """Per-role parsed conscience rules — the parser's intermediate.

    The composer consumes one of these (for the actor's role) and
    intersects it with the situation to produce a ``ConscienceDigest``.
    """

    forbidden: tuple[str, ...] = field(default_factory=tuple)
    must_ask: tuple[str, ...] = field(default_factory=tuple)
    soft_warn: tuple[str, ...] = field(default_factory=tuple)  # M14.E1.I1
    risk_overrides: dict[str, str] = field(default_factory=dict)
    tier_floor: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ConscienceDigest:
    """Composed conscience for ``(actor, T, D, situation)``.

    All four collections are evaluated by the policy gate in this
    order, with default-ALLOW for anything not mentioned:

    1. ``forbidden_acts``  → DENY with reason.
    2. ``must_ask_acts``   → REQUIRE_CONFIRMATION (HIL escalation).
    3. ``risk_overrides``  → raises baseline ``RiskClass`` for the act
       before the freshness × risk matrix lookup.
    4. ``tier_floor``      → REQUIRE_IDENTITY when current tier <
       declared floor.

    Anything else → ALLOW.
    """

    forbidden_acts: tuple[str, ...] = field(default_factory=tuple)
    must_ask_acts: tuple[str, ...] = field(default_factory=tuple)
    soft_warn_acts: tuple[str, ...] = field(default_factory=tuple)  # M14.E1.I1
    risk_overrides: dict[str, str] = field(default_factory=dict)
    protections: tuple[str, ...] = field(default_factory=tuple)
    tier_floor: dict[str, int] = field(default_factory=dict)

    def is_forbidden(self, act_id: str) -> bool:
        return act_id in self.forbidden_acts

    def is_must_ask(self, act_id: str) -> bool:
        return act_id in self.must_ask_acts

    def is_soft_warn(self, act_id: str) -> bool:
        return act_id in self.soft_warn_acts

    def to_json(self) -> dict[str, object]:
        return {
            "forbidden_acts": list(self.forbidden_acts),
            "must_ask_acts": list(self.must_ask_acts),
            "soft_warn_acts": list(self.soft_warn_acts),
            "risk_overrides": dict(self.risk_overrides),
            "protections": list(self.protections),
            "tier_floor": dict(self.tier_floor),
        }
