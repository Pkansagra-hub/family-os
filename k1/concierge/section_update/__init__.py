"""Section-update classifier contract for Concierge Front deloading.

M1 owns pure contracts, vocabulary, idempotency, compiler, and stub adapter
surfaces only. Lifecycle wiring belongs to M2.
"""

from __future__ import annotations

from k1.concierge.section_update.apply import (
    SectionUpdateApplyResult,
    apply_section_update_plan,
    summarize_writer_result,
)
from k1.concierge.section_update.classifier import (
    DeterministicSectionUpdateClassifier,
    ISectionUpdateClassifier,
)
from k1.concierge.section_update.events import (
    SectionUpdateCompletionStatus,
    build_section_update_completed_payload,
    build_section_update_requested_payload,
)
from k1.concierge.section_update.idempotency import (
    SectionUpdateIdempotencyStore,
    build_mutation_idempotency_key,
    build_plan_idempotency_key,
)
from k1.concierge.section_update.input_builder import build_section_update_input
from k1.concierge.section_update.lifecycle import (
    SectionUpdateClassificationResult,
    SectionUpdateLifecycleResult,
    classify_section_update_blocking,
    run_shadow_section_update,
)
from k1.concierge.section_update.live_api import (
    LIVE_TURN_COMPLETED_TOPIC,
    LiveTurnNormalizationResult,
    build_live_section_update_input,
    is_live_turn_complete_record,
    normalize_live_turn_complete_record,
)
from k1.concierge.section_update.overlay import (
    OVERLAY_TASK_PAYLOAD_KEY,
    attach_overlay_to_task_payload,
    build_dispatch_overlay_from_plan,
    degraded_turn_state_overlay,
    normalize_turn_state_overlay_payload,
    summarize_task_overlay,
)
from k1.concierge.section_update.plan_compiler import (
    CompileDiagnostic,
    CompileResult,
    CompileStatus,
    PlanCompiler,
)
from k1.concierge.section_update.types import (
    ApplyTiming,
    ClassifierMode,
    CommitClass,
    RejectedCandidate,
    SectionMutation,
    SectionUpdateInput,
    SectionUpdatePlan,
    SectionUpdateValidation,
    TurnStateOverlay,
)
from k1.concierge.section_update.vocabulary import (
    CLASSIFIER_OPERATION_REGISTRY,
    FORBIDDEN_SECTIONS,
    LLM_WRITABLE_SECTIONS,
    allowed_operations,
    validate_target,
)
from k1.concierge.section_update.worker import (
    SectionUpdateBackgroundWorker,
    SectionUpdateWorkerConfig,
    SectionUpdateWorkerStats,
)

__all__ = [
    "ApplyTiming",
    "SectionUpdateApplyResult",
    "apply_section_update_plan",
    "summarize_writer_result",
    "ClassifierMode",
    "CommitClass",
    "RejectedCandidate",
    "SectionMutation",
    "SectionUpdateInput",
    "SectionUpdatePlan",
    "SectionUpdateValidation",
    "TurnStateOverlay",
    "CLASSIFIER_OPERATION_REGISTRY",
    "FORBIDDEN_SECTIONS",
    "LLM_WRITABLE_SECTIONS",
    "allowed_operations",
    "validate_target",
    "SectionUpdateIdempotencyStore",
    "build_mutation_idempotency_key",
    "build_plan_idempotency_key",
    "build_section_update_input",
    "SectionUpdateCompletionStatus",
    "build_section_update_completed_payload",
    "build_section_update_requested_payload",
    "SectionUpdateClassificationResult",
    "SectionUpdateLifecycleResult",
    "classify_section_update_blocking",
    "run_shadow_section_update",
    "LIVE_TURN_COMPLETED_TOPIC",
    "LiveTurnNormalizationResult",
    "build_live_section_update_input",
    "is_live_turn_complete_record",
    "normalize_live_turn_complete_record",
    "OVERLAY_TASK_PAYLOAD_KEY",
    "attach_overlay_to_task_payload",
    "build_dispatch_overlay_from_plan",
    "degraded_turn_state_overlay",
    "normalize_turn_state_overlay_payload",
    "summarize_task_overlay",
    "CompileDiagnostic",
    "CompileResult",
    "CompileStatus",
    "PlanCompiler",
    "DeterministicSectionUpdateClassifier",
    "ISectionUpdateClassifier",
    "SectionUpdateBackgroundWorker",
    "SectionUpdateWorkerConfig",
    "SectionUpdateWorkerStats",
]
