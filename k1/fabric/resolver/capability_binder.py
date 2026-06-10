"""CapabilityBinderService — Epic 6.1.

Takes resolved intent types + resource universe + policy bundle and performs
3-pass discovery against the ``GlobalProjectionStore`` to produce a
``BindingBundle``.  Answers: "WHAT capabilities can fulfil this intent, on
THIS resource, for THIS actor?"

3-pass discovery:
  Pass 1 — typed (graph): ``ResolvedIntentType.fallback_capabilities``
           (deterministic ``capability_type_index`` results).
  Pass 2 — exact: ``find_capabilities(resource_kind, invocation_mode, effect, connector_id)``.
  Pass 3 — BM25: ``search_capabilities(query=action_text)`` (fuzzy fallback).

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epic 6.1.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.policy.selector import PolicyBundle
from k1.fabric.resolver.capability_type_resolver import ResolvedIntentType
from k1.fabric.resolver.resource_projection import ResourceCandidate, ResourceUniverse
from k1.fabric.stores.global_projection_store import (
    CapabilityRecord,
    GlobalProjectionStore,
)
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ── Universal action → (invocation_mode, effect) ───────────────────────
UNIVERSAL_ACTION_MAP: dict[str, tuple[str, str]] = {
    "list": ("read", "read"),
    "search": ("read", "read"),
    "read": ("read", "read"),
    "get": ("read", "read"),
    "create": ("execute", "write"),
    "update": ("execute", "write"),
    "send": ("execute", "write"),
    "delete": ("execute", "delete"),
}

_WRITE_EFFECTS = frozenset({"write", "delete"})
_BINDING_TTL_SECONDS = 300


# ── Dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CapabilityBinding:
    """One bound capability with full context for Back's LLM.

    Carries ``required_inputs`` and ``optional_inputs`` denormalized from
    ``CapabilityRecord`` so Back can construct valid ``params`` for
    ``fabric.execute()`` without an extra schema-lookup round-trip.
    """

    binding_id: str
    capability_name: str
    connector_id: str
    invocation_mode: str
    action_name: str
    effect: str
    resource_kind: str
    resource_id: str
    role: str  # 'primary' | 'companion' | 'prerequisite' | 'verifier' | 'alternative'
    confidence: str
    source: str  # 'typed_intent' | 'exact_match' | 'bm25_search'
    input_schema_ref: str | None
    output_schema_ref: str | None
    effect_summary: str
    safety_requirement: str
    authority_verdict: str  # 'bound' | 'pending' | 'blocked'
    verifier_ref: str | None
    required_inputs: list[dict] = field(default_factory=list)
    optional_inputs: list[dict] = field(default_factory=list)
    guide_refs: list[str] = field(default_factory=list)
    freshness_state: str = "fresh"
    limitations: list[str] = field(default_factory=list)
    created_at: str = ""
    expires_at: str = ""


@dataclass(frozen=True)
class UnboundRole:
    """A role that could not be filled — why binding failed for a candidate."""

    invocation_mode: str
    action_name: str
    resource_kind: str
    reason: str  # 'policy_block' | 'stale_projection' | 'missing_capability' | 'missing_connector' | 'guide_only'
    detail: str


@dataclass(frozen=True)
class BindingBundle:
    """Complete set of bound capabilities, separated by role."""

    bundle_id: str
    resolution_id: str
    primary: CapabilityBinding | None
    companions: list[CapabilityBinding]
    prerequisites: list[CapabilityBinding]
    verifiers: list[CapabilityBinding]
    alternatives: list[CapabilityBinding]
    unbound_roles: list[UnboundRole]
    tool_name_cards: list[dict]
    selected_schema_cards: list[dict]
    guide_refs: list[str]
    verifier_links: list[dict]
    binding_diagnostics: list[str]
    disclosure_phase: str

    @property
    def all_bindings(self) -> list[CapabilityBinding]:
        """Flat list, ordered: primary → prerequisites → companions → verifiers → alternatives."""
        result: list[CapabilityBinding] = []
        if self.primary is not None:
            result.append(self.primary)
        result.extend(self.prerequisites)
        result.extend(self.companions)
        result.extend(self.verifiers)
        result.extend(self.alternatives)
        return result

    @property
    def allowed_capability_names(self) -> list[str]:
        """Capability names Back is authorized to invoke."""
        return [b.capability_name for b in self.all_bindings if b.authority_verdict == "bound"]

    @property
    def capability_name_to_binding(self) -> dict[str, str]:
        return {b.capability_name: b.binding_id for b in self.all_bindings}

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "resolution_id": self.resolution_id,
            "primary": asdict(self.primary) if self.primary else None,
            "companions": [asdict(b) for b in self.companions],
            "prerequisites": [asdict(b) for b in self.prerequisites],
            "verifiers": [asdict(b) for b in self.verifiers],
            "alternatives": [asdict(b) for b in self.alternatives],
            "unbound_roles": [asdict(r) for r in self.unbound_roles],
            "tool_name_cards": list(self.tool_name_cards),
            "selected_schema_cards": list(self.selected_schema_cards),
            "guide_refs": list(self.guide_refs),
            "verifier_links": list(self.verifier_links),
            "binding_diagnostics": list(self.binding_diagnostics),
            "disclosure_phase": self.disclosure_phase,
        }


@dataclass(frozen=True)
class ToolSelectionCommit:
    """Post-selection commit — validates Back's chosen tools against Phase 1."""

    committed_tool_names: list[str]
    rejected_tool_names: list[str]
    accepted: bool
    reason: str | None


