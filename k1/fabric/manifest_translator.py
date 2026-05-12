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
from typing import TYPE_CHECKING

from k1.fabric.types import CapabilityContract, InputSpec, SafetyBand
from k1.tools.family.definition import ActionKind, ActionSpec, FieldSpec, ToolDefinition

if TYPE_CHECKING:  # pragma: no cover -- typing only
    from k1.fabric.core.registry import CapabilityRegistry

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


def _capability_name(adapter_id: str, action: ActionSpec) -> str:
    """Return the canonical Fabric capability name for ``action``."""

    prefix = "tool.read" if action.kind == "read" else "tool.execute"
    return f"{prefix}.{adapter_id}.{action.name}"


def _kind_to_capability_prefix(kind: ActionKind) -> str:
    """Public helper: return the Fabric capability prefix for an action kind."""

    return "tool.read" if kind == "read" else "tool.execute"


def _field_to_input_spec(f: FieldSpec) -> InputSpec:
    """Convert a family ``FieldSpec`` to a Fabric ``InputSpec``."""

    return InputSpec(
        name=f.name,
        type=f.type,
        description=f.description,
    )


def _risk_class_for_action(action: ActionSpec) -> str:
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


def _description_for_action(action: ActionSpec) -> str:
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
    definition: ToolDefinition,
    action: ActionSpec,
) -> CapabilityContract:
    """Construct the Fabric ``CapabilityContract`` for a single action.

    Pure / side-effect-free: callers (typically ``register_definition``)
    feed the result into ``CapabilityRegistry.register``.
    """

    required = [_field_to_input_spec(f) for f in action.params if f.required]
    optional = [_field_to_input_spec(f) for f in action.params if not f.required]

    now_iso = datetime.now(timezone.utc).isoformat()

    return CapabilityContract(
        name=_capability_name(definition.adapter_id, action),
        version=definition.version,
        domain=["family", definition.adapter_id, definition.category],
        description=_description_for_action(action),
        capabilities=[action.kind, f"adapter:{definition.adapter_id}"],
        limitations=list(action.llm.avoid_when),
        required_inputs=required,
        optional_inputs=optional,
        required_context=[],
        optional_context=["control"],
        output={},
        provider_type=NATIVE_PROVIDER_TYPE,
        provider_id=NATIVE_PROVIDER_ID,
        provider_endpoint=NATIVE_PROVIDER_ENDPOINT,
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
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_definition(
    definition: ToolDefinition,
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
