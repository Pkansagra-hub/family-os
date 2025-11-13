"""Integration test for concurrent idempotency TOCTOU race fix (ADR-K002)."""

from __future__ import annotations

import concurrent.futures
import gc
import sqlite3
import threading
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from fastapi.testclient import TestClient
from nacl.signing import SigningKey  # type: ignore[import]
from ward import test  # type: ignore[attr-defined]

from k0.automation.migrate import apply_migrations
from k0.gate.schema_registry import SchemaRecord, SchemaRegistry
from k0.idem import derive_idem_key
from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.kernel.dependencies import database_session
from k0.security import canonical_envelope
from k0.security.crypto import encode_base64url
from k0.storage.provisioning import DeviceKey, ProvisionedDevice, ProvisioningLedger

BASE_ENVELOPE: dict[str, Any] = {
    "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
    "tenant_id": "tenant-alpha",
    "space_id": "space-omega",
    "topic": "memory.snapshot.commit",
    "schema_uri": "https://contracts.family-ai.dev/schemas/memory.snapshot.json",
    "schema_version": "1.0.0",
    "actor": "device-123",
    "device_id": "device-123",
    "band": "GREEN",
    "policy_version": "2025-09-01",
    "ts": "2025-09-28T12:00:00Z",
    "sig": "placeholder-signature",
    "payload_sha256": None,
    # V1 required fields (ADR-K001)
    "sig_alg": "ED25519",
    "sig_kid": "did:device:device-123#1",
    "envelope_sha256": "0" * 64,  # Will be computed by gate
}

SIGNING_KEY = SigningKey(bytes(range(32)))
VERIFY_KEY_B64 = encode_base64url(SIGNING_KEY.verify_key.encode())
SCHEMA_SHA = sha256(
    f"{BASE_ENVELOPE['schema_uri']}@{BASE_ENVELOPE['schema_version']}".encode("utf-8")
).hexdigest()


def cleanup_sqlite_artifacts(db_path: Path) -> None:
    """Best-effort cleanup for SQLite database files on Windows."""

    artifacts_suffixes = ("", "-wal", "-shm")
    remaining: list[Path] = []

    for _ in range(10):
        if db_path.exists():
            try:
                with sqlite3.connect(str(db_path), timeout=0) as connection:
                    connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    connection.execute("PRAGMA journal_mode=DELETE;")
            except sqlite3.OperationalError:
                pass

        gc.collect()

        remaining.clear()
        for suffix in artifacts_suffixes:
            artifact = db_path.with_name(f"{db_path.name}{suffix}")
            if not artifact.exists():
                continue
            try:
                artifact.unlink()
            except PermissionError:
                remaining.append(artifact)

        if not remaining:
            return

    # Residual locks are tolerated; TemporaryDirectory cleanup ignores errors.
    return


