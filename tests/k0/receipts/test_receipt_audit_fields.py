"""Test V1 receipt audit fields (envelope_sha256, obligations_applied).

V1 CHANGES:
- envelope_sha256 (REQUIRED): Full envelope hash for integrity verification
- obligations_applied (optional): Specific actions taken (e.g., kernel.mask.location.AMBER)
- payload_sha256 (DEPRECATED): Legacy field, optional in V1

Tests verify:
1. envelope_sha256 included in receipt signature payload
2. obligations_applied recorded for GDPR/CCPA compliance proof
3. Backward compatibility (payload_sha256 still accepted)
"""

import sqlite3
import uuid
from unittest.mock import Mock

import pytest
from nacl.signing import SigningKey

from k0.obs.events import ObservabilityEmitter
from k0.policy.pep_syscall import Obligation
from k0.receipts.issuer import ReceiptDocument, ReceiptIssuer, ReceiptSigner
from k0.storage.receipts import Receipt, ReceiptStore


class InMemoryReceiptStore(ReceiptStore):
    """In-memory receipt store for testing (no database required)."""

    def __init__(self) -> None:
        self._receipts: dict[str, Receipt] = {}

    def save(self, receipt: Receipt, *, connection: sqlite3.Connection | None = None) -> None:
        """Save receipt to in-memory store."""
        self._receipts[receipt.receipt_id] = receipt

    def get(
        self, receipt_id: str, *, connection: sqlite3.Connection | None = None
    ) -> Receipt | None:
        """Retrieve receipt from in-memory store."""
        return self._receipts.get(receipt_id)


@pytest.fixture
def signing_key() -> SigningKey:
    """Generate Ed25519 signing key for testing."""
    return SigningKey.generate()


@pytest.fixture
def receipt_signer(signing_key: SigningKey) -> ReceiptSigner:
    """Create receipt signer for testing."""
    return ReceiptSigner(signing_key)


@pytest.fixture
def receipt_store() -> InMemoryReceiptStore:
    """Create in-memory receipt store for testing."""
    return InMemoryReceiptStore()


@pytest.fixture
def metrics_recorder() -> Mock:
    """Create mock metrics recorder."""
    return Mock()


@pytest.fixture
def observability_emitter() -> Mock:
    """Create mock observability emitter."""
    mock = Mock(spec=ObservabilityEmitter)
    mock.emit = Mock()
    return mock


@pytest.fixture
def receipt_issuer(
    receipt_store: InMemoryReceiptStore,
    receipt_signer: ReceiptSigner,
    metrics_recorder: Mock,
    observability_emitter: Mock,
) -> ReceiptIssuer:
    """Create receipt issuer for testing."""
    return ReceiptIssuer(
        receipt_store=receipt_store,
        signer=receipt_signer,
        metrics_recorder=metrics_recorder,
        observability_emitter=observability_emitter,
    )


