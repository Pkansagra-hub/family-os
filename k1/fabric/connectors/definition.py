"""Connector definition types — the Python API for declaring connectors.

Phase 1, Epic 2 (Issues 2.1–2.2).  Typed dataclasses matching the connector
onboarding doc §1.1–§1.6.  These are what a connector author writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Issue 2.2 — ServiceDefinition (compact input format) ───────────────


@dataclass
class ServiceDefinition:
    """Compact connector definition.  Expanded to ConnectorDefinition by the builder.

    This is the POC's ``DOMAINS[domain]['services'][n]`` dict, typed.
    """

    id: str  # "calendar"
    label: str  # "Calendar"
    resource: str  # primary resource_kind: "calendar_event"
    resource_kinds: list[str] = field(default_factory=list)  # additional kinds
    desc: str = ""  # description
    read_op: str = "list"  # read operation verb
    write_op: str | None = "create"  # write operation verb, None = read-only
    write_inputs: list[str] = field(default_factory=list)
    read_inputs: list[str] = field(default_factory=list)
    domain_tags: list[str] = field(default_factory=list)


# ── Issue 2.1 — Capability & Input definitions ──────────────────────────


@dataclass
class InputFieldSpec:
    """Single input/output field.  Skinny version of JSON Schema."""

    name: str
    type: str  # 'string' | 'integer' | 'number' | 'boolean' | 'datetime' | 'object' | 'array'
    required: bool = False
    description: str = ""
    example: Any = None


@dataclass
class CapabilityDefinition:
    """One operation a connector can perform.  Matches onboarding §1.2."""

    name: str  # full capability name: "tool.execute.family.calendar.create"
    action_name: str  # action verb: "create", "list", "update", "delete", "send"
    invocation_mode: str  # 'read' | 'execute'
    effect: str  # 'read' | 'write' | 'delete' | 'compute'
    resource_kind: str  # e.g. "calendar_event"
    description: str
    required_inputs: list[InputFieldSpec] = field(default_factory=list)
    optional_inputs: list[InputFieldSpec] = field(default_factory=list)
    output_schema_ref: str | None = None
    safety_band_min: str = "GREEN"
    risk_class: str = "benign"
    idempotency: str | None = None  # 'safe' | 'unsafe' | None
    compensation_capability: str | None = None
    record_type: str = "executable_capability"
    # Full JSON Schemas — nullable, falls back to InputFieldSpec
    input_schema: dict | None = None
    output_schema: dict | None = None


# ── Issue 2.1 — Constitution, Policy, Guide Cards, Ontology ────────────


@dataclass
class ConstitutionDefinition:
    """Connector execution contract.  Matches onboarding §1.3."""

    connector_id: str = ""  # filled by builder
    constitution_id: str = ""
    schema_version: str = "1.0.0"
    authored_by: str | None = None
    authored_at: str | None = None
    execution_phases: list[str] = field(default_factory=list)
    prerequisite_reads: list[dict] = field(default_factory=list)
    conflict_analysis_rules: list[dict] = field(default_factory=list)
    companion_resource_roles: list[dict] = field(default_factory=list)
    hil_gates: list[dict] = field(default_factory=list)
    mutation_sequencing: list[dict] = field(default_factory=list)
    verification_requirements: list[dict] = field(default_factory=list)
    precondition_summary: str | None = None
    companion_resource_summary: str | None = None
    hil_trigger_summary: str | None = None
    degradation_policy: str | None = None


@dataclass
class PolicyDefinition:
    """Per-connector policy rules.  Matches onboarding §1.4."""

    write_requires_actor_role: list[str] = field(default_factory=list)  # empty = default-allow
    read_allowed_roles: list[str] = field(default_factory=list)
    hil_triggers: list[dict] = field(default_factory=list)
    protected_resources: list[dict] = field(default_factory=list)


@dataclass
class GuideCardDefinition:
    """LLM-facing guidance card.  Matches onboarding §1.5."""

    guide_id: str
    title: str
    content: str
    relevance: str = "always"  # 'always' | 'on_conflict' | 'on_error'
    disclosure_phase: str = "connector_summary"


@dataclass
class OntologyDefinition:
    """Domain ontology registration.  Matches onboarding §1.6."""

    domain: str
    concept_aliases: list[dict] = field(default_factory=list)  # {alias, canonical_concept, weight}
    concept_resource_edges: list[dict] = field(
        default_factory=list
    )  # {concept, resource_family, weight}
    resource_connector_edges: list[dict] = field(
        default_factory=list
    )  # {resource_family, connector_id, weight, role}
    operation_aliases: list[dict] = field(default_factory=list)  # {alias, operation_family, effect}


# ── Issue 2.1 — Complete connector manifest ────────────────────────────


@dataclass
class ConnectorDefinition:
    """Complete connector manifest.  Matches onboarding §1.1."""

    connector_id: str  # "family.calendar"
    connector_type: str = "native"  # 'native' | 'bridge' | 'ifl'
    provider_type: str = "LOCAL"
    label: str = ""
    description: str = ""
    version: str = "1.0.0"
    provider_id: str = ""  # derived: "native.{connector_id}"
    resource_kinds: list[str] = field(default_factory=list)
    actor_scope: list[str] = field(default_factory=lambda: ["parent", "admin", "system"])
    admission_verdict: str = "admitted"
    registration_type: str = "static"
    capabilities: list[CapabilityDefinition] = field(default_factory=list)
    constitution: ConstitutionDefinition | None = None
    policy: PolicyDefinition | None = None
    guide_cards: list[GuideCardDefinition] = field(default_factory=list)
    ontology: OntologyDefinition | None = None
