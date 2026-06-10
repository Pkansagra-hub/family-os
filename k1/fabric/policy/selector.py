"""PolicySelectorService — Epic 4.1.

Evaluates connector policy declarations against the current actor, typed
intents, and safety context.  Produces a ``PolicyBundle`` that gates what
Back is authorized to do.

This lives alongside the existing ``PolicyEngine`` (which is about provider
selection).  ``PolicySelectorService`` is about *execution authority*.

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epic 4.1.

Key rule (Fix 7): policy gates on typed intent fields
(``resource_family``, ``operation_family``, ``effect``, ``role``) carried by
``ResolvedIntentType`` — NOT loose operation strings.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from typing import Any

from k1.fabric.resolver.capability_type_resolver import ResolvedIntentType
from k1.fabric.resolver.resource_projection import ResourceUniverse
from k1.fabric.stores.global_projection_store import GlobalProjectionStore

# ── Constants ──────────────────────────────────────────────────────────
SAFETY_RANK: dict[str, int] = {"GREEN": 1, "AMBER": 2, "RED": 3}
WRITE_EFFECTS: frozenset[str] = frozenset({"write", "delete"})


# ── Dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PolicyGate:
    """One policy gate produced during evaluation."""

    gate_id: str
    gate_type: (
        str  # 'role_check' | 'safety_band' | 'protected_read' | 'hil_trigger' | 'precondition'
    )
    description: str
    condition: dict[str, Any]
    action_required: str  # 'allow' | 'deny' | 'ask_hil' | 'run_read_first'


@dataclass(frozen=True)
class SafetyMappingEvidence:
    """Evidence of a safety-band mismatch."""

    evidence_id: str
    operation_family: str
    required_band: str
    actual_band: str
    connector_id: str
    capability_name: str
    mapping_result: str
    hard_block_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyBundle:
    """The execution-authority verdict for a set of typed intents."""

    policy_id: str
    connector_ids: list[str]
    intent_types: list[ResolvedIntentType]
    actor_role: str
    safety_band: str
    roles_allowed: dict[str, list[str]]  # connector_id → allowed roles
    gates: list[PolicyGate]
    hil_triggers: list[dict[str, Any]]
    protected_read_policy: dict[str, Any] | None
    guide_refs: list[str]
    verifier_requirements: dict[str, str]  # capability_name → verifier method
    policy_verdict: str  # 'allow' | 'deny' | 'needs_hil' | 'allow_with_gate'
    deny_reason: str | None
    safety_mapping_evidence: dict[str, Any] | None


# ── Service ────────────────────────────────────────────────────────────


class PolicySelectorService:
    """Gates execution authority on typed intents + connector policy.

    Reads connector ``policy_declarations`` and ``constitution`` from the
    ``GlobalProjectionStore`` and evaluates them against the typed intents.
    """

    def __init__(self, global_store: GlobalProjectionStore) -> None:
        self.global_store = global_store

    def select(
        self,
        resource_universe: ResourceUniverse,
        intent_types: list[ResolvedIntentType],
        actor_role: str,
        safety_band: str,
    ) -> PolicyBundle:
        """Evaluate policy for every candidate × typed intent.

        Verdict precedence (worst wins):
        ``deny`` > ``needs_hil`` > ``allow_with_gate`` > ``allow``.

        Default-allow: empty role lists permit all roles.
        Missing connectors (direct candidates) are skipped.
        """
        connector_ids = sorted(
            {c.connector_id for c in resource_universe.resource_candidates if c.connector_id}
        )
        gates: list[PolicyGate] = []
        hil_triggers: list[dict[str, Any]] = []
        roles_allowed: dict[str, list[str]] = {}
        verifier_requirements: dict[str, str] = {}
        guide_refs: list[str] = []
        protected_read_policy: dict[str, Any] | None = None
        deny_reason: str | None = None
        safety_evidence: SafetyMappingEvidence | None = None
        has_soft_gate = False

        for candidate in resource_universe.resource_candidates:
            connector = self.global_store.get_connector(candidate.connector_id)
            if connector is None:
                # Direct candidate (needs_resolution=False) or unknown connector.
                # No connector policy to enforce — the capability binder handles
                # discovery by resource_kind.  NEVER a false deny.
                continue

            policy = connector.policy_declarations or {}

            # ── Protected resources (gate even on reads) ──
            protected = policy.get("protected_resources") or []
            if protected:
                protected_read_policy = {
                    "connector_id": candidate.connector_id,
                    "protected_resources": protected,
                }
                for prot in protected:
                    pattern = str(prot.get("resource_id_pattern") or "")
                    required_role = prot.get("required_role")
                    if (
                        pattern
                        and required_role
                        and fnmatch(candidate.resource_id, pattern)
                        and actor_role != required_role
                    ):
                        deny_reason = deny_reason or "protected_resource"
                        gates.append(
                            PolicyGate(
                                gate_id="gate-" + uuid.uuid4().hex[:12],
                                gate_type="protected_read",
                                description=(
                                    f"Resource {candidate.resource_id} is protected; "
                                    f"requires role '{required_role}'."
                                ),
                                condition={
                                    "connector_id": candidate.connector_id,
                                    "resource_id": candidate.resource_id,
                                    "required_role": required_role,
                                },
                                action_required="deny",
                            )
                        )

            # ── Per-intent role + safety evaluation ──
            for intent in intent_types:
                caps = [
                    c
                    for c in intent.fallback_capabilities
                    if c.get("connector_id") == candidate.connector_id
                ]
                is_write = intent.effect in WRITE_EFFECTS

                if is_write:
                    allowed = list(policy.get("write_requires_actor_role") or [])
                    roles_allowed[candidate.connector_id] = allowed
                    if allowed and actor_role not in allowed:
                        deny_reason = deny_reason or "role_not_allowed"
                        gates.append(
                            PolicyGate(
                                gate_id="gate-" + uuid.uuid4().hex[:12],
                                gate_type="role_check",
                                description=(
                                    f"Write to {candidate.connector_id} requires role in "
                                    f"{allowed}; actor is '{actor_role}'."
                                ),
                                condition={
                                    "connector_id": candidate.connector_id,
                                    "operation_family": intent.operation_family,
                                    "effect": intent.effect,
                                    "allowed_roles": allowed,
                                },
                                action_required="deny",
                            )
                        )
                else:
                    allowed = list(policy.get("read_allowed_roles") or [])
                    roles_allowed.setdefault(candidate.connector_id, allowed)
                    if allowed and actor_role not in allowed:
                        deny_reason = deny_reason or "read_not_allowed"
                        gates.append(
                            PolicyGate(
                                gate_id="gate-" + uuid.uuid4().hex[:12],
                                gate_type="role_check",
                                description=(
                                    f"Read on {candidate.connector_id} requires role in "
                                    f"{allowed}; actor is '{actor_role}'."
                                ),
                                condition={
                                    "connector_id": candidate.connector_id,
                                    "operation_family": intent.operation_family,
                                    "effect": intent.effect,
                                    "allowed_roles": allowed,
                                },
                                action_required="deny",
                            )
                        )

                # ── Safety band check (per capability minimum) ──
                for cap in caps:
                    record = self.global_store.get_capability(str(cap.get("capability_name") or ""))
                    if record is None:
                        continue
                    required_band = record.safety_band_min or "GREEN"
                    if SAFETY_RANK.get(safety_band, 1) < SAFETY_RANK.get(required_band, 1):
                        deny_reason = deny_reason or "safety_band_below_capability_minimum"
                        safety_evidence = SafetyMappingEvidence(
                            evidence_id="safety-" + uuid.uuid4().hex[:12],
                            operation_family=intent.operation_family,
                            required_band=required_band,
                            actual_band=safety_band,
                            connector_id=candidate.connector_id,
                            capability_name=record.capability_name,
                            mapping_result="deny",
                            hard_block_reason="safety_band_below_capability_minimum",
                        )
                        gates.append(
                            PolicyGate(
                                gate_id="gate-" + uuid.uuid4().hex[:12],
                                gate_type="safety_band",
                                description=(
                                    f"Capability {record.capability_name} requires "
                                    f"{required_band}; actor band is {safety_band}."
                                ),
                                condition={
                                    "capability_name": record.capability_name,
                                    "required_band": required_band,
                                    "actual_band": safety_band,
                                },
                                action_required="deny",
                            )
                        )

                # ── Policy-declared HIL triggers ──
                for trig in policy.get("hil_triggers") or []:
                    if self._hil_condition_matches(trig, intent, actor_role):
                        hil_triggers.append(
                            {
                                "connector_id": candidate.connector_id,
                                "operation_family": intent.operation_family,
                                "effect": intent.effect,
                                "condition": trig.get("condition"),
                                "prompt": trig.get("prompt"),
                            }
                        )
                        gates.append(
                            PolicyGate(
                                gate_id="gate-" + uuid.uuid4().hex[:12],
                                gate_type="hil_trigger",
                                description=str(
                                    trig.get("prompt") or "Human confirmation required."
                                ),
                                condition={
                                    "connector_id": candidate.connector_id,
                                    "condition": trig.get("condition"),
                                },
                                action_required="ask_hil",
                            )
                        )

            # ── Constitution: verifier requirements + preconditions ──
            constitution = self.global_store.get_constitution(candidate.connector_id)
            if constitution is not None:
                methods = [
                    str(vr.get("method"))
                    for vr in (constitution.verification_requirements or [])
                    if vr.get("method")
                ]
                if methods:
                    for intent in intent_types:
                        for cap in intent.fallback_capabilities:
                            if cap.get("connector_id") == candidate.connector_id:
                                cap_name = str(cap.get("capability_name") or "")
                                if cap_name:
                                    verifier_requirements[cap_name] = methods[0]

                if constitution.prerequisite_reads:
                    for intent in intent_types:
                        if intent.effect in WRITE_EFFECTS:
                            gates.append(
                                PolicyGate(
                                    gate_id="gate-" + uuid.uuid4().hex[:12],
                                    gate_type="precondition",
                                    description=(
                                        f"Run prerequisite read before "
                                        f"{intent.operation_family} on {candidate.connector_id}."
                                    ),
                                    condition={
                                        "connector_id": candidate.connector_id,
                                        "operation_family": intent.operation_family,
                                        "prerequisite_reads": constitution.prerequisite_reads,
                                    },
                                    action_required="run_read_first",
                                )
                            )
                            has_soft_gate = True

        # ── Verdict precedence: deny > needs_hil > allow_with_gate > allow ──
        if deny_reason is not None:
            verdict = "deny"
        elif hil_triggers:
            verdict = "needs_hil"
        elif has_soft_gate:
            verdict = "allow_with_gate"
        else:
            verdict = "allow"

        return PolicyBundle(
            policy_id="policy-" + uuid.uuid4().hex[:16],
            connector_ids=connector_ids,
            intent_types=list(intent_types),
            actor_role=actor_role,
            safety_band=safety_band,
            roles_allowed=roles_allowed,
            gates=gates,
            hil_triggers=hil_triggers,
            protected_read_policy=protected_read_policy,
            guide_refs=guide_refs,
            verifier_requirements=verifier_requirements,
            policy_verdict=verdict,
            deny_reason=deny_reason,
            safety_mapping_evidence=safety_evidence.to_dict() if safety_evidence else None,
        )

    # ── HIL condition matching (deterministic, NO eval) ─────────────

    @staticmethod
    def _hil_condition_matches(
        trigger: dict[str, Any],
        intent: ResolvedIntentType,
        actor_role: str,
    ) -> bool:
        """Deterministically interpret a policy HIL trigger condition.

        Supports the documented grammar (no ``eval``):
          - ``write_operation`` → matches when the intent is a write.
          - ``read_operation``  → matches when the intent is a read.
          - ``actor_role == 'X'`` → matches when the actor's role is X.
        Multiple clauses are combined with AND.
        Empty/absent condition → no match.
        """
        condition = str(trigger.get("condition") or "").lower()
        if not condition:
            return False

        matches = True
        if "write_operation" in condition:
            matches = matches and (intent.effect in WRITE_EFFECTS)
        if "read_operation" in condition:
            matches = matches and (intent.effect not in WRITE_EFFECTS)

        role_match = re.search(r"actor_role\s*==\s*'([a-z_]+)'", condition)
        if role_match:
            matches = matches and (actor_role == role_match.group(1))

        return matches
