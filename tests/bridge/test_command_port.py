"""Real component tests for KernelCommandPort.

Tests submit, submit_batch, error handling per HTTP status code,
and offline queueing integration with LocalOutbox.
No mocks -- real EnvelopeBuilder, real signing, real transport (httpx.MockTransport).

Milestone: M2 Epic 2.15
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from bridge.core.envelope_builder import BridgeConfig, CommandEnvelope, EnvelopeBuilder
from bridge.core.signing import HmacSigning
from bridge.core.transport import HttpTransport, TransportConfig
from bridge.kernel.command_port import ContractViolationError, KernelCommandPort, PolicyDeniedError
from bridge.sync.local_outbox import LocalOutbox

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> BridgeConfig:
    return BridgeConfig(
        tenant_id="tenant-test",
        space_id="space-test",
        device_id="device-test-001",
    )


@pytest.fixture
def signer() -> HmacSigning:
    return HmacSigning(secret=os.urandom(32), key_id="test-key-001")


@pytest.fixture
def builder(config: BridgeConfig, signer: HmacSigning) -> EnvelopeBuilder:
    return EnvelopeBuilder(config=config, signer=signer)


def _make_transport(handler) -> HttpTransport:
    transport = HttpTransport(TransportConfig(base_url="http://test-k0:8000"))
    transport._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://test-k0:8000",
    )
    return transport


@pytest.fixture
def outbox(tmp_path: Path):
    ob = LocalOutbox(db_path=tmp_path / "cmd_port_outbox.db")
    yield ob
    ob.close()


SAMPLE_BODY = {
    "schema_version": "2.0",
    "operation": "UPSERT",
    "text": "Test atom for command port",
    "topics": ["testing"],
    "sentiment_label": "neutral",
    "affect": {"valence": 0.0, "arousal": 0.3, "dominance": 0.5},
    "source_type": "system_inferred",
    "novelty": "ROUTINE",
    "elaboration_depth": "MENTION",
    "temporal_orientation": "ONGOING",
    "confidence": 0.85,
    "session_id": "sess-test",
    "conversation_turn": 1,
    "language": "en",
}


# ===========================================================================
# Submit: success paths
# ===========================================================================


class TestSubmitSuccess:
    """Verify submit on 200 and 409 status codes."""

    async def test_submit_200_succeeds_silently(self, builder: EnvelopeBuilder) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "ok"})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder)
        # Should not raise
        await port.submit("memory.write", SAMPLE_BODY)
        await transport.close()

    async def test_submit_409_duplicate_succeeds_silently(self, builder: EnvelopeBuilder) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(409, json={"reason": "DUPLICATE"})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder)
        await port.submit("memory.write", SAMPLE_BODY)
        await transport.close()


# ===========================================================================
# Submit: contract violation errors
# ===========================================================================


class TestSubmitContractViolation:
    """Verify 400 and 403 raise appropriate errors."""

    async def test_submit_400_raises_contract_violation(self, builder: EnvelopeBuilder) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"reason": "BODY_VALIDATION_FAILED"})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder)
        with pytest.raises(ContractViolationError, match="BODY_VALIDATION_FAILED"):
            await port.submit("memory.write", SAMPLE_BODY)
        await transport.close()

    async def test_submit_403_raises_policy_denied(self, builder: EnvelopeBuilder) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"reason": "policy_denied"})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder)
        with pytest.raises(PolicyDeniedError, match="policy_denied"):
            await port.submit("memory.write", SAMPLE_BODY)
        await transport.close()

    async def test_policy_denied_is_contract_violation_subclass(self) -> None:
        assert issubclass(PolicyDeniedError, ContractViolationError)


# ===========================================================================
# Submit: offline queueing (429, 5xx, connection errors)
# ===========================================================================


class TestSubmitOfflineQueueing:
    """Verify envelopes are queued to LocalOutbox on transient failures."""

    async def test_429_enqueues_to_outbox(
        self, builder: EnvelopeBuilder, outbox: LocalOutbox
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"reason": "rate_limited"})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder, outbox=outbox)
        await port.submit("memory.write", SAMPLE_BODY)
        assert outbox.pending_count() == 1
        await transport.close()

    async def test_500_enqueues_to_outbox(
        self, builder: EnvelopeBuilder, outbox: LocalOutbox
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "internal"})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder, outbox=outbox)
        await port.submit("memory.write", SAMPLE_BODY)
        assert outbox.pending_count() == 1
        await transport.close()

    async def test_503_enqueues_to_outbox(
        self, builder: EnvelopeBuilder, outbox: LocalOutbox
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder, outbox=outbox)
        await port.submit("memory.write", SAMPLE_BODY)
        assert outbox.pending_count() == 1
        await transport.close()

    async def test_connection_error_enqueues(
        self, builder: EnvelopeBuilder, outbox: LocalOutbox
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder, outbox=outbox)
        await port.submit("memory.write", SAMPLE_BODY)
        assert outbox.pending_count() == 1
        await transport.close()

    async def test_no_outbox_does_not_raise_on_5xx(self, builder: EnvelopeBuilder) -> None:
        """Without outbox, 5xx is logged but does not raise (fire-and-forget)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder, outbox=None)
        await port.submit("memory.write", SAMPLE_BODY)  # should not raise
        await transport.close()


