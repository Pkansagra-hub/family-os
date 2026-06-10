"""Connector builder — expands ServiceDefinition → ConnectorDefinition.

Phase 1, Epic 2 (Issue 2.3).  10-step expansion proven by POC
``build_connector_manifest``, now typed.
"""

from __future__ import annotations

from .definition import (
    CapabilityDefinition,
    ConnectorDefinition,
    ConstitutionDefinition,
    GuideCardDefinition,
    InputFieldSpec,
    OntologyDefinition,
    PolicyDefinition,
    ServiceDefinition,
)


def _cap_name(invocation_mode: str, domain_id: str, service_id: str, action: str) -> str:
    """Generate globally unique capability name.

    Pattern: ``tool.{invocation_mode}.{domain_id}.{service_id}.{action}``
    Example: ``tool.execute.family.calendar.create``
    """
    return f"tool.{invocation_mode}.{domain_id}.{service_id}.{action}"


def _build_input_specs(names: list[str], *, required: bool = True) -> list[InputFieldSpec]:
    """Convert field names into InputFieldSpec entries."""
    return [InputFieldSpec(name=n, type="string", required=required) for n in names]


# Communication connector ids that use send semantics.
_COMMUNICATION_IDS = {"messaging", "team_chat", "notifications", "dispatch"}


def build_connector_definition(
    domain_id: str,
    svc: ServiceDefinition,
) -> ConnectorDefinition:
    """Expand a compact ServiceDefinition into a full ConnectorDefinition."""

    # ── Step 1: derive connector_id ──────────────────────────────────
    connector_id = f"{domain_id}.{svc.id}"

    # ── Step 2: derive provider_id ───────────────────────────────────
    provider_id = f"native.{connector_id}"

    # ── Step 3: determine resource_kinds ─────────────────────────────
    resource_kinds = [svc.resource]
    resource_kinds.extend(svc.resource_kinds)

    # Derive human-readable label
    label = svc.label or svc.id.replace("_", " ").title()

    # ── Steps 4–6: generate capabilities ─────────────────────────────
    capabilities: list[CapabilityDefinition] = []
    seen_names: set[str] = set()

    for rk in resource_kinds:
        # Step 4: read capability (one row per (mode, action); multi-resource
        # projection lives in capability_type_index, seeded at admission).
        read_name = _cap_name("read", domain_id, svc.id, svc.read_op)
        if read_name not in seen_names:
            capabilities.append(
                CapabilityDefinition(
                    name=read_name,
                    action_name=svc.read_op,
                    invocation_mode="read",
                    effect="read",
                    resource_kind=rk,
                    description=f"{svc.read_op} {rk} entries",
                    required_inputs=_build_input_specs(svc.read_inputs, required=False),
                )
            )
            seen_names.add(read_name)

        # Step 5: write / update / delete (only if write_op is set)
        if svc.write_op is not None:
            effective_write = svc.write_op  # "create" or "send"

            write_name = _cap_name("execute", domain_id, svc.id, effective_write)
            if write_name not in seen_names:
                capabilities.append(
                    CapabilityDefinition(
                        name=write_name,
                        action_name=effective_write,
                        invocation_mode="execute",
                        effect="write",
                        resource_kind=rk,
                        description=f"{effective_write} {rk} entry",
                        required_inputs=_build_input_specs(svc.write_inputs, required=True),
                    )
                )
                seen_names.add(write_name)

            # Non-communication connectors also get update + delete.
            # Communication connectors use "send" as primary write.
            if effective_write != "send":
                up_name = _cap_name("execute", domain_id, svc.id, "update")
                if up_name not in seen_names:
                    capabilities.append(
                        CapabilityDefinition(
                            name=up_name,
                            action_name="update",
                            invocation_mode="execute",
                            effect="write",
                            resource_kind=rk,
                            description=f"Update {rk} entry",
                            required_inputs=[
                                InputFieldSpec(name="resource_id", type="string", required=True),
                            ],
                        )
                    )
                    seen_names.add(up_name)

                del_name = _cap_name("execute", domain_id, svc.id, "delete")
                if del_name not in seen_names:
                    capabilities.append(
                        CapabilityDefinition(
                            name=del_name,
                            action_name="delete",
                            invocation_mode="execute",
                            effect="delete",
                            resource_kind=rk,
                            description=f"Delete {rk} entry",
                            required_inputs=[
                                InputFieldSpec(name="resource_id", type="string", required=True),
                            ],
                        )
                    )
                    seen_names.add(del_name)

    # Step 6: send only for communication connectors, and only if
    # write_op is not already "send" (avoid duplicate create/send).
    if svc.id in _COMMUNICATION_IDS and svc.write_op != "send":
        for rk in resource_kinds:
            send_name = _cap_name("execute", domain_id, svc.id, "send")
            if send_name not in seen_names:
                capabilities.append(
                    CapabilityDefinition(
                        name=send_name,
                        action_name="send",
                        invocation_mode="execute",
                        effect="write",
                        resource_kind=rk,
                        description=f"Send {rk} message",
                    )
                )
                seen_names.add(send_name)

    # ── Step 7: build ConstitutionDefinition with sensible defaults ──
    default_prerequisite_reads: list[dict] = []
    default_hil_gates: list[dict] = []
    default_verification: list[dict] = []
    default_mutation_sequencing: list[dict] = []

    if svc.write_op is not None:
        for rk in resource_kinds:
            default_prerequisite_reads.append(
                {
                    "operation": svc.read_op,
                    "resource_kind": rk,
                    "reason": f"Check existing {rk} state before mutating.",
                    "required": True,
                    "timeout_ms": 5000,
                }
            )
        for inp in svc.write_inputs:
            default_hil_gates.append(
                {
                    "trigger": "missing_required_field",
                    "field": inp,
                    "prompt": f"Please provide a value for '{inp}'.",
                }
            )
        default_verification.append(
            {
                "method": "read_after_write",
                "required_for_submit": True,
            }
        )
        default_verification.append(
            {
                "method": "output_schema",
            }
        )
        default_mutation_sequencing = [
            {
                "order": 1,
                "phase": "read",
                "operation": svc.read_op,
                "description": "Read current state before mutating.",
            },
            {
                "order": 2,
                "phase": "mutate",
                "operation": svc.write_op,
                "description": f"Execute {svc.write_op} operation.",
            },
            {
                "order": 3,
                "phase": "read",
                "operation": svc.read_op,
                "description": "Verify mutation result (read_after_write).",
            },
        ]

    constitution = ConstitutionDefinition(
        connector_id=connector_id,
        constitution_id=f"{connector_id}.v1",
        execution_phases=["read", "mutate"] if svc.write_op is not None else ["read"],
        prerequisite_reads=default_prerequisite_reads,
        hil_gates=default_hil_gates,
        verification_requirements=default_verification,
        mutation_sequencing=default_mutation_sequencing,
        precondition_summary=(
            f"List {svc.resource} before mutating to check state."
            if svc.write_op is not None
            else None
        ),
        companion_resource_summary=None,
        hil_trigger_summary=(
            "HIL required when required fields are missing." if svc.write_inputs else None
        ),
        degradation_policy=(
            "If read_after_write verification fails, retry once then submit degraded."
            if svc.write_op is not None
            else None
        ),
    )

    # ── Step 8: build PolicyDefinition with default-allow ────────────
    policy = PolicyDefinition()

    # ── Step 9: build identity ontology ──────────────────────────────
    concept_aliases: list[dict] = []
    concept_resource_edges: list[dict] = []
    resource_connector_edges: list[dict] = []

    # Collect alias sources: svc.id, label, resource, domain_tags
    alias_sources: set[str] = set()
    alias_sources.add(svc.id.replace("_", " "))
    alias_sources.add(svc.label.lower())
    for rk in resource_kinds:
        alias_sources.add(rk.replace("_", " "))
    for tag in svc.domain_tags:
        alias_sources.add(tag.lower())

    for rk in resource_kinds:
        for alias_text in sorted(alias_sources):
            if alias_text:
                concept_aliases.append(
                    {
                        "alias": alias_text,
                        "canonical_concept": rk,
                        "weight": 1.0 if alias_text == rk.replace("_", " ") else 0.85,
                    }
                )
        concept_resource_edges.append(
            {
                "concept": rk,
                "resource_family": rk,
                "weight": 1.0,
            }
        )
        resource_connector_edges.append(
            {
                "resource_family": rk,
                "connector_id": connector_id,
                "weight": 1.0,
                "role": "primary",
            }
        )

    # Copy per connector (no shared mutable reference)
    operation_aliases: list[dict] = [dict(x) for x in _DEFAULT_OPERATION_ALIASES]

    ontology = OntologyDefinition(
        domain=domain_id,
        concept_aliases=concept_aliases,
        concept_resource_edges=concept_resource_edges,
        resource_connector_edges=resource_connector_edges,
        operation_aliases=operation_aliases,
    )

    # ── Step 10: operation_aliases (already included above) ──────────

    return ConnectorDefinition(
        connector_id=connector_id,
        connector_type="native",
        provider_type="LOCAL",
        label=label,
        description=svc.desc or f"{label} connector for {domain_id} domain",
        version="1.0.0",
        provider_id=provider_id,
        resource_kinds=resource_kinds,
        actor_scope=["parent", "admin", "system"],
        admission_verdict="admitted",
        registration_type="static",
        capabilities=capabilities,
        constitution=constitution,
        policy=policy,
        guide_cards=[],
        ontology=ontology,
    )


