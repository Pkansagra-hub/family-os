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


# ── Helpers ────────────────────────────────────────────────────────────


def _record_to_dict(record: ConstitutionRecord) -> dict[str, Any]:
    """Convert a typed ``ConstitutionRecord`` into the dict shape that
    ``validate_constitution`` expects.

    The store already deserializes the JSON columns into Python lists/dicts,
    so this is a straightforward field projection.
    """
    return dataclasses.asdict(record)
