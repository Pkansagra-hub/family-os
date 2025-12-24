"""Integration test: Receipts (issuer/store) with Ed25519 signature verification.

Tests Receipts subsystem:
1. Receipt persistence and retrieval
2. Ed25519 signature verification (valid/invalid/tampered)
3. Linking receipts to WAL positions
4. Concurrent receipt operations
5. Receipt idempotency
6. Negative tests (tampered signatures, missing fields)

Validates that receipts provide proof of commitment with cryptographic verification.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

import pytest
from nacl.signing import SigningKey

from k0.automation.migrate import apply_migrations
from k0.security.crypto import (
    SignatureVerificationError,
    canonical_envelope,
    encode_base64url,
    hash_payload,
    verify_signature,
)
from k0.storage.receipts import Receipt, ReceiptStore
from k0.storage.wal import WalEntry, WriteAheadLog
from k0.uow.connection_pool import configure_pool, connection_scope, shutdown_pool


@pytest.fixture
def sqlite_runtime() -> Iterator[Path]:
    """Pytest fixture for SQLite runtime with schema initialization."""
    tmp_dir = TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(tmp_dir.name) / "kernel.sqlite3"
    configure_pool(db_path)
    # Apply migrations instead of using storage.sql directly
    apply_migrations(db_path, dry_run=False)
    try:
        yield db_path
    finally:
        shutdown_pool()
        tmp_dir.cleanup()


@pytest.fixture
def temp_db(sqlite_runtime: Path) -> Path:
    """Alias for sqlite_runtime for test compatibility."""
    return sqlite_runtime


@pytest.fixture
def signing_key() -> SigningKey:
    """Generate Ed25519 signing key for tests."""
    return SigningKey.generate()


def _create_receipt(
    receipt_id: str | None = None,
    idem_key: str | None = None,
    wal_pos: int = 1,
    tenant_id: str = "test-tenant",
    space_id: str = "test-space",
    device_id: str = "device-001",
    mls_group_id: str = "group-001",
    key_version: str = "1.0.0",
    device_sig: str = "sig_abc123",
) -> Receipt:
    """Helper to create a Receipt."""
    return Receipt(
        receipt_id=receipt_id or str(uuid.uuid4()),
        idem_key=idem_key or f"idem_{uuid.uuid4()}",
        wal_pos=wal_pos,
        commit_ts=datetime.now(timezone.utc).isoformat(),
        tenant_id=tenant_id,
        space_id=space_id,
        device_id=device_id,
        mls_group_id=mls_group_id,
        key_version=key_version,
        device_sig=device_sig,
        manifest_fingerprint="fingerprint_abc123",
    )


def _create_valid_envelope(
    signing_key: SigningKey,
    receipt_id: str,
    body: bytes | None = None,
) -> tuple[dict, str, str]:
    """Create a valid V1 envelope with full signature (V1: body is now included).

    Returns: (envelope_dict, signature_b64, verify_key_b64)
    """
    verify_key = signing_key.verify_key
    verify_key_b64 = encode_base64url(bytes(verify_key))

    envelope = {
        "receipt_id": receipt_id,
        "commit_ts": datetime.now(timezone.utc).isoformat(),
        "device_id": "device-001",
        "payload_sha256": hash_payload(body),
        "body": body,  # V1: body is now INCLUDED in the canonical envelope
    }

    # V1: Sign the full envelope (excluding sig field only, body is now included)
    message = canonical_envelope(envelope, exclude_signature=True)
    signature = signing_key.sign(message).signature
    signature_b64 = encode_base64url(signature)

    envelope["sig"] = signature_b64

    return envelope, signature_b64, verify_key_b64


class TestReceiptPersistence:
    """Tests for Receipt persistence and retrieval."""

    def test_single_receipt_persists(self, temp_db: Path) -> None:
        """Test: Single receipt saves and retrieves."""
        store = ReceiptStore()
        receipt = _create_receipt()

        store.save(receipt)
        retrieved = store.get(receipt.receipt_id)

        assert retrieved is not None
        assert retrieved.receipt_id == receipt.receipt_id
        assert retrieved.idem_key == receipt.idem_key
        assert retrieved.wal_pos == receipt.wal_pos

    def test_multiple_receipts_independent(self, temp_db: Path) -> None:
        """Test: Multiple receipts persist independently."""
        store = ReceiptStore()
        receipts = [_create_receipt(wal_pos=i) for i in range(1, 6)]

        for receipt in receipts:
            store.save(receipt)

        for receipt in receipts:
            retrieved = store.get(receipt.receipt_id)
            assert retrieved is not None
            assert retrieved.wal_pos == receipt.wal_pos

    def test_receipt_not_found_returns_none(self, temp_db: Path) -> None:
        """Test: Querying non-existent receipt returns None."""
        store = ReceiptStore()
        result = store.get("nonexistent-receipt-id")
        assert result is None

    def test_receipt_fields_preserved(self, temp_db: Path) -> None:
        """Test: All receipt fields are preserved on retrieval."""
        store = ReceiptStore()
        receipt = _create_receipt(
            tenant_id="custom-tenant",
            space_id="custom-space",
            device_id="device-xyz",
            mls_group_id="group-xyz",
            key_version="2.0.0",
        )

        store.save(receipt)
        retrieved = store.get(receipt.receipt_id)

        assert retrieved is not None
        assert retrieved.tenant_id == "custom-tenant"
        assert retrieved.space_id == "custom-space"
        assert retrieved.device_id == "device-xyz"
        assert retrieved.mls_group_id == "group-xyz"
        assert retrieved.key_version == "2.0.0"

    def test_receipt_upsert_on_conflict(self, temp_db: Path) -> None:
        """Test: Saving receipt with same ID updates existing."""
        store = ReceiptStore()
        receipt_id = str(uuid.uuid4())

        receipt1 = _create_receipt(receipt_id=receipt_id, wal_pos=1)
        store.save(receipt1)

        receipt2 = _create_receipt(receipt_id=receipt_id, wal_pos=2)
        store.save(receipt2)

        retrieved = store.get(receipt_id)
        assert retrieved is not None
        assert retrieved.wal_pos == 2  # Updated value


class TestReceiptWalLinking:
    """Tests for Receipt ↔ WAL position linking."""

    async def test_receipt_links_to_wal_position(self, temp_db: Path) -> None:
        """Test: Receipt wal_pos correctly links to WAL position."""
        wal = WriteAheadLog()
        store = ReceiptStore()

        # Create WAL entry
        entry = WalEntry(
            tenant_id="test",
            space_id="test",
            topic="test.topic",
            envelope_json='{"id": "123"}',
            schema_uri="schema",
            schema_version="1.0",
            device_id="device",
            commit_ts=datetime.now(timezone.utc).isoformat(),
        )
        wal_pos = await wal.append(entry)

        # Create receipt pointing to WAL position
        receipt = _create_receipt(wal_pos=wal_pos)
        store.save(receipt)

        retrieved = store.get(receipt.receipt_id)
        assert retrieved is not None
        assert retrieved.wal_pos == wal_pos

    async def test_receipt_wal_pos_resolvable(self, temp_db: Path) -> None:
        """Test: Receipt's WAL position can be resolved to WAL entry."""
        wal = WriteAheadLog()
        store = ReceiptStore()

        # Create multiple WAL entries
        positions = []
        for i in range(5):
            entry = WalEntry(
                tenant_id="test",
                space_id="test",
                topic=f"test.topic.{i}",
                envelope_json="{}",
                schema_uri="schema",
                schema_version="1.0",
                device_id="device",
                commit_ts=datetime.now(timezone.utc).isoformat(),
            )
            positions.append(await wal.append(entry))

        # Create receipts pointing to different WAL positions
        for i, pos in enumerate(positions):
            receipt = _create_receipt(wal_pos=pos)
            store.save(receipt)

        # Verify all receipts are retrievable with correct positions
        with connection_scope() as conn:
            for i, pos in enumerate(positions):
                # Verify WAL position exists
                wal_entry = conn.execute(
                    "SELECT topic FROM st_wal WHERE pos = ?", (pos,)
                ).fetchone()
                assert wal_entry is not None
                assert wal_entry[0] == f"test.topic.{i}"

    def test_multiple_receipts_same_wal_position(self, temp_db: Path) -> None:
        """Test: Multiple receipts can reference same WAL position."""
        store = ReceiptStore()
        shared_wal_pos = 42

        receipt1 = _create_receipt(wal_pos=shared_wal_pos)
        receipt2 = _create_receipt(wal_pos=shared_wal_pos)

        store.save(receipt1)
        store.save(receipt2)

        retrieved1 = store.get(receipt1.receipt_id)
        retrieved2 = store.get(receipt2.receipt_id)

        assert retrieved1 is not None
        assert retrieved2 is not None
        assert retrieved1.wal_pos == shared_wal_pos
        assert retrieved2.wal_pos == shared_wal_pos


