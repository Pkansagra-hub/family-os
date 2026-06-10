"""PromptPackBuilder — Epic 6.3.

Builds the LLM-facing prompt pack from a ``ResolutionEnvelope``.  5 disclosure
phases gate field visibility; redaction leak detection (triple-checked on
source, pack, and rendered output) ensures no secret markers reach the LLM.

Constitution cards are built from the typed ``ConstitutionLoader`` (Epic 5.2),
never raw store dicts.  Stale cards are flagged, not hidden.

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epic 6.3.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.resolver.situated_resolver import ResolutionEnvelope
from k1.fabric.stores.global_projection_store import GlobalProjectionStore

# ── Redaction ──────────────────────────────────────────────────────────
SECRET_MARKERS: tuple[str, ...] = (
    "token",
    "secret",
    "credential",
    "oauth",
    "password",
    "bearer",
    "api_key",
    "authorization",
)
SECRET_KEY_EXCEPTIONS: frozenset[str] = frozenset(
    {"max_prompt_tokens", "prompt_budget", "prompt_budget_tokens"}
)

# ── Phase whitelist ────────────────────────────────────────────────────
PHASE_ALLOWED_FIELDS: dict[str, set[str]] = {
    "loop_start": {"candidate_summary", "uncertainty_markers"},
    "connector_summary": {
        "connector_constitution_cards",
        "tool_name_cards",
        "policy_cards",
        "guide_cards",
        "candidate_summary",
        "omission_summary",
        "allowed_next_actions",
        "forbidden_tool_calls",
    },
    "tool_name_selection": {
        "tool_name_cards",
        "allowed_next_actions",
        "decision_surface",
        "hil_options",
    },
    "schema_binding": {"selected_schema_cards", "allowed_tool_calls"},
    "execution": {"allowed_tool_calls", "allowed_next_actions"},
    "post_execution": {"candidate_summary"},
}

_PROMPT_PACK_TTL_MINUTES = 5


# ── Errors ─────────────────────────────────────────────────────────────


class PromptPackError(ValueError):
    pass


class PromptPackPhaseError(PromptPackError):
    pass


class PromptPackLeakError(PromptPackError):
    pass


# ── Cards ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConstitutionCard:
    connector_id: str
    label: str
    preconditions: list[str]
    companion_resource_roles: dict[str, Any]
    verification_requirement: str
    stale: bool = False


@dataclass(frozen=True)
class ToolNameCard:
    capability_name: str
    description: str
    role: str
    stale: bool = False


@dataclass(frozen=True)
class PolicyCard:
    connector_id: str
    what_is_required: str
    what_triggers_hil: list[str]
    what_is_denied: list[str]
    stale: bool = False


@dataclass(frozen=True)
class GuideCard:
    guide_id: str
    title: str
    content: str
    relevance: str
    stale: bool = False


@dataclass(frozen=True)
class SchemaCard:
    capability_name: str
    binding_id: str
    input_schema: dict[str, Any]
    required_fields: list[str]
    optional_fields: list[str]
    stale: bool = False


@dataclass(frozen=True)
class RedactionEvidence:
    redaction_id: str
    prompt_hash: str
    fields_redacted: list[str]
    fields_verified_absent: list[str]
    prompt_visible_leak_count: int
    verdict: str


# ── PromptPack ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PromptPack:
    prompt_pack_id: str
    react_state: str
    target_tier: str
    disclosure_phase: str
    source_refs: list[str]
    source_versions: dict[str, str]
    candidate_summary: dict[str, Any]
    connector_constitution_cards: list[ConstitutionCard]
    tool_name_cards: list[ToolNameCard]
    policy_cards: list[PolicyCard]
    guide_cards: list[GuideCard]
    selected_schema_cards: list[SchemaCard]
    decision_surface: str
    uncertainty_markers: list[str]
    omission_summary: str
    allowed_tool_calls: list[str]
    forbidden_tool_calls: list[str]
    allowed_next_actions: list[str]
    hil_options: list[dict[str, Any]]
    redaction_summary: RedactionEvidence
    expires_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Builder ────────────────────────────────────────────────────────────


class PromptPackBuilder:
    """Builds redaction-proof, phase-gated prompt packs from resolution envelopes."""

    def __init__(
        self,
        global_store: GlobalProjectionStore,
        *,
        constitution_loader: ConstitutionLoader | None = None,
    ) -> None:
        self.global_store = global_store
        self.constitution_loader = constitution_loader or ConstitutionLoader(global_store)

    # ── Public API ─────────────────────────────────────────────────

    def build(
        self,
        resolution_envelope: ResolutionEnvelope,
        *,
        disclosure_phase: str,
        prompt_budget_tokens: int = 8000,
        committed_tool_names: list[str] | None = None,
    ) -> PromptPack:
        if disclosure_phase not in PHASE_ALLOWED_FIELDS:
            raise PromptPackPhaseError(f"unknown disclosure_phase {disclosure_phase}")
        if disclosure_phase == "schema_binding" and not committed_tool_names:
            raise PromptPackPhaseError("schema_binding requires committed_tool_names")

        # 1. Redaction check on the source envelope.
        source = redaction_check(resolution_envelope.to_dict())
        if source["verdict"] != "pass":
            raise PromptPackLeakError(
                f"source envelope leaks restricted fields: {source['fields_with_leaks']}"
            )

        candidate_summary = _candidate_summary(resolution_envelope)
        constitution_cards = self._constitution_cards(resolution_envelope)
        tool_name_cards = self._tool_name_cards(resolution_envelope)
        policy_cards = _policy_cards(resolution_envelope)
        guide_cards = self._guide_cards(resolution_envelope)
        schema_cards = self._schema_cards(resolution_envelope, committed_tool_names or [])
        forbidden = _forbidden_tool_calls(resolution_envelope)

        now = datetime.now(timezone.utc)
        pack = PromptPack(
            prompt_pack_id="prompt-pack-" + uuid.uuid4().hex[:16],
            react_state=_react_state(resolution_envelope.verdict),
            target_tier=resolution_envelope.request_frame.target_tier,
            disclosure_phase=disclosure_phase,
            source_refs=[resolution_envelope.resolution_id, resolution_envelope.request_id],
            source_versions={"resolution_envelope": "v1", "prompt_pack": "p1"},
            candidate_summary=candidate_summary,
            connector_constitution_cards=constitution_cards,
            tool_name_cards=tool_name_cards,
            policy_cards=policy_cards,
            guide_cards=guide_cards,
            selected_schema_cards=schema_cards,
            decision_surface=_decision_surface(resolution_envelope),
            uncertainty_markers=_uncertainty_markers(resolution_envelope),
            omission_summary=_omission_summary(resolution_envelope),
            allowed_tool_calls=list(resolution_envelope.allowed_capability_names),
            forbidden_tool_calls=forbidden,
            allowed_next_actions=list(resolution_envelope.allowed_next_actions),
            hil_options=_hil_options(resolution_envelope),
            redaction_summary=RedactionEvidence(
                redaction_id="redaction-pending",
                prompt_hash="pending",
                fields_redacted=[],
                fields_verified_absent=["restricted_prompt_fields"],
                prompt_visible_leak_count=0,
                verdict="pending",
            ),
            expires_at=(now + timedelta(minutes=_PROMPT_PACK_TTL_MINUTES)).isoformat(),
        )

        # 2. Apply phase whitelist.
        phase_pack = _apply_phase(pack, disclosure_phase)

        # 3. Redaction check on the rendered-shape pack (excluding the
        #    redaction_summary itself, which is computed below).
        checked = phase_pack.to_dict()
        checked.pop("redaction_summary", None)
        pack_check = redaction_check(checked)
        if pack_check["verdict"] != "pass":
            raise PromptPackLeakError(
                f"prompt pack leaks restricted fields: {pack_check['fields_with_leaks']}"
            )

        prompt_hash = hashlib.sha256(
            json.dumps(checked, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        return replace(
            phase_pack,
            redaction_summary=RedactionEvidence(
                redaction_id="redaction-" + uuid.uuid4().hex[:12],
                prompt_hash=prompt_hash,
                fields_redacted=[],
                fields_verified_absent=["restricted_prompt_fields"],
                prompt_visible_leak_count=int(pack_check["prompt_visible_leak_count"]),
                verdict="pass",
            ),
        )

    def render(self, pack: PromptPack, *, budget_tokens: int | None = None) -> str:
        """Render a pack to markdown, with a final redaction check on the output."""
        lines: list[str] = ["## Situated Execution Update", f"Phase: {pack.disclosure_phase}"]

        if pack.candidate_summary:
            lines.append("## Candidate Summary")
            lines.append(json.dumps(pack.candidate_summary, sort_keys=True))

        for card in pack.connector_constitution_cards:
            stale = " (STALE)" if card.stale else ""
            lines.append(f"## Connector Guide: {card.label}{stale}")
            if card.preconditions:
                lines.append("Before action: " + "; ".join(card.preconditions))
            lines.append("After write: " + card.verification_requirement)

        if pack.tool_name_cards:
            lines.append("## Available Actions")
            for card in pack.tool_name_cards:
                stale = " (STALE)" if card.stale else ""
                lines.append(
                    f"{card.capability_name}: {card.description} (role: {card.role}){stale}"
                )

        for card in pack.policy_cards:
            lines.append("## Policy")
            lines.append("Allowed: " + card.what_is_required)
            if card.what_triggers_hil:
                lines.append("Human review: " + "; ".join(card.what_triggers_hil))
            if card.what_is_denied:
                lines.append("Denied: " + "; ".join(card.what_is_denied))

        for card in pack.guide_cards:
            lines.append(f"## Guide: {card.title}")
            lines.append(card.content)

        for card in pack.selected_schema_cards:
            lines.append(f"## Schema for {card.capability_name}")
            lines.append("Required fields: " + ", ".join(card.required_fields))
            lines.append("```json")
            lines.append(json.dumps(card.input_schema, indent=2, sort_keys=True))
            lines.append("```")

        if pack.allowed_next_actions:
            lines.append("## You may do:")
            lines.extend(pack.allowed_next_actions)

        if pack.forbidden_tool_calls:
            lines.append("## You must NOT do yet:")
            lines.extend(pack.forbidden_tool_calls)

        if pack.omission_summary:
            lines.append("## Note: Some connectors were excluded")
            lines.append(pack.omission_summary)

        rendered = "\n".join(lines)

        # Final redaction check on the rendered string.
        if redaction_check({"rendered": rendered})["verdict"] != "pass":
            raise PromptPackLeakError("rendered prompt pack leaks restricted fields")

        budget = (
            budget_tokens
            if budget_tokens is not None
            else max(1, len(pack.allowed_tool_calls) or len(pack.tool_name_cards)) * 200
        )
        return _truncate_rendered(rendered, budget)

    # ── Card builders ──────────────────────────────────────────────

    def _constitution_cards(self, envelope: ResolutionEnvelope) -> list[ConstitutionCard]:
        cards: list[ConstitutionCard] = []
        seen: set[str] = set()
        universe = envelope.candidate_universe
        if universe is None:
            return cards
        # Build a connector_id → stale map from candidates.
        stale_connectors = {
            c.connector_id
            for c in universe.resource_candidates
            if c.freshness_state == "stale" and c.connector_id
        }
        # Resolve connector_ids from bindings (real connector) + candidates.
        connector_ids: list[str] = []
        if envelope.binding_bundle is not None:
            for b in envelope.binding_bundle.all_bindings:
                if b.connector_id and b.connector_id not in connector_ids:
                    connector_ids.append(b.connector_id)
        for c in universe.resource_candidates:
            if c.connector_id and c.connector_id not in connector_ids:
                connector_ids.append(c.connector_id)

        for connector_id in connector_ids:
            if connector_id in seen:
                continue
            seen.add(connector_id)
            artifact = self.constitution_loader.load(connector_id)
            connector = self.global_store.get_connector(connector_id)
            label = connector.label if connector else connector_id
            if artifact is None:
                cards.append(
                    ConstitutionCard(
                        connector_id=connector_id,
                        label=label,
                        preconditions=[],
                        companion_resource_roles={},
                        verification_requirement="none",
                        stale=connector_id in stale_connectors,
                    )
                )
                continue
            preconditions = [
                f"{pr.operation} {pr.resource_kind}: {pr.reason}"
                for pr in artifact.prerequisite_reads
            ]
            companions = {
                comp.resource_kind: comp.role for comp in artifact.companion_resource_roles
            }
            verification = (
                artifact.verification_requirements[0].method
                if artifact.verification_requirements
                else "none"
            )
            cards.append(
                ConstitutionCard(
                    connector_id=connector_id,
                    label=label,
                    preconditions=preconditions,
                    companion_resource_roles=companions,
                    verification_requirement=verification,
                    stale=connector_id in stale_connectors,
                )
            )
        return cards

    def _tool_name_cards(self, envelope: ResolutionEnvelope) -> list[ToolNameCard]:
        if envelope.binding_bundle is None:
            return []
        stale_by_cap = {
            b.capability_name: (b.freshness_state == "stale")
            for b in envelope.binding_bundle.all_bindings
        }
        cards: list[ToolNameCard] = []
        for card in envelope.binding_bundle.tool_name_cards:
            name = str(card["name"])
            cards.append(
                ToolNameCard(
                    capability_name=name,
                    description=str(card["description"]),
                    role=str(card["role"]),
                    stale=stale_by_cap.get(name, False),
                )
            )
        return cards

    def _guide_cards(self, envelope: ResolutionEnvelope) -> list[GuideCard]:
        # Two sources, deduplicated by guide_id:
        #   1. Connector-declared guide cards persisted on the ConnectorRecord
        #      by register_definition_to_store (Phase 1.1, Epics 9-13).
        #   2. Policy-referenced guide refs from the policy bundle (Phase 1).
        cards: list[GuideCard] = []
        seen_ids: set[str] = set()

        connector_ids: list[str] = []
        if envelope.binding_bundle is not None:
            for b in envelope.binding_bundle.all_bindings:
                cid = getattr(b, "connector_id", "")
                if cid and cid not in connector_ids:
                    connector_ids.append(cid)

        for cid in connector_ids:
            connector = self.global_store.get_connector(cid)
            if connector is None:
                continue
            for raw in connector.guide_cards or []:
                gid = str(raw.get("guide_id", ""))
                if not gid or gid in seen_ids:
                    continue
                seen_ids.add(gid)
                cards.append(
                    GuideCard(
                        guide_id=gid,
                        title=str(raw.get("title", "")),
                        content=str(raw.get("content", "")),
                        relevance=str(raw.get("relevance", "always")),
                    )
                )

        if envelope.policy_bundle is not None:
            for ref in envelope.policy_bundle.guide_refs:
                gid = str(ref)
                if not gid or gid in seen_ids:
                    continue
                seen_ids.add(gid)
                cards.append(
                    GuideCard(
                        guide_id=gid,
                        title="Execution guide",
                        content=(
                            "Follow the allowed action order; refresh after "
                            "prerequisites complete."
                        ),
                        relevance="Referenced by policy bundle for this request.",
                    )
                )

        return cards

    def _schema_cards(
        self,
        envelope: ResolutionEnvelope,
        committed_tool_names: list[str],
    ) -> list[SchemaCard]:
        if envelope.binding_bundle is None or not committed_tool_names:
            return []
        committed = set(committed_tool_names)
        cards: list[SchemaCard] = []
        for b in envelope.binding_bundle.all_bindings:
            if b.capability_name not in committed:
                continue
            record = self.global_store.get_capability(b.capability_name)
            if record is None:
                continue
            required = [str(f.get("name")) for f in record.required_inputs if f.get("name")]
            optional = [str(f.get("name")) for f in record.optional_inputs if f.get("name")]
            contract = record.contract_json or {}
            input_schema = contract.get("input_schema") or _input_schema(required, optional)
            cards.append(
                SchemaCard(
                    capability_name=b.capability_name,
                    binding_id=b.binding_id,
                    input_schema=input_schema,
                    required_fields=required,
                    optional_fields=optional,
                    stale=(b.freshness_state == "stale"),
                )
            )
        return cards


# ── Redaction ──────────────────────────────────────────────────────────


def redaction_check(record: Any) -> dict[str, Any]:
    """Walk a record and flag any key/value containing a secret marker."""
    leaks: list[str] = []
    checked = 0

    def walk(value: Any, path: str) -> None:
        nonlocal checked
        if isinstance(value, dict):
            for key, child in value.items():
                key_path = f"{path}.{key}" if path else str(key)
                checked += 1
                key_lower = str(key).lower()
                if key_lower not in SECRET_KEY_EXCEPTIONS and any(
                    marker in key_lower for marker in SECRET_MARKERS
                ):
                    leaks.append(key_path)
                walk(child, key_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif isinstance(value, str):
            checked += 1
            lower = value.lower()
            if any(marker in lower for marker in SECRET_MARKERS):
                leaks.append(path)

    walk(record, "")
    unique = sorted({item for item in leaks if item})
    return {
        "fields_checked": checked,
        "fields_with_leaks": unique,
        "prompt_visible_leak_count": len(unique),
        "verdict": "pass" if not unique else "fail",
    }


# ── Phase application ──────────────────────────────────────────────────


def _apply_phase(pack: PromptPack, phase: str) -> PromptPack:
    allowed = PHASE_ALLOWED_FIELDS[phase]
    return replace(
        pack,
        candidate_summary=pack.candidate_summary if "candidate_summary" in allowed else {},
        connector_constitution_cards=(
            pack.connector_constitution_cards if "connector_constitution_cards" in allowed else []
        ),
        tool_name_cards=pack.tool_name_cards if "tool_name_cards" in allowed else [],
        policy_cards=pack.policy_cards if "policy_cards" in allowed else [],
        guide_cards=pack.guide_cards if "guide_cards" in allowed else [],
        selected_schema_cards=(
            pack.selected_schema_cards if "selected_schema_cards" in allowed else []
        ),
        decision_surface=pack.decision_surface if "decision_surface" in allowed else "",
        uncertainty_markers=pack.uncertainty_markers if "uncertainty_markers" in allowed else [],
        omission_summary=pack.omission_summary if "omission_summary" in allowed else "",
        allowed_tool_calls=pack.allowed_tool_calls if "allowed_tool_calls" in allowed else [],
        forbidden_tool_calls=(
            pack.forbidden_tool_calls if "forbidden_tool_calls" in allowed else []
        ),
        allowed_next_actions=(
            pack.allowed_next_actions if "allowed_next_actions" in allowed else []
        ),
        hil_options=pack.hil_options if "hil_options" in allowed else [],
    )


# ── Summary helpers ────────────────────────────────────────────────────


def _candidate_summary(envelope: ResolutionEnvelope) -> dict[str, Any]:
    universe = envelope.candidate_universe
    if universe is None:
        return {"verdict": envelope.verdict}
    return {
        "connectors": sorted(
            {c.connector_id for c in universe.resource_candidates if c.connector_id}
        ),
        "resources": [
            {
                "label": r.label,
                "kind": r.resource_kind,
                "freshness": r.freshness_state,
                "permission": r.actor_permission,
            }
            for r in universe.resource_candidates
        ],
        "people": [{"label": p.label, "role": p.role} for p in universe.person_candidates],
        "verdict": envelope.verdict,
        "freshness": universe.freshness,
        "completeness": universe.completeness,
    }


def _policy_cards(envelope: ResolutionEnvelope) -> list[PolicyCard]:
    bundle = envelope.policy_bundle
    if bundle is None:
        return []
    denied: list[str] = []
    if bundle.deny_reason:
        denied.append(bundle.deny_reason)
    if envelope.binding_bundle is not None:
        denied.extend(role.reason for role in envelope.binding_bundle.unbound_roles)
    return [
        PolicyCard(
            connector_id=connector_id,
            what_is_required=json.dumps(bundle.roles_allowed, sort_keys=True),
            what_triggers_hil=[json.dumps(item, sort_keys=True) for item in bundle.hil_triggers],
            what_is_denied=sorted(set(denied)),
        )
        for connector_id in bundle.connector_ids
    ]


def _forbidden_tool_calls(envelope: ResolutionEnvelope) -> list[str]:
    allowed = set(envelope.allowed_capability_names)
    forbidden: list[str] = []
    if envelope.binding_bundle is not None:
        for b in envelope.binding_bundle.all_bindings:
            if b.capability_name not in allowed:
                forbidden.append(f"{b.capability_name} is not allowed in this phase")
    return forbidden


def _hil_options(envelope: ResolutionEnvelope) -> list[dict[str, Any]]:
    if envelope.hil_request is None:
        return []
    return [envelope.hil_request]


def _uncertainty_markers(envelope: ResolutionEnvelope) -> list[str]:
    universe = envelope.candidate_universe
    if universe is None:
        return []
    markers = [u.reason for u in universe.unresolved]
    if universe.freshness != "fresh":
        markers.append("freshness_" + universe.freshness)
    return sorted(set(markers))


def _omission_summary(envelope: ResolutionEnvelope) -> str:
    universe = envelope.candidate_universe
    if universe is None:
        return ""
    omissions = universe.scope_proof.omissions
    if not omissions:
        return ""
    return "; ".join(str(o.get("reason") or "omitted") for o in omissions)


def _decision_surface(envelope: ResolutionEnvelope) -> str:
    return f"verdict={envelope.verdict}; next_actions={len(envelope.allowed_next_actions)}"


def _react_state(verdict: str) -> str:
    if verdict == "can_execute_with_gate":
        return "needs_prerequisite"
    if verdict == "can_execute":
        return "ready_to_execute"
    if verdict in {"needs_disambiguation", "needs_hil"}:
        return "needs_hil"
    return "blocked"


def _input_schema(required: list[str], optional: list[str]) -> dict[str, Any]:
    properties = {f: {"type": "string"} for f in [*required, *optional]}
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _truncate_rendered(text: str, budget: int) -> str:
    words = text.split()
    if len(words) <= budget:
        return text
    return " ".join(words[:budget]) + " …[truncated]"