@test("100 concurrent requests with same idem_key result in exactly 1 commit (TOCTOU fix)")
def _() -> None:
    """
    Verify ADR-K002 fix for TOCTOU race condition:
    - 100 threads submit same envelope concurrently
    - Exactly 1 commit to WAL (first request succeeds)
    - 99 requests receive 409 CONFLICT with same receipt_id
    - No duplicate receipts in st_receipts
    - No duplicate entries in idem_ledger
    
    This test would FAIL before ADR-K002 fix (multiple commits).
    After fix: SQLite BEGIN IMMEDIATE ensures atomic CHECK+USE.
    """
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "kernel.db"
        apply_migrations(db_path)

        primary_connection = sqlite3.connect(str(db_path), check_same_thread=False)
        primary_connection.row_factory = sqlite3.Row  # type: ignore[assignment]

        # Provision device and schema
        provisioning = ProvisioningLedger()
        device = ProvisionedDevice(
            device_id=str(BASE_ENVELOPE["device_id"]),
            tenant_id=str(BASE_ENVELOPE["tenant_id"]),
            space_id=str(BASE_ENVELOPE["space_id"]),
            mls_group_id="mls-group-id",
            provisioned_ts="2025-09-28T12:00:00Z",
        )
        device_key = DeviceKey(
            device_id=str(BASE_ENVELOPE["device_id"]),
            key_version="1",
            verify_key=VERIFY_KEY_B64,
            key_state="ACTIVE",
            registered_ts="2025-09-28T12:00:00Z",
            activated_ts="2025-09-28T12:00:00Z",
        )
        provisioning.register(device, connection=primary_connection)
        provisioning.add_key(device_key, connection=primary_connection)
        primary_connection.commit()

        registry = SchemaRegistry()
        registry.upsert(
            SchemaRecord(
                uri=str(BASE_ENVELOPE["schema_uri"]),
                version=str(BASE_ENVELOPE["schema_version"]),
                sha256=SCHEMA_SHA,
                status="ACTIVE",
            ),
            connection=primary_connection,
        )
        primary_connection.commit()

        # Prepare envelope with signature
        envelope = dict(BASE_ENVELOPE)
        if envelope.get("payload_sha256") is None:
            envelope.pop("payload_sha256", None)
        idem_key = derive_idem_key(
            envelope, payload_hash=envelope.get("payload_sha256")
        )
        envelope["idem_key"] = idem_key
        message = canonical_envelope(envelope)
        signature = SIGNING_KEY.sign(message).signature
        envelope["sig"] = encode_base64url(signature)

        settings = KernelSettings.load(overrides={"database": {"path": str(db_path)}})
        app = create_app(settings=settings)

        def _connection_override() -> Iterator[sqlite3.Connection]:
            try:
                yield primary_connection
            finally:
                pass

        app.dependency_overrides[database_session] = _connection_override

        # Concurrent submission function
        results: list[dict[str, Any]] = []
        results_lock = threading.Lock()

        def submit_envelope(thread_id: int) -> None:
            """Submit envelope via HTTP client (thread-safe TestClient instance)."""
            with TestClient(app) as client:
                response = client.post("/k0/command.submit", json=envelope)
                result = {
                    "thread_id": thread_id,
                    "status": response.status_code,
                    "body": response.json() if response.status_code in (200, 409) else None,
                }
                response.close()
                with results_lock:
                    results.append(result)

        # Launch 100 concurrent requests
        NUM_CONCURRENT = 100
        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_CONCURRENT) as executor:
            futures = [executor.submit(submit_envelope, i) for i in range(NUM_CONCURRENT)]
            concurrent.futures.wait(futures)

        # Analyze results
        success_results = [r for r in results if r["status"] == 200]
        conflict_results = [r for r in results if r["status"] == 409]

        # CRITICAL ASSERTION: Exactly 1 success, 99 conflicts
        assert len(success_results) == 1, (
            f"Expected exactly 1 successful commit, got {len(success_results)}. "
            f"TOCTOU race detected! Multiple commits occurred."
        )
        assert len(conflict_results) == NUM_CONCURRENT - 1, (
            f"Expected {NUM_CONCURRENT - 1} conflicts, got {len(conflict_results)}"
        )

        # Verify all conflicts reference same receipt_id
        success_receipt = success_results[0]["body"]["receipt_id"]
        for conflict in conflict_results:
            assert conflict["body"]["receipt_id"] == success_receipt, (
                "Conflict receipt_id mismatch - indicates multiple commits occurred"
            )
            assert conflict["body"]["idem_key"] == idem_key

        # Verify database integrity
        wal_count = primary_connection.execute(
            "SELECT COUNT(*) as cnt FROM st_wal WHERE idem_key = ?",
            (idem_key,),
        ).fetchone()["cnt"]
        assert wal_count == 1, f"Expected 1 WAL entry, found {wal_count} (duplicate commits!)"

        receipt_count = primary_connection.execute(
            "SELECT COUNT(*) as cnt FROM st_receipts WHERE idem_key = ?",
            (idem_key,),
        ).fetchone()["cnt"]
        assert receipt_count == 1, f"Expected 1 receipt, found {receipt_count}"

        idem_count = primary_connection.execute(
            "SELECT COUNT(*) as cnt FROM idem_ledger WHERE idem_key = ?",
            (idem_key,),
        ).fetchone()["cnt"]
        assert idem_count == 1, f"Expected 1 idem_ledger entry, found {idem_count}"

        # Cleanup
        app.dependency_overrides.pop(database_session, None)
        try:
            primary_connection.rollback()
        except sqlite3.ProgrammingError:
            pass
        primary_connection.close()
        gc.collect()
        cleanup_sqlite_artifacts(db_path)


