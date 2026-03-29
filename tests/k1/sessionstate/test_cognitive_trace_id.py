"""
Tests for Epic 5.3.1: cognitive_trace_id Propagation
======================================================

Verifies that cognitive_trace_id is properly propagated through all
SessionState operations for distributed tracing correlation.

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.3 Tracing & Logging
ISSUE: 5.3.1 Add cognitive_trace_id to all operations
"""

import uuid

import pytest

from k1.sessionstate.factory import SessionStateFactory
from k1.sessionstate.manager import (
    CheckpointResult,
    MutationResult,
    RestoreResult,
    StartResult,
    StopResult,
)


@pytest.fixture
def unstarted_manager(tmp_path):
    """Create manager that is NOT started (for testing start())."""
    db_path = tmp_path / "trace_test.db"
    session_id = f"trace-{uuid.uuid4().hex[:8]}"
    manager = SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
    )
    yield manager


class TestMutationResultTraceId:
    """Test cognitive_trace_id in MutationResult."""

    def test_mutation_result_has_trace_id_field(self):
        """MutationResult has cognitive_trace_id field."""
        result = MutationResult(
            success=True,
            section="beliefs_active",
            operation="set",
            cognitive_trace_id="trace-123",
        )
        assert result.cognitive_trace_id == "trace-123"

    def test_mutation_result_trace_id_defaults_empty(self):
        """MutationResult.cognitive_trace_id defaults to empty string."""
        result = MutationResult(
            success=True,
            section="beliefs_active",
            operation="set",
        )
        assert result.cognitive_trace_id == ""

    def test_mutation_result_to_dict_includes_trace_id(self):
        """MutationResult.to_dict() includes cognitive_trace_id."""
        result = MutationResult(
            success=True,
            section="beliefs_active",
            operation="set",
            cognitive_trace_id="trace-456",
        )
        data = result.to_dict()
        assert "cognitive_trace_id" in data
        assert data["cognitive_trace_id"] == "trace-456"

    def test_mutation_result_rejected_factory_includes_trace_id(self):
        """MutationResult.rejected() factory includes cognitive_trace_id."""
        result = MutationResult.rejected(
            section="beliefs_active",
            operation="set",
            reason="capacity exceeded",
            cognitive_trace_id="trace-rej",
        )
        assert result.cognitive_trace_id == "trace-rej"

    def test_mutation_result_failure_factory_includes_trace_id(self):
        """MutationResult.failure() factory includes cognitive_trace_id."""
        result = MutationResult.failure(
            section="beliefs_active",
            operation="set",
            error="internal error",
            cognitive_trace_id="trace-fail",
        )
        assert result.cognitive_trace_id == "trace-fail"


class TestStartResultTraceId:
    """Test cognitive_trace_id in StartResult."""

    def test_start_result_has_trace_id_field(self):
        """StartResult has cognitive_trace_id field."""
        result = StartResult(
            success=True,
            session_id="session-123",
            cognitive_trace_id="trace-start",
        )
        assert result.cognitive_trace_id == "trace-start"

    def test_start_result_trace_id_defaults_empty(self):
        """StartResult.cognitive_trace_id defaults to empty string."""
        result = StartResult(success=True)
        assert result.cognitive_trace_id == ""

    def test_start_result_to_dict_includes_trace_id(self):
        """StartResult.to_dict() includes cognitive_trace_id."""
        result = StartResult(
            success=True,
            cognitive_trace_id="trace-start-dict",
        )
        data = result.to_dict()
        assert "cognitive_trace_id" in data
        assert data["cognitive_trace_id"] == "trace-start-dict"


class TestStopResultTraceId:
    """Test cognitive_trace_id in StopResult."""

    def test_stop_result_has_trace_id_field(self):
        """StopResult has cognitive_trace_id field."""
        result = StopResult(
            success=True,
            cognitive_trace_id="trace-stop",
        )
        assert result.cognitive_trace_id == "trace-stop"

    def test_stop_result_trace_id_defaults_empty(self):
        """StopResult.cognitive_trace_id defaults to empty string."""
        result = StopResult(success=True)
        assert result.cognitive_trace_id == ""

    def test_stop_result_to_dict_includes_trace_id(self):
        """StopResult.to_dict() includes cognitive_trace_id."""
        result = StopResult(
            success=True,
            cognitive_trace_id="trace-stop-dict",
        )
        data = result.to_dict()
        assert "cognitive_trace_id" in data
        assert data["cognitive_trace_id"] == "trace-stop-dict"


class TestCheckpointResultTraceId:
    """Test cognitive_trace_id in CheckpointResult."""

    def test_checkpoint_result_has_trace_id_field(self):
        """CheckpointResult has cognitive_trace_id field."""
        result = CheckpointResult(
            success=True,
            checkpoint_id="cp-123",
            cognitive_trace_id="trace-checkpoint",
        )
        assert result.cognitive_trace_id == "trace-checkpoint"

    def test_checkpoint_result_trace_id_defaults_empty(self):
        """CheckpointResult.cognitive_trace_id defaults to empty string."""
        result = CheckpointResult(success=True)
        assert result.cognitive_trace_id == ""

    def test_checkpoint_result_to_dict_includes_trace_id(self):
        """CheckpointResult.to_dict() includes cognitive_trace_id."""
        result = CheckpointResult(
            success=True,
            cognitive_trace_id="trace-cp-dict",
        )
        data = result.to_dict()
        assert "cognitive_trace_id" in data
        assert data["cognitive_trace_id"] == "trace-cp-dict"