# ── Service ────────────────────────────────────────────────────────────


class CapabilityBinderService:
    """3-pass discovery + constitution-driven companion/prerequisite binding."""

    def __init__(
        self,
        global_store: GlobalProjectionStore,
        local_store: LocalProjectionStore,
    ) -> None:
        self.global_store = global_store
        self.local_store = local_store

    # ── Public API ─────────────────────────────────────────────────

    def bind(
        self,
        resolved_intents: list[ResolvedIntentType],
        resource_universe: ResourceUniverse,
        policy_bundle: PolicyBundle,
        *,
        actor_id: str,
        session_id: str,
        disclosure_phase: str = "connector_summary",
        committed_tool_names: list[str] | None = None,
        intent_actions: list[str] | None = None,
        constitution_loader: ConstitutionLoader | None = None,
        resolution_id: str = "",
    ) -> BindingBundle:
        """Run 3-pass discovery for every typed intent × candidate pair."""
        primary: CapabilityBinding | None = None
        companions: list[CapabilityBinding] = []
        prerequisites: list[CapabilityBinding] = []
        verifiers: list[CapabilityBinding] = []
        alternatives: list[CapabilityBinding] = []
        unbound: list[UnboundRole] = []
        verifier_links: list[dict] = []
        diagnostics: list[str] = []
        seen_binding_ids: set[str] = set()

        actions = intent_actions or []
        candidates = resource_universe.resource_candidates

        for idx, intent in enumerate(resolved_intents):
            invocation_mode, effect = self._mode_effect(intent)
            action_name = intent.operation_family
            action_text = actions[idx] if idx < len(actions) else ""
            is_write = effect in _WRITE_EFFECTS

            for candidate in candidates:
                resource_kind = candidate.resource_kind or (intent.resource_family or "")

                # ── Policy gate ──
                if policy_bundle.policy_verdict == "deny":
                    unbound.append(
                        UnboundRole(
                            invocation_mode,
                            action_name,
                            resource_kind,
                            "policy_block",
                            policy_bundle.deny_reason or "deny",
                        )
                    )
                    continue

                # ── Stale gate (write on stale projection) ──
                if candidate.freshness_state == "stale" and is_write:
                    unbound.append(
                        UnboundRole(
                            invocation_mode,
                            action_name,
                            resource_kind,
                            "stale_projection",
                            candidate.resource_id,
                        )
                    )
                    continue

                # ── 3-pass discovery ──
                matches, source = self._find_all_capabilities(
                    candidate,
                    intent,
                    invocation_mode,
                    effect,
                    action_text=action_text,
                )
                if not matches:
                    unbound.append(
                        UnboundRole(
                            invocation_mode,
                            action_name,
                            resource_kind,
                            "missing_capability",
                            candidate.connector_id or "<no_connector>",
                        )
                    )
                    continue

                confidence = (
                    intent.confidence
                    if source == "typed_intent"
                    else ("high" if source == "exact_match" else "medium")
                )

                # Primary = best match for the first satisfiable intent.
                primary_role = "primary"
                best = matches[0]
                binding = self._make_binding(
                    best,
                    candidate,
                    actor_id,
                    session_id,
                    role=primary_role,
                    source=source,
                    confidence=confidence,
                )
                if binding.binding_id not in seen_binding_ids:
                    seen_binding_ids.add(binding.binding_id)
                    if primary is None:
                        primary = binding
                    else:
                        alternatives.append(binding)

                # Alternatives = remaining top matches.
                for alt in matches[1:5]:
                    alt_binding = self._make_binding(
                        alt,
                        candidate,
                        actor_id,
                        session_id,
                        role="alternative",
                        source=source,
                        confidence=confidence,
                    )
                    if alt_binding.binding_id not in seen_binding_ids:
                        seen_binding_ids.add(alt_binding.binding_id)
                        alternatives.append(alt_binding)

                # ── Constitution-driven prerequisites + companions + verifier ──
                # Use the resolved capability's connector_id so direct candidates
                # (connector_id="") still get their constitution roles.
                effective_connector_id = candidate.connector_id or best.connector_id
                if constitution_loader is not None and effective_connector_id:
                    self._bind_constitution_roles(
                        candidate,
                        effective_connector_id,
                        actor_id,
                        session_id,
                        constitution_loader,
                        prerequisites,
                        companions,
                        verifiers,
                        verifier_links,
                        seen_binding_ids,
                        is_write=is_write,
                        primary_capability=best,
                    )

        all_for_cards = []
        if primary is not None:
            all_for_cards.append(primary)
        all_for_cards.extend(prerequisites)
        all_for_cards.extend(companions)
        all_for_cards.extend(verifiers)
        all_for_cards.extend(alternatives)

        tool_name_cards = [
            {"name": b.capability_name, "description": b.effect_summary, "role": b.role}
            for b in all_for_cards
        ]

        selected_schema_cards: list[dict] = []
        if disclosure_phase == "schema_binding":
            committed = set(committed_tool_names or [])
            for b in all_for_cards:
                if b.capability_name in committed:
                    selected_schema_cards.append(
                        {
                            "capability_name": b.capability_name,
                            "binding_id": b.binding_id,
                            "input_schema_ref": b.input_schema_ref,
                            "output_schema_ref": b.output_schema_ref,
                        }
                    )

        if not all_for_cards and not unbound:
            diagnostics.append("no resource candidates available for binding")

        return BindingBundle(
            bundle_id="bundle-" + uuid.uuid4().hex[:16],
            resolution_id=resolution_id,
            primary=primary,
            companions=companions,
            prerequisites=prerequisites,
            verifiers=verifiers,
            alternatives=alternatives,
            unbound_roles=unbound,
            tool_name_cards=tool_name_cards,
            selected_schema_cards=selected_schema_cards,
            guide_refs=list(policy_bundle.guide_refs),
            verifier_links=verifier_links,
            binding_diagnostics=diagnostics,
            disclosure_phase=disclosure_phase,
        )

    def commit_tool_selection(
        self,
        binding_bundle: BindingBundle,
        committed_tool_names: list[str],
    ) -> ToolSelectionCommit:
        """Phase 2 gate: every committed tool name must exist in the bundle."""
        available = {b.capability_name for b in binding_bundle.all_bindings}
        rejected = [n for n in committed_tool_names if n not in available]
        accepted = [n for n in committed_tool_names if n in available]
        if rejected:
            return ToolSelectionCommit(
                committed_tool_names=accepted,
                rejected_tool_names=rejected,
                accepted=False,
                reason=(
                    "Unknown tools: "
                    + ", ".join(rejected)
                    + ". Available: "
                    + ", ".join(sorted(available))
                ),
            )
        return ToolSelectionCommit(
            committed_tool_names=accepted,
            rejected_tool_names=[],
            accepted=True,
            reason=None,
        )

    def refresh_binding(self, binding_id: str) -> CapabilityBinding:
        """Refresh a binding's TTL.

        Bindings are stateless (derived from inputs), so a standalone refresh
        requires the original inputs.  Raises ``KeyError`` to signal the caller
        must re-bind.
        """
        raise KeyError(f"binding refresh requires original binding inputs: {binding_id}")

    # ── 3-pass discovery ───────────────────────────────────────────

    def _find_all_capabilities(
        self,
        candidate: ResourceCandidate,
        intent: ResolvedIntentType,
        invocation_mode: str,
        effect: str,
        *,
        action_text: str,
    ) -> tuple[list[CapabilityRecord], str]:
        """Return (matches, source) using typed → exact → BM25 passes."""
        cid = candidate.connector_id or None

        # ── Pass 1: typed graph results ──
        typed: list[CapabilityRecord] = []
        for tc in intent.fallback_capabilities:
            tc_cid = tc.get("connector_id", "")
            tc_effect = tc.get("effect", "")
            connector_ok = (not tc_cid) or (cid is None) or (tc_cid == cid)
            effect_ok = (not tc_effect) or (tc_effect == effect)
            if connector_ok and effect_ok:
                cap_name = tc.get("capability_name", "")
                if cap_name:
                    full = self.global_store.get_capability(cap_name)
                    if full is not None and full not in typed:
                        typed.append(full)
        if typed:
            return typed, "typed_intent"

        # ── Pass 2: exact structured match ──
        resource_kind = candidate.resource_kind or (intent.resource_family or "")
        if resource_kind:
            exact = self.global_store.find_capabilities(
                resource_kind=resource_kind,
                invocation_mode=invocation_mode,
                effect=effect,
                connector_id=cid,
            )
            if exact:
                return exact, "exact_match"

        # ── Pass 3: BM25 semantic fallback ──
        if action_text:
            connector_ids = [cid] if cid else None
            fts = self.global_store.search_capabilities(
                action_text, top_k=10, connector_ids=connector_ids
            )
            filtered = [c for c in fts if c.effect == effect]
            if filtered:
                return filtered, "bm25_search"

        return [], "none"

    # ── Constitution-driven roles ──────────────────────────────────

    def _bind_constitution_roles(
        self,
        candidate: ResourceCandidate,
        connector_id: str,
        actor_id: str,
        session_id: str,
        loader: ConstitutionLoader,
        prerequisites: list[CapabilityBinding],
        companions: list[CapabilityBinding],
        verifiers: list[CapabilityBinding],
        verifier_links: list[dict],
        seen: set[str],
        *,
        is_write: bool,
        primary_capability: CapabilityRecord,
    ) -> None:
        artifact = loader.load(connector_id)
        if artifact is None:
            return

        # Prerequisites: read capabilities the constitution requires first.
        if is_write and artifact.prerequisite_reads:
            for pr in artifact.prerequisite_reads:
                read_caps = self.global_store.find_capabilities(
                    resource_kind=pr.resource_kind or candidate.resource_kind,
                    invocation_mode="read",
                    effect="read",
                    connector_id=connector_id,
                )
                if read_caps:
                    b = self._make_binding(
                        read_caps[0],
                        candidate,
                        actor_id,
                        session_id,
                        role="prerequisite",
                        source="constitution",
                        confidence="high",
                    )
                    if b.binding_id not in seen:
                        seen.add(b.binding_id)
                        prerequisites.append(b)

        # Companions: resources the constitution names as companions.
        for comp in artifact.companion_resource_roles:
            comp_caps = self.global_store.find_capabilities(
                resource_kind=comp.resource_kind,
                invocation_mode="read",
                effect="read",
                connector_id=connector_id,
            )
            if comp_caps:
                b = self._make_binding(
                    comp_caps[0],
                    candidate,
                    actor_id,
                    session_id,
                    role="companion",
                    source="constitution",
                    confidence="medium",
                )
                if b.binding_id not in seen:
                    seen.add(b.binding_id)
                    companions.append(b)

        # Verifier link for write primaries.
        if is_write and artifact.verification_requirements:
            method = artifact.verification_requirements[0].method
            verifier_links.append(
                {
                    "capability_name": primary_capability.capability_name,
                    "connector_id": connector_id,
                    "verification": method,
                }
            )

    # ── Binding construction ───────────────────────────────────────

    def _make_binding(
        self,
        capability: CapabilityRecord,
        candidate: ResourceCandidate,
        actor_id: str,
        session_id: str,
        *,
        role: str,
        source: str,
        confidence: str,
    ) -> CapabilityBinding:
        now = datetime.now(timezone.utc)
        verifier_ref = None
        if role == "primary" and capability.effect in _WRITE_EFFECTS:
            verifier_ref = f"verifier:{capability.connector_id}:{capability.action_name}"
        return CapabilityBinding(
            binding_id=_make_binding_id(
                candidate.connector_id,
                capability.capability_name,
                candidate.resource_id,
                actor_id,
                session_id,
            ),
            capability_name=capability.capability_name,
            connector_id=candidate.connector_id or capability.connector_id,
            invocation_mode=capability.invocation_mode,
            action_name=capability.action_name,
            effect=capability.effect,
            resource_kind=capability.resource_kind or candidate.resource_kind,
            resource_id=candidate.resource_id,
            role=role,
            confidence=confidence,
            source=source,
            input_schema_ref=_input_schema_ref(capability),
            output_schema_ref=capability.output_schema_ref,
            required_inputs=list(capability.required_inputs),
            optional_inputs=list(capability.optional_inputs),
            effect_summary=capability.description or capability.capability_name,
            safety_requirement=capability.safety_band_min or "GREEN",
            authority_verdict="bound",
            verifier_ref=verifier_ref,
            guide_refs=[],
            freshness_state=candidate.freshness_state,
            limitations=[],
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=_BINDING_TTL_SECONDS)).isoformat(),
        )

    @staticmethod
    def _mode_effect(intent: ResolvedIntentType) -> tuple[str, str]:
        """Map a typed intent to (invocation_mode, effect)."""
        mapped = UNIVERSAL_ACTION_MAP.get(intent.operation_family)
        if mapped is not None:
            return mapped
        # Fall back to the intent's declared effect.
        if intent.effect in _WRITE_EFFECTS:
            return "execute", intent.effect
        return "read", "read"


# ── Module helpers ─────────────────────────────────────────────────────


def _make_binding_id(
    connector_id: str,
    capability_name: str,
    resource_id: str,
    actor_id: str,
    session_id: str,
) -> str:
    raw = f"{connector_id}:{capability_name}:{resource_id}:{actor_id}:{session_id}"
    return "bind_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _input_schema_ref(capability: CapabilityRecord) -> str | None:
    """Reference to the capability's input schema (full schema in contract_json)."""
    contract = capability.contract_json or {}
    if contract.get("input_schema"):
        return f"capability:{capability.capability_name}#input_schema"
    if capability.required_inputs:
        return f"capability:{capability.capability_name}#required_inputs"
    return None
