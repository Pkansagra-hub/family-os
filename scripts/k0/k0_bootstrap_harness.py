from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from nacl.signing import SigningKey  # noqa: E402

SchemaRecord = None
create_app = None
KernelSettings = None
DeviceKey = None
ProvisionedDevice = None
connection_scope = None
canonical_envelope = None
canonical_json = None
hash_payload = None


def _import_kernel_dependencies() -> None:
    global SchemaRecord, create_app, KernelSettings, DeviceKey, ProvisionedDevice, connection_scope, canonical_envelope, canonical_json, hash_payload, shutdown_pool, verify_signature

    from k0.gate.schema_registry import SchemaRecord as _SchemaRecord
    from k0.kernel.app import create_app as _create_app
    from k0.kernel.config import KernelSettings as _KernelSettings
    from k0.storage.provisioning import DeviceKey as _DeviceKey, ProvisionedDevice as _ProvisionedDevice
    from k0.uow.connection_pool import connection_scope as _connection_scope, shutdown_pool as _shutdown_pool
    from k0.security import canonical_envelope as _canonical_envelope, canonical_json as _canonical_json, hash_payload as _hash_payload, verify_signature as _verify_signature

    SchemaRecord = _SchemaRecord
    create_app = _create_app
    KernelSettings = _KernelSettings
    DeviceKey = _DeviceKey
    ProvisionedDevice = _ProvisionedDevice
    connection_scope = _connection_scope
    shutdown_pool = _shutdown_pool
    canonical_envelope = _canonical_envelope
    canonical_json = _canonical_json
    hash_payload = _hash_payload
    verify_signature = _verify_signature


def _decode_base64url(value: str) -> bytes:
    padding = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding))