# ── Internal helpers ────────────────────────────────────────────────────


# Common operation aliases seeded into every connector's ontology.
# Copied per connector so no shared mutable reference.
_DEFAULT_OPERATION_ALIASES: list[dict] = [
    {"alias": "list", "operation_family": "list", "effect": "read"},
    {"alias": "search", "operation_family": "list", "effect": "read"},
    {"alias": "find", "operation_family": "list", "effect": "read"},
    {"alias": "show", "operation_family": "list", "effect": "read"},
    {"alias": "get", "operation_family": "list", "effect": "read"},
    {"alias": "create", "operation_family": "create", "effect": "write"},
    {"alias": "add", "operation_family": "create", "effect": "write"},
    {"alias": "schedule", "operation_family": "create", "effect": "write"},
    {"alias": "book", "operation_family": "create", "effect": "write"},
    {"alias": "update", "operation_family": "update", "effect": "write"},
    {"alias": "edit", "operation_family": "update", "effect": "write"},
    {"alias": "change", "operation_family": "update", "effect": "write"},
    {"alias": "move", "operation_family": "update", "effect": "write"},
    {"alias": "delete", "operation_family": "delete", "effect": "write"},
    {"alias": "remove", "operation_family": "delete", "effect": "write"},
    {"alias": "cancel", "operation_family": "delete", "effect": "write"},
    {"alias": "send", "operation_family": "send", "effect": "write"},
]