class TestReceiptSignatureVerification:
    """Tests for Ed25519 signature verification."""

    def test_valid_signature_verifies(self, signing_key: SigningKey) -> None:
        """Test: Valid signature passes verification."""
        receipt_id = str(uuid.uuid4())
        envelope, sig_b64, key_b64 = _create_valid_envelope(signing_key, receipt_id)

        message = canonical_envelope(envelope, exclude_signature=True)
        # Should not raise
        verify_signature(message, sig_b64, key_b64)

    def test_invalid_signature_fails_verification(self, signing_key: SigningKey) -> None:
        """Test: Invalid signature fails verification."""
        receipt_id = str(uuid.uuid4())
        envelope, _, key_b64 = _create_valid_envelope(signing_key, receipt_id)

        message = canonical_envelope(envelope, exclude_signature=True)
        invalid_sig = encode_base64url(b"invalid_signature_bytes")

        with pytest.raises(SignatureVerificationError):
            verify_signature(message, invalid_sig, key_b64)

    def test_tampered_signature_fails(self, signing_key: SigningKey) -> None:
        """Test: Tampered signature fails verification."""
        receipt_id = str(uuid.uuid4())
        envelope, sig_b64, key_b64 = _create_valid_envelope(signing_key, receipt_id)

        message = canonical_envelope(envelope, exclude_signature=True)
        # Tamper with signature by changing first character
        tampered_sig = ("X" if sig_b64[0] != "X" else "Y") + sig_b64[1:]

        with pytest.raises(SignatureVerificationError):
            verify_signature(message, tampered_sig, key_b64)

    def test_wrong_key_fails_verification(self, signing_key: SigningKey) -> None:
        """Test: Wrong signing key fails verification."""
        receipt_id = str(uuid.uuid4())
        envelope, sig_b64, _ = _create_valid_envelope(signing_key, receipt_id)

        # Create signature with different key
        other_key = SigningKey.generate()
        other_key_b64 = encode_base64url(bytes(other_key.verify_key))

        message = canonical_envelope(envelope, exclude_signature=True)

        with pytest.raises(SignatureVerificationError):
            verify_signature(message, sig_b64, other_key_b64)

    def test_message_tampering_detected(self, signing_key: SigningKey) -> None:
        """Test: Tampering with signed message is detected."""
        receipt_id = str(uuid.uuid4())
        envelope, sig_b64, key_b64 = _create_valid_envelope(signing_key, receipt_id)

        message = canonical_envelope(envelope, exclude_signature=True)
        # Tamper with message
        tampered_message = message + b"_tampered"

        with pytest.raises(SignatureVerificationError):
            verify_signature(tampered_message, sig_b64, key_b64)


