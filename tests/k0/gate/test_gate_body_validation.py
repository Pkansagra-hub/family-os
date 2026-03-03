"""Real component tests for TopicBodyValidator + MinimalGate integration.

Validates per-topic body schema enforcement against the actual
gate_topic_validation.yaml contract and per-topic JSON Schema files.
No mocks -- real validators, real schemas, real YAML.

Milestone: M2 Epic 2.15
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from k0.gate.topic_body_validator import (
    TOPIC_BAND_NOT_ALLOWED,
    TOPIC_BODY_SIZE_EXCEEDED,
    TOPIC_BODY_VALIDATION_FAILED,
    TOPIC_UNKNOWN,
    BodyViolation,
    TopicBodyValidator,
    TopicValidationResult,
)

# ---------------------------------------------------------------------------
# Valid body fixtures -- conform to memory_atom.v2.schema.json
# ---------------------------------------------------------------------------


def _valid_memory_write_body() -> dict[str, Any]:
    """Minimal valid body for memory.write (14 required fields)."""
    return {
        "schema_version": "2.0",
        "operation": "UPSERT",
        "text": "Family dinner at the Italian place downtown",
        "topics": ["dining"],
        "sentiment_label": "positive",
        "affect": {"valence": 0.8, "arousal": 0.5, "dominance": 0.6},
        "source_type": "user_stated",
        "novelty": "NOVEL",
        "elaboration_depth": "DISCUSSED",
        "temporal_orientation": "PAST",
        "confidence": 0.92,
        "session_id": "sess-001",
        "conversation_turn": 3,
        "language": "en",
    }


# ---------------------------------------------------------------------------
# Fixture: real TopicBodyValidator
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def validator() -> TopicBodyValidator:
    """Construct a real TopicBodyValidator from production YAML + schemas."""
    return TopicBodyValidator()


# ===========================================================================
# Happy path: valid body passes validation
# ===========================================================================


class TestValidBody:
    """Confirm that correctly-formed bodies pass schema validation."""

    def test_valid_memory_write(self, validator: TopicBodyValidator) -> None:
        body = _valid_memory_write_body()
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is True
        assert result.reason is None
        assert result.violations == ()

    def test_valid_memory_write_amber_band(self, validator: TopicBodyValidator) -> None:
        body = _valid_memory_write_body()
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "AMBER", body_bytes)
        assert result.valid is True

    def test_valid_memory_write_red_band(self, validator: TopicBodyValidator) -> None:
        body = _valid_memory_write_body()
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "RED", body_bytes)
        assert result.valid is True

    def test_valid_memory_write_all_optional_fields(self, validator: TopicBodyValidator) -> None:
        """Body with all 34 fields passes validation."""
        body = _valid_memory_write_body()
        body["participants"] = ["person_alice"]
        body["location_name"] = "Downtown Italian"
        body["location_type"] = "restaurant"
        body["activity_type"] = "MEAL"
        body["categories"] = ["food"]
        body["emotion_tags"] = ["happy"]
        body["social_context"] = "nuclear_family"
        body["social_intimacy"] = "HIGH"
        body["entity_salience"] = {"person_alice": 0.9}
        body["intent_type"] = "log_memory"
        body["goal_context"] = None
        body["task_context"] = None
        body["identity_domains"] = ["parent"]
        body["narrative"] = {
            "thread_id": "thread-1",
            "arc_position": "RISING_ACTION",
            "is_goal_event": False,
        }
        body["temporal"] = {
            "mentioned_time": "yesterday evening",
            "resolved_epoch_ms": 1700000000000,
            "is_backdated": True,
        }
        body["participant_relationships"] = {
            "person_alice": {
                "type": "SPOUSE_OF",
                "target": "person_bob",
                "confidence": 0.95,
            }
        }
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is True


# ===========================================================================
# Unknown topic
# ===========================================================================


class TestUnknownTopic:
    """Topics not in gate_topic_validation.yaml are rejected."""

    def test_completely_unknown_topic(self, validator: TopicBodyValidator) -> None:
        result = validator.validate_topic_body("does.not.exist", {}, "GREEN", 0)
        assert result.valid is False
        assert TOPIC_UNKNOWN in (result.reason or "")

    def test_empty_topic(self, validator: TopicBodyValidator) -> None:
        result = validator.validate_topic_body("", {}, "GREEN", 0)
        assert result.valid is False
        assert TOPIC_UNKNOWN in (result.reason or "")


# ===========================================================================
# Band not allowed
# ===========================================================================


class TestBandNotAllowed:
    """Verify band restriction enforcement per topic."""

    def test_sync_delta_rejects_amber(self, validator: TopicBodyValidator) -> None:
        """sync.delta only allows GREEN band."""
        result = validator.validate_topic_body("sync.delta", {"data": "x"}, "AMBER", 10)
        assert result.valid is False
        assert TOPIC_BAND_NOT_ALLOWED in (result.reason or "")

    def test_sync_delta_rejects_red(self, validator: TopicBodyValidator) -> None:
        result = validator.validate_topic_body("sync.delta", {"data": "x"}, "RED", 10)
        assert result.valid is False
        assert TOPIC_BAND_NOT_ALLOWED in (result.reason or "")

    def test_sync_delta_accepts_green(self, validator: TopicBodyValidator) -> None:
        """sync.delta allows GREEN -- body may still fail schema but band passes."""
        result = validator.validate_topic_body("sync.delta", {"data": "x"}, "GREEN", 10)
        # Band check passes; may fail on schema, but reason should NOT be BAND_NOT_ALLOWED
        assert TOPIC_BAND_NOT_ALLOWED not in (result.reason or "")

    def test_session_snapshot_rejects_red(self, validator: TopicBodyValidator) -> None:
        """session.snapshot allows GREEN + AMBER only."""
        result = validator.validate_topic_body("session.snapshot", {"data": "x"}, "RED", 10)
        assert result.valid is False
        assert TOPIC_BAND_NOT_ALLOWED in (result.reason or "")


# ===========================================================================
# Body size exceeded
# ===========================================================================


class TestBodySizeExceeded:
    """Verify per-topic max_body_bytes enforcement."""

    def test_memory_write_max_8192(self, validator: TopicBodyValidator) -> None:
        body = _valid_memory_write_body()
        result = validator.validate_topic_body("memory.write", body, "GREEN", 8193)
        assert result.valid is False
        assert TOPIC_BODY_SIZE_EXCEEDED in (result.reason or "")

    def test_memory_write_at_limit(self, validator: TopicBodyValidator) -> None:
        body = _valid_memory_write_body()
        result = validator.validate_topic_body("memory.write", body, "GREEN", 8192)
        assert result.valid is True

    def test_session_snapshot_max_65536(self, validator: TopicBodyValidator) -> None:
        result = validator.validate_topic_body("session.snapshot", {"x": "y"}, "GREEN", 65537)
        assert result.valid is False
        assert TOPIC_BODY_SIZE_EXCEEDED in (result.reason or "")


# ===========================================================================
# Body required
# ===========================================================================


class TestBodyRequired:
    """All topics require a body; None or empty dict should fail."""

    def test_none_body_rejected(self, validator: TopicBodyValidator) -> None:
        result = validator.validate_topic_body("memory.write", None, "GREEN", 0)
        assert result.valid is False
        assert "BODY_REQUIRED" in (result.reason or "")

    def test_empty_body_rejected(self, validator: TopicBodyValidator) -> None:
        result = validator.validate_topic_body("memory.write", {}, "GREEN", 0)
        assert result.valid is False
        assert "BODY_REQUIRED" in (result.reason or "")


# ===========================================================================
# Schema validation failures -- field-level violations
# ===========================================================================


class TestSchemaValidationFailures:
    """Verify that invalid bodies produce detailed BodyViolation entries."""

    def test_missing_required_field(self, validator: TopicBodyValidator) -> None:
        """Omit 'text' -- a required field."""
        body = _valid_memory_write_body()
        del body["text"]
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False
        assert TOPIC_BODY_VALIDATION_FAILED in (result.reason or "")
        assert len(result.violations) > 0
        # At least one violation should mention 'text'
        violation_messages = [v.message for v in result.violations]
        assert any("text" in m.lower() or "'text'" in m for m in violation_messages)

    def test_wrong_type_for_confidence(self, validator: TopicBodyValidator) -> None:
        """confidence must be a number, not a string."""
        body = _valid_memory_write_body()
        body["confidence"] = "high"
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False
        assert TOPIC_BODY_VALIDATION_FAILED in (result.reason or "")

    def test_invalid_enum_value(self, validator: TopicBodyValidator) -> None:
        """source_type must be one of the 4 enum values."""
        body = _valid_memory_write_body()
        body["source_type"] = "made_up_source"
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False
        assert TOPIC_BODY_VALIDATION_FAILED in (result.reason or "")

    def test_affect_missing_subfield(self, validator: TopicBodyValidator) -> None:
        """affect requires valence, arousal, dominance."""
        body = _valid_memory_write_body()
        body["affect"] = {"valence": 0.5}  # missing arousal, dominance
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False
        assert TOPIC_BODY_VALIDATION_FAILED in (result.reason or "")

    def test_confidence_out_of_range(self, validator: TopicBodyValidator) -> None:
        """confidence must be 0.0-1.0."""
        body = _valid_memory_write_body()
        body["confidence"] = 1.5
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False
        assert TOPIC_BODY_VALIDATION_FAILED in (result.reason or "")

    def test_topics_empty_array(self, validator: TopicBodyValidator) -> None:
        """topics requires minItems: 1."""
        body = _valid_memory_write_body()
        body["topics"] = []
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False
        assert TOPIC_BODY_VALIDATION_FAILED in (result.reason or "")

    def test_additional_properties_rejected(self, validator: TopicBodyValidator) -> None:
        """Schema has additionalProperties: false."""
        body = _valid_memory_write_body()
        body["not_a_real_field"] = "surprise"
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False
        assert TOPIC_BODY_VALIDATION_FAILED in (result.reason or "")

    def test_schema_version_must_be_2_0(self, validator: TopicBodyValidator) -> None:
        """schema_version is const: '2.0'."""
        body = _valid_memory_write_body()
        body["schema_version"] = "1.0"
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False

    def test_operation_must_be_upsert(self, validator: TopicBodyValidator) -> None:
        """operation is const: 'UPSERT'."""
        body = _valid_memory_write_body()
        body["operation"] = "DELETE"
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False

    def test_conversation_turn_must_be_integer(self, validator: TopicBodyValidator) -> None:
        body = _valid_memory_write_body()
        body["conversation_turn"] = "three"
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False


# ===========================================================================
# Glob topic validation (ifl.*)
# ===========================================================================


class TestGlobTopicValidation:
    """Verify that glob-matched topics (ifl.*) validate against their schema."""

    def test_ifl_glob_is_known(self, validator: TopicBodyValidator) -> None:
        assert validator.is_known_topic("ifl.health.fitbit.hr") is True

    def test_ifl_glob_band_check(self, validator: TopicBodyValidator) -> None:
        """ifl.* allows GREEN, AMBER, RED."""
        for band in ("GREEN", "AMBER", "RED"):
            result = validator.validate_topic_body("ifl.health.fitbit.hr", {"data": "x"}, band, 10)
            # Band check passes (may fail on schema, but not on band)
            assert TOPIC_BAND_NOT_ALLOWED not in (result.reason or "")


# ===========================================================================
# Violation details
# ===========================================================================


class TestViolationDetails:
    """Verify BodyViolation path and message formatting."""

    def test_violation_has_path_and_message(self, validator: TopicBodyValidator) -> None:
        body = _valid_memory_write_body()
        del body["text"]
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False
        for v in result.violations:
            assert isinstance(v, BodyViolation)
            assert isinstance(v.path, str)
            assert isinstance(v.message, str)
            assert len(v.message) > 0

    def test_nested_violation_path(self, validator: TopicBodyValidator) -> None:
        """Violation in affect.valence should have a nested path."""
        body = _valid_memory_write_body()
        body["affect"]["valence"] = "not-a-number"
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False
        paths = [v.path for v in result.violations]
        # Should have a path like $.affect.valence or similar nested reference
        assert any("affect" in p for p in paths)

    def test_max_10_violations_cap(self, validator: TopicBodyValidator) -> None:
        """Violations are capped at 10 to avoid huge responses."""
        # Body with many errors: all required fields missing
        body = {"garbage_field_1": 1, "garbage_field_2": 2}
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert result.valid is False
        assert len(result.violations) <= 10


# ===========================================================================
# is_known_topic + known_topics
# ===========================================================================


class TestKnownTopics:
    """Verify topic enumeration helpers."""

    def test_known_topics_includes_exact(self, validator: TopicBodyValidator) -> None:
        topics = validator.known_topics()
        assert "memory.write" in topics
        assert "session.snapshot" in topics
        assert "sync.delta" in topics

    def test_is_known_for_exact(self, validator: TopicBodyValidator) -> None:
        assert validator.is_known_topic("memory.write") is True

    def test_is_known_for_glob(self, validator: TopicBodyValidator) -> None:
        assert validator.is_known_topic("ifl.something") is True

    def test_not_known_for_random(self, validator: TopicBodyValidator) -> None:
        assert validator.is_known_topic("random.topic.xyz") is False


# ===========================================================================
# TopicValidationResult immutability
# ===========================================================================


class TestResultProperties:
    """TopicValidationResult is a frozen dataclass."""

    def test_valid_result_fields(self, validator: TopicBodyValidator) -> None:
        body = _valid_memory_write_body()
        body_bytes = len(json.dumps(body).encode("utf-8"))
        result = validator.validate_topic_body("memory.write", body, "GREEN", body_bytes)
        assert isinstance(result, TopicValidationResult)
        assert result.valid is True
        assert result.reason is None
        assert result.violations == ()

    def test_invalid_result_fields(self, validator: TopicBodyValidator) -> None:
        result = validator.validate_topic_body("unknown.topic", {}, "GREEN", 0)
        assert isinstance(result, TopicValidationResult)
        assert result.valid is False
        assert result.reason is not None