# ===========================================================================
# Submit: envelope correctness
# ===========================================================================


class TestSubmitEnvelopeCorrectness:
    """Verify the envelope sent over the wire is properly constructed."""

    async def test_envelope_has_required_fields(self, builder: EnvelopeBuilder) -> None:
        received_envelopes: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            received_envelopes.append(json.loads(request.content))
            return httpx.Response(200, json={"status": "ok"})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder)
        await port.submit("memory.write", SAMPLE_BODY, trace_id="trace-check")
        assert len(received_envelopes) == 1
        env = received_envelopes[0]
        assert env["topic"] == "memory.write"
        assert env["tenant_id"] == "tenant-test"
        assert env["body"] == SAMPLE_BODY
        assert env["cognitive_trace_id"] == "trace-check"
        assert "idem_key" not in env
        assert "sig" in env
        await transport.close()


# ===========================================================================
# Submit batch
# ===========================================================================


class TestSubmitBatch:
    """Verify batch submission with bounded concurrency."""

    async def test_batch_all_succeed(self, builder: EnvelopeBuilder) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "ok"})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder)
        envelopes = [
            CommandEnvelope(topic="memory.write", body=SAMPLE_BODY),
            CommandEnvelope(topic="memory.write", body={**SAMPLE_BODY, "text": "Second atom"}),
        ]
        await port.submit_batch(envelopes)  # should not raise
        await transport.close()

    async def test_batch_exceeds_max_size_raises(self, builder: EnvelopeBuilder) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder)
        envelopes = [CommandEnvelope(topic="memory.write", body=SAMPLE_BODY) for _ in range(51)]
        with pytest.raises(ValueError, match="exceeds maximum"):
            await port.submit_batch(envelopes)
        await transport.close()

    async def test_batch_collects_contract_violations(self, builder: EnvelopeBuilder) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(400, json={"reason": "VALIDATION_FAILED"})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder)
        envelopes = [
            CommandEnvelope(topic="memory.write", body=SAMPLE_BODY),
            CommandEnvelope(topic="memory.write", body=SAMPLE_BODY),
        ]
        with pytest.raises(ContractViolationError, match="contract violation"):
            await port.submit_batch(envelopes)
        await transport.close()

    async def test_batch_empty_list(self, builder: EnvelopeBuilder) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder)
        await port.submit_batch([])  # should not raise
        await transport.close()

    async def test_batch_409_not_treated_as_error(self, builder: EnvelopeBuilder) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(409, json={"reason": "DUPLICATE"})

        transport = _make_transport(handler)
        port = KernelCommandPort(transport=transport, builder=builder)
        envelopes = [CommandEnvelope(topic="memory.write", body=SAMPLE_BODY)]
        await port.submit_batch(envelopes)  # should not raise
        await transport.close()
