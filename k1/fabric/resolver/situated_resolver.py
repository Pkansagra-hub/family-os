"""ResolveSituationService — RES-010/012 simplified (2026-06-17).

Single-pass resolver: connector search → tools fetch → envelope.
Verdict is always can_execute.  No blocking cascade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.resolver.capability_binder import (
    CapabilityBinderService,
)
from k1.fabric.resolver.capability_type_resolver import (
    ConnectorResolver,
)
from k1.fabric.resolver.request_frame import RequestFrame
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

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
    """Resolution packet returned to Back.  RES-002 (2026-06-16).

    Hard-purge of old fields: no request_frame, candidate_universe,
    intent_resolutions, policy_bundle, binding_bundle, prompt_pack,
    allowed_capability_names, capability_name_to_binding, hil_request,
    recovery_directive, execution_plan, machine_verdict.

    Back receives a clean packet: connector + tools + constitution +
    confidence + alternatives.
    """

    verdict: str = "can_execute"  # ALWAYS "can_execute"
    connectors: list[dict] = field(default_factory=list)
    # [{connector_id, label, description, score,
    #   tools: [{capability_name, action_name, invocation_mode,
    #            effect, description, required_inputs, optional_inputs}],
    #   constitution: {precondition_summary, how_to_sequence,
    #                  what_to_verify, companion_connectors,
    #                  when_to_ask_human, conflict_rules}}]
    search_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "connectors": self.connectors,
            "search_confidence": self.search_confidence,
        }


# ── Service ────────────────────────────────────────────────────────────


class ResolveSituationService:
    """Single-pass resolver: connector search → tools → envelope."""

    def __init__(
        self,
        global_store: GlobalProjectionStore,
        local_store: LocalProjectionStore,
        *,
        connector_resolver: ConnectorResolver | None = None,
        capability_binder: CapabilityBinderService | None = None,
        constitution_loader: ConstitutionLoader | None = None,
    ) -> None:
        self.global_store = global_store
        self.local_store = local_store
        self.connector_resolver = connector_resolver or ConnectorResolver(global_store)
        self.capability_binder = capability_binder or CapabilityBinderService(global_store)
        self.constitution_loader = constitution_loader or ConstitutionLoader(global_store)

    # ── Public API ─────────────────────────────────────────────────

    def resolve(self, request: ResolveSituationRequest) -> ResolutionEnvelope:
        """Full resolution pipeline — RES-010 simplified."""
        frame = request.frame

        action_text = frame.intents[0].action if frame.intents else ""
        connector_hits = self.connector_resolver.resolve(action_text)

        # RES-010: bind() now returns all connectors with tools+constitutions
        connector_dicts = self.capability_binder.bind(
            connector_hits,
            actor_id=request.actor_id,
            session_id=request.session_id,
            constitution_loader=self.constitution_loader,
        )

        # RES-011b: inject session-aware dynamic enums
        for cd in connector_dicts:
            cd["tools"] = self._inject_session_aware_enums(
                cd["tools"], request.session_id, cd["connector_id"]
            )

        search_confidence = connector_dicts[0]["score"] if connector_dicts else 0.0

        envelope = ResolutionEnvelope(
            verdict="can_execute",
            connectors=connector_dicts,
            search_confidence=search_confidence,
        )

        return envelope

    # ── RES-011b: Dynamic enum injection (2026-06-17) ──────────────────

    def _inject_session_aware_enums(
        self,
        tools: list[Any],
        session_id: str,
        connector_id: str,
    ) -> list[Any]:
        """Populate dynamic enum values from LPS connected backends.

        For each tool input with ``enum_source == "lps.connected_backends"``,
        query LPS for the session's connected backends and replace the
        static placeholder with live enum values.
        """
        if not session_id or not connector_id:
            return tools

        try:
            connected = self.local_store.get_connected_backends(session_id, connector_id)
        except Exception:
            return tools  # LPS unavailable — return tools with empty enums

        backend_ids = [r.get("backend_id", "") for r in connected if r.get("backend_id")]
        backend_labels = [r.get("label", "") for r in connected if r.get("label")]

        for tool in tools:
            for inp in tool.get("required_inputs", []) or []:
                if inp.get("enum_source") == "lps.connected_backends":
                    inp["enum"] = list(backend_ids)
                    inp["enum_labels"] = list(backend_labels)
                    if not backend_ids:
                        inp["enum"] = ["__no_connected_backends__"]
                        inp["description"] = (
                            inp.get("description", "")
                            + " (No backends connected. Connect a backend first.)"
                        )
            for inp in tool.get("optional_inputs", []) or []:
                if inp.get("enum_source") == "lps.connected_backends":
                    inp["enum"] = list(backend_ids)
                    inp["enum_labels"] = list(backend_labels)
                    if not backend_ids:
                        inp["enum"] = ["__no_connected_backends__"]

        return tools

    # ── Verdict (RES-012a: always can_execute, 2026-06-17) ─────────

    def _determine_verdict(self) -> tuple[str, str | None]:
        return "can_execute", None