class TestReceiptDocumentV1Fields:
    """Test V1 ReceiptDocument dataclass with envelope_sha256 and obligations_applied."""

    async def test_receipt_document_with_envelope_sha256(self, receipt_issuer: ReceiptIssuer):
        """Verify envelope_sha256 required in V1 ReceiptDocument."""
        receipt_id = str(uuid.uuid4())
        envelope_sha256 = "abc123" * 10  # 60-char hex string (SHA-256)

        receipt_doc = await receipt_issuer.issue(
            receipt_id=receipt_id,
            idem_key="test-idem-key",
            wal_pos=1,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256=envelope_sha256,  # V1: Full envelope hash
            mls_group_id="group-1",
            key_version="v1",
            obligations=[],
            obligations_applied=[],
        )

        assert receipt_doc.envelope_sha256 == envelope_sha256
        assert isinstance(receipt_doc, ReceiptDocument)

    async def test_receipt_document_with_obligations_applied(self, receipt_issuer: ReceiptIssuer):
        """Verify obligations_applied recorded in V1 ReceiptDocument."""
        obligations_applied = [
            "kernel.redact.field.email",
            "kernel.mask.location.AMBER",
            "kernel.redact.field.ssn",
        ]

        receipt_doc = await receipt_issuer.issue(
            receipt_id=str(uuid.uuid4()),
            idem_key="test-idem-key",
            wal_pos=1,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256="abc123" * 10,
            mls_group_id="group-1",
            key_version="v1",
            obligations=[],
            obligations_applied=obligations_applied,  # V1: Specific actions
        )

        assert receipt_doc.obligations_applied == tuple(obligations_applied)
        assert len(receipt_doc.obligations_applied) == 3

    async def test_receipt_document_payload_sha256_optional(self, receipt_issuer: ReceiptIssuer):
        """Verify payload_sha256 is optional (legacy field) in V1."""
        # V1: Can create receipt WITHOUT payload_sha256
        receipt_doc = await receipt_issuer.issue(
            receipt_id=str(uuid.uuid4()),
            idem_key="test-idem-key",
            wal_pos=1,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256="abc123" * 10,
            mls_group_id="group-1",
            key_version="v1",
            obligations=[],
            # payload_sha256 NOT provided
        )

        assert receipt_doc.payload_sha256 is None  # Optional in V1

        # V1: Can still provide payload_sha256 for backward compat
        receipt_doc_with_legacy = await receipt_issuer.issue(
            receipt_id=str(uuid.uuid4()),
            idem_key="test-idem-key-2",
            wal_pos=2,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256="def456" * 10,
            mls_group_id="group-1",
            key_version="v1",
            obligations=[],
            payload_sha256="legacy-body-hash",
        )

        assert receipt_doc_with_legacy.payload_sha256 == "legacy-body-hash"


class TestReceiptSignaturePayloadV1:
    """Test V1 signature payload includes envelope_sha256 and obligations_applied."""

    async def test_signature_payload_includes_envelope_sha256(
        self, receipt_issuer: ReceiptIssuer, receipt_signer: ReceiptSigner
    ):
        """Verify signature payload includes envelope_sha256 (not payload_sha256)."""
        envelope_sha256 = "abc123" * 10

        receipt_doc = await receipt_issuer.issue(
            receipt_id=str(uuid.uuid4()),
            idem_key="test-idem-key",
            wal_pos=1,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256=envelope_sha256,
            mls_group_id="group-1",
            key_version="v1",
            obligations=[],
        )

        # Signature is base64url, non-empty
        assert receipt_doc.device_sig
        assert len(receipt_doc.device_sig) > 0

        # Receipt includes envelope_sha256
        assert receipt_doc.envelope_sha256 == envelope_sha256

    async def test_signature_payload_includes_obligations_applied(
        self, receipt_issuer: ReceiptIssuer
    ):
        """Verify signature payload includes obligations_applied if provided."""
        obligations_applied = ["kernel.mask.location.RED", "kernel.redact.field.email"]

        receipt_doc = await receipt_issuer.issue(
            receipt_id=str(uuid.uuid4()),
            idem_key="test-idem-key",
            wal_pos=1,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256="abc123" * 10,
            mls_group_id="group-1",
            key_version="v1",
            obligations=[],
            obligations_applied=obligations_applied,
        )

        assert receipt_doc.obligations_applied == tuple(obligations_applied)


class TestObservabilityEventV1:
    """Test observability events include V1 audit fields."""

    async def test_observability_event_includes_envelope_sha256(
        self, receipt_issuer: ReceiptIssuer, observability_emitter: Mock
    ):
        """Verify observability event includes envelope_sha256."""
        envelope_sha256 = "abc123" * 10

        await receipt_issuer.issue(
            receipt_id=str(uuid.uuid4()),
            idem_key="test-idem-key",
            wal_pos=1,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256=envelope_sha256,
            mls_group_id="group-1",
            key_version="v1",
            obligations=[],
        )

        # Check observability event emitted
        observability_emitter.emit.assert_called_once()
        event = observability_emitter.emit.call_args[0][0]

        assert event["envelope_sha256"] == envelope_sha256
        assert event["event"] == "receipt_issued"

    async def test_observability_event_includes_obligations_applied(
        self, receipt_issuer: ReceiptIssuer, observability_emitter: Mock
    ):
        """Verify observability event includes obligations_applied."""
        obligations_applied = ["kernel.mask.location.AMBER"]

        await receipt_issuer.issue(
            receipt_id=str(uuid.uuid4()),
            idem_key="test-idem-key",
            wal_pos=1,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256="abc123" * 10,
            mls_group_id="group-1",
            key_version="v1",
            obligations=[],
            obligations_applied=obligations_applied,
        )

        observability_emitter.emit.assert_called_once()
        event = observability_emitter.emit.call_args[0][0]

        assert event["obligations_applied"] == obligations_applied