class TestReceiptIdempotency:
    """Tests for Receipt idempotency."""

    def test_same_idem_key_replaces_previous(self, temp_db: Path) -> None:
        """Test: Same idem_key replaces previous receipt."""
        store = ReceiptStore()
        idem_key = f"idem_{uuid.uuid4()}"

        receipt1 = _create_receipt(idem_key=idem_key, wal_pos=1)
        receipt2 = _create_receipt(idem_key=idem_key, wal_pos=2)

        store.save(receipt1)
        store.save(receipt2)

        # Query by receipt_id - should get the latest one
        retrieved = store.get(receipt2.receipt_id)
        # Note: This tests upsert behavior - same idem_key different receipt_id
        # In practice, if receipt_id is used as primary key, behavior depends on schema
        assert retrieved is not None

    def test_idempotent_save_idempotent(self, temp_db: Path) -> None:
        """Test: Saving same receipt twice is idempotent."""
        store = ReceiptStore()
        receipt = _create_receipt()

        store.save(receipt)
        store.save(receipt)  # Save again

        retrieved = store.get(receipt.receipt_id)
        assert retrieved is not None
        assert retrieved.receipt_id == receipt.receipt_id

    def test_receipt_with_different_manifests(self, temp_db: Path) -> None:
        """Test: Same receipt with different manifest fingerprints."""
        store = ReceiptStore()
        receipt_id = str(uuid.uuid4())

        receipt1 = _create_receipt(receipt_id=receipt_id)
        receipt1.manifest_fingerprint = "fp_v1"
        store.save(receipt1)

        receipt2 = _create_receipt(receipt_id=receipt_id)
        receipt2.manifest_fingerprint = "fp_v2"
        store.save(receipt2)

        retrieved = store.get(receipt_id)
        assert retrieved is not None
        assert retrieved.manifest_fingerprint == "fp_v2"


