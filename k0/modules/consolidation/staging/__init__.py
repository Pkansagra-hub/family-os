"""
R6 Staging Module — Issue 5.0.1

Provides components for R6 phase: accumulate staged writes,
validate, and prepare for atomic R7 commit.

Spec Reference:
    - Dossier §4.7 (R6 — Staging Table Updates)
    - M5_EXECUTION.md (Issue 5.0.1, 5.1.1-5.1.12)

Components (populated as issues complete):
    - R6Output: Core output dataclass containing all staged writes
    - StagedEventUpdate: Per-event status update for st_hipp_events
    - StagedWritesContainer: Mutable container that builds R6Output
    - ConsolidationStatusMarker: Status assignment logic (Issue 5.1.2)
    - DedupMetadataPopulator: Near-duplicates JSON builder (Issue 5.1.3)
    - ReconciliationRecorder: Decision audit trail (Issue 5.1.4)
    - IdempotencyKeyGenerator: Key generation (Issue 5.1.5)
    - StagedTruthAssembler: Truth layer write assembly (Issue 5.1.6)
    - StagedKGAssembler: KG entity/edge assembly (Issue 5.1.7)
    - StagedOutboxAssembler: Outbox event assembly (Issue 5.1.8)
    - ManifestValidator: Pre-commit validation (Issue 5.1.9)
    - ReconciliationSummary: Cycle statistics (Issue 5.1.10)
    - R6Coordinator: Phase orchestration (Issue 5.1.11)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

# Issue 5.1.3 exports (DedupMetadataPopulator)
from k0.modules.consolidation.staging.dedup_metadata import (
    DedupMetadata,
    DedupMetadataPopulator,
    NearDuplicateEntry,
    create_near_duplicate_entry,
    parse_near_duplicates_json,
    parse_novelty_bonuses_json,
)

# Issue 5.1.5 exports (IdempotencyKeyGenerator)
from k0.modules.consolidation.staging.idempotency import (
    IdempotencyKeyGenerator,
    ParsedKey,
    extract_cycle_ulid,
    keys_same_cycle,
    parse_idempotency_key,
    validate_idempotency_key,
)

# GAP-001 Phase 4 exports (IntentSignalAssembler)
from k0.modules.consolidation.staging.intent_signal_assembler import (
    IntentSignalAssembler,
    assemble_intent_signal_writes,
)

# Issue 5.1.7 exports (KGWriteAssembler)
from k0.modules.consolidation.staging.kg_write_assembler import (
    KGWriteAssembler,
    ValidationResult,
    count_kg_writes,
    summarize_kg_assembly,
)

# Issue 5.1.9 exports (ManifestValidator)
from k0.modules.consolidation.staging.manifest_validator import (
    ManifestValidationResult,
    ManifestValidator,
    is_valid_manifest,
    summarize_validation,
    validate_r6_output,
)

# Issue 5.1.8 exports (OutboxEventAssembler)
from k0.modules.consolidation.staging.outbox_assembler import (
    AssembledOutbox,
    OutboxEventAssembler,
    count_outbox_events,
    get_events_by_priority,
    summarize_outbox,
)

# Issue 5.1.11 exports (R6Coordinator)
from k0.modules.consolidation.staging.r6_coordinator import (
    R6Coordinator,
    R6CoordinatorConfig,
    R6CoordinatorResult,
    create_r6_coordinator,
)

# Issue 5.1.1 exports (R6Output, StagedEventUpdate, StagedWritesContainer)
from k0.modules.consolidation.staging.r6_output import (
    R6Output,
    ReconciliationSummary,
    StagedEventUpdate,
    StagedWritesContainer,
)

# Issue 5.1.4 exports (ReconciliationRecorder)
from k0.modules.consolidation.staging.reconciliation_recorder import (
    ReconciliationRecord,
    ReconciliationRecorder,
    parse_reconciliation_json,
    summarize_decisions,
)

# Issue 5.1.2 exports (ConsolidationStatusMarker)
from k0.modules.consolidation.staging.status_marker import ConsolidationStatusMarker, StatusResult

# Issue 5.1.10 exports (SummaryGenerator)
from k0.modules.consolidation.staging.summary_generator import (
    GeneratorResult,
    SummaryGenerator,
    count_actions,
    generate_summary,
    validate_total,
)

# Issue 4.3.13 exports (TruthQueryService - for ReconciliationEngine)
from k0.modules.consolidation.staging.truth_query_service import TruthCandidate, TruthQueryService

# Issue 5.1.6 exports (TruthWriteAssembler)
from k0.modules.consolidation.staging.truth_write_assembler import (
    AssembledWrite,
    TruthWriteAssembler,
    flatten_writes,
    summarize_assembly,
)

__all__ = [
    # Issue 5.1.1
    "R6Output",
    "StagedEventUpdate",
    "StagedWritesContainer",
    "ReconciliationSummary",
    # Issue 5.1.2
    "ConsolidationStatusMarker",
    "StatusResult",
    # Issue 5.1.3
    "DedupMetadata",
    "DedupMetadataPopulator",
    "NearDuplicateEntry",
    "create_near_duplicate_entry",
    "parse_near_duplicates_json",
    "parse_novelty_bonuses_json",
    # Issue 5.1.4
    "ReconciliationRecord",
    "ReconciliationRecorder",
    "parse_reconciliation_json",
    "summarize_decisions",
    # Issue 5.1.5
    "IdempotencyKeyGenerator",
    "ParsedKey",
    "parse_idempotency_key",
    "validate_idempotency_key",
    "extract_cycle_ulid",
    "keys_same_cycle",
    # Issue 5.1.6
    "TruthWriteAssembler",
    "AssembledWrite",
    "flatten_writes",
    "summarize_assembly",
    # Issue 5.1.7
    "KGWriteAssembler",
    "ValidationResult",
    "count_kg_writes",
    "summarize_kg_assembly",
    # Issue 5.1.8
    "OutboxEventAssembler",
    "AssembledOutbox",
    "count_outbox_events",
    "summarize_outbox",
    "get_events_by_priority",
    # Issue 5.1.9
    "ManifestValidator",
    "ManifestValidationResult",
    "validate_r6_output",
    "is_valid_manifest",
    "summarize_validation",
    # Issue 5.1.10
    "SummaryGenerator",
    "GeneratorResult",
    "generate_summary",
    "count_actions",
    "validate_total",
    # Issue 5.1.11
    "R6Coordinator",
    "R6CoordinatorConfig",
    "R6CoordinatorResult",
    "create_r6_coordinator",
    # GAP-001 Phase 4
    "IntentSignalAssembler",
    "assemble_intent_signal_writes",
    # Issue 4.3.13 (TruthQueryService)
    "TruthQueryService",
    "TruthCandidate",
]
