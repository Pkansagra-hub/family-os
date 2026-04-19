"""
Tests for Phase 6 P6.11 -- Schema validation in TopicRegistry/Middleware.
"""

from __future__ import annotations

import pytest

from k1.bus.envelope import Envelope
from k1.bus.middleware.topic_validation import (
    SchemaValidationError,
    TopicRegistry,
    TopicValidationMiddleware,
)


def _env(topic: str, payload: bytes = b"{}", envelope_id: int = 1) -> Envelope:
    return Envelope(topic=topic, payload=payload, envelope_id=envelope_id)


def _strict_json_validator(payload: bytes, envelope: Envelope) -> None:
    """Reject payloads that are not valid JSON dicts."""
    import json

    try:
        obj = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise SchemaValidationError(f"not JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise SchemaValidationError("payload must be a JSON object")


class TestRegistryValidatorStorage:
    def test_register_with_validator_stores_it(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.cmd.do.v1", validator=_strict_json_validator)
        assert reg.is_known("k1.cmd.do.v1")
        assert reg.lookup_validator("k1.cmd.do.v1") is _strict_json_validator

    def test_register_without_validator_returns_none(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.cmd.do.v1")
        assert reg.lookup_validator("k1.cmd.do.v1") is None

    def test_register_prefix_validator_applies_to_matching_topics(self) -> None:
        reg = TopicRegistry()
        reg.register_prefix("k1.cmd.", validator=_strict_json_validator)
        assert reg.lookup_validator("k1.cmd.foo.v1") is _strict_json_validator
        assert reg.lookup_validator("k1.other.v1") is None

    def test_unregister_removes_validator(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.cmd.do.v1", validator=_strict_json_validator)
        assert reg.unregister("k1.cmd.do.v1") is True
        assert reg.lookup_validator("k1.cmd.do.v1") is None

    def test_clear_drops_all_validators(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.cmd.do.v1", validator=_strict_json_validator)
        reg.register_prefix("k1.evt.", validator=_strict_json_validator)
        reg.clear()
        assert reg.lookup_validator("k1.cmd.do.v1") is None
        assert reg.lookup_validator("k1.evt.x.v1") is None


class TestPermissiveMode:
    def test_valid_payload_passes_through(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.cmd.do.v1", validator=_strict_json_validator)
        mw = TopicValidationMiddleware(reg, schema_validation_mode="permissive")
        env = _env("k1.cmd.do.v1", payload=b'{"k":"v"}')
        result = mw.process(env)
        assert result is env
        assert mw.schema_violation_count == 0

    def test_invalid_payload_logs_and_passes(self, caplog) -> None:
        import logging

        reg = TopicRegistry()
        reg.register("k1.cmd.do.v1", validator=_strict_json_validator)
        mw = TopicValidationMiddleware(reg, schema_validation_mode="permissive")
        env = _env("k1.cmd.do.v1", payload=b"not json")
        with caplog.at_level(logging.WARNING, logger="k1.bus.middleware.topic_validation"):
            result = mw.process(env)
        assert result is env  # still delivered
        assert mw.schema_violation_count == 1
        assert mw.schema_drop_count == 0
        assert any("permissive" in r.getMessage() for r in caplog.records)

    def test_topic_without_validator_skips_validation(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.cmd.do.v1")  # no validator
        mw = TopicValidationMiddleware(reg)
        env = _env("k1.cmd.do.v1", payload=b"anything")
        assert mw.process(env) is env
        assert mw.schema_violation_count == 0


class TestStrictMode:
    def test_invalid_payload_drops_and_counts(self, caplog) -> None:
        import logging

        reg = TopicRegistry()
        reg.register("k1.cmd.do.v1", validator=_strict_json_validator)
        mw = TopicValidationMiddleware(reg, schema_validation_mode="strict")
        env = _env("k1.cmd.do.v1", payload=b"not json")
        with caplog.at_level(logging.WARNING, logger="k1.bus.middleware.topic_validation"):
            result = mw.process(env)
        assert result is None
        assert mw.schema_violation_count == 1
        assert mw.schema_drop_count == 1

    def test_valid_payload_still_passes_in_strict_mode(self) -> None:
        reg = TopicRegistry()
        reg.register("k1.cmd.do.v1", validator=_strict_json_validator)
        mw = TopicValidationMiddleware(reg, schema_validation_mode="strict")
        env = _env("k1.cmd.do.v1", payload=b'{"ok": 1}')
        assert mw.process(env) is env

    def test_invalid_mode_raises(self) -> None:
        reg = TopicRegistry()
        with pytest.raises(ValueError):
            TopicValidationMiddleware(reg, schema_validation_mode="bogus")
