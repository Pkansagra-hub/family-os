"""ConstitutionLoader — Epic 5.2.

The single read path for connector constitutions.  Loads from the
``GlobalProjectionStore.connector_constitutions`` table, validates against
the ``ConstitutionArtifact`` schema, and returns typed artifacts.

No consumer reads the store's constitution rows directly — they all go
through this loader so validation happens exactly once, at load time.

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epic 5.2.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from k1.fabric.constitution.schema import (
    ConflictRule,
    ConstitutionArtifact,
    ConstitutionValidationError,
    HILGate,
    MutationStep,
    PrerequisiteRead,
    VerificationRequirement,
    validate_constitution,
    validate_constitution_semantics,
)
from k1.fabric.stores.global_projection_store import (
    ConstitutionRecord,
    GlobalProjectionStore,
)

logger = logging.getLogger(__name__)


class ConstitutionLoader:
    """Loads and validates connector constitutions from the global store."""

    def __init__(self, global_store: GlobalProjectionStore) -> None:
        self.global_store = global_store

    # ── Public API ─────────────────────────────────────────────────

    def load(
        self,
        connector_id: str,
        *,
        known_resource_kinds: set[str] | None = None,
    ) -> ConstitutionArtifact | None:
        """Load a single connector's constitution.

        Returns ``None`` if not found.  Runs structural validation always;
        runs semantic validation when ``known_resource_kinds`` is provided.
        Raises ``ConstitutionValidationError`` if the stored data is invalid.
        """
        raw = self._load_raw(connector_id)
        if raw is None:
            return None

        artifact = validate_constitution(raw)

        # RES-016: populate teaching-surface fields from old structured fields
        artifact = _populate_teaching_fields(artifact)

        if known_resource_kinds is not None:
            violations = validate_constitution_semantics(artifact, known_resource_kinds)
            if violations:
                raise ConstitutionValidationError(
                    f"constitution for '{connector_id}' failed semantic validation: "
                    + "; ".join(violations)
                )

        return artifact

    def load_all(
        self,
        *,
        known_resource_kinds: set[str] | None = None,
    ) -> list[ConstitutionArtifact]:
        """Load all constitutions.

        Skips connectors with missing or invalid constitutions (logs a
        warning and continues) — a corrupt constitution for one connector
        must not block the whole system.
        """
        artifacts: list[ConstitutionArtifact] = []
        for record in self.global_store.list_constitutions():
            try:
                raw = _record_to_dict(record)
                artifact = validate_constitution(raw)
                if known_resource_kinds is not None:
                    violations = validate_constitution_semantics(artifact, known_resource_kinds)
                    if violations:
                        logger.warning(
                            "skipping constitution %s: semantic violations: %s",
                            record.connector_id,
                            "; ".join(violations),
                        )
                        continue
                artifacts.append(artifact)
            except ConstitutionValidationError as exc:
                logger.warning(
                    "skipping invalid constitution %s: %s",
                    record.connector_id,
                    exc,
                )
        return artifacts

    # ── Convenience accessors ──────────────────────────────────────

    def get_prerequisite_reads(self, connector_id: str) -> list[PrerequisiteRead]:
        artifact = self.load(connector_id)
        return list(artifact.prerequisite_reads) if artifact else []

    def get_verification_requirements(self, connector_id: str) -> list[VerificationRequirement]:
        artifact = self.load(connector_id)
        return list(artifact.verification_requirements) if artifact else []

    def get_hil_gates(self, connector_id: str) -> list[HILGate]:
        artifact = self.load(connector_id)
        return list(artifact.hil_gates) if artifact else []

    def get_conflict_rules(self, connector_id: str) -> list[ConflictRule]:
        artifact = self.load(connector_id)
        return list(artifact.conflict_analysis_rules) if artifact else []

    def get_mutation_sequence(self, connector_id: str) -> list[MutationStep]:
        artifact = self.load(connector_id)
        if artifact is None:
            return []
        return sorted(artifact.mutation_sequencing, key=lambda s: s.order)

    # ── Internal ───────────────────────────────────────────────────

    def _load_raw(self, connector_id: str) -> dict[str, Any] | None:
        """Load the stored constitution as a plain dict, without validation."""
        record = self.global_store.get_constitution(connector_id)
        if record is None:
            return None
        return _record_to_dict(record)

    def _row_to_artifact(self, record: ConstitutionRecord) -> ConstitutionArtifact:
        """Validate a ``ConstitutionRecord`` into a typed artifact."""
        return validate_constitution(_record_to_dict(record))


# ── RES-016: Teaching field population (2026-06-17) ────────────────────


def _populate_teaching_fields(artifact: ConstitutionArtifact) -> ConstitutionArtifact:
    """Map old structured constitution fields into new teaching-surface prose fields.

    This is a lazy, additive transform — old fields are preserved, new
    fields are derived.  Call from ConstitutionLoader.load() after validation.
    """
    # 1. mutation_sequencing → how_to_sequence
    if not artifact.how_to_sequence and artifact.mutation_sequencing:
        steps: list[str] = []
        for m in sorted(artifact.mutation_sequencing, key=lambda s: s.order):
            desc = getattr(m, "description", "") or ""
            steps.append(f"{m.order}. [{m.phase}] {m.operation}: {desc}")
        artifact = dataclasses.replace(artifact, how_to_sequence=steps)

    # 2. verification_requirements → what_to_verify
    if not artifact.what_to_verify and artifact.verification_requirements:
        checks: list[str] = []
        for v in artifact.verification_requirements:
            method = getattr(v, "method", "") or ""
            desc = getattr(v, "description", "") or ""
            checks.append(f"After {method}: {desc}")
        artifact = dataclasses.replace(artifact, what_to_verify=checks)

    # 3. hil_gates → when_to_ask_human
    if not artifact.when_to_ask_human and artifact.hil_gates:
        gates: list[dict] = []
        for g in artifact.hil_gates:
            trigger = getattr(g, "trigger", "") or ""
            prompt = getattr(g, "prompt", "") or ""
            gates.append({"trigger": trigger, "reason": prompt, "prompt": prompt})
        artifact = dataclasses.replace(artifact, when_to_ask_human=gates)

    # 4. companion_resource_roles → companion_connectors
    if not artifact.companion_connectors and artifact.companion_resource_roles:
        companions: list[dict] = []
        for c in artifact.companion_resource_roles:
            rk = getattr(c, "resource_kind", "") or ""
            role = getattr(c, "role", "") or ""
            desc = getattr(c, "description", "") or ""
            companions.append(
                {
                    "connector_id": "",  # resolved at runtime via GPS lookup
                    "resource_kind": rk,
                    "role": role,
                    "description": desc,
                }
            )
        artifact = dataclasses.replace(artifact, companion_connectors=companions)

    # 5. conflict_analysis_rules → conflict_rules
    if not artifact.conflict_rules and artifact.conflict_analysis_rules:
        rules: list[str] = []
        for r in artifact.conflict_analysis_rules:
            check = getattr(r, "check", "") or ""
            with_kinds = getattr(r, "with_resource_kinds", []) or []
            desc = getattr(r, "description", "") or ""
            resolution = getattr(r, "resolution", "") or ""
            kinds_str = ", ".join(with_kinds) if with_kinds else "other resources"
            rules.append(f"If {check} with {kinds_str}: {desc}. Resolution: {resolution}")
        artifact = dataclasses.replace(artifact, conflict_rules=rules)

    return artifact


# ── Helpers ────────────────────────────────────────────────────────────


def _record_to_dict(record: ConstitutionRecord) -> dict[str, Any]:
    """Convert a typed ``ConstitutionRecord`` into the dict shape that
    ``validate_constitution`` expects.

    The store already deserializes the JSON columns into Python lists/dicts,
    so this is a straightforward field projection.
    """
    return dataclasses.asdict(record)