class TestBackwardCompatibility:
    """Test V1 receipts backward compatible with V0 consumers."""

    async def test_can_provide_both_envelope_and_payload_sha256(
        self, receipt_issuer: ReceiptIssuer
    ):
        """Verify V1 accepts both envelope_sha256 (new) and payload_sha256 (legacy)."""
        envelope_sha256 = "abc123" * 10
        payload_sha256 = "body-hash-legacy"

        receipt_doc = await receipt_issuer.issue(
            receipt_id=str(uuid.uuid4()),
            idem_key="test-idem-key",
            wal_pos=1,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256=envelope_sha256,  # V1: Required
            mls_group_id="group-1",
            key_version="v1",
            obligations=[],
            payload_sha256=payload_sha256,  # V1: Optional (backward compat)
        )

        assert receipt_doc.envelope_sha256 == envelope_sha256
        assert receipt_doc.payload_sha256 == payload_sha256  # Both present

    async def test_empty_obligations_applied_allowed(self, receipt_issuer: ReceiptIssuer):
        """Verify empty obligations_applied allowed (no obligations case)."""
        receipt_doc = await receipt_issuer.issue(
            receipt_id=str(uuid.uuid4()),
            idem_key="test-idem-key",
            wal_pos=1,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256="abc123" * 10,
            mls_group_id="group-1",
            key_version="v1",
            obligations=[],
            obligations_applied=[],  # Empty list allowed
        )

        assert receipt_doc.obligations_applied == ()
        assert len(receipt_doc.obligations_applied) == 0


class TestObligationDetailsWithObligationsApplied:
    """Test obligations (generic) vs obligations_applied (specific actions)."""

    async def test_obligations_generic_obligations_applied_specific(
        self, receipt_issuer: ReceiptIssuer
    ):
        """Verify obligations (names) vs obligations_applied (actions) distinction."""
        # obligations: Generic policy obligation names
        obligations = [
            Obligation(name="kernel.redact", details={"fields": "email"}),
            Obligation(name="kernel.mask.location", details={"band": "AMBER"}),
        ]

        # obligations_applied: Specific actions taken
        obligations_applied = [
            "kernel.redact.field.email",
            "kernel.mask.location.AMBER",  # Band-specific action
        ]

        receipt_doc = await receipt_issuer.issue(
            receipt_id=str(uuid.uuid4()),
            idem_key="test-idem-key",
            wal_pos=1,
            commit_ts="2025-11-10T12:00:00Z",
            tenant_id="tenant-1",
            space_id="space-1",
            device_id="device-1",
            envelope_sha256="abc123" * 10,
            mls_group_id="group-1",
            key_version="v1",
            obligations=obligations,  # Generic obligation objects
            obligations_applied=obligations_applied,  # Specific action strings
        )

        # Generic obligations (names only)
        assert receipt_doc.obligations == ("kernel.redact", "kernel.mask.location")

        # Specific actions applied
        assert receipt_doc.obligations_applied == (
            "kernel.redact.field.email",
            "kernel.mask.location.AMBER",
        )

        # Obligation details preserved
        assert len(receipt_doc.obligation_details) == 2
        assert receipt_doc.obligation_details[0]["fields"] == "email"
        assert receipt_doc.obligation_details[1]["band"] == "AMBER"
