"""
tests.poc.test_m01_event_validator -- E1.3 Event Schema Validation Infrastructure.

Validates:
    1. EVENT_SCHEMA_REGISTRY mirrors EVENT_TYPE_REGISTRY (no duplication)
    2. validate_event -- canonical metadata + type-specific field validation
    3. validate_event_chain -- causation chain integrity
    4. Builder validation wiring (config flag)
    5. hitl_wiring canonical schema checks
    6. All 16 event types pass roundtrip validation
    7. Edge cases: unknown event_type, missing fields, duplicate event_ids
"""

from __future__ import annotations

import uuid

import pytest

from k1.concierge.events.base import CanonicalEventMeta, validate_canonical_metadata
from k1.concierge.events.conversation import (
    DeadLettered,
    IntentArbitrated,
    UserInputReceived,
)
from k1.concierge.events.hitl import (
    HILRequested,
    HILResolved,
    TaskResumed,
    TaskSuspended,
)
from k1.concierge.events.registry import EVENT_TYPE_REGISTRY
from k1.concierge.events.task import (
    TaskCancelled,
    TaskCompleted,
    TaskCreated,
    TaskFailed,
    TaskLeased,
    TaskProgressed,
)
from k1.concierge.events.validator import (
    EVENT_SCHEMA_REGISTRY,
    validate_event,
    validate_event_chain,
)
from k1.concierge.events.weave import (
    WeaveCandidateArrived,
    WeaveDecisionMade,
    WeaveEmitted,
)

# =========================================================================
# Fixtures
# =========================================================================

ALL_16_EVENT_CLASSES: list[type[CanonicalEventMeta]] = [
    UserInputReceived,
    IntentArbitrated,
    DeadLettered,
    TaskCreated,
    TaskLeased,
    TaskProgressed,
    TaskCompleted,
    TaskFailed,
    TaskCancelled,
    HILRequested,
    HILResolved,
    TaskSuspended,
    TaskResumed,
    WeaveCandidateArrived,
    WeaveDecisionMade,
    WeaveEmitted,
]

# E-0.5.23 added 6 previously unregistered event types (27th-32nd)
# M2 E2.5.4 added ResponseFinalDecided (17th event type)
# M6 E6.3 (C04) added ResponseDelivered (33rd event type)
from k1.concierge.events.conversation import (
    Phase1Classified,
    ResponseDelivered,
    ResponseFinalDecided,
    TaskRouted,
)
from k1.concierge.events.hitl import (
    HITLBlockedRedEvent,
    HITLRequestedEvent,
    HITLResolvedEvent,
    HITLTimedOutEvent,
)

# M4 E4.5.4 added TurnMutationSummary (18th event type)
from k1.concierge.events.mutation import TurnMutationSummary

# M7 E7.5.1 added 7 pool event types (19th-25th)
from k1.concierge.events.pool import (
    BackPoolWorkerAcquiredEvent,
    BackPoolWorkerReleasedEvent,
    DependencyFailedEvent,
    TaskDeferredEvent,
    TaskLeasedEvent,
    TaskLeaseExpiredEvent,
    TaskLeaseRenewedEvent,
)

# M8 E8.5 added WeaveMetricsEvent (26th event type)
from k1.concierge.events.weave import WeaveMetricsEvent

ALL_EVENT_CLASSES: list[type[CanonicalEventMeta]] = ALL_16_EVENT_CLASSES + [
    ResponseFinalDecided,
    ResponseDelivered,
    TurnMutationSummary,
    BackPoolWorkerAcquiredEvent,
    BackPoolWorkerReleasedEvent,
    TaskLeasedEvent,
    TaskLeaseExpiredEvent,
    TaskLeaseRenewedEvent,
    TaskDeferredEvent,
    DependencyFailedEvent,
    WeaveMetricsEvent,
    Phase1Classified,
    TaskRouted,
    HITLRequestedEvent,
    HITLResolvedEvent,
    HITLTimedOutEvent,
    HITLBlockedRedEvent,
]