class TestRestoreResultTraceId:
    """Test cognitive_trace_id in RestoreResult."""

    def test_restore_result_has_trace_id_field(self):
        """RestoreResult has cognitive_trace_id field."""
        result = RestoreResult(
            success=True,
            source="local_cold",
            cognitive_trace_id="trace-restore",
        )
        assert result.cognitive_trace_id == "trace-restore"

    def test_restore_result_trace_id_defaults_empty(self):
        """RestoreResult.cognitive_trace_id defaults to empty string."""
        result = RestoreResult(success=True)
        assert result.cognitive_trace_id == ""

    def test_restore_result_to_dict_includes_trace_id(self):
        """RestoreResult.to_dict() includes cognitive_trace_id."""
        result = RestoreResult(
            success=True,
            cognitive_trace_id="trace-restore-dict",
        )
        data = result.to_dict()
        assert "cognitive_trace_id" in data
        assert data["cognitive_trace_id"] == "trace-restore-dict"


class TestManagerMutateTraceId:
    """Test cognitive_trace_id propagation in manager.mutate()."""

    def test_mutate_accepts_trace_id_parameter(self, standalone_session_state):
        """manager.mutate() accepts cognitive_trace_id parameter."""
        manager = standalone_session_state
        trace_id = str(uuid.uuid4())

        result = manager.mutate(
            section="beliefs_active",
            operation="set",
            data={"key": "value"},
            cognitive_trace_id=trace_id,
        )

        assert result.cognitive_trace_id == trace_id

    def test_mutate_returns_trace_id_on_success(self, standalone_session_state):
        """manager.mutate() returns trace_id on successful mutation."""
        manager = standalone_session_state
        trace_id = "trace-mutate-success"

        result = manager.mutate(
            section="beliefs_active",
            operation="set",
            data={"key": "value"},
            cognitive_trace_id=trace_id,
        )

        assert result.success is True
        assert result.cognitive_trace_id == trace_id

    def test_mutate_returns_trace_id_on_rejection(self, standalone_session_state):
        """manager.mutate() returns trace_id on rejected mutation."""
        manager = standalone_session_state
        trace_id = "trace-mutate-reject"

        result = manager.mutate(
            section="invalid_section",
            operation="set",
            data={"key": "value"},
            cognitive_trace_id=trace_id,
        )

        assert result.success is False
        assert result.cognitive_trace_id == trace_id

    def test_mutate_without_trace_id_uses_empty_string(self, standalone_session_state):
        """manager.mutate() uses empty string when no trace_id provided."""
        manager = standalone_session_state

        result = manager.mutate(
            section="beliefs_active",
            operation="set",
            data={"key": "value"},
        )

        assert result.cognitive_trace_id == ""


class TestManagerStartTraceId:
    """Test cognitive_trace_id propagation in manager.start()."""

    def test_start_accepts_trace_id_parameter(self, unstarted_manager):
        """manager.start() accepts cognitive_trace_id parameter."""
        trace_id = str(uuid.uuid4())

        result = unstarted_manager.start(cognitive_trace_id=trace_id)

        assert result.cognitive_trace_id == trace_id

    def test_start_returns_trace_id_on_success(self, unstarted_manager):
        """manager.start() returns trace_id on successful start."""
        trace_id = "trace-start-success"

        result = unstarted_manager.start(cognitive_trace_id=trace_id)

        assert result.success is True
        assert result.cognitive_trace_id == trace_id

    def test_start_returns_trace_id_on_error(self, standalone_session_state):
        """manager.start() returns trace_id on error (already running)."""
        manager = standalone_session_state
        trace_id = "trace-start-error"

        result = manager.start(cognitive_trace_id=trace_id)

        assert result.success is False
        assert result.cognitive_trace_id == trace_id

    def test_start_without_trace_id_uses_empty_string(self, unstarted_manager):
        """manager.start() uses empty string when no trace_id provided."""
        result = unstarted_manager.start()

        assert result.cognitive_trace_id == ""


