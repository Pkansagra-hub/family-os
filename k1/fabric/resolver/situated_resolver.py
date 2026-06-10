"""ResolveSituationService — Epic 6.2.

The main orchestrator.  Takes a ``RequestFrame``, runs the full pipeline
through all Epic 3–5 services, and produces a ``ResolutionEnvelope`` with a
verdict + sub_reason via a 13-step cascade.  This is THE entry point Back calls.

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epic 6.2.
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Protocol

from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.constitution.schema import ConstitutionArtifact
from k1.fabric.policy.selector import PolicyBundle, PolicySelectorService
from k1.fabric.resolver.capability_binder import (
    BindingBundle,
    CapabilityBinderService,
)
from k1.fabric.resolver.capability_type_resolver import (
    CapabilityTypeResolver,
    ResolvedIntentType,
)
from k1.fabric.resolver.request_frame import RequestFrame
from k1.fabric.resolver.resource_projection import (
    ResolveResourcesService,
    ResourceUniverse,
)
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.idempotency_store import IdempotencyStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

if TYPE_CHECKING:
    from k1.fabric.prompt_pack.builder import PromptPack

# ── Constants ──────────────────────────────────────────────────────────
_WRITE_EFFECTS = frozenset({"write", "delete"})
_WRITE_OPERATIONS = frozenset({"create", "update", "delete", "send", "fire", "write"})
_RESOLUTION_TTL_MINUTES = 5


# ── Builder port (avoids circular import with Epic 6.3) ────────────────


class PromptPackBuilderLike(Protocol):
    """Structural port for the Epic 6.3 ``PromptPackBuilder``."""

    def build(
        self,
        resolution_envelope: Any,
        *,
        disclosure_phase: str,
        prompt_budget_tokens: int = 8000,
        committed_tool_names: list[str] | None = None,
    ) -> Any: ...


# ── Request / envelope ─────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolveSituationRequest:
    """What Back sends to initiate resolution."""

    request_id: str
    frame: RequestFrame
    actor_id: str
    space_id: str
    session_id: str
    tier: str  # 'LOW' | 'MEDIUM' | 'HIGH'
    safety_band: str  # 'GREEN' | 'AMBER' | 'RED'
    disclosure_phase: str = "connector_summary"
    freshness_policy: str = "allow_stale_reads"
    prompt_budget_tokens: int = 8000
    completed_prerequisite_bindings: list[str] = field(default_factory=list)
    previous_resolution_id: str | None = None
    idempotency_keys: list[str] = field(default_factory=list)
    budget_remaining: dict | None = None


@dataclass(frozen=True)
class ResolutionEnvelope:
    """Complete resolution snapshot returned to Back."""

    resolution_id: str
    request_id: str
    request_frame: RequestFrame
    candidate_universe: ResourceUniverse | None
    intent_resolutions: list[ResolvedIntentType]
    policy_bundle: PolicyBundle | None
    binding_bundle: BindingBundle | None
    constitution: ConstitutionArtifact | None
    prompt_pack: "PromptPack | None"
    verdict: str
    sub_reason: str | None
    allowed_next_actions: list[str]
    allowed_capability_names: list[str]
    capability_name_to_binding: dict[str, str]
    hil_request: dict | None
    recovery_directive: dict | None
    diagnostics: list[dict]
    created_at: str
    expires_at: str
    # ── Phase-1 contract completion (additive, defaulted) ──
    # Concrete, ordered, single-pass execution plan synthesized from the
    # binding bundle + constitution.  Every step carries its binding's
    # denormalized required_inputs so Back can build params WITHOUT a second
    # resolve call.  ``depends_on`` encodes read-before-write / verify-after-
    # write ordering — this is what removes the re-resolve round-trip.
    execution_plan: list[dict] = field(default_factory=list)
    # Advisory machine recommendation (mirror of ``verdict``).  ``verdict`` is
    # retained for backward compat; Back may reason past it using the raw info
    # surface (candidate_universe, policy_bundle, intent_resolutions).
    machine_verdict: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution_id": self.resolution_id,
            "request_id": self.request_id,
            "verdict": self.verdict,
            "machine_verdict": self.machine_verdict or self.verdict,
            "sub_reason": self.sub_reason,
            "allowed_next_actions": list(self.allowed_next_actions),
            "allowed_capability_names": list(self.allowed_capability_names),
            "capability_name_to_binding": dict(self.capability_name_to_binding),
            "hil_request": self.hil_request,
            "recovery_directive": self.recovery_directive,
            "diagnostics": list(self.diagnostics),
            "completeness": (
                self.candidate_universe.completeness if self.candidate_universe else "unknown"
            ),
            "freshness": (
                self.candidate_universe.freshness if self.candidate_universe else "unknown"
            ),
            # ── Ordered single-pass plan (prereq → primary → verifier) ──
            "execution_plan": [dict(s) for s in self.execution_plan],
            # ── Full structural info surface (previously withheld) ──
            "request_frame": self._request_frame_dict(),
            "candidate_universe": self._candidate_universe_dict(),
            "intent_resolutions": self._intent_resolutions_dict(),
            "policy_bundle": self._policy_bundle_dict(),
            "binding_bundle": self.binding_bundle.to_dict() if self.binding_bundle else None,
            "constitution": self._constitution_dict(),
            "prompt_pack": (
                {
                    "disclosure_phase": self.prompt_pack.disclosure_phase,
                    "decision_surface": self.prompt_pack.decision_surface,
                    "allowed_next_actions": list(self.prompt_pack.allowed_next_actions),
                    "allowed_tool_calls": list(self.prompt_pack.allowed_tool_calls),
                    "uncertainty_markers": list(self.prompt_pack.uncertainty_markers),
                }
                if self.prompt_pack
                else None
            ),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    # ── to_dict() sub-serializers (keep the main dict readable) ──────

    def _request_frame_dict(self) -> dict[str, Any] | None:
        frame = self.request_frame
        if frame is None:
            return None
        twh = frame.time_window_hint
        return {
            "request_id": frame.request_id,
            "task_id": frame.task_id,
            "trace_id": frame.trace_id,
            "actor_id": frame.actor_id,
            "space_id": frame.space_id,
            "intents": [
                {
                    "intent_id": it.intent_id,
                    "action": it.action,
                    "domain": it.domain,
                    "operation_hint": it.operation_hint,
                    "resource_kind_hint": it.resource_kind_hint,
                    "subject_hint": it.subject_hint,
                    "params": dict(it.params),
                }
                for it in frame.intents
            ],
            "time_window_hint": (
                {
                    "raw_phrase": twh.raw_phrase,
                    "resolved_start": twh.resolved_start,
                    "resolved_end": twh.resolved_end,
                }
                if twh is not None
                else None
            ),
            "target_tier": frame.target_tier,
            "resolution_mode": frame.resolution_mode,
        }

    def _candidate_universe_dict(self) -> dict[str, Any] | None:
        uni = self.candidate_universe
        if uni is None:
            return None
        return {
            "universe_id": uni.universe_id,
            "completeness": uni.completeness,
            "freshness": uni.freshness,
            "resource_candidates": [
                {
                    "resource_id": c.resource_id,
                    "label": c.label,
                    "resource_kind": c.resource_kind,
                    "connector_id": c.connector_id,
                    "actor_permission": c.actor_permission,
                    "freshness_state": c.freshness_state,
                    "aliases": list(c.aliases),
                    "admission_verdict": c.admission_verdict,
                }
                for c in uni.resource_candidates
            ],
            "person_candidates": [
                {
                    "person_id": p.person_id,
                    "label": p.label,
                    "role": p.role,
                    "linked_resource_ids": list(p.linked_resource_ids),
                    "resolved": p.resolved,
                }
                for p in uni.person_candidates
            ],
            "unresolved": [
                {
                    "raw": u.raw,
                    "entity_type": u.entity_type,
                    "reason": u.reason,
                    "candidates": list(u.candidates),
                }
                for u in uni.unresolved
            ],
        }

    def _intent_resolutions_dict(self) -> list[dict[str, Any]]:
        return [
            {
                "intent_id": it.intent_id,
                "domain": it.domain,
                "resource_family": it.resource_family,
                "operation_family": it.operation_family,
                "effect": it.effect,
                "role": it.role,
                "confidence": it.confidence,
            }
            for it in self.intent_resolutions
        ]

    def _policy_bundle_dict(self) -> dict[str, Any] | None:
        pol = self.policy_bundle
        if pol is None:
            return None
        return {
            "policy_verdict": pol.policy_verdict,
            "deny_reason": pol.deny_reason,
            "roles_allowed": {k: list(v) for k, v in pol.roles_allowed.items()},
            "gates": [
                {
                    "gate_id": g.gate_id,
                    "gate_type": g.gate_type,
                    "description": g.description,
                    "condition": (
                        dict(g.condition) if isinstance(g.condition, dict) else g.condition
                    ),
                    "action_required": g.action_required,
                }
                for g in pol.gates
            ],
            "hil_triggers": [dict(t) for t in pol.hil_triggers],
            "verifier_requirements": dict(pol.verifier_requirements),
        }

    def _constitution_dict(self) -> dict[str, Any] | None:
        const = self.constitution
        if const is None:
            return None
        return {
            "connector_id": const.connector_id,
            "execution_phases": list(const.execution_phases or []),
            "prerequisite_reads": [
                {
                    "operation": r.operation,
                    "resource_kind": r.resource_kind,
                    "reason": r.reason,
                    "required": r.required,
                }
                for r in (const.prerequisite_reads or [])
            ],
            "companion_resource_roles": [
                {
                    "resource_kind": c.resource_kind,
                    "role": c.role,
                    "description": c.description,
                }
                for c in (const.companion_resource_roles or [])
            ],
            "mutation_sequencing": [
                {
                    "order": m.order,
                    "phase": m.phase,
                    "operation": m.operation,
                    "description": m.description,
                }
                for m in (const.mutation_sequencing or [])
            ],
            "hil_gates": [
                {
                    "trigger": g.trigger,
                    "field": g.field,
                    "prompt": g.prompt,
                    "options": list(g.options),
                }
                for g in (const.hil_gates or [])
            ],
            "verification_requirements": [
                {"method": v.method, "required_for_submit": v.required_for_submit}
                for v in (const.verification_requirements or [])
            ],
            "degradation_policy": const.degradation_policy,
        }


# ── Service ────────────────────────────────────────────────────────────


class ResolveSituationService:
    """Full resolution pipeline + 13-step verdict cascade."""

    def __init__(
        self,
        global_store: GlobalProjectionStore,
        local_store: LocalProjectionStore,
        *,
        resource_resolver: ResolveResourcesService | None = None,
        type_resolver: CapabilityTypeResolver | None = None,
        policy_selector: PolicySelectorService | None = None,
        capability_binder: CapabilityBinderService | None = None,
        constitution_loader: ConstitutionLoader | None = None,
        prompt_pack_builder: PromptPackBuilderLike | None = None,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        self.global_store = global_store
        self.local_store = local_store
        self.resource_resolver = resource_resolver or ResolveResourcesService(
            global_store, local_store
        )
        self.type_resolver = type_resolver or CapabilityTypeResolver(global_store, local_store)
        self.policy_selector = policy_selector or PolicySelectorService(global_store)
        self.capability_binder = capability_binder or CapabilityBinderService(
            global_store, local_store
        )
        self.constitution_loader = constitution_loader or ConstitutionLoader(global_store)
        self.prompt_pack_builder = prompt_pack_builder
        self.idempotency_store = idempotency_store

    # ── Public API ─────────────────────────────────────────────────

    def resolve(self, request: ResolveSituationRequest) -> ResolutionEnvelope:
        """Full resolution pipeline."""
        frame = request.frame
        diagnostics: list[dict] = []
        resolution_id = "res-" + uuid.uuid4().hex[:16]

        # ── Pipeline ──
        universe = self.resource_resolver.resolve(frame, request.actor_id, request.space_id)
        diagnostics.extend(_universe_diagnostics(universe))

        intent_types = self.type_resolver.resolve(frame, universe)
        actor_role = str(frame.safety_context.get("actor_role") or "parent")
        policy_bundle = self.policy_selector.select(
            universe, intent_types, actor_role, request.safety_band
        )

        intent_actions = [it_action(frame, i) for i in range(len(intent_types))]
        binding_bundle = self.capability_binder.bind(
            intent_types,
            universe,
            policy_bundle,
            actor_id=request.actor_id,
            session_id=request.session_id,
            disclosure_phase=request.disclosure_phase,
            intent_actions=intent_actions,
            constitution_loader=self.constitution_loader,
            resolution_id=resolution_id,
        )

        # Constitution for the primary binding's connector (loaded once).
        constitution: ConstitutionArtifact | None = None
        if binding_bundle.primary is not None and binding_bundle.primary.connector_id:
            constitution = self.constitution_loader.load(binding_bundle.primary.connector_id)

        # ── 13-step verdict cascade ──
        verdict, sub_reason = self._determine_verdict(
            request,
            universe,
            intent_types,
            policy_bundle,
            binding_bundle,
            constitution,
            diagnostics,
        )

        allowed = self._allowed_next_actions(
            verdict, binding_bundle, request.completed_prerequisite_bindings
        )
        hil_request = self._hil_request(verdict, universe, constitution, frame)
        recovery_directive = self._recovery_directive(verdict, universe, binding_bundle)

        # Single-pass plan: prereq(read) -> primary(mutate) -> verifier(verify),
        # always fully populated regardless of the advisory gate verdict.  This
        # is what removes the re-resolve round-trip for Back.
        execution_plan = _build_execution_plan(
            binding_bundle, constitution, request.completed_prerequisite_bindings
        )

        now = datetime.now(timezone.utc)
        envelope = ResolutionEnvelope(
            resolution_id=resolution_id,
            request_id=frame.request_id,
            request_frame=frame,
            candidate_universe=universe,
            intent_resolutions=intent_types,
            policy_bundle=policy_bundle,
            binding_bundle=binding_bundle,
            constitution=constitution,
            prompt_pack=None,
            verdict=verdict,
            sub_reason=sub_reason,
            allowed_next_actions=[a["description"] for a in allowed],
            allowed_capability_names=[a["capability_name"] for a in allowed],
            capability_name_to_binding={a["capability_name"]: a["binding_id"] for a in allowed},
            hil_request=hil_request,
            recovery_directive=recovery_directive,
            diagnostics=diagnostics + _binding_diagnostics(policy_bundle, binding_bundle),
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=_RESOLUTION_TTL_MINUTES)).isoformat(),
            execution_plan=execution_plan,
            machine_verdict=verdict,
        )

        # ── Build prompt pack (if a builder is wired) ──
        if self.prompt_pack_builder is not None:
            pack = self.prompt_pack_builder.build(
                envelope,
                disclosure_phase=request.disclosure_phase,
                prompt_budget_tokens=request.prompt_budget_tokens,
            )
            envelope = dataclasses.replace(envelope, prompt_pack=pack)

        return envelope

    # ── 13-step cascade ────────────────────────────────────────────

    def _determine_verdict(
        self,
        request: ResolveSituationRequest,
        universe: ResourceUniverse,
        intent_types: list[ResolvedIntentType],
        policy_bundle: PolicyBundle,
        binding_bundle: BindingBundle,
        constitution: ConstitutionArtifact | None,
        diagnostics: list[dict],
    ) -> tuple[str, str | None]:
        frame = request.frame
        write_intended = any(it.effect in _WRITE_EFFECTS for it in intent_types)

        # 1. Budget exhausted
        field_name = _budget_exhausted_field(request)
        if field_name is not None:
            diagnostics.append({"type": "budget", "verdict": "cannot_execute"})
            return "cannot_execute", f"budget_exhausted:{field_name}"

        # 2. Idempotency duplicate
        if self.idempotency_store is not None:
            for key in request.idempotency_keys:
                if self.idempotency_store.check(key).state == "succeeded":
                    return "cannot_execute", f"idempotency_duplicate:{key}"

        # 3. Ambiguous person reference
        raw = self._first_ambiguous_person(request.actor_id, frame)
        if raw is not None:
            return "needs_disambiguation", f"ambiguous_person:{raw}"

        # 4. Stale projection on write intent
        if write_intended:
            for c in universe.resource_candidates:
                if c.freshness_state == "stale":
                    return "stale_projection", f"stale_resource:{c.resource_id}"

        # 5. Unresolved ambiguous refs
        for u in universe.unresolved:
            if u.reason == "ambiguous":
                return "needs_disambiguation", f"ambiguous_resource:{u.raw}"

        # 6. Unresolved not_found refs
        for u in universe.unresolved:
            if u.reason == "not_found":
                return "missing_required_params", f"resource_not_found:{u.raw}"

        # 7. Intent too vague
        if _intent_too_vague(frame):
            return "missing_required_params", "intent_too_vague"

        # 8. Promote to Tier 3
        promote, detail = _should_promote_to_tier3(binding_bundle)
        if promote:
            return "promote_to_tier3", detail

        # 9. Policy denied
        if policy_bundle.policy_verdict == "deny":
            return "blocked_by_policy", policy_bundle.deny_reason or "deny"

        # 10. Stale binding
        for role in binding_bundle.unbound_roles:
            if role.reason == "stale_projection":
                return "stale_projection", f"stale_binding:{role.detail}"

        # 11. Missing capability
        for role in binding_bundle.unbound_roles:
            if role.reason in {"missing_capability", "missing_connector", "guide_only"}:
                return "missing_capability", f"{role.reason}:{role.resource_kind}"

        # 12. Incomplete prerequisites
        incomplete = _incomplete_prerequisite(
            binding_bundle, request.completed_prerequisite_bindings
        )
        if incomplete is not None:
            return "can_execute_with_gate", f"prerequisite_read_incomplete:{incomplete}"

        # 13. HIL gate triggered (only for write intents — gates guard write fields)
        if write_intended:
            trigger = _hil_gate_triggered(constitution, frame)
            if trigger is not None:
                return "needs_hil", f"hil_gate:{trigger}"

        return "can_execute", None

    # ── Helpers ────────────────────────────────────────────────────

    def _first_ambiguous_person(self, actor_id: str, frame: RequestFrame) -> str | None:
        for person_ref in frame.person_refs:
            if not person_ref.needs_resolution:
                continue
            raw = str(person_ref.raw or "").strip()
            if not raw:
                continue
            matches = self.local_store.resolve_alias(raw, actor_id, entity_type="person")
            entities = {str(m.get("entity_id") or "").strip() for m in matches}
            entities.discard("")
            if len(entities) > 1:
                return raw
        return None

    def _allowed_next_actions(
        self,
        verdict: str,
        binding_bundle: BindingBundle,
        completed_prerequisite_bindings: list[str],
    ) -> list[dict[str, str]]:
        if verdict == "can_execute_with_gate":
            completed = set(completed_prerequisite_bindings)
            return [
                _action(b) for b in binding_bundle.prerequisites if b.binding_id not in completed
            ]
        if verdict == "can_execute":
            completed = set(completed_prerequisite_bindings)
            prereqs_done = all(b.binding_id in completed for b in binding_bundle.prerequisites)
            actions: list[dict[str, str]] = []
            for b in binding_bundle.all_bindings:
                if b.role == "primary":
                    if b.effect in _WRITE_EFFECTS and not prereqs_done:
                        continue
                    actions.append(_action(b))
                elif b.role in {"prerequisite", "companion"} and b.effect == "read":
                    actions.append(_action(b))
            return actions
        return []

    def _hil_request(
        self,
        verdict: str,
        universe: ResourceUniverse,
        constitution: ConstitutionArtifact | None,
        frame: RequestFrame,
    ) -> dict | None:
        if verdict == "needs_disambiguation":
            options = [
                {"raw": u.raw, "candidates": u.candidates}
                for u in universe.unresolved
                if u.reason == "ambiguous"
            ]
            return {"type": "disambiguation", "options": options}
        if verdict == "needs_hil" and constitution is not None:
            trigger = _hil_gate_triggered(constitution, frame)
            gate = next(
                (g for g in constitution.hil_gates if g.trigger == trigger),
                None,
            )
            if gate is not None:
                return {
                    "type": "hil_gate",
                    "trigger": gate.trigger,
                    "prompt": gate.prompt,
                    "options": list(gate.options),
                    "field": gate.field,
                }
        return None

    def _recovery_directive(
        self,
        verdict: str,
        universe: ResourceUniverse,
        binding_bundle: BindingBundle,
    ) -> dict | None:
        if verdict == "stale_projection":
            stale_ids = [
                c.resource_id for c in universe.resource_candidates if c.freshness_state == "stale"
            ]
            return {"action": "refresh_projection", "resource_ids": stale_ids}
        return None


# ── Module helpers ─────────────────────────────────────────────────────


def it_action(frame: RequestFrame, idx: int) -> str:
    """Return the raw action text for the intent at ``idx`` (for BM25)."""
    if 0 <= idx < len(frame.intents):
        return frame.intents[idx].action
    return ""


def _budget_exhausted_field(request: ResolveSituationRequest) -> str | None:
    if request.prompt_budget_tokens <= 1:
        return "max_prompt_tokens"
    budget = request.budget_remaining or {}
    if int(budget.get("max_iterations", 1)) <= 0:
        return "max_iterations"
    if int(budget.get("max_fabric_calls", 1)) <= 0:
        return "max_fabric_calls"
    if int(budget.get("max_prompt_tokens", 2)) <= 1:
        return "max_prompt_tokens"
    return None


def _intent_too_vague(frame: RequestFrame) -> bool:
    """A write intent with no subject_hint, no params, and no time window."""
    for intent in frame.intents:
        if intent.operation_hint not in _WRITE_OPERATIONS:
            continue
        has_subject = bool(intent.subject_hint)
        has_params = bool(intent.params)
        has_time = frame.time_window_hint is not None
        if not has_subject and not has_params and not has_time:
            return True
    return False


def _should_promote_to_tier3(binding_bundle: BindingBundle) -> tuple[bool, str | None]:
    """Data-driven tier promotion from the binding structure."""
    connectors: set[str] = set()
    for b in binding_bundle.all_bindings:
        if b.connector_id:
            connectors.add(b.connector_id)
    connector_count = len(connectors)

    has_prereq = len(binding_bundle.prerequisites) > 0
    has_verifier = len(binding_bundle.verifiers) > 0
    dep_depth = 0
    if has_prereq:
        dep_depth = 1
    if has_prereq and has_verifier:
        dep_depth = 2
    if has_prereq and has_verifier and binding_bundle.companions:
        dep_depth = 3

    has_companion = len(binding_bundle.companions) > 0

    if connector_count >= 6 or dep_depth >= 3 or (has_companion and connector_count >= 4):
        return True, f"connectors:{connector_count}_depth:{dep_depth}"
    return False, None


def _build_execution_plan(
    binding_bundle: BindingBundle | None,
    constitution: ConstitutionArtifact | None,
    completed_prerequisite_bindings: list[str],
) -> list[dict[str, Any]]:
    """Synthesize a concrete, ordered, single-pass execution plan.

    Order: prerequisite reads -> companion reads -> primary (mutate/read) ->
    verifiers.  Each step carries the binding's denormalized ``required_inputs``
    and ``optional_inputs`` so Back can construct ``params`` without a second
    resolve call.  ``depends_on`` encodes read-before-write (primary depends on
    all prerequisites) and verify-after-write (verifier depends on primary) so
    Back executes the plan top-to-bottom in ONE pass — no re-resolve.
    """
    if binding_bundle is None:
        return []

    completed = set(completed_prerequisite_bindings)
    steps: list[dict[str, Any]] = []
    counter = {"n": 0}
    prereq_ids: list[str] = []

    def _emit(b: Any, *, phase: str, role: str, depends_on: list[str]) -> None:
        counter["n"] += 1
        steps.append(
            {
                "step": counter["n"],
                "phase": phase,
                "role": role,
                "capability_name": b.capability_name,
                "binding_id": b.binding_id,
                "connector_id": b.connector_id,
                "resource_kind": b.resource_kind,
                "resource_id": b.resource_id,
                "effect": b.effect,
                "invocation_mode": b.invocation_mode,
                "action_name": b.action_name,
                "required_inputs": list(b.required_inputs),
                "optional_inputs": list(b.optional_inputs),
                "depends_on": list(depends_on),
                "completed": b.binding_id in completed,
            }
        )

    # Phase 1 - prerequisite reads (run first).
    for b in binding_bundle.prerequisites:
        _emit(b, phase="read", role="prerequisite", depends_on=[])
        prereq_ids.append(b.binding_id)

    # Phase 1b - companion reads (context, no hard dependency).
    for b in binding_bundle.companions:
        phase = "read" if b.effect not in _WRITE_EFFECTS else "mutate"
        _emit(b, phase=phase, role="companion", depends_on=[])

    # Phase 2 - primary (waits on all prerequisites for read-before-write).
    primary_id: str | None = None
    if binding_bundle.primary is not None:
        p = binding_bundle.primary
        phase = "mutate" if p.effect in _WRITE_EFFECTS else "read"
        _emit(p, phase=phase, role="primary", depends_on=prereq_ids)
        primary_id = p.binding_id

    # Phase 3 - verifiers (verify-after-write).
    for b in binding_bundle.verifiers:
        _emit(
            b,
            phase="verify",
            role="verifier",
            depends_on=[primary_id] if primary_id else [],
        )

    return steps


def _incomplete_prerequisite(
    binding_bundle: BindingBundle,
    completed_prerequisite_bindings: list[str],
) -> str | None:
    """Return the capability_name of the first incomplete prerequisite, else None."""
    completed = set(completed_prerequisite_bindings)
    for b in binding_bundle.prerequisites:
        if b.binding_id not in completed:
            return b.capability_name
    return None


def _hil_gate_triggered(
    constitution: ConstitutionArtifact | None,
    frame: RequestFrame,
) -> str | None:
    """Check constitution HIL gates against missing required fields.

    Only ``missing_required_field`` gates can be evaluated deterministically at
    resolve time (other triggers like ``time_conflict_detected`` need runtime
    conflict detection).  Returns the trigger name when a required field is
    absent from every intent's params and the time window.
    """
    if constitution is None:
        return None

    provided: set[str] = set()
    for intent in frame.intents:
        provided.update(intent.params.keys())
        if intent.subject_hint:
            provided.add("title")
            provided.add("subject")
    if frame.time_window_hint is not None:
        if frame.time_window_hint.resolved_start:
            provided.update({"start", "time", "date"})
        if frame.time_window_hint.resolved_end:
            provided.add("end")

    for gate in constitution.hil_gates:
        if gate.trigger != "missing_required_field":
            continue
        if gate.field and gate.field not in provided:
            return gate.trigger
    return None


def _action(binding: Any) -> dict[str, str]:
    if binding.role == "prerequisite":
        description = "run prerequisite " + binding.capability_name
    else:
        description = "invoke " + binding.capability_name
    return {
        "description": description,
        "capability_name": binding.capability_name,
        "binding_id": binding.binding_id,
    }


def _universe_diagnostics(universe: ResourceUniverse) -> list[dict]:
    diagnostics: list[dict] = []
    for u in universe.unresolved:
        diagnostics.append(
            {
                "type": "unresolved_ref",
                "raw": u.raw,
                "entity_type": u.entity_type,
                "reason": u.reason,
                "candidate_count": len(u.candidates),
            }
        )
    for omission in universe.scope_proof.omissions:
        diagnostics.append({"type": "scope_omission", **omission})
    return diagnostics


def _binding_diagnostics(policy_bundle: PolicyBundle, binding_bundle: BindingBundle) -> list[dict]:
    diagnostics: list[dict] = [
        {
            "type": "policy",
            "verdict": policy_bundle.policy_verdict,
            "deny_reason": policy_bundle.deny_reason,
        },
        {
            "type": "binding",
            "binding_count": len(binding_bundle.all_bindings),
            "unbound_roles": [asdict(r) for r in binding_bundle.unbound_roles],
        },
    ]
    if policy_bundle.safety_mapping_evidence:
        diagnostics.append({"type": "safety_mapping", **policy_bundle.safety_mapping_evidence})
    return diagnostics
