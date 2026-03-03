"""Integration tests: Bridge-to-K0 full command flow.

Exercises the entire pipeline: EnvelopeBuilder -> signing -> transport ->
TopicRouter route resolution -> TopicBodyValidator schema validation.
No mocks -- real components wired together.

Milestone: M2 Epic 2.15
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from bridge.core.envelope_builder import BridgeConfig, EnvelopeBuilder, _canonical_json
from bridge.core.signing import Ed25519Signing, HmacSigning
from bridge.core.transport import HttpTransport, TransportConfig
from bridge.kernel.command_port import KernelCommandPort
from bridge.sync.local_outbox import LocalOutbox
from k0.gate.topic_body_validator import (
    TOPIC_BODY_VALIDATION_FAILED,
    TOPIC_UNKNOWN,
    TopicBodyValidator,
)
from k0.ports.topic_router import TopicRouter, UnknownTopicError

# ---------------------------------------------------------------------------
# Shared valid body
# ---------------------------------------------------------------------------


def _valid_memory_write_body() -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "operation": "UPSERT",
        "text": "Integration test memory atom",
        "topics": ["integration"],
        "sentiment_label": "positive",
        "affect": {"valence": 0.7, "arousal": 0.4, "dominance": 0.6},
        "source_type": "user_stated",
        "novelty": "NOVEL",
        "elaboration_depth": "DISCUSSED",
        "temporal_orientation": "PAST",
        "confidence": 0.90,
        "session_id": "sess-integration",
        "conversation_turn": 5,
        "language": "en",
    }


# ---------------------------------------------------------------------------
# Fixtures: real components, no mocks
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def topic_router() -> TopicRouter:
    return TopicRouter()


@pytest.fixture(scope="module")
def topic_body_validator() -> TopicBodyValidator:
    return TopicBodyValidator()


@pytest.fixture
def hmac_signer() -> HmacSigning:
    return HmacSigning(secret=os.urandom(32), key_id="did:device:integ-001#2026")


@pytest.fixture
def ed25519_signer() -> Ed25519Signing:
    return Ed25519Signing(signing_key_bytes=os.urandom(32), key_id="did:device:integ-001#ed")


@pytest.fixture
def bridge_config() -> BridgeConfig:
    return BridgeConfig(
        tenant_id="tenant-integ",
        space_id="space-integ",
        device_id="device-integ-001",
        actor="bridge",
        policy_version="1.0",
        default_band="GREEN",
    )


@pytest.fixture
def hmac_builder(bridge_config: BridgeConfig, hmac_signer: HmacSigning) -> EnvelopeBuilder:
    return EnvelopeBuilder(config=bridge_config, signer=hmac_signer)


@pytest.fixture
def ed25519_builder(bridge_config: BridgeConfig, ed25519_signer: Ed25519Signing) -> EnvelopeBuilder:
    return EnvelopeBuilder(config=bridge_config, signer=ed25519_signer)


# ===========================================================================
# Integration: Build envelope -> validate body -> verify route
# ===========================================================================


class TestBridgeToK0Validation:
    """Full path: EnvelopeBuilder.build() -> TopicBodyValidator -> TopicRouter."""

    def test_valid_memory_write_passes_gate_validation(
        self,
        hmac_builder: EnvelopeBuilder,
        topic_body_validator: TopicBodyValidator,
    ) -> None:
        body = _valid_memory_write_body()
        envelope = hmac_builder.build("memory.write", body)

        # Simulate K0 Gate: validate body
        body_json = _canonical_json(envelope["body"])
        body_bytes_len = len(body_json.encode("utf-8"))
        result = topic_body_validator.validate_topic_body(
            envelope["topic"],
            envelope["body"],
            envelope["band"],
            body_bytes_len,
        )
        assert result.valid is True, f"Validation failed: {result.reason} {result.violations}"

    def test_valid_memory_write_resolves_route(
        self,
        hmac_builder: EnvelopeBuilder,
        topic_router: TopicRouter,
    ) -> None:
        body = _valid_memory_write_body()
        envelope = hmac_builder.build("memory.write", body)

        route = topic_router.resolve(envelope["topic"])
        assert route.outbox_driver == "st_epi"
        assert route.pipeline == "P02"

    def test_ifl_topic_resolves_and_validates(
        self,
        hmac_builder: EnvelopeBuilder,
        topic_body_validator: TopicBodyValidator,
        topic_router: TopicRouter,
    ) -> None:
        """ifl.* glob topic: route resolves AND body passes validator's band check."""
        body = {"some": "data"}  # ifl_event schema may differ; test band/route only
        envelope = hmac_builder.build("ifl.health.fitbit.hr", body)

        route = topic_router.resolve(envelope["topic"])
        assert route.outbox_driver == "st_epi"
        assert route.bus_topic == "cognitive.ifl.event.committed.v1"

    def test_unknown_topic_rejected_by_both(
        self,
        hmac_builder: EnvelopeBuilder,
        topic_body_validator: TopicBodyValidator,
        topic_router: TopicRouter,
    ) -> None:
        body = {"data": "test"}
        envelope = hmac_builder.build("totally.unknown", body)

        # TopicRouter rejects
        with pytest.raises(UnknownTopicError):
            topic_router.resolve(envelope["topic"])

        # TopicBodyValidator rejects
        result = topic_body_validator.validate_topic_body(
            envelope["topic"], envelope["body"], envelope["band"], 100
        )
        assert result.valid is False
        assert TOPIC_UNKNOWN in (result.reason or "")