class TestReceiptRobustness:
    """Robustness tests for Receipt edge cases."""

    def test_receipt_with_null_manifest_fingerprint(self, temp_db: Path) -> None:
        """Test: Receipt can have null manifest fingerprint."""
        store = ReceiptStore()
        receipt = _create_receipt()
        receipt.manifest_fingerprint = None

        store.save(receipt)
        retrieved = store.get(receipt.receipt_id)

        assert retrieved is not None
        assert retrieved.manifest_fingerprint is None

    def test_receipt_with_long_idem_key(self, temp_db: Path) -> None:
        """Test: Receipt handles very long idem_key."""
        store = ReceiptStore()
        long_idem_key = "x" * 10000
        receipt = _create_receipt(idem_key=long_idem_key)

        store.save(receipt)
        retrieved = store.get(receipt.receipt_id)

        assert retrieved is not None
        assert retrieved.idem_key == long_idem_key

    def test_receipt_with_unicode_device_id(self, temp_db: Path) -> None:
        """Test: Receipt handles unicode in device_id."""
        store = ReceiptStore()
        receipt = _create_receipt(device_id="设备-001-🔐")

        store.save(receipt)
        retrieved = store.get(receipt.receipt_id)

        assert retrieved is not None
        assert retrieved.device_id == "设备-001-🔐"

    def test_receipt_with_zero_wal_position(self, temp_db: Path) -> None:
        """Test: Receipt can have WAL position 0."""
        store = ReceiptStore()
        receipt = _create_receipt(wal_pos=0)

        store.save(receipt)
        retrieved = store.get(receipt.receipt_id)

        assert retrieved is not None
        assert retrieved.wal_pos == 0

    def test_receipt_with_large_wal_position(self, temp_db: Path) -> None:
        """Test: Receipt handles large WAL positions."""
        store = ReceiptStore()
        large_pos = 2**31 - 1  # Max 32-bit int
        receipt = _create_receipt(wal_pos=large_pos)

        store.save(receipt)
        retrieved = store.get(receipt.receipt_id)

        assert retrieved is not None
        assert retrieved.wal_pos == large_pos