@test("concurrent requests with different idem_keys all succeed")
def _() -> None:
    """
    Verify that concurrent requests with DIFFERENT idem_keys all succeed.
    This ensures the fix doesn't introduce unnecessary serialization.
    """
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "kernel.db"
        apply_migrations(db_path)

        primary_connection = sqlite3.connect(str(db_path), check_same_thread=False)
        primary_connection.row_factory = sqlite3.Row  # type: ignore[assignment]

        # Provision device and schema
        provisioning = ProvisioningLedger()
        device = ProvisionedDevice(
            device_id=str(BASE_ENVELOPE["device_id"]),
            tenant_id=str(BASE_ENVELOPE["tenant_id"]),
            space_id=str(BASE_ENVELOPE["space_id"]),
            mls_group_id="mls-group-id",
            provisioned_ts="2025-09-28T12:00:00Z",
        )
        device_key = DeviceKey(
            device_id=str(BASE_ENVELOPE["device_id"]),
            key_version="1",
            verify_key=VERIFY_KEY_B64,
            key_state="ACTIVE",
            registered_ts="2025-09-28T12:00:00Z",
            activated_ts="2025-09-28T12:00:00Z",
        )
        provisioning.register(device, connection=primary_connection)
        provisioning.add_key(device_key, connection=primary_connection)
        primary_connection.commit()

        registry = SchemaRegistry()
        registry.upsert(
            SchemaRecord(
                uri=str(BASE_ENVELOPE["schema_uri"]),
                version=str(BASE_ENVELOPE["schema_version"]),
                sha256=SCHEMA_SHA,
                status="ACTIVE",
            ),
            connection=primary_connection,
        )
        primary_connection.commit()

        settings = KernelSettings.load(overrides={"database": {"path": str(db_path)}})
        app = create_app(settings=settings)

        def _connection_override() -> Iterator[sqlite3.Connection]:
            try:
                yield primary_connection
            finally:
                pass

        app.dependency_overrides[database_session] = _connection_override

        # Concurrent submission with unique envelopes
        results: list[dict[str, Any]] = []
        results_lock = threading.Lock()

        def submit_unique_envelope(thread_id: int) -> None:
            """Submit unique envelope (different ts = different idem_key)."""
            envelope = dict(BASE_ENVELOPE)
            envelope["ts"] = f"2025-09-28T12:{thread_id:02d}:00Z"  # Unique timestamp
            envelope["cognitive_trace_id"] = f"{thread_id:08d}-2222-3333-4444-555555555555"
            
            if envelope.get("payload_sha256") is None:
                envelope.pop("payload_sha256", None)
            idem_key = derive_idem_key(
                envelope, payload_hash=envelope.get("payload_sha256")
            )
            envelope["idem_key"] = idem_key
            message = canonical_envelope(envelope)
            signature = SIGNING_KEY.sign(message).signature
            envelope["sig"] = encode_base64url(signature)

            with TestClient(app) as client:
                response = client.post("/k0/command.submit", json=envelope)
                result = {
                    "thread_id": thread_id,
                    "status": response.status_code,
                    "idem_key": idem_key,
                }
                response.close()
                with results_lock:
                    results.append(result)

        # Launch 50 concurrent requests with unique idem_keys
        NUM_CONCURRENT = 50
        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_CONCURRENT) as executor:
            futures = [executor.submit(submit_unique_envelope, i) for i in range(NUM_CONCURRENT)]
            concurrent.futures.wait(futures)

        # All should succeed
        success_count = sum(1 for r in results if r["status"] == 200)
        assert success_count == NUM_CONCURRENT, (
            f"Expected all {NUM_CONCURRENT} unique requests to succeed, "
            f"got {success_count}. Transaction serialization too aggressive."
        )

        # Verify WAL contains all entries
        wal_count = primary_connection.execute(
            "SELECT COUNT(*) as cnt FROM st_wal"
        ).fetchone()["cnt"]
        assert wal_count == NUM_CONCURRENT, (
            f"Expected {NUM_CONCURRENT} WAL entries, found {wal_count}"
        )

        # Cleanup
        app.dependency_overrides.pop(database_session, None)
        try:
            primary_connection.rollback()
        except sqlite3.ProgrammingError:
            pass
        primary_connection.close()
        gc.collect()
        cleanup_sqlite_artifacts(db_path)
