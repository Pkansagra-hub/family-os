"""
k1.tools.family.definition -- declarative manifest for a family tool service.

A ``ToolDefinition`` is the single source of truth a family adapter
publishes to describe itself.  It drives three independent consumers:

1. ``k1.fabric.manifest_translator.register_definition`` -- converts each
   ``ActionSpec`` into a Fabric ``CapabilityContract`` so the action is
   discoverable, governable, and dispatchable through the Capability
   Fabric (LLM tool calls, planners, workflows).

2. ``k1.fabric.providers.native_tool_provider.NativeToolProvider`` --
   uses ``LLMHints`` + ``FieldSpec`` to validate inbound params and to
   project results, and uses ``ActionSpec.kind`` + ``min_band`` for
   policy enforcement.

3. The K1 SSE / event surface -- ``SSESpec`` describes the audit-event
   topics each action publishes via ``EventEmitter`` so subscribers know
   what to expect.

All types are Pydantic v2, ``extra="forbid"``, immutable
(``frozen=True``) so a definition cannot drift at runtime.

References
----------
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.2
* Aligned with ``k1.fabric.types.SafetyBand`` (GREEN/AMBER/RED/CRISIS).
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Band = Literal["GREEN", "AMBER", "RED", "CRISIS"]
"""Safety band literal aligned to ``k1.fabric.types.SafetyBand``.

Note: the original plan draft used ``BLACK`` here; we use ``CRISIS`` to
match the Fabric enum so contract translation does not need a mapping
table (one source of truth across the system).
"""

Role = Literal["parent", "child", "guardian", "elder", "system", "guest"]
"""Caller role consumed by ACL evaluation and action-level role gates.

Ordering used for ``min_role`` gates (higher = stronger): ``system=5 >
parent=4 > guardian=3 > elder=2 > child=1 > guest=0``.  Imported from
:mod:`k1.tools.family.base` as the single source of truth; re-aliased
here so adapter authors importing from ``definition`` get the same
type.
"""

ActionKind = Literal["read", "write", "delete", "compute"]
"""High-level shape of an action.

* ``read``    -- pure query, no state change, never idempotent-keyed.
* ``write``   -- creates or mutates persisted state.
* ``delete``  -- soft- or hard-deletes persisted state.
* ``compute`` -- non-persisting computation (forecasts, summaries).

The manifest translator uses this to decide which Fabric capability
prefix (``tool.read.*`` vs ``tool.execute.*``) the action publishes
under.
"""


# ---------------------------------------------------------------------------
# FieldSpec
# ---------------------------------------------------------------------------


class FieldSpec(BaseModel):
    """Declarative description of a single parameter or result field.

    ``FieldSpec`` is intentionally narrower than a full JSON-schema node:
    it captures only the information the manifest translator needs to
    emit a Fabric ``parameters_schema`` and the information the LLM tool
    surface needs to render argument hints.  Adapter authors who need
    richer validation should attach a Pydantic model on the action's
    ``params_model`` side rather than expanding this type.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(
        ..., min_length=1, description="Field key as it appears in params/result dicts."
    )
    type: Literal["string", "integer", "number", "boolean", "datetime", "object", "array"] = Field(
        ..., description="JSON-schema compatible primitive type."
    )
    required: bool = Field(default=False, description="Whether the field is mandatory.")
    description: str = Field(default="", description="Short human-readable hint, surfaced to LLMs.")
    example: Optional[Any] = Field(
        default=None,
        description="Optional example value used in LLM tool documentation.",
    )


# ---------------------------------------------------------------------------
# LLMHints
# ---------------------------------------------------------------------------