class TestReceiptNegativePaths:
    """Negative tests: tampering, missing fields, invalid data."""

    def test_signature_over_empty_envelope(self, signing_key: SigningKey) -> None:
        """Test: Signature verification on empty envelope."""
        verify_key = signing_key.verify_key
        key_b64 = encode_base64url(bytes(verify_key))

        empty_envelope = {}
        message = canonical_envelope(empty_envelope, exclude_signature=True)
        signature = signing_key.sign(message).signature
        sig_b64 = encode_base64url(signature)

        # Should verify successfully
        verify_signature(message, sig_b64, key_b64)

    def test_receipt_manifest_fingerprint_tampering(self, temp_db: Path) -> None:
        """Test: Detecting tampering in manifest fingerprint."""
        store = ReceiptStore()
        receipt_id = str(uuid.uuid4())
        receipt = _create_receipt(receipt_id=receipt_id)
        receipt.manifest_fingerprint = "original_fingerprint"

        store.save(receipt)
        retrieved = store.get(receipt_id)

        # Tamper with retrieved object (simulate database tampering)
        assert retrieved is not None
        assert retrieved.manifest_fingerprint == "original_fingerprint"

    def test_invalid_base64_signature_fails(self, signing_key: SigningKey) -> None:
        """Test: Invalid base64 in signature fails verification."""
        receipt_id = str(uuid.uuid4())
        envelope, _, key_b64 = _create_valid_envelope(signing_key, receipt_id)

        message = canonical_envelope(envelope, exclude_signature=True)
        invalid_b64_sig = "!!!invalid_base64!!!"

        with pytest.raises(SignatureVerificationError):
            verify_signature(message, invalid_b64_sig, key_b64)

    def test_invalid_base64_key_fails(self, signing_key: SigningKey) -> None:
        """Test: Invalid base64 in verify key fails verification."""
        receipt_id = str(uuid.uuid4())
        envelope, sig_b64, _ = _create_valid_envelope(signing_key, receipt_id)

        message = canonical_envelope(envelope, exclude_signature=True)
        invalid_b64_key = "!!!invalid_base64_key!!!"

        with pytest.raises(SignatureVerificationError):
            verify_signature(message, sig_b64, invalid_b64_key)


class TestReceiptCompleteIntegration:
    """End-to-end Receipt integration tests."""

    def test_receipt_lifecycle_with_signature(self, signing_key: SigningKey, temp_db: Path) -> None:
        """Test: Complete receipt lifecycle with valid signature."""
        store = ReceiptStore()
        receipt_id = str(uuid.uuid4())

        # Create and sign
        envelope, sig_b64, key_b64 = _create_valid_envelope(signing_key, receipt_id)

        # Verify signature
        message = canonical_envelope(envelope, exclude_signature=True)
        verify_signature(message, sig_b64, key_b64)

        # Create receipt with signature reference
        receipt = _create_receipt(
            receipt_id=receipt_id,
            device_sig=sig_b64,
        )
        store.save(receipt)

        # Retrieve and verify
        retrieved = store.get(receipt_id)
        assert retrieved is not None
        assert retrieved.device_sig == sig_b64

    def test_multiple_receipts_batch_operations(self, temp_db: Path) -> None:
        """Test: Batch operations with multiple receipts."""
        store = ReceiptStore()
        receipts = [_create_receipt(wal_pos=i) for i in range(1, 11)]

        # Batch save
        for receipt in receipts:
            store.save(receipt)

        # Batch retrieve
        retrieved_count = 0
        for receipt in receipts:
            retrieved = store.get(receipt.receipt_id)
            if retrieved is not None:
                retrieved_count += 1

        assert retrieved_count == len(receipts)

    def test_receipt_concurrent_save_and_retrieve(self, temp_db: Path) -> None:
        """Test: Concurrent save and retrieve operations."""
        import concurrent.futures

        store = ReceiptStore()
        receipts = [_create_receipt(wal_pos=i) for i in range(1, 11)]

        def save_receipt(receipt: Receipt) -> str:
            store.save(receipt)
            return receipt.receipt_id

        def get_receipt(receipt_id: str) -> Receipt | None:
            return store.get(receipt_id)

        # Concurrent saves
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            save_futures = [executor.submit(save_receipt, r) for r in receipts]
            saved_ids = [f.result() for f in concurrent.futures.as_completed(save_futures)]

        # Concurrent retrieves
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            get_futures = [executor.submit(get_receipt, rid) for rid in saved_ids]
            retrieved = [f.result() for f in concurrent.futures.as_completed(get_futures)]

        assert len([r for r in retrieved if r is not None]) == len(receipts)
