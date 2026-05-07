"""M5 Request Pipeline -- Test AuditLogger [F52].

Tests full audit logging of every Model Hub call (MH-11).

Covers:
  - AuditRecord: construction, frozen, defaults
  - log(): successful request/response pair
  - log_error(): failed request
  - Query: records, count, clear
  - Re-exports from services/__init__.py
"""

from __future__ import annotations

import pytest

from k1.model_hub.services.audit_logger import AuditLogger, AuditRecord
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    HubRequest,
    HubResponse,
    Message,
    RequestConstraints,
    ResponseMetadata,
    TokenUsage,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_request(
    *,
    consumer_id: str = "concierge",
    trace_id: str = "t-1",
) -> HubRequest:
    return HubRequest(
        capability=CapabilityType.CHAT,
        payload=ChatPayload(messages=[Message(role="user", content="hi")]),
        trace_id=trace_id,
        constraints=RequestConstraints(consumer_id=consumer_id),
    )


def _make_response(
    *,
    request_id: str = "r-1",
    model_id: str = "gpt-4o",
    provider_id: str = "openai",
    cost_usd: float = 0.01,
    latency_ms: int = 200,
    cache_hit: bool = False,
    fallback_used: bool = False,
) -> HubResponse:
    return HubResponse(
        result="hello",
        metadata=ResponseMetadata(
            request_id=request_id,
            model_id=model_id,
            provider_id=provider_id,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            capability=CapabilityType.CHAT,
            trace_id="t-1",
            fallback_used=fallback_used,
        ),
    )


# ===========================================================================
# AuditRecord Tests
# ===========================================================================


class TestAuditRecord:
    def test_construction(self) -> None:
        r = AuditRecord(
            request_id="r-1",
            trace_id="t-1",
            consumer_id="concierge",
            capability=CapabilityType.CHAT,
            model_id="gpt-4o",
            provider_id="openai",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.01,
            latency_ms=200,
            cache_hit=False,
        )
        assert r.request_id == "r-1"
        assert r.error is None
        assert r.fallback_chain == []

    def test_frozen(self) -> None:
        r = AuditRecord(
            request_id="r-1",
            trace_id="t-1",
            consumer_id="",
            capability=CapabilityType.CHAT,
            model_id="m",
            provider_id="p",
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            latency_ms=0,
            cache_hit=False,
        )
        with pytest.raises(AttributeError):
            r.cost_usd = 1.0  # type: ignore[misc]


# ===========================================================================
# log() Tests
# ===========================================================================


class TestLog:
    def test_log_returns_record(self) -> None:
        logger = AuditLogger()
        req = _make_request()
        resp = _make_response()
        record = logger.log(req, resp)
        assert record.request_id == resp.metadata.request_id
        assert record.consumer_id == "concierge"
        assert record.model_id == "gpt-4o"
        assert record.cost_usd == 0.01

    def test_log_with_fallback_chain(self) -> None:
        logger = AuditLogger()
        record = logger.log(
            _make_request(),
            _make_response(fallback_used=True),
            fallback_chain=["openai", "anthropic"],
        )
        assert record.fallback_used is True
        assert record.fallback_chain == ["openai", "anthropic"]

    def test_log_increments_count(self) -> None:
        logger = AuditLogger()
        logger.log(_make_request(), _make_response())
        logger.log(_make_request(), _make_response())
        assert logger.count == 2

    def test_log_cache_hit(self) -> None:
        logger = AuditLogger()
        record = logger.log(
            _make_request(),
            _make_response(cache_hit=True),
        )
        assert record.cache_hit is True


# ===========================================================================
# log_error() Tests
# ===========================================================================


class TestLogError:
    def test_log_error_returns_record(self) -> None:
        logger = AuditLogger()
        record = logger.log_error(_make_request(), "timeout exceeded")
        assert record.error == "timeout exceeded"
        assert record.model_id == ""
        assert record.cost_usd == 0.0

    def test_log_error_with_fallback_chain(self) -> None:
        logger = AuditLogger()
        record = logger.log_error(
            _make_request(),
            "all providers failed",
            fallback_chain=["openai", "anthropic"],
        )
        assert record.fallback_chain == ["openai", "anthropic"]

    def test_log_error_increments_count(self) -> None:
        logger = AuditLogger()
        logger.log_error(_make_request(), "err")
        assert logger.count == 1


# ===========================================================================
# Query Tests
# ===========================================================================


class TestQuery:
    def test_records_empty(self) -> None:
        logger = AuditLogger()
        assert logger.records == []

    def test_records_returns_copy(self) -> None:
        logger = AuditLogger()
        logger.log(_make_request(), _make_response())
        records = logger.records
        records.clear()
        assert logger.count == 1

    def test_clear(self) -> None:
        logger = AuditLogger()
        logger.log(_make_request(), _make_response())
        logger.log_error(_make_request(), "err")
        logger.clear()
        assert logger.count == 0
        assert logger.records == []


# ===========================================================================
# Re-exports
# ===========================================================================


class TestAuditLoggerReExports:
    def test_audit_logger_reexport(self) -> None:
        from k1.model_hub.services import AuditLogger as Reexported

        assert Reexported is AuditLogger

    def test_audit_record_reexport(self) -> None:
        from k1.model_hub.services import AuditRecord as Reexported

        assert Reexported is AuditRecord
