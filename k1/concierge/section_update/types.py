"""Runtime-free SectionUpdateClassifier contract types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class SectionUpdateContractError(ValueError):
    """Raised when a section-update contract object is malformed."""


class ApplyTiming(str, Enum):
    """When a section-update plan is intended to become visible."""

    ASYNC_AFTER_RESPONSE = "async_after_response"
    BEFORE_NEXT_TURN = "before_next_turn"
    PRE_PROMPT_OVERLAY = "pre_prompt_overlay"
    BEFORE_DISPATCH = "before_dispatch"
    SHADOW_ONLY = "shadow_only"
    NO_OP = "no_op"


class CommitClass(str, Enum):
    """How important a mutation is to near-term continuity."""

    PROMPT_CRITICAL = "prompt_critical"
    DISPATCH_CRITICAL = "dispatch_critical"
    NEXT_TURN_CONTINUITY = "next_turn_continuity"
    NONCRITICAL = "noncritical"
    BACKGROUND_QUALITY = "background_quality"


class ClassifierMode(str, Enum):
    """Classifier runtime mode declared by input constraints or configuration."""

    DISABLED = "disabled"
    SHADOW = "shadow"
    ACTIVE = "active"
    ONLINE = "online"
    OFFLINE_STUB = "offline_stub"
    DEGRADED_NOOP = "degraded_noop"


def _coerce_enum(enum_cls: type[Enum], value: Any, field_name: str) -> Enum:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value))
    except Exception as exc:  # noqa: BLE001 - contract validation boundary.
        raise SectionUpdateContractError(f"invalid {field_name}: {value!r}") from exc


def _require_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SectionUpdateContractError(f"{field_name} is required")
    return text


def _coerce_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise SectionUpdateContractError(f"{field_name} must be an object")
    return dict(value)


def _coerce_confidence(value: Any, field_name: str = "confidence") -> float:
    if not isinstance(value, (int, float)):
        raise SectionUpdateContractError(f"{field_name} must be numeric")
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise SectionUpdateContractError(f"{field_name} must be in [0.0, 1.0]")
    return confidence


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


@dataclass
class SectionUpdateValidation:
    """Validation status carried with a plan."""

    schema_valid: bool = True
    snapshot_freshness_status: str = "unchecked"
    whole_plan_preflight_status: str = "unchecked"
    mutation_guard_preflight_status: str = "unchecked"
    idempotency_status: str = "unchecked"
    privacy_band_status: str = "unchecked"
    budget_status: str = "unchecked"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.schema_valid = bool(self.schema_valid)
        self.errors = [str(item) for item in self.errors]
        self.warnings = [str(item) for item in self.warnings]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_valid": self.schema_valid,
            "snapshot_freshness_status": self.snapshot_freshness_status,
            "whole_plan_preflight_status": self.whole_plan_preflight_status,
            "mutation_guard_preflight_status": self.mutation_guard_preflight_status,
            "idempotency_status": self.idempotency_status,
            "privacy_band_status": self.privacy_band_status,
            "budget_status": self.budget_status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SectionUpdateValidation":
        return cls(**_coerce_mapping(data, "validation"))


@dataclass
class SectionMutation:
    """One proposed cognitive SessionState mutation."""

    section: str
    operation: str
    data: dict[str, Any]
    confidence: float
    reason: str
    source: str = "classifier:section_update"
    idempotency_key: str = ""
    commit_class: CommitClass | str = CommitClass.NEXT_TURN_CONTINUITY
    commitment_match: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.section = _require_text(self.section, "section")
        self.operation = _require_text(self.operation, "operation")
        self.data = _coerce_mapping(self.data, "data")
        self.confidence = _coerce_confidence(self.confidence)
        self.reason = _require_text(self.reason, "reason")
        self.source = _require_text(self.source, "source")
        self.idempotency_key = str(self.idempotency_key or "")
        self.commit_class = _coerce_enum(CommitClass, self.commit_class, "commit_class")
        self.commitment_match = (
            None
            if self.commitment_match is None
            else _coerce_mapping(self.commitment_match, "commitment_match")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "operation": self.operation,
            "data": _plain(self.data),
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
            "idempotency_key": self.idempotency_key,
            "commit_class": _plain(self.commit_class),
            "commitment_match": _plain(self.commitment_match),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SectionMutation":
        payload = _coerce_mapping(data, "mutation")
        return cls(
            section=payload.get("section"),
            operation=payload.get("operation"),
            data=payload.get("data", {}),
            confidence=payload.get("confidence"),
            reason=payload.get("reason"),
            source=payload.get("source", "classifier:section_update"),
            idempotency_key=payload.get("idempotency_key") or payload.get("idempotency_hint", ""),
            commit_class=payload.get("commit_class", CommitClass.NEXT_TURN_CONTINUITY),
            commitment_match=payload.get("commitment_match"),
        )


@dataclass
class RejectedCandidate:
    """A candidate the classifier or compiler rejected before writer submission."""

    section: str
    reason: str
    operation: str = ""
    confidence: float | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.section = _require_text(self.section, "section")
        self.reason = _require_text(self.reason, "reason")
        self.operation = str(self.operation or "")
        if self.confidence is not None:
            self.confidence = _coerce_confidence(self.confidence)
        self.data = _coerce_mapping(self.data, "data")

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "operation": self.operation,
            "reason": self.reason,
            "confidence": self.confidence,
            "data": _plain(self.data),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RejectedCandidate":
        payload = _coerce_mapping(data, "rejected_candidate")
        return cls(
            section=payload.get("section", "all"),
            operation=payload.get("operation", ""),
            reason=payload.get("reason"),
            confidence=payload.get("confidence"),
            data=payload.get("data", {}),
        )


@dataclass
class TurnStateOverlay:
    """Optional same-turn projection for future lifecycle milestones."""

    turn_id: str
    sections: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.turn_id = _require_text(self.turn_id, "turn_id")
        self.sections = _coerce_mapping(self.sections, "sections")
        self.diagnostics = _coerce_mapping(self.diagnostics, "diagnostics")

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "sections": _plain(self.sections),
            "diagnostics": _plain(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "TurnStateOverlay | None":
        if data is None:
            return None
        payload = _coerce_mapping(data, "overlay")
        return cls(
            turn_id=payload.get("turn_id"),
            sections=payload.get("sections", {}),
            diagnostics=payload.get("diagnostics", {}),
        )


@dataclass
class SectionUpdateInput:
    """Post-turn input read by the narrow section-update classifier."""

    turn_id: str
    session_id: str
    cognitive_trace_id: str = ""
    prompt_mode: str = ""
    fsm_state: str = ""
    bus_topic: str = ""
    admission_context: dict[str, Any] = field(default_factory=dict)
    user_turn: dict[str, Any] = field(default_factory=dict)
    assistant_turn: dict[str, Any] = field(default_factory=dict)
    arbiter_context: dict[str, Any] = field(default_factory=dict)
    prompt_context: dict[str, Any] = field(default_factory=dict)
    session_snapshot: dict[str, Any] = field(default_factory=dict)
    history_context: dict[str, Any] = field(default_factory=dict)
    scenario_context: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.turn_id = _require_text(self.turn_id, "turn_id")
        self.session_id = _require_text(self.session_id, "session_id")
        self.cognitive_trace_id = str(self.cognitive_trace_id or "")
        self.prompt_mode = str(self.prompt_mode or "")
        self.fsm_state = str(self.fsm_state or "")
        self.bus_topic = str(self.bus_topic or "")
        for field_name in (
            "admission_context",
            "user_turn",
            "assistant_turn",
            "arbiter_context",
            "prompt_context",
            "session_snapshot",
            "history_context",
            "scenario_context",
            "constraints",
        ):
            setattr(self, field_name, _coerce_mapping(getattr(self, field_name), field_name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "cognitive_trace_id": self.cognitive_trace_id,
            "prompt_mode": self.prompt_mode,
            "fsm_state": self.fsm_state,
            "bus_topic": self.bus_topic,
            "admission_context": _plain(self.admission_context),
            "user_turn": _plain(self.user_turn),
            "assistant_turn": _plain(self.assistant_turn),
            "arbiter_context": _plain(self.arbiter_context),
            "prompt_context": _plain(self.prompt_context),
            "session_snapshot": _plain(self.session_snapshot),
            "history_context": _plain(self.history_context),
            "scenario_context": _plain(self.scenario_context),
            "constraints": _plain(self.constraints),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SectionUpdateInput":
        payload = _coerce_mapping(data, "section_update_input")
        return cls(**payload)


@dataclass
class SectionUpdatePlan:
    """Classifier output envelope. It is data only; it never writes."""

    plan_id: str
    turn_id: str
    session_id: str
    snapshot_version: str = ""
    snapshot_source_epoch: str = ""
    classifier_version: str = "section-update-v0"
    plan_idempotency_key: str = ""
    apply_timing: ApplyTiming | str = ApplyTiming.ASYNC_AFTER_RESPONSE
    mutations: list[SectionMutation | Mapping[str, Any]] = field(default_factory=list)
    overlay: TurnStateOverlay | Mapping[str, Any] | None = None
    rejected_candidates: list[RejectedCandidate | Mapping[str, Any]] = field(default_factory=list)
    validation: SectionUpdateValidation | Mapping[str, Any] = field(
        default_factory=SectionUpdateValidation
    )
    diagnostics: dict[str, Any] = field(default_factory=dict)
    cognitive_trace_id: str = ""
    confidence: float | None = None  # classifier self-assessed confidence [0,1]

    def __post_init__(self) -> None:
        self.plan_id = _require_text(self.plan_id, "plan_id")
        self.turn_id = _require_text(self.turn_id, "turn_id")
        self.session_id = _require_text(self.session_id, "session_id")
        self.snapshot_version = str(self.snapshot_version or "")
        self.snapshot_source_epoch = str(self.snapshot_source_epoch or "")
        self.classifier_version = _require_text(self.classifier_version, "classifier_version")
        self.apply_timing = _coerce_enum(ApplyTiming, self.apply_timing, "apply_timing")
        self.mutations = [
            item if isinstance(item, SectionMutation) else SectionMutation.from_dict(item)
            for item in self.mutations
        ]
        if self.apply_timing == ApplyTiming.NO_OP and self.mutations:
            raise SectionUpdateContractError("no_op apply_timing cannot contain mutations")
        self.overlay = (
            self.overlay
            if isinstance(self.overlay, TurnStateOverlay) or self.overlay is None
            else TurnStateOverlay.from_dict(self.overlay)
        )
        self.rejected_candidates = [
            item if isinstance(item, RejectedCandidate) else RejectedCandidate.from_dict(item)
            for item in self.rejected_candidates
        ]
        self.validation = (
            self.validation
            if isinstance(self.validation, SectionUpdateValidation)
            else SectionUpdateValidation.from_dict(self.validation)
        )
        self.diagnostics = _coerce_mapping(self.diagnostics, "diagnostics")
        self.cognitive_trace_id = str(self.cognitive_trace_id or "")
        if not self.plan_idempotency_key:
            self.plan_idempotency_key = ":".join(
                [self.session_id, self.turn_id, self.snapshot_version, self.classifier_version]
            )

    @property
    def is_noop(self) -> bool:
        return not self.mutations

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "snapshot_version": self.snapshot_version,
            "snapshot_source_epoch": self.snapshot_source_epoch,
            "classifier_version": self.classifier_version,
            "plan_idempotency_key": self.plan_idempotency_key,
            "apply_timing": _plain(self.apply_timing),
            "mutations": [_plain(item) for item in self.mutations],
            "overlay": _plain(self.overlay),
            "rejected_candidates": [_plain(item) for item in self.rejected_candidates],
            "validation": _plain(self.validation),
            "diagnostics": _plain(self.diagnostics),
            "cognitive_trace_id": self.cognitive_trace_id,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SectionUpdatePlan":
        payload = _coerce_mapping(data, "section_update_plan")
        return cls(**payload)

    @classmethod
    def noop(
        cls,
        *,
        plan_id: str,
        turn_id: str,
        session_id: str,
        classifier_version: str = "section-update-v0",
        reason: str = "no section update required",
        cognitive_trace_id: str = "",
    ) -> "SectionUpdatePlan":
        return cls(
            plan_id=plan_id,
            turn_id=turn_id,
            session_id=session_id,
            classifier_version=classifier_version,
            apply_timing=ApplyTiming.NO_OP,
            mutations=[],
            rejected_candidates=[RejectedCandidate(section="all", reason=reason)],
            validation=SectionUpdateValidation(
                schema_valid=True,
                whole_plan_preflight_status="noop",
            ),
            cognitive_trace_id=cognitive_trace_id,
        )