class TestManagerStopTraceId:
    """Test cognitive_trace_id propagation in manager.stop()."""

    def test_stop_accepts_trace_id_parameter(self, standalone_session_state):
        """manager.stop() accepts cognitive_trace_id parameter."""
        manager = standalone_session_state
        trace_id = str(uuid.uuid4())

        result = manager.stop(cognitive_trace_id=trace_id)

        assert result.cognitive_trace_id == trace_id

    def test_stop_returns_trace_id_on_success(self, standalone_session_state):
        """manager.stop() returns trace_id on successful stop."""
        manager = standalone_session_state
        trace_id = "trace-stop-success"

        result = manager.stop(cognitive_trace_id=trace_id)

        assert result.success is True
        assert result.cognitive_trace_id == trace_id

    def test_stop_returns_trace_id_on_error(self, unstarted_manager):
        """manager.stop() returns trace_id on error (not running)."""
        trace_id = "trace-stop-error"

        result = unstarted_manager.stop(cognitive_trace_id=trace_id)

        assert result.success is False
        assert result.cognitive_trace_id == trace_id

    def test_stop_without_trace_id_uses_empty_string(self, standalone_session_state):
        """manager.stop() uses empty string when no trace_id provided."""
        manager = standalone_session_state

        result = manager.stop()

        assert result.cognitive_trace_id == ""


class TestManagerCheckpointTraceId:
    """Test cognitive_trace_id propagation in manager.checkpoint()."""

    def test_checkpoint_accepts_trace_id_parameter(self, standalone_session_state):
        """manager.checkpoint() accepts cognitive_trace_id parameter."""
        manager = standalone_session_state
        trace_id = str(uuid.uuid4())

        result = manager.checkpoint(cognitive_trace_id=trace_id)

        assert result.cognitive_trace_id == trace_id

    def test_checkpoint_returns_trace_id_on_success(self, standalone_session_state):
        """manager.checkpoint() returns trace_id on success."""
        manager = standalone_session_state
        trace_id = "trace-checkpoint-success"

        result = manager.checkpoint(cognitive_trace_id=trace_id)

        assert result.success is True
        assert result.cognitive_trace_id == trace_id

    def test_checkpoint_without_trace_id_uses_empty_string(self, standalone_session_state):
        """manager.checkpoint() uses empty string when no trace_id provided."""
        manager = standalone_session_state

        result = manager.checkpoint()

        assert result.cognitive_trace_id == ""


class TestManagerRestoreTraceId:
    """Test cognitive_trace_id propagation in manager.restore()."""

    def test_restore_accepts_trace_id_parameter(self, unstarted_manager):
        """manager.restore() accepts cognitive_trace_id parameter."""
        trace_id = str(uuid.uuid4())

        result = unstarted_manager.restore(
            session_id=unstarted_manager.session_id,
            cognitive_trace_id=trace_id,
        )

        assert result.cognitive_trace_id == trace_id

    def test_restore_returns_trace_id_fresh(self, unstarted_manager):
        """manager.restore() returns trace_id on fresh session."""
        trace_id = "trace-restore-fresh"

        result = unstarted_manager.restore(
            session_id=unstarted_manager.session_id,
            cognitive_trace_id=trace_id,
        )

        assert result.source == "fresh"
        assert result.cognitive_trace_id == trace_id

    def test_restore_without_trace_id_uses_empty_string(self, unstarted_manager):
        """manager.restore() uses empty string when no trace_id provided."""
        result = unstarted_manager.restore(session_id=unstarted_manager.session_id)

        assert result.cognitive_trace_id == ""


class TestTraceIdEndToEnd:
    """End-to-end trace ID propagation tests."""

    def test_trace_id_flows_through_start_to_stop(self, unstarted_manager):
        """Trace ID flows through complete lifecycle."""
        trace_id = "trace-e2e-lifecycle"

        start_result = unstarted_manager.start(cognitive_trace_id=trace_id)
        assert start_result.cognitive_trace_id == trace_id

        mutate_result = unstarted_manager.mutate(
            section="beliefs_active",
            operation="set",
            data={"test": True},
            cognitive_trace_id=trace_id,
        )
        assert mutate_result.cognitive_trace_id == trace_id

        checkpoint_result = unstarted_manager.checkpoint(cognitive_trace_id=trace_id)
        assert checkpoint_result.cognitive_trace_id == trace_id

        stop_result = unstarted_manager.stop(cognitive_trace_id=trace_id)
        assert stop_result.cognitive_trace_id == trace_id

    def test_different_trace_ids_for_different_operations(self, unstarted_manager):
        """Different operations can have different trace IDs."""
        unstarted_manager.start(cognitive_trace_id="trace-start-1")

        result1 = unstarted_manager.mutate(
            section="beliefs_active",
            operation="set",
            data={"op": 1},
            cognitive_trace_id="trace-op-1",
        )
        result2 = unstarted_manager.mutate(
            section="beliefs_active",
            operation="set",
            data={"op": 2},
            cognitive_trace_id="trace-op-2",
        )

        assert result1.cognitive_trace_id == "trace-op-1"
        assert result2.cognitive_trace_id == "trace-op-2"

        unstarted_manager.stop(cognitive_trace_id="trace-stop-1")

    def test_uuid_format_trace_id(self, standalone_session_state):
        """UUID format trace IDs work correctly."""
        manager = standalone_session_state
        trace_id = str(uuid.uuid4())

        result = manager.mutate(
            section="beliefs_active",
            operation="set",
            data={"uuid_test": True},
            cognitive_trace_id=trace_id,
        )

        assert result.cognitive_trace_id == trace_id
        # Verify it's a valid UUID
        uuid.UUID(result.cognitive_trace_id)