def _make_valid_payload(cls: type[CanonicalEventMeta]) -> dict:
    """Construct a default instance and return its to_payload() dict."""
    instance = cls(
        session_id="sess-1",
        correlation_id="corr-1",
        causation_id="cause-1",
        actor="test",
    )
    return instance.to_payload()


# =========================================================================
# 1. Registry identity: EVENT_SCHEMA_REGISTRY IS EVENT_TYPE_REGISTRY
# =========================================================================


class TestSchemaRegistryIdentity:
    """EVENT_SCHEMA_REGISTRY must be the SAME object as EVENT_TYPE_REGISTRY."""

    def test_registry_is_same_object(self) -> None:
        assert EVENT_SCHEMA_REGISTRY is EVENT_TYPE_REGISTRY

    def test_registry_has_16_entries(self) -> None:
        # M4 E4.5.4 added TurnMutationSummary -> now 18 entries
        assert len(EVENT_SCHEMA_REGISTRY) >= 18

    def test_all_16_classes_present(self) -> None:
        registered_classes = set(EVENT_SCHEMA_REGISTRY.values())
        expected_classes = set(ALL_EVENT_CLASSES)
        assert registered_classes == expected_classes


# =========================================================================
# 2. validate_event -- positive cases
# =========================================================================


class TestValidateEventPositive:
    """All 16 event types pass validation when constructed via default constructor."""

    @pytest.mark.parametrize("cls", ALL_16_EVENT_CLASSES, ids=lambda c: c.__name__)
    def test_roundtrip_validation_passes(self, cls: type[CanonicalEventMeta]) -> None:
        payload = _make_valid_payload(cls)
        ok, errors = validate_event(payload)
        assert ok, f"{cls.__name__} validation failed: {errors}"
        assert errors == []

    def test_valid_task_completed_with_all_fields(self) -> None:
        evt = TaskCompleted(
            session_id="s1",
            correlation_id="c1",
            causation_id="cause1",
            actor="back",
            task_id="t1",
            result_data={"answer": "42"},
            action="search",
            tool_calls_count=3,
            elapsed_ms=1500,
        )
        ok, errors = validate_event(evt.to_payload())
        assert ok
        assert errors == []


# =========================================================================
# 3. validate_event -- negative cases
# =========================================================================


class TestValidateEventNegative:
    """Detect missing/invalid fields."""

    def test_empty_payload(self) -> None:
        ok, errors = validate_event({})
        assert not ok
        assert any("event_type" in e for e in errors)

    def test_missing_event_type(self) -> None:
        payload = _make_valid_payload(TaskCompleted)
        del payload["event_type"]
        ok, errors = validate_event(payload)
        assert not ok
        assert any("event_type" in e.lower() for e in errors)

    def test_unknown_event_type(self) -> None:
        payload = _make_valid_payload(TaskCompleted)
        payload["event_type"] = "totally.unknown.type"
        ok, errors = validate_event(payload)
        assert not ok
        assert any("Unknown event_type" in e for e in errors)

    def test_missing_canonical_field(self) -> None:
        payload = _make_valid_payload(TaskCompleted)
        del payload["session_id"]
        ok, errors = validate_event(payload)
        assert not ok
        assert any("session_id" in e for e in errors)

    def test_missing_type_specific_field(self) -> None:
        payload = _make_valid_payload(TaskCompleted)
        del payload["result_data"]
        ok, errors = validate_event(payload)
        assert not ok
        assert any("result_data" in e for e in errors)

    def test_multiple_missing_type_specific_fields(self) -> None:
        payload = _make_valid_payload(HILRequested)
        del payload["hil_type"]
        del payload["question"]
        ok, errors = validate_event(payload)
        assert not ok
        assert any("hil_type" in e for e in errors)
        assert any("question" in e for e in errors)

    def test_empty_event_type_string(self) -> None:
        payload = _make_valid_payload(TaskCompleted)
        payload["event_type"] = ""
        ok, errors = validate_event(payload)
        assert not ok
        assert any("event_type" in e.lower() for e in errors)


# =========================================================================
# 4. validate_event_chain -- positive cases
# =========================================================================