class LLMHints(BaseModel):
    """LLM-facing metadata about an action.

    The fabric tool surface renders these into the model's tool catalog;
    keep them short, declarative, and free of internal jargon.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    use_when: list[str] = Field(
        default_factory=list,
        description="One-line phrases describing situations to invoke this action.",
    )
    avoid_when: list[str] = Field(
        default_factory=list,
        description="One-line phrases describing situations to NOT invoke this action.",
    )
    examples: list[str] = Field(
        default_factory=list,
        description="Example user utterances that map to this action.",
    )

    @field_validator("use_when")
    @classmethod
    def _validate_use_when(cls, v: list[str]) -> list[str]:
        """The first entry, if any, is used as the Fabric contract description."""

        if v and not v[0].strip():
            raise ValueError("LLMHints.use_when[0] must be non-empty if provided.")
        return v


# ---------------------------------------------------------------------------
# SSESpec
# ---------------------------------------------------------------------------


class SSESpec(BaseModel):
    """Declares the SSE/audit topics an action publishes.

    Subscribers (planner, supervision, audit log) discover these via the
    definition; the manifest translator embeds them in the Fabric
    contract metadata so governance tooling can audit them.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    emits: list[str] = Field(
        default_factory=list,
        description=(
            "Topic strings the action emits via EventEmitter "
            "(e.g. ``family.calendar.event.created.v1``)."
        ),
    )
    redact_fields: list[str] = Field(
        default_factory=list,
        description="Result/payload fields that must be redacted before publishing.",
    )


# ---------------------------------------------------------------------------
# ActionSpec
# ---------------------------------------------------------------------------