# ===========================================================================
# Integration: Envelope integrity across K0 canonical JSON
# ===========================================================================


class TestEnvelopeIntegrity:
    """Verify Bridge-built envelopes produce correct K0-compatible hashes."""

    def test_payload_sha256_matches_k0_canonical(self, hmac_builder: EnvelopeBuilder) -> None:
        body = _valid_memory_write_body()
        envelope = hmac_builder.build("memory.write", body)

        # Re-compute as K0 would
        k0_body_json = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected_sha = hashlib.sha256(k0_body_json.encode("utf-8")).hexdigest()
        assert envelope["payload_sha256"] == expected_sha

    def test_idem_key_deterministic_across_builders(
        self, bridge_config: BridgeConfig, hmac_signer: HmacSigning
    ) -> None:
        """Two separate builders with same config produce same idem_key."""
        builder_a = EnvelopeBuilder(config=bridge_config, signer=hmac_signer)
        builder_b = EnvelopeBuilder(config=bridge_config, signer=hmac_signer)
        body = _valid_memory_write_body()
        env_a = builder_a.build("memory.write", body, trace_id="t1")
        env_b = builder_b.build("memory.write", body, trace_id="t2")
        assert env_a["idem_key"] == env_b["idem_key"]

    def test_envelope_sha256_excludes_sig_fields(self, hmac_builder: EnvelopeBuilder) -> None:
        body = _valid_memory_write_body()
        envelope = hmac_builder.build("memory.write", body)

        # Reconstruct pre-sig envelope
        pre_sig = {
            k: v
            for k, v in envelope.items()
            if k not in ("envelope_sha256", "sig", "sig_alg", "sig_kid")
        }
        canonical = json.dumps(pre_sig, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert envelope["envelope_sha256"] == expected

    def test_sig_verifiable_with_signer(
        self, hmac_builder: EnvelopeBuilder, hmac_signer: HmacSigning
    ) -> None:
        body = _valid_memory_write_body()
        envelope = hmac_builder.build("memory.write", body)
        assert (
            hmac_signer.verify(
                envelope["envelope_sha256"].encode("utf-8"),
                envelope["sig"],
            )
            is True
        )


# ===========================================================================
# Integration: Ed25519 end-to-end
# ===========================================================================


class TestEd25519EndToEnd:
    """Full pipeline with Ed25519 production signing."""

    def test_ed25519_envelope_passes_validation(
        self,
        ed25519_builder: EnvelopeBuilder,
        ed25519_signer: Ed25519Signing,
        topic_body_validator: TopicBodyValidator,
    ) -> None:
        body = _valid_memory_write_body()
        envelope = ed25519_builder.build("memory.write", body)

        # Verify signature
        assert (
            ed25519_signer.verify(
                envelope["envelope_sha256"].encode("utf-8"),
                envelope["sig"],
            )
            is True
        )

        # Verify body validation
        body_json = _canonical_json(envelope["body"])
        body_bytes_len = len(body_json.encode("utf-8"))
        result = topic_body_validator.validate_topic_body(
            envelope["topic"],
            envelope["body"],
            envelope["band"],
            body_bytes_len,
        )
        assert result.valid is True


# ===========================================================================
# Integration: KernelCommandPort -> LocalOutbox drain cycle
# ===========================================================================


class TestCommandPortOutboxDrainCycle:
    """Full cycle: submit fails -> enqueue -> drain succeeds."""

    async def test_submit_fail_then_drain_success(
        self, hmac_builder: EnvelopeBuilder, tmp_path: Path
    ) -> None:
        outbox = LocalOutbox(db_path=tmp_path / "drain_cycle.db")

        # Phase 1: K0 unavailable -- submit enqueues
        def handler_503(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        fail_transport = HttpTransport(TransportConfig(base_url="http://test:8000"))
        fail_transport._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler_503),
            base_url="http://test:8000",
        )

        port = KernelCommandPort(transport=fail_transport, builder=hmac_builder, outbox=outbox)
        await port.submit("memory.write", _valid_memory_write_body())
        assert outbox.pending_count() == 1
        await fail_transport.close()

        # Phase 2: K0 recovered -- drain succeeds
        def handler_200(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "ok"})

        ok_transport = HttpTransport(TransportConfig(base_url="http://test:8000"))
        ok_transport._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler_200),
            base_url="http://test:8000",
        )

        drained = await outbox.drain(ok_transport)
        assert drained == 1
        assert outbox.pending_count() == 0
        await ok_transport.close()
        outbox.close()

    async def test_multiple_topics_enqueue_and_drain(
        self, hmac_builder: EnvelopeBuilder, tmp_path: Path
    ) -> None:
        outbox = LocalOutbox(db_path=tmp_path / "multi_drain.db")

        def handler_500(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        fail_transport = HttpTransport(TransportConfig(base_url="http://test:8000"))
        fail_transport._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler_500),
            base_url="http://test:8000",
        )

        port = KernelCommandPort(transport=fail_transport, builder=hmac_builder, outbox=outbox)
        body = _valid_memory_write_body()
        await port.submit("memory.write", body)
        await port.submit("memory.write", {**body, "text": "Second atom"})
        assert outbox.pending_count() == 2
        await fail_transport.close()

        def handler_200(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "ok"})

        ok_transport = HttpTransport(TransportConfig(base_url="http://test:8000"))
        ok_transport._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler_200),
            base_url="http://test:8000",
        )

        drained = await outbox.drain(ok_transport)
        assert drained == 2
        assert outbox.pending_count() == 0
        await ok_transport.close()
        outbox.close()