class TestValidateEventChainPositive:
    """Valid causation chains pass."""

    def test_single_root_event(self) -> None:
        evt = _make_valid_payload(UserInputReceived)
        evt["causation_id"] = ""  # root event
        ok, errors = validate_event_chain([evt])
        assert ok
        assert errors == []

    def test_linear_chain(self) -> None:
        root_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        grandchild_id = str(uuid.uuid4())

        root = _make_valid_payload(UserInputReceived)
        root["event_id"] = root_id
        root["causation_id"] = ""

        child = _make_valid_payload(TaskCreated)
        child["event_id"] = child_id
        child["causation_id"] = root_id

        grandchild = _make_valid_payload(TaskCompleted)
        grandchild["event_id"] = grandchild_id
        grandchild["causation_id"] = child_id

        ok, errors = validate_event_chain([root, child, grandchild])
        assert ok
        assert errors == []

    def test_branching_chain(self) -> None:
        root_id = str(uuid.uuid4())
        branch_a = str(uuid.uuid4())
        branch_b = str(uuid.uuid4())

        root = _make_valid_payload(UserInputReceived)
        root["event_id"] = root_id
        root["causation_id"] = ""

        a = _make_valid_payload(TaskCreated)
        a["event_id"] = branch_a
        a["causation_id"] = root_id

        b = _make_valid_payload(TaskCreated)
        b["event_id"] = branch_b
        b["causation_id"] = root_id

        ok, errors = validate_event_chain([root, a, b])
        assert ok
        assert errors == []

    def test_empty_chain(self) -> None:
        ok, errors = validate_event_chain([])
        assert ok
        assert errors == []


# =========================================================================
# 5. validate_event_chain -- negative cases
# =========================================================================


class TestValidateEventChainNegative:
    """Detect broken causation chains."""

    def test_missing_event_id(self) -> None:
        evt = _make_valid_payload(UserInputReceived)
        del evt["event_id"]
        ok, errors = validate_event_chain([evt])
        assert not ok
        assert any("no event_id" in e for e in errors)

    def test_duplicate_event_id(self) -> None:
        shared_id = str(uuid.uuid4())
        a = _make_valid_payload(UserInputReceived)
        a["event_id"] = shared_id
        a["causation_id"] = ""

        b = _make_valid_payload(TaskCreated)
        b["event_id"] = shared_id
        b["causation_id"] = ""

        ok, errors = validate_event_chain([a, b])
        assert not ok
        assert any("Duplicate" in e for e in errors)

    def test_dangling_causation_id(self) -> None:
        evt = _make_valid_payload(TaskCompleted)
        evt["event_id"] = str(uuid.uuid4())
        evt["causation_id"] = "nonexistent-parent"

        ok, errors = validate_event_chain([evt])
        assert not ok
        assert any("not in the chain" in e for e in errors)


# =========================================================================
# 6. Builder validation wiring (config flag)
# =========================================================================


class TestBuilderValidationWiring:
    """_build() calls validate_event when config flag is on."""

    def test_config_flag_exists(self) -> None:
        from k1.concierge.config.loader import BusConfig

        cfg = BusConfig()
        assert hasattr(cfg, "validate_canonical_events")
        assert cfg.validate_canonical_events is False  # default off

    def test_builder_with_valid_canonical_event(self) -> None:
        """Builder accepts valid canonical events regardless of flag."""
        from k1.bus.envelope import Envelope
        from k1.concierge.bus.builders import build_task_complete

        evt = TaskCompleted(
            session_id="s1",
            correlation_id="c1",
            causation_id="cause1",
            actor="back",
            task_id="t1",
        )
        env = build_task_complete(evt, parent_id=42)
        assert isinstance(env, Envelope)
        assert env.parent_id == 42


# =========================================================================
# 7. hitl_wiring canonical schema checks
# =========================================================================


