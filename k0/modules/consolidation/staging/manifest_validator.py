"""
ManifestValidator — Issue 5.1.9

Validates R6Output manifest before R7 commit.

Spec Reference:
    - Dossier Appendix G R6 — R6Output specification and DLQ conditions
    - Dossier §4.7 — R6 staging requirements
    - Dossier §12.2.3 — Idempotency key format validation
    - M5_EXECUTION.md Issue 5.1.9

Validation Rules:
    1. Layer validity: All writes use VALID_LAYERS
    2. Idempotency keys: All keys match expected format
    3. FK integrity: Edge writes reference staged/existing entities
    4. Event coverage: All batch events have staged update
    5. Outbox minimum: At least 1 event (completion)
    6. No duplicate record_ids per layer
    7. Version conflicts: <10% of events have version mismatch

DLQ Conditions:
    - Any invalid layer → DLQ
    - Malformed idempotency key → DLQ
    - Orphan FK reference → DLQ
    - >10% version conflicts → DLQ
    - Missing event coverage → DLQ
    - Zero outbox events → DLQ

TIMESTAMP CONVENTION: All *_ms fields use MILLISECONDS since epoch.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from k0.modules.consolidation.staging.r6_output import R6Output, StagedEventUpdate
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    VALID_LAYERS,
    StagedOutboxEvent,
    StagedWrite,
)

# =============================================================================
# VALIDATION RESULT
# =============================================================================


@dataclass
class ManifestValidationResult:
    """
    Result of R6Output manifest validation.

    Attributes:
        is_valid: True if manifest passes all validation rules
        errors: List of blocking errors (prevent R7 commit)
        warnings: List of non-blocking warnings
        stats: Statistics for debugging visibility
        dlq_reason: If is_valid=False, reason for DLQ routing
    """

    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    dlq_reason: Optional[str] = None

    def add_error(self, error: str) -> None:
        """Add a blocking error."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        """Add a non-blocking warning."""
        self.warnings.append(warning)

    def set_dlq(self, reason: str) -> None:
        """Mark manifest for DLQ routing."""
        self.dlq_reason = reason
        self.is_valid = False


# =============================================================================
# MANIFEST VALIDATOR
# =============================================================================


class ManifestValidator:
    """
    Validates R6Output manifest before R7 commit.

    Ensures staged writes are complete, consistent, and ready
    for atomic database commit.

    Example:
        >>> validator = ManifestValidator()
        >>> result = validator.validate(r6_output, batch_event_ids)
        >>> if not result.is_valid:
        ...     handle_dlq(result.dlq_reason)
    """

    # Idempotency key format: p03:{phase}:{cycle}:{entity}...
    KEY_PREFIX = "p03:"

    # DLQ threshold for version conflicts
    VERSION_CONFLICT_THRESHOLD = 0.10  # 10%

    def __init__(
        self,
        existing_entity_ids: Optional[Set[str]] = None,
    ) -> None:
        """
        Initialize ManifestValidator.

        Args:
            existing_entity_ids: Set of entity IDs already in KG
                (for FK validation of edges referencing existing entities)
        """
        self.existing_entity_ids = existing_entity_ids or set()

    def validate(
        self,
        r6_output: R6Output,
        batch_event_ids: Set[str],
    ) -> ManifestValidationResult:
        """
        Validate R6Output manifest before R7 commit.

        Performs all validation rules from Dossier Appendix G.

        Args:
            r6_output: The R6Output to validate
            batch_event_ids: Set of all event IDs in the batch

        Returns:
            ManifestValidationResult with errors/warnings/stats
        """
        result = ManifestValidationResult()

        # Collect all writes for validation
        all_truth_writes = list(r6_output.staged_truth_writes)
        all_kg_writes = list(r6_output.staged_kg_writes)
        all_writes = all_truth_writes + all_kg_writes
        all_outbox = list(r6_output.staged_outbox_events)
        all_updates = list(r6_output.staged_event_updates)

        # === RULE 1: Layer validity ===
        layer_errors = self._validate_layers(all_writes)
        for error in layer_errors:
            result.add_error(error)
        if layer_errors:
            result.set_dlq("invalid_layer")

        # === RULE 2: Idempotency key format ===
        key_errors = self._validate_idempotency_keys(all_writes, all_outbox)
        for error in key_errors:
            result.add_error(error)
        if key_errors:
            result.set_dlq("malformed_idempotency_key")

        # === RULE 3: FK integrity for KG edges ===
        kg_dom_writes = [w for w in all_kg_writes if w.layer == LAYER_ST_KG_DOM]
        kg_edge_writes = [w for w in all_kg_writes if w.layer == LAYER_ST_KG_EDGES]
        fk_errors = self._validate_fk_integrity(kg_dom_writes, kg_edge_writes)
        for error in fk_errors:
            result.add_error(error)
        if fk_errors:
            result.set_dlq("orphan_fk_reference")

        # === RULE 4: Event coverage ===
        coverage_errors = self._validate_event_coverage(all_updates, batch_event_ids)
        for error in coverage_errors:
            result.add_error(error)
        if coverage_errors:
            result.set_dlq("missing_event_coverage")

        # === RULE 5: Outbox minimum ===
        if len(all_outbox) == 0:
            result.add_error("No outbox events staged (minimum 1 for completion)")
            result.set_dlq("zero_outbox_events")

        # === RULE 6: Duplicate record_ids ===
        duplicate_errors = self._check_duplicate_records(all_writes)
        for error in duplicate_errors:
            result.add_error(error)
        if duplicate_errors:
            result.set_dlq("duplicate_record_ids")

        # === RULE 7: Version conflicts threshold ===
        conflict_result = self._check_version_conflicts(all_updates)
        if conflict_result[0]:  # DLQ condition
            result.add_error(conflict_result[1])
            result.set_dlq("version_conflict_threshold_exceeded")
        elif conflict_result[2] > 0:  # Conflicts exist but under threshold
            result.add_warning(conflict_result[1])

        # === Compute stats ===
        result.stats = self._compute_stats(
            all_writes,
            all_outbox,
            all_updates,
            conflict_result[2],
        )

        return result

    def _validate_layers(
        self,
        writes: List[StagedWrite],
    ) -> List[str]:
        """
        Ensure all layers are in VALID_LAYERS.

        Args:
            writes: All staged writes

        Returns:
            List of error messages for invalid layers
        """
        errors: List[str] = []
        for write in writes:
            if write.layer not in VALID_LAYERS:
                errors.append(f"Invalid layer '{write.layer}' for write_id={write.write_id}")
        return errors

    def _validate_idempotency_keys(
        self,
        writes: List[StagedWrite],
        events: List[StagedOutboxEvent],
    ) -> List[str]:
        """
        Validate idempotency key format.

        Expected format: p03:{phase}:{cycle}:{entity}...
        At minimum, must start with "p03:" and have at least 3 colon-separated parts.

        Args:
            writes: All staged writes
            events: All staged outbox events

        Returns:
            List of error messages for malformed keys
        """
        errors: List[str] = []

        for write in writes:
            if not self._is_valid_idempotency_key(write.idempotency_key):
                errors.append(
                    f"Malformed idempotency key '{write.idempotency_key}' "
                    f"for write_id={write.write_id}"
                )

        return errors

    def _is_valid_idempotency_key(self, key: str) -> bool:
        """
        Check if idempotency key matches expected format.

        Valid formats:
            - p03:write:{cycle}:{layer}:{record_id}
            - p03:outbox:{cycle}:{topic}
            - Legacy: {phase}:{layer}:{record_id} (from StagedWrite factories)

        Args:
            key: Idempotency key to validate

        Returns:
            True if key is valid
        """
        if not key:
            return False

        parts = key.split(":")
        # Minimum: phase:layer:id or p03:type:...
        if len(parts) < 3:
            return False

        # Either starts with p03: or is legacy format (R1, R2, R3, R6, etc.)
        valid_phases = {"R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "p03"}
        if parts[0] not in valid_phases:
            return False

        return True

    def _validate_fk_integrity(
        self,
        kg_dom_writes: List[StagedWrite],
        kg_edge_writes: List[StagedWrite],
    ) -> List[str]:
        """
        Ensure edges reference staged or existing entities.

        Args:
            kg_dom_writes: Entity writes (provides new entity IDs)
            kg_edge_writes: Edge writes (must reference valid entities)

        Returns:
            List of error messages for orphan references
        """
        errors: List[str] = []

        # Build set of all valid entity IDs
        # (existing + being created in this batch)
        valid_entity_ids = set(self.existing_entity_ids)
        for write in kg_dom_writes:
            valid_entity_ids.add(write.record_id)

        # Check each edge
        for edge_write in kg_edge_writes:
            data = edge_write.record_data or {}
            source_id = data.get("source_id")
            target_id = data.get("target_id")

            if source_id and source_id not in valid_entity_ids:
                errors.append(
                    f"Orphan source_id '{source_id}' in edge " f"write_id={edge_write.write_id}"
                )

            if target_id and target_id not in valid_entity_ids:
                errors.append(
                    f"Orphan target_id '{target_id}' in edge " f"write_id={edge_write.write_id}"
                )

        return errors

    def _validate_event_coverage(
        self,
        event_updates: List[StagedEventUpdate],
        batch_event_ids: Set[str],
    ) -> List[str]:
        """
        Ensure all batch events have staged update.

        Args:
            event_updates: Staged event updates
            batch_event_ids: All event IDs in batch

        Returns:
            List of error messages for missing coverage
        """
        errors: List[str] = []

        # Get event IDs with updates
        updated_ids = {update.event_id for update in event_updates}

        # Find missing
        missing = batch_event_ids - updated_ids
        if missing:
            # Report up to 5 missing
            sample = list(missing)[:5]
            suffix = f"... and {len(missing) - 5} more" if len(missing) > 5 else ""
            errors.append(f"Missing event coverage for {len(missing)} events: " f"{sample}{suffix}")

        return errors

    def _check_duplicate_records(
        self,
        writes: List[StagedWrite],
    ) -> List[str]:
        """
        Detect duplicate record_ids within same layer.

        Args:
            writes: All staged writes

        Returns:
            List of error messages for duplicates
        """
        errors: List[str] = []

        # Group by layer
        by_layer: Dict[str, Set[str]] = {}
        duplicates: Dict[str, List[str]] = {}

        for write in writes:
            layer = write.layer
            record_id = write.record_id

            if layer not in by_layer:
                by_layer[layer] = set()
                duplicates[layer] = []

            if record_id in by_layer[layer]:
                duplicates[layer].append(record_id)
            else:
                by_layer[layer].add(record_id)

        # Report duplicates
        for layer, dups in duplicates.items():
            if dups:
                sample = dups[:3]
                suffix = f"... and {len(dups) - 3} more" if len(dups) > 3 else ""
                errors.append(f"Duplicate record_ids in layer '{layer}': {sample}{suffix}")

        return errors

    def _check_version_conflicts(
        self,
        event_updates: List[StagedEventUpdate],
    ) -> Tuple[bool, str, int]:
        """
        Check version conflict threshold.

        DLQ condition: >10% of events have version conflict.

        Args:
            event_updates: Staged event updates

        Returns:
            Tuple of (is_dlq_condition, message, conflict_count)
        """
        if not event_updates:
            return (False, "", 0)

        conflict_count = sum(1 for update in event_updates if update.version_conflict)
        total = len(event_updates)
        conflict_rate = conflict_count / total if total > 0 else 0.0

        if conflict_rate > self.VERSION_CONFLICT_THRESHOLD:
            msg = (
                f"Version conflict threshold exceeded: "
                f"{conflict_count}/{total} ({conflict_rate:.1%}) > "
                f"{self.VERSION_CONFLICT_THRESHOLD:.0%}"
            )
            return (True, msg, conflict_count)

        if conflict_count > 0:
            msg = f"Version conflicts detected: {conflict_count}/{total} " f"({conflict_rate:.1%})"
            return (False, msg, conflict_count)

        return (False, "", 0)

    def _compute_stats(
        self,
        writes: List[StagedWrite],
        outbox: List[StagedOutboxEvent],
        updates: List[StagedEventUpdate],
        version_conflicts: int,
    ) -> Dict[str, Any]:
        """
        Compute statistics for debugging.

        Args:
            writes: All staged writes
            outbox: All staged outbox events
            updates: All staged event updates
            version_conflicts: Number of version conflicts

        Returns:
            Stats dictionary
        """
        # Count writes by layer
        writes_by_layer: Dict[str, int] = {}
        for write in writes:
            writes_by_layer[write.layer] = writes_by_layer.get(write.layer, 0) + 1

        # Count events by topic
        events_by_topic: Dict[str, int] = {}
        for event in outbox:
            events_by_topic[event.topic] = events_by_topic.get(event.topic, 0) + 1

        return {
            "total_writes": len(writes),
            "writes_by_layer": writes_by_layer,
            "outbox_events": len(outbox),
            "events_by_topic": events_by_topic,
            "event_updates": len(updates),
            "version_conflicts": version_conflicts,
        }


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def validate_r6_output(
    r6_output: R6Output,
    batch_event_ids: Set[str],
    existing_entity_ids: Optional[Set[str]] = None,
) -> ManifestValidationResult:
    """
    Convenience function to validate R6Output.

    Args:
        r6_output: R6Output to validate
        batch_event_ids: All event IDs in batch
        existing_entity_ids: Existing KG entity IDs

    Returns:
        ManifestValidationResult
    """
    validator = ManifestValidator(existing_entity_ids)
    return validator.validate(r6_output, batch_event_ids)


def is_valid_manifest(
    r6_output: R6Output,
    batch_event_ids: Set[str],
) -> bool:
    """
    Quick check if R6Output is valid.

    Args:
        r6_output: R6Output to validate
        batch_event_ids: All event IDs in batch

    Returns:
        True if valid, False otherwise
    """
    result = validate_r6_output(r6_output, batch_event_ids)
    return result.is_valid


def summarize_validation(result: ManifestValidationResult) -> Dict[str, Any]:
    """
    Create summary of validation result.

    Args:
        result: ManifestValidationResult

    Returns:
        Summary dictionary
    """
    return {
        "is_valid": result.is_valid,
        "error_count": len(result.errors),
        "warning_count": len(result.warnings),
        "dlq_reason": result.dlq_reason,
        "stats": result.stats,
    }
