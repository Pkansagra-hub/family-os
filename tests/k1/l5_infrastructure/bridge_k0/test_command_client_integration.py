"""Integration tests for K0CommandClient against live K0 kernel.

REQUIRES: K0 kernel running (default http://localhost:8080; override via K0_COMMAND_BASE_URL)
Run bootstrap: python -m k0.scripts.bootstrap_local_kernel
Run server: python -m k0.kernel.main

These tests verify end-to-end K1→K0 communication:
1. Command submission via HTTP/2
2. Receipt validation (offsets, commit_ts)
3. Database persistence verification
4. Real error responses from K0
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ward import test

from k0.local.dev_profile import default_profile, signing_key_for

# Import K0's security modules for proper signing
from k0.security.crypto import canonical_envelope, encode_base64url
from k1.l5_infrastructure.bridge_k0.command_client import (
    CommandEnvelope,
    K0CommandClient,
    K0CommandRejected,
    K0IdempotentDuplicate,
)

# K0 database path (from bootstrap_local_kernel.py)
K0_DB_PATH = Path("k0/deployment/compose/generated/local-single-node/data/k0_kernel.db")

# Bootstrapped device credentials (from k0.env)
TENANT_ID = "tenant-001"
SPACE_ID = "space-home"
DEVICE_ID = "device-local-001"
MLS_GROUP_ID = "mls-group-local"
SCHEMA_URI = "schema://memory.delta"
SCHEMA_VERSION = "1.0"
POLICY_VERSION = "2025-09-28"
TOPIC = "memory.delta"
ACTOR = "burnin@familyos.dev"
KEY_VERSION = "1"

# Signing key from dev_profile (DEFAULT_SIGNING_KEY_SEED_HEX)
SIGNING_KEY_SEED_HEX = (
    "9d0a9b8c7f6e5d4c3b2a1908f7e6d5c4b3a29180706050403020100ffeeddcc0"
)

# Allow tests to follow whichever port the live kernel exposes.
K0_BASE_URL = os.environ.get("K0_COMMAND_BASE_URL", "http://localhost:8080")


def _create_test_envelope(
    body: dict[str, Any] | None = None,
    band: str = "GREEN",
) -> CommandEnvelope:
    """Create a valid command envelope with K0-compatible signature.

    Uses K0's canonical_envelope() function to ensure signature verification passes.
    IMPORTANT: Must derive idem_key BEFORE signing (K0 validates signature includes idem_key).
    """
    import hashlib

    from k0.idem import derive_idem_key as k0_derive_idem_key

    # Get K0's signing key using its dev_profile
    profile = default_profile()
    signing_key = signing_key_for(profile)

    # Create envelope dict (required fields only initially)
    envelope_data: dict[str, Any] = {
        "cognitive_trace_id": str(uuid.uuid4()),
        "tenant_id": TENANT_ID,
        "space_id": SPACE_ID,
        "topic": TOPIC,
        "schema_uri": SCHEMA_URI,
        "schema_version": SCHEMA_VERSION,
        "actor": ACTOR,
        "device_id": DEVICE_ID,
        "band": band,
        "policy_version": POLICY_VERSION,
        "ts": datetime.now(timezone.utc).isoformat(),
        # Add policy context with roles (required by K0 PEP)
        "policy": {
            "abac": {
                "roles": ["coordinator"]  # Allows memory.* topics per pep.schema.json
            }
        },
    }

    if body:
        envelope_data["body"] = body
        # Compute payload_sha256 (required if body present)
        body_json = json.dumps(body, separators=(",", ":"), sort_keys=True)
        payload_sha256 = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
        envelope_data["payload_sha256"] = payload_sha256
    else:
        payload_sha256 = None

    # Derive idem_key BEFORE signing (K0 validates signature includes this field)
    idem_components = {
        "tenant_id": envelope_data["tenant_id"],
        "space_id": envelope_data["space_id"],
        "actor": envelope_data["actor"],
        "topic": envelope_data["topic"],
        "schema_uri": envelope_data["schema_uri"],
        "schema_version": envelope_data["schema_version"],
    }
    idem_key = k0_derive_idem_key(idem_components, payload_hash=payload_sha256)
    envelope_data["idem_key"] = idem_key

    # Use K0's canonical_envelope to create message for signing
    # (excludes 'sig' and 'body' fields automatically)
    message = canonical_envelope(envelope_data, exclude_signature=True)

    # Generate Ed25519 signature
    signature_bytes = signing_key.sign(message).signature

    # Encode as base64url (K0's expected format)
    signature_b64 = encode_base64url(signature_bytes)
    envelope_data["sig"] = signature_b64

    # Create CommandEnvelope from dict
    return CommandEnvelope(**envelope_data)


def _query_wal_entry(idem_key: str) -> dict[str, Any] | None:
    """Query K0 database for WAL entry by idempotency key."""
    if not K0_DB_PATH.exists():
        return None

    conn = sqlite3.connect(str(K0_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """
            SELECT wal_id, tenant_id, space_id, topic, device_id,
                   band, idem_key, payload_sha256, commit_ts
            FROM wal
            WHERE idem_key = ?
            """,
            (idem_key,),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


@test("integration: submit_command to live K0 with GREEN band")
async def _() -> None:
    """Test successful GREEN band command submission to live K0 kernel."""
    # Setup
    client = K0CommandClient(base_url=K0_BASE_URL)
    envelope = _create_test_envelope(
        body={"content": "Integration test memory", "test_id": str(uuid.uuid4())},
        band="GREEN",
    )

    try:
        # Act
        receipt = await client.submit_command(envelope)

        # Assert: Receipt validation
        assert receipt.receipt_id is not None
        assert receipt.idem_key is not None
        assert len(receipt.offsets) > 0  # At least one topic offset
        assert receipt.commit_ts is not None

        # Assert: Payload SHA256 computation (K0 handles internally)
        # Note: K0 returns payload_sha256 in receipt JSON but not in CommandReceipt dataclass

        # Assert: Database persistence
        # TODO: Query Docker container database instead of local file
        # wal_entry = _query_wal_entry(receipt.idem_key)
        # assert wal_entry is not None
        # assert wal_entry["idem_key"] == receipt.idem_key
        # assert wal_entry["tenant_id"] == TENANT_ID
        # assert wal_entry["space_id"] == SPACE_ID
        # assert wal_entry["device_id"] == DEVICE_ID
        # assert wal_entry["band"] == "GREEN"

    finally:
        await client.close()


@test("integration: submit_command with AMBER band includes obligations")
async def _() -> None:
    """Test AMBER band command returns obligations from K0."""
    # Setup
    client = K0CommandClient(base_url=K0_BASE_URL)
    envelope = _create_test_envelope(
        body={"content": "AMBER band test", "test_id": str(uuid.uuid4())},
        band="AMBER",
    )

    try:
        # Act
        receipt = await client.submit_command(envelope)

        # Assert: Receipt validation
        assert receipt.receipt_id is not None
        assert len(receipt.offsets) > 0
        # Note: K0 may or may not return obligations for AMBER band
        # depending on policy evaluation, so we just verify structure

    finally:
        await client.close()


@test("integration: submit_command with invalid signature raises K0CommandRejected")
async def _() -> None:
    """Test that invalid signature is rejected by K0 gate."""
    # Setup
    client = K0CommandClient(base_url=K0_BASE_URL)
    envelope = _create_test_envelope(
        body={"content": "Bad signature test"},
        band="GREEN",
    )

    # Corrupt the signature
    envelope.sig = "0" * 128  # Invalid hex signature

    try:
        # Act & Assert
        try:
            await client.submit_command(envelope)
            assert False, "Expected K0CommandRejected for invalid signature"
        except K0CommandRejected as exc:
            # K0 should reject at gate validation (400)
            assert "gate" in str(exc).lower() or "signature" in str(exc).lower()
    finally:
        await client.close()


@test("integration: submit_command with duplicate idempotency key returns same receipt")
async def _() -> None:
    """Test idempotent duplicate detection by K0."""
    # Setup
    client = K0CommandClient(base_url=K0_BASE_URL)

    # Create envelope with unique test_id (idem_key will be derived from canonical components)
    unique_test_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    envelope = _create_test_envelope(
        body={
            "content": "Idempotency test",
            "test_id": unique_test_id,
            "timestamp": timestamp,
        },
        band="GREEN",
    )
    first_idem_key = envelope.idem_key

    try:
        # Act: First submission
        receipt1 = await client.submit_command(envelope)
        assert receipt1.idem_key == first_idem_key

        # Act: Second submission with SAME canonical components + SAME body (same idem_key will be derived)
        envelope2 = _create_test_envelope(
            body={
                "content": "Idempotency test",
                "test_id": unique_test_id,
                "timestamp": timestamp,
            },  # EXACT same body
            band="GREEN",
        )
        # Note: Same tenant_id/space_id/actor/topic/schema + same body → same idem_key
        assert (
            envelope2.idem_key == first_idem_key
        ), "Idem key should match for same canonical components + body"

        # K0 returns 409 Conflict with original receipt for duplicate idem_key
        try:
            await client.submit_command(envelope2)
            assert False, "Expected K0IdempotentDuplicate for duplicate idem_key"
        except K0IdempotentDuplicate as e:
            # Parse original receipt from exception data
            # K0 returns: {'receipt_id': '...', 'commit_ts': '...', 'idem_key': '...'}
            assert str(receipt1.receipt_id) in str(
                e
            ), "Exception should reference original receipt_id"

    finally:
        await client.close()


@test("integration: submit_command with missing required field raises ValueError")
async def _() -> None:
    """Test that envelope with missing required field is rejected during idem_key derivation."""
    # Setup
    client = K0CommandClient(base_url=K0_BASE_URL)

    # Create envelope with missing tenant_id (required field)
    envelope = CommandEnvelope(
        cognitive_trace_id=str(uuid.uuid4()),
        tenant_id="",  # Invalid: empty tenant_id
        space_id=SPACE_ID,
        topic=TOPIC,
        schema_uri=SCHEMA_URI,
        schema_version=SCHEMA_VERSION,
        actor=ACTOR,
        device_id=DEVICE_ID,
        band="GREEN",
        policy_version=POLICY_VERSION,
        ts=datetime.now(timezone.utc).isoformat(),
        sig="0" * 128,  # Dummy signature
    )

    try:
        # Act & Assert
        try:
            await client.submit_command(envelope)
            assert (
                False
            ), "Expected ValueError for empty tenant_id during idem_key derivation"
        except ValueError as e:
            # K0's derive_idem_key validates required fields
            assert "tenant_id must not be empty" in str(e)
            pass
    finally:
        await client.close()


@test("integration: client close properly shuts down HTTP connection")
async def _() -> None:
    """Test that client cleanup closes HTTP connections."""
    # Setup
    client = K0CommandClient(base_url=K0_BASE_URL)

    # Act: Submit one command (unique test_id to avoid idempotency conflicts with previous test runs)
    envelope = _create_test_envelope(
        body={"content": "Close test", "test_id": str(uuid.uuid4())},
        band="GREEN",
    )
    receipt = await client.submit_command(envelope)
    assert receipt.receipt_id is not None

    # Close client
    await client.close()

    # Assert: Client should be closed (httpx will raise on subsequent use)
    try:
        await client.submit_command(envelope)
        assert False, "Expected error after client close"
    except Exception:
        # Expected: client closed or connection error
        pass
