"""Whole-plan validation and BatchRequest compilation for section updates."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from k1.concierge.section_update.idempotency import (
    SectionUpdateIdempotencyStore,
    build_mutation_idempotency_key,
)
from k1.concierge.section_update.types import (
    RejectedCandidate,
    SectionMutation,
    SectionUpdatePlan,
)
from k1.concierge.section_update.vocabulary import validate_target
from k1.sessionstate.public_types import BatchRequest, MutationRequest

DEFAULT_CLASSIFIER_WRITER_ID = "tool:section_update_classifier"


class CompileStatus(str, Enum):
    """Compiler decision status."""

    COMPILED = "compiled"
    NOOP = "noop"
    REJECTED = "rejected"
    STALE = "stale"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class CompileDiagnostic:
    """Human/debug readable compile diagnostic."""

    code: str
    message: str
    section: str = ""
    operation: str = ""
    index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "section": self.section,
            "operation": self.operation,
            "index": self.index,
        }


@dataclass
class CompileResult:
    """Result of compiling a SectionUpdatePlan."""

    status: CompileStatus
    plan_id: str
    batch_request: BatchRequest | None = None
    accepted_mutations: list[SectionMutation] = field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = field(default_factory=list)
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == CompileStatus.COMPILED

    @property
    def writer_call_required(self) -> bool:
        return self.batch_request is not None and bool(self.batch_request.requests)

    def to_summary(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "plan_id": self.plan_id,
            "accepted": len(self.accepted_mutations),
            "rejected": len(self.rejected_candidates),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


class PlanCompiler:
    """Validate entire plans before creating writer-port batch requests."""

    def __init__(
        self,
        *,
        writer_id: str = DEFAULT_CLASSIFIER_WRITER_ID,
        stop_on_rejection: bool = True,
        idempotency_store: SectionUpdateIdempotencyStore | None = None,
    ) -> None:
        self.writer_id = writer_id
        self.stop_on_rejection = stop_on_rejection
        self.idempotency_store = idempotency_store

    def compile(
        self,
        plan: SectionUpdatePlan | Mapping[str, Any],
        *,
        current_snapshot_version: str | None = None,
        current_snapshot_epoch: str | None = None,
    ) -> CompileResult:
        """Compile a validated plan into a BatchRequest, or return diagnostics."""

        plan = plan if isinstance(plan, SectionUpdatePlan) else SectionUpdatePlan.from_dict(plan)
        mutations = [
            item if isinstance(item, SectionMutation) else SectionMutation.from_dict(item)
            for item in plan.mutations
        ]
        plan_rejected_candidates = [
            item if isinstance(item, RejectedCandidate) else RejectedCandidate.from_dict(item)
            for item in plan.rejected_candidates
        ]
        duplicate = self._check_duplicate(plan)
        if duplicate is not None:
            return duplicate

        stale = self._check_stale(
            plan,
            current_snapshot_version=current_snapshot_version,
            current_snapshot_epoch=current_snapshot_epoch,
        )
        if stale is not None:
            self._remember(plan, stale)
            return stale

        if not plan.mutations:
            result = CompileResult(
                status=CompileStatus.NOOP,
                plan_id=plan.plan_id,
                rejected_candidates=plan_rejected_candidates,
                diagnostics=[
                    CompileDiagnostic(
                        code="noop",
                        message="plan contains no mutations; writer_port is not called",
                    )
                ],
            )
            self._remember(plan, result)
            return result

        diagnostics: list[CompileDiagnostic] = []
        rejected: list[RejectedCandidate] = list(plan_rejected_candidates)
        for index, mutation in enumerate(mutations):
            target = validate_target(mutation.section, mutation.operation)
            if not target.ok:
                diagnostics.append(
                    CompileDiagnostic(
                        code="invalid_target",
                        message=target.reason,
                        section=mutation.section,
                        operation=mutation.operation,
                        index=index,
                    )
                )
                rejected.append(
                    RejectedCandidate(
                        section=mutation.section,
                        operation=mutation.operation,
                        reason=target.reason,
                        confidence=mutation.confidence,
                        data=mutation.data,
                    )
                )
            if not isinstance(mutation.data, dict):
                diagnostics.append(
                    CompileDiagnostic(
                        code="invalid_payload",
                        message="mutation data must be an object",
                        section=mutation.section,
                        operation=mutation.operation,
                        index=index,
                    )
                )

        if diagnostics:
            result = CompileResult(
                status=CompileStatus.REJECTED,
                plan_id=plan.plan_id,
                rejected_candidates=rejected,
                diagnostics=diagnostics,
            )
            self._remember(plan, result)
            return result

        requests: list[MutationRequest] = []
        for index, mutation in enumerate(mutations):
            mutation_key = mutation.idempotency_key or build_mutation_idempotency_key(
                plan_idempotency_key=plan.plan_idempotency_key,
                index=index,
                section=mutation.section,
                operation=mutation.operation,
                data=mutation.data,
            )
            request = MutationRequest.create(
                section=mutation.section,
                operation=mutation.operation,
                data=mutation.data,
                writer_id=self.writer_id,
                cognitive_trace_id=plan.cognitive_trace_id or f"section-update:{plan.plan_id}",
                estimated_bytes=estimate_mutation_bytes(mutation),
                delegated_from="section_update_classifier",
            )
            request.metadata.update(
                {
                    "section_update_plan_id": plan.plan_id,
                    "section_update_plan_key": plan.plan_idempotency_key,
                    "section_update_mutation_key": mutation_key,
                    "commit_class": mutation.commit_class.value,
                    "confidence": mutation.confidence,
                    "reason": mutation.reason,
                }
            )
            requests.append(request)

        batch = BatchRequest.create(
            requests=requests,
            writer_id=self.writer_id,
            cognitive_trace_id=plan.cognitive_trace_id or f"section-update:{plan.plan_id}",
            stop_on_rejection=self.stop_on_rejection,
        )
        result = CompileResult(
            status=CompileStatus.COMPILED,
            plan_id=plan.plan_id,
            batch_request=batch,
            accepted_mutations=list(mutations),
            rejected_candidates=rejected,
        )
        self._remember(plan, result)
        return result

    def _check_duplicate(self, plan: SectionUpdatePlan) -> CompileResult | None:
        if self.idempotency_store is None:
            return None
        record = self.idempotency_store.get(plan.plan_idempotency_key)
        if record is None:
            return None
        return CompileResult(
            status=CompileStatus.DUPLICATE,
            plan_id=plan.plan_id,
            diagnostics=[
                CompileDiagnostic(
                    code="duplicate_plan",
                    message=f"plan key already processed with status={record.status}",
                )
            ],
        )

    def _check_stale(
        self,
        plan: SectionUpdatePlan,
        *,
        current_snapshot_version: str | None,
        current_snapshot_epoch: str | None,
    ) -> CompileResult | None:
        diagnostics: list[CompileDiagnostic] = []
        if (
            current_snapshot_version is not None
            and plan.snapshot_version
            and plan.snapshot_version != current_snapshot_version
        ):
            diagnostics.append(
                CompileDiagnostic(
                    code="stale_snapshot_version",
                    message=(
                        "plan snapshot_version does not match current snapshot_version: "
                        f"{plan.snapshot_version} != {current_snapshot_version}"
                    ),
                )
            )
        if (
            current_snapshot_epoch is not None
            and plan.snapshot_source_epoch
            and plan.snapshot_source_epoch != current_snapshot_epoch
        ):
            diagnostics.append(
                CompileDiagnostic(
                    code="stale_snapshot_epoch",
                    message=(
                        "plan snapshot_source_epoch does not match current snapshot epoch: "
                        f"{plan.snapshot_source_epoch} != {current_snapshot_epoch}"
                    ),
                )
            )
        if not diagnostics:
            return None
        return CompileResult(
            status=CompileStatus.STALE,
            plan_id=plan.plan_id,
            diagnostics=diagnostics,
        )

    def _remember(self, plan: SectionUpdatePlan, result: CompileResult) -> None:
        if self.idempotency_store is None:
            return
        self.idempotency_store.remember(
            key=plan.plan_idempotency_key,
            status=result.status.value,
            plan_id=plan.plan_id,
            result_summary=result.to_summary(),
        )


def estimate_mutation_bytes(mutation: SectionMutation) -> int:
    """Estimate non-zero mutation payload bytes for guard preflight."""

    payload = {
        "section": mutation.section,
        "operation": mutation.operation,
        "data": mutation.data,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return max(1, len(encoded))
