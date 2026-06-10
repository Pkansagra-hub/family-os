"""
k1.fabric.manifest_translator -- ``ToolDefinition`` -> Fabric registration.

This module is the single bridge between the declarative family-tool
manifest (``k1.tools.family.ToolDefinition``) and the Fabric capability
surface.  For every ``ActionSpec`` declared on a definition it builds
exactly one ``CapabilityContract`` and registers it with the supplied
``CapabilityRegistry`` so that:

* The action becomes discoverable in the Fabric capability catalog
  (LLM tools, planner, workflows).
* Safety-band gating, risk classification, and provider routing all
  flow through the standard Fabric pipeline.
* The provider hand-off is unified: every family-tool action resolves
  to ``provider_type="LOCAL"``, ``provider_id="k1_native_tools"`` --
  which the boot wiring (§E15.0.10) connects to
  ``NativeToolProvider``.

Capability name convention
--------------------------
* ``ActionKind`` ``"read"`` -> ``tool.read.{adapter_id}.{action_name}``.
* All other kinds (``write``, ``delete``, ``compute``) ->
  ``tool.execute.{adapter_id}.{action_name}``.

Both shapes satisfy ``CapabilityRequest`` validation
(``tool.*`` prefix) and let downstream policy infer side-effect
semantics from the name alone.

References
----------
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.0 -- manifest translator.
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.7 -- NativeToolProvider.
* Plan invariant: all family-tool capabilities share one provider_id
  so a single in-process provider satisfies them all.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from k1.fabric.types import CapabilityContract, InputSpec, SafetyBand

if TYPE_CHECKING:  # pragma: no cover -- typing only
    from k1.fabric.core.registry import CapabilityRegistry
    from k1.fabric.stores.global_projection_store import GlobalProjectionStore
    from k1.tools.family.definition import (
        ActionKind,
        ActionSpec,
        FieldSpec,
        ToolDefinition,
    )

# ---------------------------------------------------------------------------
# Constants -- shared with NativeToolProvider
# ---------------------------------------------------------------------------

NATIVE_PROVIDER_TYPE: str = "LOCAL"
"""Provider-type string for in-process K1-native tool services.

This is intentionally *not* a member of ``k1.fabric.types.ProviderType``
yet: ``ProviderFactory`` accepts any string handler key, so the enum is
optional.  Promoting to the enum is a future hygiene step that does not
gate M15 delivery.
"""

NATIVE_PROVIDER_ID: str = "k1_native_tools"
"""Unique provider id every family-tool capability resolves to."""

NATIVE_PROVIDER_ENDPOINT: str = "local://k1_native_tools"
"""Synthetic endpoint string -- in-process providers have no network endpoint."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capability_name(adapter_id: str, action: "ActionSpec") -> str:
    """Return the canonical Fabric capability name for ``action``."""

    prefix = "tool.read" if action.kind == "read" else "tool.execute"
    return f"{prefix}.{adapter_id}.{action.name}"


def _kind_to_capability_prefix(kind: "ActionKind") -> str:
    """Public helper: return the Fabric capability prefix for an action kind."""

    return "tool.read" if kind == "read" else "tool.execute"


def _field_to_input_spec(f: "FieldSpec") -> InputSpec:
    """Convert a family ``FieldSpec`` to a Fabric ``InputSpec``."""

    return InputSpec(
        name=f.name,
        type=f.type,
        description=f.description,
    )


def _json_schema_type(field_type: str) -> str:
    normalized = str(field_type or "").lower()
    type_map = {
        "str": "string",
        "string": "string",
        "datetime": "string",
        "int": "integer",
        "integer": "integer",
        "float": "number",
        "number": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "list": "array",
        "array": "array",
        "dict": "object",
        "object": "object",
    }
    return type_map.get(normalized, "string")


def _fields_to_output_schema(fields: list["FieldSpec"]) -> dict[str, Any]:
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for field in fields:
        properties[field.name] = {
            "type": _json_schema_type(field.type),
            "description": field.description,
        }
        if field.required:
            required.append(field.name)
    return {"type": "object", "properties": properties, "required": required}