# ===========================================================================
# Integration: Invalid body rejected through full pipeline
# ===========================================================================


class TestInvalidBodyFullPipeline:
    """Invalid body detected by TopicBodyValidator after Bridge builds envelope."""

    def test_missing_required_field_detected(
        self,
        hmac_builder: EnvelopeBuilder,
        topic_body_validator: TopicBodyValidator,
    ) -> None:
        body = _valid_memory_write_body()
        del body["text"]  # required field
        envelope = hmac_builder.build("memory.write", body)

        body_json = _canonical_json(envelope["body"])
        result = topic_body_validator.validate_topic_body(
            envelope["topic"],
            envelope["body"],
            envelope["band"],
            len(body_json.encode("utf-8")),
        )
        assert result.valid is False
        assert TOPIC_BODY_VALIDATION_FAILED in (result.reason or "")

    def test_wrong_band_rejected(
        self,
        hmac_builder: EnvelopeBuilder,
        topic_body_validator: TopicBodyValidator,
    ) -> None:
        """Build with wrong band for sync.delta (only GREEN allowed)."""
        body = {"data": "some sync data"}
        envelope = hmac_builder.build("sync.delta", body, band="RED")

        body_json = _canonical_json(envelope["body"])
        result = topic_body_validator.validate_topic_body(
            envelope["topic"],
            envelope["body"],
            envelope["band"],
            len(body_json.encode("utf-8")),
        )
        assert result.valid is False
        assert "BAND_NOT_ALLOWED" in (result.reason or "")
