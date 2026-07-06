"""ManifestAdmissionService — Epic 4.3.

The ingestion gate.  Takes a typed ``ConnectorDefinition`` (Epic 2),
validates it, and writes it into the ``GlobalProjectionStore``.  This is the
ONLY path for connectors to enter the store.

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epic 4.3.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from k1.fabric.connectors.definition import (
    CapabilityDefinition,
    ConnectorDefinition,
)
from k1.fabric.resolver.capability_type_resolver import UNIVERSAL_OPERATION_ALIASES
from k1.fabric.stores.global_projection_store import (
    CapabilityRecord,
    ConnectorRecord,
    ConstitutionRecord,
    GlobalProjectionStore,
    ResourceKindRecord,
)

logger = logging.getLogger(__name__)

# ── Validation constants ───────────────────────────────────────────────
_VALID_CONNECTOR_TYPES = frozenset({"native", "bridge", "ifl"})
_VALID_ADMISSION_VERDICTS = frozenset({"admitted", "pending", "rejected"})
_VALID_REGISTRATION_TYPES = frozenset({"static", "dynamic", "discovered"})
_VALID_INVOCATION_MODES = frozenset({"read", "execute"})
_VALID_EFFECTS = frozenset({"read", "write", "delete", "compute"})
_VALID_SAFETY_BANDS = frozenset({"GREEN", "AMBER", "RED"})
_VALID_RECORD_TYPES = frozenset({"executable_capability", "activity_profile", "workflow", "agent"})


# ── Result record ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ManifestAdmissionRecord:
    """The outcome of admitting one connector definition."""

    manifest_id: str
    connector_id: str
    admission_verdict: str  # 'admitted' | 'rejected'
    record_type: str
    capabilities_admitted_count: int
    capabilities_rejected_count: int
    reason: str | None
    admitted_at: str


# ── Service ────────────────────────────────────────────────────────────


class ManifestAdmissionService:
    """Validates and ingests typed connector definitions into the store."""

    def __init__(self, store: GlobalProjectionStore) -> None:
        self.store = store

    # ── Public API ─────────────────────────────────────────────────

    def admit(self, definition: ConnectorDefinition) -> ManifestAdmissionRecord:
        """Validate a definition and, if valid, write it into the store.

        On validation failure the connector is NOT written — the record
        carries ``admission_verdict='rejected'`` and a reason.
        """
        errors = self._validate_connector(definition)

        seen_names: set[str] = set()
        for cap in definition.capabilities:
            errors.extend(self._validate_capability(cap, seen_names))
            seen_names.add(cap.name)

        if errors:
            return ManifestAdmissionRecord(
                manifest_id="manifest-" + uuid.uuid4().hex[:12],
                connector_id=definition.connector_id,
                admission_verdict="rejected",
                record_type=definition.registration_type,
                capabilities_admitted_count=0,
                capabilities_rejected_count=len(definition.capabilities),
                reason="; ".join(errors),
                admitted_at=_utc_now_iso(),
            )

        self._ingest_connector(definition)
        admitted = self._ingest_capabilities(definition)
        self._ingest_constitution(definition)
        self._ingest_resource_kinds(definition)
        self._ingest_ontology(definition)
        self._ingest_connector_fts_text(definition)  # RES-004: connector-level FTS

        return ManifestAdmissionRecord(
            manifest_id="manifest-" + uuid.uuid4().hex[:12],
            connector_id=definition.connector_id,
            admission_verdict="admitted",
            record_type=definition.registration_type,
            capabilities_admitted_count=admitted,
            capabilities_rejected_count=0,
            reason=None,
            admitted_at=_utc_now_iso(),
        )

    def admit_all(self, definitions: list[ConnectorDefinition]) -> list[ManifestAdmissionRecord]:
        """Admit a batch.  Each definition is independently validated and
        ingested — one bad connector does NOT block the rest.
        """
        records: list[ManifestAdmissionRecord] = []
        for definition in definitions:
            try:
                records.append(self.admit(definition))
            except Exception as exc:  # isolate partial-batch failure
                logger.error(
                    "admit failed for connector %s: %s",
                    definition.connector_id,
                    exc,
                    exc_info=True,
                )
                records.append(
                    ManifestAdmissionRecord(
                        manifest_id="manifest-" + uuid.uuid4().hex[:12],
                        connector_id=definition.connector_id,
                        admission_verdict="rejected",
                        record_type=definition.registration_type,
                        capabilities_admitted_count=0,
                        capabilities_rejected_count=len(definition.capabilities),
                        reason=f"ingestion_error: {exc}",
                        admitted_at=_utc_now_iso(),
                    )
                )
        return records

    # ── Validation ─────────────────────────────────────────────────

    def _validate_connector(self, d: ConnectorDefinition) -> list[str]:
        """Validate the connector-level required fields."""
        errors: list[str] = []
        if not d.connector_id:
            errors.append("connector_id is required")
        if d.connector_type not in _VALID_CONNECTOR_TYPES:
            errors.append(f"connector_type must be one of {sorted(_VALID_CONNECTOR_TYPES)}")
        if not d.provider_type:
            errors.append("provider_type is required")
        if not d.label:
            errors.append("label is required")
        if not d.description:
            errors.append("description is required")
        if not d.version:
            errors.append("version is required")
        if not d.provider_id:
            errors.append("provider_id is required")
        if d.admission_verdict not in _VALID_ADMISSION_VERDICTS:
            errors.append(f"admission_verdict must be one of {sorted(_VALID_ADMISSION_VERDICTS)}")
        if d.registration_type not in _VALID_REGISTRATION_TYPES:
            errors.append(f"registration_type must be one of {sorted(_VALID_REGISTRATION_TYPES)}")
        if not d.resource_kinds:
            errors.append("resource_kinds must be a non-empty list")
        if not d.actor_scope:
            errors.append("actor_scope must be a non-empty list")
        if not d.capabilities:
            errors.append("capabilities must be a non-empty list")
        return errors

    def _validate_capability(self, c: CapabilityDefinition, seen_names: set[str]) -> list[str]:
        """Validate one capability's required fields, naming, and uniqueness."""
        errors: list[str] = []
        if not c.name:
            errors.append("capability name is required")
        if c.invocation_mode not in _VALID_INVOCATION_MODES:
            errors.append(
                f"capability '{c.name}': invocation_mode must be one of "
                f"{sorted(_VALID_INVOCATION_MODES)}"
            )
        if c.effect not in _VALID_EFFECTS:
            errors.append(f"capability '{c.name}': effect must be one of {sorted(_VALID_EFFECTS)}")
        if not c.resource_kind:
            errors.append(f"capability '{c.name}': resource_kind is required")
        if not c.description:
            errors.append(f"capability '{c.name}': description is required")
        if c.safety_band_min not in _VALID_SAFETY_BANDS:
            errors.append(
                f"capability '{c.name}': safety_band_min must be one of "
                f"{sorted(_VALID_SAFETY_BANDS)}"
            )
        if c.record_type not in _VALID_RECORD_TYPES:
            errors.append(
                f"capability '{c.name}': record_type must be one of "
                f"{sorted(_VALID_RECORD_TYPES)}"
            )
        # Naming convention: tool.{invocation_mode}.{...}
        if c.name and c.invocation_mode in _VALID_INVOCATION_MODES:
            expected_prefix = f"tool.{c.invocation_mode}."
            if not c.name.startswith(expected_prefix):
                errors.append(f"capability '{c.name}': name must start with '{expected_prefix}'")
        # Uniqueness within the connector
        if c.name in seen_names:
            errors.append(f"capability '{c.name}': duplicate capability name")
        return errors

    # ── Ingestion ──────────────────────────────────────────────────

    def _ingest_connector(self, d: ConnectorDefinition) -> None:
        now = _utc_now_iso()
        constitution_dict = asdict(d.constitution) if d.constitution is not None else {}
        policy_dict = (
            {
                "write_requires_actor_role": d.policy.write_requires_actor_role,
                "read_allowed_roles": d.policy.read_allowed_roles,
                "hil_triggers": d.policy.hil_triggers,
                "protected_resources": d.policy.protected_resources,
            }
            if d.policy is not None
            else {}
        )
        self.store.upsert_connector(
            ConnectorRecord(
                connector_id=d.connector_id,
                label=d.label,
                connector_type=d.connector_type,
                provider_type=d.provider_type,
                version=d.version,
                admission_verdict=d.admission_verdict,
                registration_type=d.registration_type,
                constitution=constitution_dict,
                policy_declarations=policy_dict,
                resource_kinds=list(d.resource_kinds),
                created_at=now,
                updated_at=now,
            )
        )

    def _ingest_capabilities(self, d: ConnectorDefinition) -> int:
        now = _utc_now_iso()
        domain = d.connector_id.split(".")[0] if "." in d.connector_id else d.connector_id
        count = 0
        for cap in d.capabilities:
            self.store.upsert_capability(
                CapabilityRecord(
                    capability_name=cap.name,
                    connector_id=d.connector_id,
                    invocation_mode=cap.invocation_mode,
                    action_name=cap.action_name,
                    effect=cap.effect,
                    resource_kind=cap.resource_kind,
                    description=cap.description,
                    required_inputs=[asdict(f) for f in cap.required_inputs],
                    optional_inputs=[asdict(f) for f in cap.optional_inputs],
                    output_schema_ref=cap.output_schema_ref,
                    safety_band_min=cap.safety_band_min,
                    risk_class=cap.risk_class,
                    idempotency=cap.idempotency,
                    compensation_capability=cap.compensation_capability,
                    record_type=cap.record_type,
                    created_at=now,
                    contract_json=_capability_contract_json(cap),
                )
            )
            # Seed capability_type_index so the typed resolver can find this
            # capability.  One row per (capability, resource_family) — the
            # multi-resource projection per Epic 1.1.  Capabilities apply to
            # every resource_kind the connector declares.
            op_family, type_effect = UNIVERSAL_OPERATION_ALIASES.get(
                cap.action_name,
                (cap.action_name, "write" if cap.invocation_mode == "execute" else "read"),
            )
            index_resource_families = d.resource_kinds or (
                [cap.resource_kind] if cap.resource_kind else []
            )
            for resource_family in index_resource_families:
                self.store.upsert_capability_type_index(
                    capability_name=cap.name,
                    connector_id=d.connector_id,
                    domain=domain,
                    resource_family=resource_family,
                    operation_family=op_family,
                    effect=type_effect,
                    side_effect_class=None,
                    risk_class=cap.risk_class,
                )
            count += 1
        return count

    def _ingest_constitution(self, d: ConnectorDefinition) -> None:
        c = d.constitution
        if c is None:
            return
        self.store.upsert_constitution(
            ConstitutionRecord(
                connector_id=d.connector_id,
                constitution_id=c.constitution_id or f"{d.connector_id}.v1",
                schema_version=c.schema_version,
                authored_by=c.authored_by,
                authored_at=c.authored_at,
                last_proven_at=None,
                execution_phases=list(c.execution_phases),
                prerequisite_reads=list(c.prerequisite_reads),
                conflict_analysis_rules=list(c.conflict_analysis_rules),
                hil_gates=list(c.hil_gates),
                mutation_sequencing=list(c.mutation_sequencing),
                verification_requirements=list(c.verification_requirements),
                companion_resource_roles=list(c.companion_resource_roles),
                precondition_summary=c.precondition_summary,
                companion_resource_summary=c.companion_resource_summary,
                hil_trigger_summary=c.hil_trigger_summary,
                degradation_policy=c.degradation_policy,
            )
        )

    def _ingest_resource_kinds(self, d: ConnectorDefinition) -> None:
        now = _utc_now_iso()
        for rk in d.resource_kinds:
            self.store.upsert_resource_kind(
                ResourceKindRecord(
                    kind_id=rk,
                    connector_id=d.connector_id,
                    label=rk.replace("_", " ").title(),
                    created_at=now,
                )
            )

    def _ingest_ontology(self, d: ConnectorDefinition) -> None:
        if d.ontology is None:
            return
        domain = d.ontology.domain or (
            d.connector_id.split(".")[0] if "." in d.connector_id else d.connector_id
        )

        for entry in d.ontology.concept_aliases:
            alias = entry.get("alias")
            concept = entry.get("canonical_concept")
            if alias and concept:
                self.store.upsert_concept_alias(
                    alias=str(alias),
                    canonical_concept=str(concept),
                    domain=domain,
                    weight=float(entry.get("weight", 1.0)),
                )

        for entry in d.ontology.concept_resource_edges:
            concept = entry.get("concept")
            resource_family = entry.get("resource_family")
            if concept and resource_family:
                self.store.upsert_concept_resource_edge(
                    concept=str(concept),
                    resource_family=str(resource_family),
                    domain=domain,
                    weight=float(entry.get("weight", 1.0)),
                )

        for entry in d.ontology.resource_connector_edges:
            resource_family = entry.get("resource_family")
            connector_id = entry.get("connector_id") or d.connector_id
            if resource_family:
                self.store.upsert_resource_connector_edge(
                    domain=domain,
                    resource_family=str(resource_family),
                    connector_id=str(connector_id),
                    weight=float(entry.get("weight", 1.0)),
                    role=str(entry.get("role", "primary")),
                )

        for entry in d.ontology.operation_aliases:
            alias = entry.get("alias")
            operation_family = entry.get("operation_family")
            effect = entry.get("effect")
            if alias and operation_family and effect:
                self.store.upsert_operation_alias(
                    alias=str(alias),
                    operation_family=str(operation_family),
                    effect=str(effect),
                )

    def _ingest_connector_fts_text(self, d: ConnectorDefinition) -> None:
        """Build and upsert connector-level FTS search_text from the definition.

        Aggregates label, description, capability names/descriptions,
        resource kinds, and ontology aliases into a single searchable
        text field for FTS5 + embedding retrieval.
        """
        parts: list[str] = [
            d.label or "",
            d.description or "",
        ]
        for cap in d.capabilities or []:
            parts.append(cap.name or "")
            parts.append(cap.description or "")
        for rk in d.resource_kinds or []:
            parts.append(str(rk))
        ont = getattr(d, "ontology", None) or {}
        for alias in ont.get("concept_aliases", []) or []:
            if isinstance(alias, dict):
                parts.append(alias.get("alias", ""))
            else:
                parts.append(str(alias))
        for alias in ont.get("operation_aliases", []) or []:
            if isinstance(alias, dict):
                parts.append(alias.get("alias", ""))
            else:
                parts.append(str(alias))
        search_text = " ".join(p for p in parts if p)
        if not search_text.strip():
            return
        self.store.upsert_connector_fts_text(
            connector_id=d.connector_id,
            label=d.label or "",
            description=d.description or "",
            search_text=search_text,
        )


# ── Helpers ────────────────────────────────────────────────────────────


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capability_contract_json(cap: CapabilityDefinition) -> dict:
    """Build the authoritative ``contract_json`` blob for a capability.

    Prefers the full JSON Schemas when present, falling back to the
    skinny ``InputFieldSpec`` lists.
    """
    return {
        "name": cap.name,
        "action_name": cap.action_name,
        "invocation_mode": cap.invocation_mode,
        "effect": cap.effect,
        "resource_kind": cap.resource_kind,
        "description": cap.description,
        "required_inputs": [asdict(f) for f in cap.required_inputs],
        "optional_inputs": [asdict(f) for f in cap.optional_inputs],
        "input_schema": cap.input_schema,
        "output_schema": cap.output_schema,
        "output_schema_ref": cap.output_schema_ref,
        "safety_band_min": cap.safety_band_min,
        "risk_class": cap.risk_class,
        "idempotency": cap.idempotency,
        "compensation_capability": cap.compensation_capability,
        "record_type": cap.record_type,
    }