class ActionSpec(BaseModel):
    """Declarative description of a single tool action.

    Each ``ActionSpec`` becomes exactly one Fabric ``CapabilityContract``
    (one capability name in the Fabric registry).  The dispatcher in
    ``NativeToolProvider`` uses ``name`` to route to the matching
    service method.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(
        ...,
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Snake-case action identifier, unique within the parent ToolDefinition.",
    )
    kind: ActionKind = Field(..., description="High-level action shape.")
    summary: str = Field(
        ..., min_length=1, description="One-line description of what the action does."
    )
    label: str = Field(
        default="",
        description="Human-facing button/label rendered by ``ManifestGenerator.ui_manifest``.",
    )
    primary: bool = Field(
        default=False,
        description="Whether the UI should surface this action prominently.",
    )
    context: list[str] = Field(
        default_factory=list,
        description="UI context tags (e.g. ``entity_detail``, ``home``) consumed by the manifest renderer.",
    )
    min_band: Band = Field(
        default="GREEN",
        description="Lowest caller safety band permitted to invoke the action.",
    )
    min_role: Optional[Role] = Field(
        default=None,
        description=(
            "Optional minimum role per the privilege ladder (system=5..guest=0). "
            "Enforced in addition to ``allowed_roles``: a caller must satisfy BOTH gates."
        ),
    )
    allowed_roles: list[Role] = Field(
        default_factory=lambda: ["parent", "guardian", "system"],
        description="Caller roles permitted to invoke the action.",
    )
    params: list[FieldSpec] = Field(
        default_factory=list,
        description="Inbound parameter schema.",
    )
    result: list[FieldSpec] = Field(
        default_factory=list,
        description="Outbound result schema (per-row for list actions).",
    )
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional explicit JSON-schema (Draft-07) for the action params. "
            "When present, the manifest translator persists it to "
            "``GlobalProjectionStore`` (Phase 1.1); when empty, ``params`` "
            "(``FieldSpec`` list) remains the source."
        ),
    )
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional explicit JSON-schema for the action result. "
            "When empty, ``ManifestGenerator`` derives one from ``result`` instead."
        ),
    )
    llm: LLMHints = Field(
        default_factory=LLMHints,
        description="LLM-facing metadata.",
    )
    prompt_template: Optional[str] = Field(
        default=None,
        description="Optional PromptContract name to use for this action.",
    )
    activity_profile: Optional[str] = Field(
        default=None,
        description="Optional activity profile id for Back/Fabric execution guidance.",
    )
    tool_instructions: Optional[str] = Field(
        default=None,
        description="Optional concise operating instructions for LLM-backed execution.",
    )
    social_act: Optional[str] = Field(
        default=None,
        description="Optional constitution/social act id manifested by this action.",
    )
    side_effects: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured side effects emitted by this action for policy/HIL/audit.",
    )
    sse: SSESpec = Field(
        default_factory=SSESpec,
        description="SSE/audit emission declaration.",
    )
    idempotent: bool = Field(
        default=False,
        description=(
            "If True, repeated calls with the same idempotency_key MUST yield "
            "the same effect/result. Write/delete actions are encouraged to set True."
        ),
    )

    @field_validator("allowed_roles")
    @classmethod
    def _validate_allowed_roles(cls, v: list[Role]) -> list[Role]:
        if not v:
            raise ValueError("ActionSpec.allowed_roles must contain at least one role.")
        return v


# ---------------------------------------------------------------------------
# ToolDefinition
# ---------------------------------------------------------------------------


class ToolDefinition(BaseModel):
    """Top-level manifest published by a family adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_id: str = Field(
        ...,
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Snake-case adapter identifier (unique across all family tools).",
    )
    version: str = Field(
        default="1.0.0",
        pattern=r"^\d+\.\d+\.\d+$",
        description="SemVer of the adapter's published surface.",
    )
    category: str = Field(
        default="family",
        min_length=1,
        description="Top-level grouping label (e.g. ``family``, ``health``, ``finance``).",
    )
    summary: str = Field(
        ...,
        min_length=1,
        description="One-line description of the adapter's purpose; surfaced to LLMs.",
    )
    title: str = Field(
        default="",
        description="Human-facing title (defaults to a capitalised ``adapter_id`` when empty).",
    )
    icon: str = Field(
        default="",
        description="Icon identifier (emoji or icon-set key) for UI rendering.",
    )
    description: str = Field(
        default="",
        description="Longer human-facing description; falls back to ``summary`` when empty.",
    )
    entity_type: str = Field(
        default="",
        description="Canonical entity name (e.g. ``calendar_event``); used by ``can_reference`` and SSE.",
    )
    views: list[str] = Field(
        default_factory=list,
        description="UI view names this adapter exposes (e.g. ``list``, ``calendar``, ``timeline``).",
    )
    filters: list[FieldSpec] = Field(
        default_factory=list,
        description="UI list-filter fields; rendered by ``ManifestGenerator.ui_manifest``.",
    )
    can_reference: list[str] = Field(
        default_factory=list,
        description="Other adapters' ``entity_type`` values this adapter may cross-link to.",
    )
    activity_profile: Optional[str] = Field(
        default=None,
        description="Default activity profile id inherited by actions without an override.",
    )
    domain_tags: list[str] = Field(
        default_factory=list,
        description="Additional discovery/ranking domain tags for Fabric contracts.",
    )
    feature_flags: list[str] = Field(
        default_factory=list,
        description="Feature-flag tags the kernel can consult before enabling this adapter.",
    )
    tables_sql: str = Field(
        ...,
        min_length=1,
        description=(
            "DDL block executed once at ``BaseToolService.__init__`` to create the adapter's "
            "projection tables.  MUST include a ``<adapter_id>_schema_version`` table (P7 invariant)."
        ),
    )
    actions: list[ActionSpec] = Field(
        ...,
        min_length=1,
        description="The action list -- at least one entry required.",
    )

    # ------------------------------------------------------------------ #
    # Phase 1.1 -- Constitution enrichment (Epics 9-14).
    #
    # All seven fields are ``Optional`` with ``default=None`` so existing
    # adapters that do not declare them remain valid.  They are consumed
    # by ``k1.fabric.manifest_translator.register_definition_to_store``
    # which projects the definition into ``GlobalProjectionStore`` for the
    # situated resolver.  ``snapshot_types`` is declared now but its store
    # column is added in Phase 2.5 (Epic 19); until then it is dormant.
    # ------------------------------------------------------------------ #
    constitution: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Connector constitution artifact (prerequisite_reads, "
            "conflict_analysis_rules, companion_resource_roles, hil_gates, "
            "mutation_sequencing, verification_requirements, summaries). "
            "See connector_onboarding_familyos.md §1.3."
        ),
    )
    policy_declarations: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Per-connector policy rules (operation_role_gates, "
            "operation_safety_bands, protected_resources, hil_triggers) "
            "enforced by PolicySelectorService. See onboarding §1.4."
        ),
    )
    guide_cards: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description=(
            "LLM-facing guidance cards persisted to GlobalProjectionStore "
            "and injected into Back's prompt pack. See onboarding §1.5."
        ),
    )
    ontology: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Domain ontology registration (concept_aliases, "
            "concept_resource_edges, resource_connector_edges, "
            "operation_aliases, operation_equivalences) seeded into the "
            "graph-ontology tables. See onboarding §1.6."
        ),
    )
    resource_kinds: Optional[list[str]] = Field(
        default=None,
        description=(
            "Resource kinds this connector owns (overrides singular "
            "``entity_type`` for the store). E.g. ``['calendar_event', "
            "'appointment']``."
        ),
    )
    resource_families: Optional[list[str]] = Field(
        default=None,
        description=(
            "Phase 2.6: taxonomy resource family IDs this connector "
            "manages. E.g. ``['event']`` for calendar, ``['task']`` for "
            "tasks.  Populates ``connector_resource_families`` at "
            "bootstrap and becomes the ``family_id`` on ``CapabilityRecord``."
        ),
    )
    domain_id: Optional[str] = Field(
        default=None,
        description=(
            "Phase 2.6: taxonomy domain this connector belongs to "
            "(e.g. ``'family'``, ``'health'``).  Populates "
            "``connectors.domain_id`` at bootstrap."
        ),
    )
    actor_scope: Optional[list[str]] = Field(
        default=None,
        description=(
            "Roles permitted to use this connector. Defaults to "
            "``['parent', 'admin', 'system']`` when absent."
        ),
    )
    snapshot_types: Optional[list[str]] = Field(
        default=None,
        description=(
            "Snapshot types this connector participates in, e.g. "
            "``['daily_snapshot', 'weekly_overview']``. Empty/absent = no "
            "participation. Consumed by the lookup() tool. NOTE: store "
            "persistence is added in Phase 2.5 (Epic 19); dormant until then."
        ),
    )
    back_execution_profile: bool = Field(
        default=False,
        description=(
            "When ``True`` this connector self-declares a Back execution "
            "profile keyed by ``activity_profile``. The profile is built at "
            "import time from this definition (domains from ``adapter_id`` + "
            "``domain_tags``, guidance derived from ``guide_cards``) and "
            "selected by ``k1.concierge.prompt.back_profiles``. Connectors "
            "that leave this ``False`` are intentionally unbacked and fall "
            "back to the generic discovery profile (e.g. chores, shopping)."
        ),
    )

    @field_validator("tables_sql")
    @classmethod
    def _validate_tables_sql(cls, v: str, info) -> str:  # type: ignore[no-untyped-def]
        # P7: every adapter MUST own a ``<adapter_id>_schema_version`` table so
        # migrations can be coordinated without colliding across adapters.
        adapter_id = info.data.get("adapter_id", "")
        if adapter_id:
            expected = f"{adapter_id}_schema_version"
            if expected not in v:
                raise ValueError(
                    f"ToolDefinition.tables_sql must include a `{expected}` table (P7 invariant)."
                )
        return v

    @field_validator("actions")
    @classmethod
    def _validate_action_names_unique(cls, v: list[ActionSpec]) -> list[ActionSpec]:
        seen: set[str] = set()
        for a in v:
            if a.name in seen:
                raise ValueError(f"ToolDefinition.actions has duplicate action name: {a.name!r}")
            seen.add(a.name)
        return v

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #

    def find_action(self, name: str) -> Optional[ActionSpec]:
        """Return the named action, or ``None`` if not present."""

        for a in self.actions:
            if a.name == name:
                return a
        return None
