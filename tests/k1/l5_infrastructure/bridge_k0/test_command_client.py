"""
Unit tests for K0 Command Client (WARD Framework)

Tests the K0 Bridge Command Client implementation for:
- GREEN band commands (<50ms P95)
- AMBER/RED band commands (<200ms P95)
- Error handling (400, 403, 409, 429, 5xx)
- Retry logic with exponential backoff
- Receipt validation

Test Framework: WARD
ADR Reference: ADR-0001a (K0 Bridge), ADR-0024 (Performance Budgets)
Performance: <50ms GREEN, <200ms AMBER/RED
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from ward import test  # type: ignore[attr-defined]

from k1.l5_infrastructure.bridge_k0.command_client import (
    CommandEnvelope,
    K0CommandClient,
    K0CommandRejected,
    K0IdempotentDuplicate,
    K0PolicyDenied,
    K0QoSExhausted,
    K0Unavailable,
)


def mock_connection_manager_client(mock_http_client: AsyncMock):
    """Helper to mock HTTP2ConnectionManager.get_client() context manager"""

    @asynccontextmanager
    async def mock_get_client(*args, **kwargs):
        yield mock_http_client

    return mock_get_client


def create_sample_envelope() -> CommandEnvelope:
    """Create a sample command envelope for testing"""
    return CommandEnvelope(
        cognitive_trace_id=str(uuid.uuid4()),
        tenant_id="test_tenant",
        space_id="test_space",
        topic="memory.write",
        schema_uri="familyos://schemas/memory/v1",
        schema_version="1.0",
        actor="user_dad",
        device_id="device_dad_phone",
        band="GREEN",
        policy_version="1.0",
        ts=datetime.now(timezone.utc).isoformat(),
        sig="test_signature_placeholder",
        body={"content": "Test memory"},
    )


@test("submit_command: GREEN band success returns receipt with offsets")
async def _() -> None:
    """Test successful GREEN band command submission (<50ms P95)"""
    # Setup
    client = K0CommandClient(base_url="http://localhost:5200")
    mock_http_client = AsyncMock()

    envelope = create_sample_envelope()

    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "receipt_id": str(uuid.uuid4()),
        "commit_ts": datetime.now(timezone.utc).isoformat(),
        "offsets": {"memory.write": 12345},
        "idem_key": "test_idem_key",
        "obligations": [],
    }
    mock_http_client.post.return_value = mock_response

    # Mock connection manager
    client._connection_manager.get_client = mock_connection_manager_client(
        mock_http_client
    )

    # Execute
    receipt = await client.submit_command(envelope)

    # Verify
    assert receipt.receipt_id is not None
    assert receipt.commit_ts is not None
    assert "memory.write" in receipt.offsets
    assert receipt.offsets["memory.write"] == 12345
    assert receipt.idem_key == "test_idem_key"
    assert receipt.obligations == []

    # Verify HTTP call
    mock_http_client.post.assert_called_once()
    call_args = mock_http_client.post.call_args
    assert call_args[0][0] == "http://localhost:5200/k0/command.submit"


@test("submit_command: AMBER band success includes obligations")
async def _() -> None:
    """Test successful AMBER band command submission (<200ms P95)"""
    # Setup
    client = K0CommandClient(base_url="http://localhost:5200")
    mock_http_client = AsyncMock()

    envelope = create_sample_envelope()
    envelope.band = "AMBER"  # Smart Lane

    # Mock successful response with obligations
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "receipt_id": str(uuid.uuid4()),
        "commit_ts": datetime.now(timezone.utc).isoformat(),
        "offsets": {"memory.write": 12346},
        "idem_key": "test_idem_key_amber",
        "obligations": ["pattern_separation", "consolidation"],
    }
    mock_http_client.post.return_value = mock_response

    # Mock connection manager
    client._connection_manager.get_client = mock_connection_manager_client(
        mock_http_client
    )

    # Execute
    receipt = await client.submit_command(envelope)

    # Verify
    assert receipt.receipt_id is not None
    assert receipt.obligations == ["pattern_separation", "consolidation"]


@test("submit_command: 400 Bad Request raises K0CommandRejected")
async def _() -> None:
    """Test K0 Minimal Gate rejection (400)"""
    # Setup
    client = K0CommandClient(base_url="http://localhost:5200")
    mock_http_client = AsyncMock()
    # Mock connection manager

    client._connection_manager.get_client = mock_connection_manager_client(
        mock_http_client
    )

    envelope = create_sample_envelope()

    # Mock 400 response
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "error": {
            "code": "REJECTED_KERNEL_GATE",
            "component": "kernel.gate",
            "reason": "PAYLOAD_HASH_MISMATCH",
            "trace_id": envelope.cognitive_trace_id,
        }
    }
    mock_http_client.post.return_value = mock_response

    # Execute & Verify
    try:
        await client.submit_command(envelope)
        assert False, "Expected K0CommandRejected exception"
    except K0CommandRejected as exc:
        assert exc.reason == "PAYLOAD_HASH_MISMATCH"
        assert exc.component == "kernel.gate"


@test("submit_command: 403 Forbidden raises K0PolicyDenied")
async def _() -> None:
    """Test K0 policy enforcement deny (403)"""
    # Setup
    client = K0CommandClient(base_url="http://localhost:5200")
    mock_http_client = AsyncMock()
    # Mock connection manager

    client._connection_manager.get_client = mock_connection_manager_client(
        mock_http_client
    )

    envelope = create_sample_envelope()

    # Mock 403 response
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.json.return_value = {
        "error": {
            "code": "PEP_DENY",
            "component": "kernel.policy",
            "reason": "ROLE_FORBIDDEN",
            "trace_id": envelope.cognitive_trace_id,
        }
    }
    mock_http_client.post.return_value = mock_response

    # Execute & Verify
    try:
        await client.submit_command(envelope)
        assert False, "Expected K0PolicyDenied exception"
    except K0PolicyDenied as exc:
        assert exc.reason == "ROLE_FORBIDDEN"


@test("submit_command: 409 Conflict raises K0IdempotentDuplicate")
async def _() -> None:
    """Test K0 idempotent duplicate detection (409)"""
    # Setup
    client = K0CommandClient(base_url="http://localhost:5200")
    mock_http_client = AsyncMock()
    # Mock connection manager

    client._connection_manager.get_client = mock_connection_manager_client(
        mock_http_client
    )

    envelope = create_sample_envelope()

    # Mock 409 response
    existing_receipt_id = str(uuid.uuid4())
    mock_response = Mock()
    mock_response.status_code = 409
    mock_response.json.return_value = {
        "receipt_id": existing_receipt_id,
        "commit_ts": "2025-10-24T12:00:00Z",
        "idem_key": "duplicate_key",
    }
    mock_http_client.post.return_value = mock_response

    # Execute & Verify
    try:
        await client.submit_command(envelope)
        assert False, "Expected K0IdempotentDuplicate exception"
    except K0IdempotentDuplicate as exc:
        assert exc.receipt["receipt_id"] == existing_receipt_id


@test("submit_command: 429 Too Many Requests raises K0QoSExhausted")
async def _() -> None:
    """Test K0 QoS budget exhaustion (429)"""
    # Setup
    client = K0CommandClient(base_url="http://localhost:5200")
    mock_http_client = AsyncMock()
    # Mock connection manager

    client._connection_manager.get_client = mock_connection_manager_client(
        mock_http_client
    )

    envelope = create_sample_envelope()

    # Mock 429 response
    mock_response = Mock()
    mock_response.status_code = 429
    mock_response.json.return_value = {
        "error": {
            "code": "QOS_BUDGET_EXHAUSTED",
            "component": "kernel.qos",
            "reason": "FANOUT_BUDGET_EXHAUSTED",
            "trace_id": envelope.cognitive_trace_id,
            "budgets": {"fanout": 0, "top_k": 8},
            "details": {"cap": "fanout"},
        }
    }
    mock_http_client.post.return_value = mock_response

    # Execute & Verify
    try:
        await client.submit_command(envelope)
        assert False, "Expected K0QoSExhausted exception"
    except K0QoSExhausted as exc:
        assert exc.cap == "fanout"
        assert exc.budgets["fanout"] == 0


@test("submit_command: 5xx retries and succeeds on third attempt")
async def _() -> None:
    """Test K0 unavailable with retry logic (5xx)"""
    # Setup
    client = K0CommandClient(base_url="http://localhost:5200")
    mock_http_client = AsyncMock()
    # Mock connection manager

    client._connection_manager.get_client = mock_connection_manager_client(
        mock_http_client
    )

    envelope = create_sample_envelope()

    # Mock 503 response for first 2 attempts, then success on 3rd
    mock_response_503 = Mock()
    mock_response_503.status_code = 503
    mock_response_503.text = "Service Unavailable"

    mock_response_200 = Mock()
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {
        "receipt_id": str(uuid.uuid4()),
        "commit_ts": datetime.now(timezone.utc).isoformat(),
        "offsets": {"memory.write": 12347},
        "idem_key": "test_idem_key_retry",
        "obligations": [],
    }

    # Configure mock to fail twice, then succeed
    mock_http_client.post.side_effect = [
        mock_response_503,  # 1st attempt fails
        mock_response_503,  # 2nd attempt fails
        mock_response_200,  # 3rd attempt succeeds
    ]

    # Execute
    receipt = await client.submit_command(envelope)

    # Verify
    assert receipt.receipt_id is not None
    assert receipt.idem_key == "test_idem_key_retry"
    assert mock_http_client.post.call_count == 3


@test("submit_command: 5xx all retries exhausted raises K0Unavailable")
async def _() -> None:
    """Test K0 unavailable with all retries exhausted (5xx)"""
    # Setup
    client = K0CommandClient(base_url="http://localhost:5200")
    mock_http_client = AsyncMock()
    # Mock connection manager

    client._connection_manager.get_client = mock_connection_manager_client(
        mock_http_client
    )

    envelope = create_sample_envelope()

    # Mock 503 response for all attempts
    mock_response_503 = Mock()
    mock_response_503.status_code = 503
    mock_response_503.text = "Service Unavailable"
    mock_http_client.post.return_value = mock_response_503

    # Execute & Verify
    try:
        await client.submit_command(envelope)
        assert False, "Expected K0Unavailable exception"
    except K0Unavailable as exc:
        assert exc.status_code == 503
        assert mock_http_client.post.call_count == 3  # max_retries


@test("submit_command: auto-generates idempotency key if not provided")
async def _() -> None:
    """Test automatic idempotency key generation"""
    # Setup
    client = K0CommandClient(base_url="http://localhost:5200")
    mock_http_client = AsyncMock()
    # Mock connection manager

    client._connection_manager.get_client = mock_connection_manager_client(
        mock_http_client
    )

    envelope = create_sample_envelope()
    envelope.idem_key = None  # Remove idempotency key

    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "receipt_id": str(uuid.uuid4()),
        "commit_ts": datetime.now(timezone.utc).isoformat(),
        "offsets": {"memory.write": 12348},
        "idem_key": "generated_idem_key",
        "obligations": [],
    }
    mock_http_client.post.return_value = mock_response

    # Execute
    receipt = await client.submit_command(envelope)

    # Verify idempotency key was generated
    assert envelope.idem_key is not None
    assert receipt.idem_key == "generated_idem_key"


@test("submit_command: auto-computes payload SHA256 if not provided")
async def _() -> None:
    """Test automatic payload SHA256 computation"""

    # Setup
    client = K0CommandClient(base_url="http://localhost:5200")

    envelope = create_sample_envelope()
    envelope.payload_sha256 = None  # Remove payload hash

    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "receipt_id": str(uuid.uuid4()),
        "commit_ts": datetime.now(timezone.utc).isoformat(),
        "offsets": {"memory.write": 12349},
        "idem_key": "test_idem_key",
        "obligations": [],
    }

    # Mock the HTTP client returned by connection manager
    mock_http_client = AsyncMock()
    mock_http_client.post.return_value = mock_response

    # Mock the connection manager's get_client context manager
    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__.return_value = mock_http_client
    mock_context_manager.__aexit__.return_value = AsyncMock()

    # Patch the connection manager's get_client method
    with patch.object(
        client._connection_manager, "get_client", return_value=mock_context_manager
    ):
        # Execute
        receipt = await client.submit_command(envelope)

    # Verify payload SHA256 was computed
    assert envelope.payload_sha256 is not None
    assert len(envelope.payload_sha256) == 64  # SHA256 hex digest length
    assert receipt.receipt_id is not None


@test("client close: properly closes HTTP connection pool")
async def _() -> None:
    """Test client connection pool closure"""

    # Setup - client creates its own connection manager
    client = K0CommandClient(base_url="http://localhost:5200")
    assert client._own_connection_manager is True  # Verify precondition

    # Mock the connection manager's stop method
    mock_stop = AsyncMock()
    with patch.object(client._connection_manager, "stop", new=mock_stop):
        # Execute
        await client.close()

        # Verify connection manager stop was called (since client owns it)
        mock_stop.assert_called_once()