def _load_contract(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _seed_schema(app, seeds: list[dict[str, Any]]) -> None:
    with connection_scope() as conn:
        for entry in seeds:
            record = SchemaRecord(
                uri=str(entry["uri"]),
                version=str(entry["version"]),
                sha256=str(entry["sha256"]),
                status=str(entry.get("status", "ACTIVE")).upper(),
            )
            app.state.schema_registry.upsert(record, connection=conn)
        conn.commit()
    app.state.schema_registry.clear_cache()


def _seed_devices(app, devices: list[dict[str, Any]]) -> None:
    with connection_scope() as conn:
        for entry in devices:
            device = ProvisionedDevice(
                device_id=str(entry["device_id"]),
                tenant_id=str(entry["tenant_id"]),
                space_id=str(entry["space_id"]),
                mls_group_id=str(entry["mls_group_id"]),
                provisioned_ts=str(entry["provisioned_ts"]),
            )
            app.state.provisioning_ledger.register(device, connection=conn)
            for key_entry in entry.get("keys", []):
                key = DeviceKey(
                    device_id=device.device_id,
                    key_version=str(key_entry["key_version"]),
                    verify_key=str(key_entry["verify_key"]),
                    key_state=str(key_entry.get("key_state", "ACTIVE")),
                    registered_ts=str(key_entry["registered_ts"]),
                    activated_ts=str(key_entry.get("activated_ts")),
                )
                app.state.provisioning_ledger.add_key(key, connection=conn)
        conn.commit()
    app.state.provisioning_ledger.clear_cache()


def _build_command_envelope(
    template: Path,
    signing_key: SigningKey,
    verify_key_b64: str,
) -> dict[str, Any]:
    payload = json.loads(template.read_text(encoding="utf-8"))
    body = payload.get("body")
    if body is None:
        raise RuntimeError("Command envelope fixture is missing 'body'")

    payload_hash = hash_payload(canonical_json(body).encode("utf-8"))
    if payload_hash is None:
        raise RuntimeError("Failed to compute payload hash")

    envelope = {
        key: value for key, value in payload.items() if key != "body"
    }
    envelope["payload_sha256"] = payload_hash
    envelope["cognitive_trace_id"] = str(uuid.uuid4())

    message = canonical_envelope(envelope)
    signature = signing_key.sign(message).signature

    request_payload = dict(envelope)
    request_payload["sig"] = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    request_payload["body"] = body

    verify_signature(message, request_payload["sig"], verify_key_b64)
    return request_payload


def _invoke_command(app, client: TestClient, contract: dict[str, Any], signing_key: SigningKey) -> dict[str, Any]:
    request_cfg = contract["requests"]["command_submit"]
    fixture_path = Path(request_cfg["envelope_fixture"])
    if not fixture_path.is_absolute():
        fixture_path = REPO_ROOT / fixture_path
    fixture = fixture_path
    verify_key_b64 = None
    for device in contract["seed"].get("devices", []):
        if device.get("device_id") == "device-local-001":
            keys = device.get("keys", [])
            if keys:
                verify_key_b64 = str(keys[0]["verify_key"])
                break
    if verify_key_b64 is None:
        raise RuntimeError("Verify key not found in contract for device-local-001")

    envelope = _build_command_envelope(fixture, signing_key, verify_key_b64)
    response = client.post(request_cfg["route"], json=envelope)
    status_ok = response.status_code == int(request_cfg["expect"]["status"])

    wal_ok = receipt_ok = True
    if status_ok and request_cfg["expect"].get("wal_appended"):
        with connection_scope() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM st_wal").fetchone()
            wal_ok = bool(row and row["cnt"] > 0)
    if status_ok and request_cfg["expect"].get("receipt_issued"):
        with connection_scope() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM st_receipts").fetchone()
            receipt_ok = bool(row and row["cnt"] > 0)

    metrics_ok = True
    metrics_expected = request_cfg["expect"].get("metrics", [])
    if metrics_expected:
        metrics_blob = app.state.metrics_exporter.latest().decode("utf-8")
        metrics_ok = all(metric in metrics_blob for metric in metrics_expected)

    debug_payload = None
    if not status_ok:
        try:
            debug_payload = response.json()
        except ValueError:
            debug_payload = response.text

    return {
        "status": response.status_code,
        "status_ok": status_ok,
        "wal_ok": wal_ok,
        "receipt_ok": receipt_ok,
        "metrics_ok": metrics_ok,
        "payload": debug_payload,
    }


def _invoke_query(client: TestClient, contract: dict[str, Any]) -> dict[str, Any]:
    request_cfg = contract["requests"]["query_recall"]
    fixture_path = Path(request_cfg.get("envelope_fixture", ""))
    if fixture_path and not fixture_path.is_absolute():
        fixture_path = REPO_ROOT / fixture_path
    if fixture_path and fixture_path.exists():
        body = json.loads(fixture_path.read_text(encoding="utf-8"))
    else:
        body = {
            "space_id": "space-home",
            "tenant_id": "tenant-001",
            "selectors": [
                {
                    "type": "semantic",
                    "topic": "memory.delta",
                    "limit": 1,
                }
            ],
        }
    response = client.post(request_cfg["route"], json=body)
    expected_status = int(request_cfg["expect"]["status"])
    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
    admission_logged = request_cfg["expect"].get("admission_logged")
    if admission_logged:
        admission_logged = bool(payload)
    return {
        "status": response.status_code,
        "status_ok": response.status_code == expected_status,
        "payload": payload,
        "admission_logged": admission_logged,
    }


def _invoke_driver_handshake(client: TestClient, contract: dict[str, Any]) -> dict[str, Any]:
    request_cfg = contract["requests"]["driver_handshake"]
    fixture_path = Path(request_cfg.get("payload_fixture", ""))
    if fixture_path and not fixture_path.is_absolute():
        fixture_path = REPO_ROOT / fixture_path
    if fixture_path and fixture_path.exists():
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    else:
        payload = {
            "alias": "st_epi",
            "transport": "http",
            "endpoint": "http://127.0.0.1/mock",
            "capabilities": ["wal"],
        }
    response = client.post(request_cfg["route"], json=payload)
    expected = int(request_cfg["expect"]["status"])
    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
    return {
        "status": response.status_code,
        "status_ok": response.status_code == expected,
        "payload": payload,
    }


def _invoke_sse(client: TestClient, contract: dict[str, Any]) -> dict[str, Any]:
    request_cfg = contract["requests"]["sse_subscribe"]
    params = {
        "topics": "memory.delta",
        "space_id": "space-home",
        "tenant_id": "tenant-001",
    }
    headers = {
        "Accept": "text/event-stream",
        "X-SSE-Subscriber": "tester",
        "X-SSE-Roles": "coordinator",
    }
    with client.stream("GET", request_cfg["route"], params=params, headers=headers) as response:
        status_ok = response.status_code == int(request_cfg["expect"]["status"])
        if response.is_success:
            iterator = response.iter_bytes()
            try:
                next(iterator)
            except StopIteration:
                pass
        status_code = response.status_code
    return {"status": status_code, "status_ok": status_ok}


def _print_summary(results: dict[str, Any]) -> None:
    lines = ["K0 bootstrap verification summary:"]
    for key, value in results.items():
        lines.append(f"  {key}: {value}")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the K0 bootstrap verification harness")
    parser.add_argument("--contract", default="scripts/contracts/k0_bootstrap_harness.yml")
    parser.add_argument("--secret", required=True, help="URL-safe base64 Ed25519 secret key")
    args = parser.parse_args()

    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = REPO_ROOT / contract_path
    contract = _load_contract(contract_path)
    secret_bytes = _decode_base64url(args.secret)
    if len(secret_bytes) != 32:
        raise SystemExit("secret key must decode to 32 bytes")

    signing_key = SigningKey(secret_bytes)

    _import_kernel_dependencies()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "k0_runtime.sqlite3"
        overrides: dict[str, Any] = {
            "database": {"path": str(db_path)},
            "telemetry": {"otlp_endpoint": None, "prometheus_enabled": True},
        }
        settings = KernelSettings.load(overrides=overrides)
        app = create_app(settings=settings)

        _seed_schema(app, contract["seed"].get("schemas", []))
        _seed_devices(app, contract["seed"].get("devices", []))

        with TestClient(app) as client:
            results = {}
            results.update({"command": _invoke_command(app, client, contract, signing_key)})
            results.update({"query": _invoke_query(client, contract)})
            results.update({"driver": _invoke_driver_handshake(client, contract)})
            results.update({"sse": _invoke_sse(client, contract)})

        # ensure sqlite connections are closed prior to temp dir cleanup
        connections = getattr(app.state, "_sqlite_connections", [])
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass

        if shutdown_pool is not None:
            shutdown_pool()

    flattened = {
        key: json.dumps(value) if isinstance(value, dict) else value for key, value in results.items()
    }
    _print_summary(flattened)

    success = all(
        isinstance(value, dict) and value.get("status_ok") for value in results.values()
    )
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