class TestHitlWiringCanonicalChecks:
    """validate_hitl_wiring() now includes canonical schema checks."""

    def test_hitl_wiring_passes_with_canonical_checks(self) -> None:
        from k1.concierge.protocols.hitl_wiring import validate_hitl_wiring

        issues = validate_hitl_wiring()
        # No issues from canonical checks (HITL events are well-formed)
        canonical_issues = [i for i in issues if "HITL event" in i or "EVENT_SCHEMA_REGISTRY" in i]
        assert canonical_issues == [], f"Canonical check issues: {canonical_issues}"

    def test_all_hitl_event_types_in_registry(self) -> None:
        hitl_types = ["hil.requested", "hil.resolved", "task.suspended", "task.resumed"]
        for et in hitl_types:
            assert et in EVENT_SCHEMA_REGISTRY, f"{et} not in registry"

    def test_hitl_events_roundtrip_validate(self) -> None:
        """Each HITL event type passes validate_event after default construction."""
        hitl_classes = [HILRequested, HILResolved, TaskSuspended, TaskResumed]
        for cls in hitl_classes:
            payload = _make_valid_payload(cls)
            ok, errors = validate_event(payload)
            assert ok, f"{cls.__name__} roundtrip failed: {errors}"


# =========================================================================
# 8. Type-specific field introspection
# =========================================================================


class TestTypeSpecificFieldIntrospection:
    """_get_type_specific_fields returns correct domain fields."""

    def test_task_completed_fields(self) -> None:
        from k1.concierge.events.validator import _get_type_specific_fields

        fields = _get_type_specific_fields(TaskCompleted)
        assert "result_data" in fields
        assert "action" in fields
        assert "tool_calls_count" in fields
        assert "elapsed_ms" in fields
        # Must NOT include base fields
        assert "event_id" not in fields
        assert "session_id" not in fields

    def test_hil_requested_fields(self) -> None:
        from k1.concierge.events.validator import _get_type_specific_fields

        fields = _get_type_specific_fields(HILRequested)
        assert "hil_type" in fields
        assert "question" in fields
        assert "options" in fields
        assert "context" in fields
        assert "side_effects" in fields
        assert "safety_band" in fields
        assert "timeout_s" in fields
        assert "max_rounds" in fields

    def test_base_class_has_no_type_specific_fields(self) -> None:
        from k1.concierge.events.validator import _get_type_specific_fields

        fields = _get_type_specific_fields(CanonicalEventMeta)
        assert fields == frozenset()


# =========================================================================
# 9. Package-level exports
# =========================================================================


class TestPackageExports:
    """events/__init__.py re-exports validator symbols."""

    def test_validate_event_importable_from_package(self) -> None:
        from k1.concierge.events import validate_event as ve

        assert ve is validate_event

    def test_validate_event_chain_importable_from_package(self) -> None:
        from k1.concierge.events import validate_event_chain as vec

        assert vec is validate_event_chain

    def test_schema_registry_importable_from_package(self) -> None:
        from k1.concierge.events import EVENT_SCHEMA_REGISTRY as reg

        assert reg is EVENT_SCHEMA_REGISTRY


# =========================================================================
# 10. validate_canonical_metadata compatibility
# =========================================================================


class TestValidateCanonicalMetadataCompat:
    """validate_event layer 1 delegates to existing validate_canonical_metadata."""

    def test_validate_event_catches_same_errors(self) -> None:
        """When canonical fields are missing, both validators agree."""
        payload = _make_valid_payload(TaskCompleted)
        del payload["actor"]

        meta_ok, meta_errs = validate_canonical_metadata(payload)
        event_ok, event_errs = validate_event(payload)

        assert not meta_ok
        assert not event_ok
        # validate_event includes all meta errors
        for err in meta_errs:
            assert err in event_errs

        assert not meta_ok
        assert not event_ok
        # validate_event includes all meta errors
        for err in meta_errs:
            assert err in event_errs
        payload = _make_valid_payload(TaskCompleted)
        del payload["actor"]

        meta_ok, meta_errs = validate_canonical_metadata(payload)
        event_ok, event_errs = validate_event(payload)

        assert not meta_ok
        assert not event_ok
        # validate_event includes all meta errors
        for err in meta_errs:
            assert err in event_errs

        assert not meta_ok
        assert not event_ok
        # validate_event includes all meta errors
        for err in meta_errs:
            assert err in event_errs