def _risk_class_for_action(action: "ActionSpec") -> str:
    """Map action kind + safety band to a Fabric ``risk_class`` value.

    The Fabric defaults to ``"safety_sensitive"`` for unmigrated
    contracts (fail-closed).  We classify read/compute actions as
    ``benign`` and any write/delete action above GREEN as
    ``safety_sensitive``.
    """

    if action.kind in ("read", "compute"):
        return "benign"
    # write / delete:
    return "benign" if action.min_band == "GREEN" else "safety_sensitive"


def _description_for_action(action: "ActionSpec") -> str:
    """Choose the contract ``description`` field.

    Order of preference: the first ``llm.use_when`` hint (LLM-facing
    summary), falling back to the action ``summary``.
    """

    hints = action.llm.use_when
    if hints and hints[0].strip():
        return hints[0]
    return action.summary


# ---------------------------------------------------------------------------
# Contract construction
# ---------------------------------------------------------------------------


def build_contract(
    definition: "ToolDefinition",
    action: "ActionSpec",
) -> CapabilityContract:
    """Construct the Fabric ``CapabilityContract`` for a single action.

    Pure / side-effect-free: callers (typically ``register_definition``)
    feed the result into ``CapabilityRegistry.register``.
    """

    required = [_field_to_input_spec(f) for f in action.params if f.required]
    optional = [_field_to_input_spec(f) for f in action.params if not f.required]

    now_iso = datetime.now(timezone.utc).isoformat()

    domains = list(
        dict.fromkeys(
            ["family", definition.adapter_id, definition.category, *definition.domain_tags]
        )
    )
    tool_instructions = action.tool_instructions
    if tool_instructions is None and action.llm.examples:
        tool_instructions = "Examples: " + " | ".join(action.llm.examples[:3])

    return CapabilityContract(
        name=_capability_name(definition.adapter_id, action),
        version=definition.version,
        domain=domains,
        description=_description_for_action(action),
        capabilities=[action.kind, f"adapter:{definition.adapter_id}"],
        limitations=list(action.llm.avoid_when),
        required_inputs=required,
        optional_inputs=optional,
        required_context=[],
        optional_context=["control"],
        output=_fields_to_output_schema(list(action.result)),
        provider_type=NATIVE_PROVIDER_TYPE,
        provider_id=NATIVE_PROVIDER_ID,
        provider_endpoint=NATIVE_PROVIDER_ENDPOINT,
        prompt_template=action.prompt_template,
        activity_profile=action.activity_profile or definition.activity_profile,
        tool_instructions=tool_instructions,
        safety_band_min=action.min_band if action.min_band != "CRISIS" else SafetyBand.CRISIS.value,
        cost_per_call=0.0,
        avg_latency_ms=10,
        max_latency_ms=1000,
        registered_at=now_iso,
        last_updated=now_iso,
        ephemeral=False,
        created_by=NATIVE_PROVIDER_ID,
        created_at_iso=now_iso,
        session_scoped=False,
        risk_class=_risk_class_for_action(action),
        social_act=action.social_act,
        side_effects=list(action.side_effects),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_definition(
    definition: "ToolDefinition",
    registry: "CapabilityRegistry",
    *,
    skip_validation: bool = True,
) -> list[str]:
    """Register every action in ``definition`` with the Fabric registry.

    The default ``skip_validation=True`` is correct here: ``ToolDefinition``
    is itself a Pydantic-validated schema, and the Fabric JSON-schema
    validator targets YAML-loaded contracts (which carry fields like
    ``capabilities`` differently).  Re-validating against the YAML schema
    would reject syntactically valid in-code contracts.

    Returns
    -------
    The list of capability names registered (one per action) -- useful
    for boot logging and tests.
    """

    names: list[str] = []
    for action in definition.actions:
        contract = build_contract(definition, action)
        registry.register(contract, skip_validation=skip_validation)
        names.append(contract.name)
    return names


# ---------------------------------------------------------------------------
# Phase 1.1 -- GlobalProjectionStore projection (Epic 9.8)
# ---------------------------------------------------------------------------

# capability_type_index models effect as the resolver does: deletes are a
# kind of write, and compute is read-like (no persisted mutation).
_TYPE_INDEX_EFFECT: dict[str, str] = {
    "read": "read",
    "compute": "read",
    "write": "write",
    "delete": "write",
}


def _safety_band_min(action: "ActionSpec") -> str:
    """Map an action's ``min_band`` to a store ``safety_band_min`` value.

    The ``capabilities`` table CHECK allows only GREEN/AMBER/RED, so CRISIS
    folds into RED (the strongest persisted band).
    """

    band = action.min_band
    return band if band in ("GREEN", "AMBER", "RED") else "RED"


def _operation_family(action: "ActionSpec") -> str:
    """Canonical operation verb for ``capability_type_index``.

    The situated resolver maps user intents onto the action name's first
    token (e.g. ``create_event`` -> ``create``, ``list_events`` -> ``list``).
    """

    return action.name.split("_", 1)[0]


def _action_to_inputs(action: "ActionSpec") -> tuple[list[dict], list[dict]]:
    """Split an action's ``params`` into required/optional input dicts."""

    required = [
        {"name": f.name, "type": f.type, "description": f.description}
        for f in action.params
        if f.required
    ]
    optional = [
        {"name": f.name, "type": f.type, "description": f.description}
        for f in action.params
        if not f.required
    ]
    return required, optional


def register_definition_to_store(
    definition: "ToolDefinition",
    store: "GlobalProjectionStore",
) -> int:
    """Project a family ``ToolDefinition`` into ``GlobalProjectionStore``.

    Phase 1.1 (Epic 9.8) companion to :func:`register_definition`.  Where
    ``register_definition`` populates the in-memory ``CapabilityRegistry``
    (which ``NativeToolProvider`` dispatches against), this projects the
    SAME surface into the SQLite ``GlobalProjectionStore`` so the situated
    resolver (``resolve_situation``) can discover, type-resolve, and govern
    the connector.

    Both paths share the SAME capability names (``_capability_name``) so a
    resolver binding dispatches cleanly through the existing provider.

    Persists:
      * One ``ConnectorRecord`` (``connector_id = "family.<adapter_id>"``)
        carrying constitution / policy_declarations / resource_kinds /
        guide_cards.
      * One ``CapabilityRecord`` per action.
      * One ``capability_type_index`` row per action (typed resolution).
      * One ``ConstitutionRecord`` when ``definition.constitution`` is set.
      * Graph-ontology edges when ``definition.ontology`` is set.

    The existing ``register_definition`` path is UNCHANGED; this is purely
    additive.  Returns the number of capabilities registered.
    """

    from datetime import datetime, timezone

    from k1.fabric.stores.global_projection_store import (
        CapabilityRecord,
        ConnectorRecord,
        ConstitutionRecord,
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    connector_id = f"family.{definition.adapter_id}"
    domain = "family"

    resource_kinds = list(definition.resource_kinds or [])
    if not resource_kinds and definition.entity_type:
        resource_kinds = [definition.entity_type]
    primary_resource_kind = resource_kinds[0] if resource_kinds else None

    # ── Connector ──────────────────────────────────────────────────────
    store.upsert_connector(
        ConnectorRecord(
            connector_id=connector_id,
            label=definition.title or definition.adapter_id,
            connector_type="native",
            provider_type=NATIVE_PROVIDER_TYPE,
            version=definition.version,
            admission_verdict="admitted",
            registration_type="static",
            constitution=dict(definition.constitution or {}),
            policy_declarations=dict(definition.policy_declarations or {}),
            resource_kinds=resource_kinds,
            guide_cards=list(definition.guide_cards or []),
            created_at=now_iso,
            updated_at=now_iso,
        )
    )

    # ── Capabilities + typed index ─────────────────────────────────────
    count = 0
    for action in definition.actions:
        cap_name = _capability_name(definition.adapter_id, action)
        invocation_mode = "read" if action.kind == "read" else "execute"
        required_inputs, optional_inputs = _action_to_inputs(action)

        store.upsert_capability(
            CapabilityRecord(
                capability_name=cap_name,
                connector_id=connector_id,
                invocation_mode=invocation_mode,
                action_name=action.name,
                effect=action.kind,
                resource_kind=primary_resource_kind,
                description=_description_for_action(action),
                required_inputs=required_inputs,
                optional_inputs=optional_inputs,
                output_schema_ref=None,
                safety_band_min=_safety_band_min(action),
                risk_class=_risk_class_for_action(action),
                idempotency="safe" if action.idempotent else None,
                record_type="executable_capability",
                created_at=now_iso,
                contract_json=build_contract(definition, action).to_dict(),
                synthetic=False,
            )
        )

        if primary_resource_kind:
            store.upsert_capability_type_index(
                capability_name=cap_name,
                connector_id=connector_id,
                domain=domain,
                resource_family=primary_resource_kind,
                operation_family=_operation_family(action),
                effect=_TYPE_INDEX_EFFECT.get(action.kind, "write"),
                side_effect_class=None,
                risk_class=_risk_class_for_action(action),
            )
        count += 1

    # ── Constitution ───────────────────────────────────────────────────
    if definition.constitution:
        c = definition.constitution
        store.upsert_constitution(
            ConstitutionRecord(
                connector_id=connector_id,
                constitution_id=str(c.get("constitution_id") or f"{connector_id}.v1"),
                schema_version=str(c.get("schema_version") or "1.0.0"),
                authored_by=c.get("authored_by"),
                authored_at=c.get("authored_at"),
                last_proven_at=c.get("last_proven_at"),
                execution_phases=list(c.get("execution_phases") or []),
                prerequisite_reads=list(c.get("prerequisite_reads") or []),
                conflict_analysis_rules=list(c.get("conflict_analysis_rules") or []),
                hil_gates=list(c.get("hil_gates") or []),
                mutation_sequencing=list(c.get("mutation_sequencing") or []),
                verification_requirements=list(c.get("verification_requirements") or []),
                companion_resource_roles=list(c.get("companion_resource_roles") or []),
                precondition_summary=c.get("precondition_summary"),
                companion_resource_summary=c.get("companion_resource_summary"),
                hil_trigger_summary=c.get("hil_trigger_summary"),
                degradation_policy=c.get("degradation_policy"),
            )
        )

    # ── Graph-ontology edges ───────────────────────────────────────────
    onto = definition.ontology or {}
    onto_domain = str(onto.get("domain") or domain)
    for entry in onto.get("concept_aliases", []) or []:
        store.upsert_concept_alias(
            alias=str(entry.get("alias", "")),
            canonical_concept=str(entry.get("canonical_concept", "")),
            domain=onto_domain,
            weight=float(entry.get("weight", 1.0)),
        )
    for entry in onto.get("concept_resource_edges", []) or []:
        store.upsert_concept_resource_edge(
            concept=str(entry.get("concept", "")),
            resource_family=str(entry.get("resource_family", "")),
            domain=onto_domain,
            weight=float(entry.get("weight", 1.0)),
        )
    for entry in onto.get("resource_connector_edges", []) or []:
        store.upsert_resource_connector_edge(
            domain=onto_domain,
            resource_family=str(entry.get("resource_family", "")),
            connector_id=str(entry.get("connector_id", connector_id)),
            weight=float(entry.get("weight", 1.0)),
            role=str(entry.get("role", "primary")),
        )
    for entry in onto.get("operation_aliases", []) or []:
        store.upsert_operation_alias(
            alias=str(entry.get("alias", "")),
            operation_family=str(entry.get("operation_family", "")),
            effect=str(entry.get("effect", "write")),
        )
    for entry in onto.get("operation_equivalences", []) or []:
        store.upsert_operation_equivalence(
            canonical_operation=str(entry.get("canonical_operation", "")),
            equivalent_operation=str(entry.get("equivalent_operation", "")),
            resource_family=entry.get("resource_family"),
            domain=onto_domain,
        )

    return count
