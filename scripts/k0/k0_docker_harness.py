from __future__ import annotations

import argparse
import base64
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from k0.security import (  # noqa: E402
    canonical_envelope,
    canonical_json,
    hash_payload,
    verify_signature,
)


def _decode_base64url(value: str) -> bytes:
    padding = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding))


def _load_contract(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _build_command_envelope(
    template: Path,
    signing_key: Any,
    verify_key_b64: str,
) -> dict[str, Any]:
    payload = json.loads(template.read_text(encoding="utf-8"))
    body = payload.get("body")
    if body is None:
        raise RuntimeError("Command envelope fixture is missing 'body'")

    payload_hash = hash_payload(canonical_json(body).encode("utf-8"))
    if payload_hash is None:
        raise RuntimeError("Failed to compute payload hash")

    envelope = {key: value for key, value in payload.items() if key != "body"}
    envelope["payload_sha256"] = payload_hash
    envelope["cognitive_trace_id"] = str(uuid.uuid4())

    message = canonical_envelope(envelope)
    signature = signing_key.sign(message).signature

    request_payload = dict(envelope)
    request_payload["sig"] = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    request_payload["body"] = body

    verify_signature(message, request_payload["sig"], verify_key_b64)
    return request_payload


def _invoke_command(
    client: httpx.Client,
    endpoint: str,
    contract: dict[str, Any],
    signing_key: Any,
) -> dict[str, Any]:
    request_cfg = contract["requests"]["command_submit"]
    fixture_path = Path(request_cfg["envelope_fixture"])
    if not fixture_path.is_absolute():
        fixture_path = REPO_ROOT / fixture_path

    verify_key_b64 = None
    for device in contract["seed"].get("devices", []):
        if device.get("device_id") == "device-local-001":
            keys = device.get("keys", [])
            if keys:
                verify_key_b64 = str(keys[0]["verify_key"])
                break
    if verify_key_b64 is None:
        raise RuntimeError("Verify key not found in contract for device-local-001")

    envelope = _build_command_envelope(fixture_path, signing_key, verify_key_b64)

    response = client.post(request_cfg["route"], json=envelope)
    status_ok = response.status_code == int(request_cfg["expect"]["status"])

    metrics_ok = True
    metrics_expected = request_cfg["expect"].get("metrics", [])
    if metrics_expected:
        metrics_resp = client.get("/metrics")
        if metrics_resp.is_success:
            metrics_blob = metrics_resp.text
            metrics_ok = all(metric in metrics_blob for metric in metrics_expected)
        else:
            metrics_ok = False

    wal_ok = request_cfg["expect"].get("wal_appended") is None
    receipt_ok = request_cfg["expect"].get("receipt_issued") is None

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


def _invoke_query(client: httpx.Client, contract: dict[str, Any]) -> dict[str, Any]:
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


def _invoke_driver_handshake(client: httpx.Client, contract: dict[str, Any]) -> dict[str, Any]:
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


def _invoke_sse(client: httpx.Client, contract: dict[str, Any]) -> dict[str, Any]:
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

    with client.stream("GET", request_cfg["route"], params=params, headers=headers, timeout=None) as response:
        status_ok = response.status_code == int(request_cfg["expect"]["status"])
        if response.is_success:
            iterator = response.iter_bytes()
            try:
                next(iterator)
            except StopIteration:
                pass
        status_code = response.status_code

    return {
        "status": status_code,
        "status_ok": status_ok,
    }


def _print_summary(results: dict[str, Any]) -> None:
    lines = ["K0 docker verification summary:"]
    for key, value in results.items():
        lines.append(f"  {key}: {value}")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the K0 docker verification harness")
    parser.add_argument("--contract", default="scripts/contracts/k0_bootstrap_harness.yml")
    parser.add_argument("--secret", required=True, help="URL-safe base64 Ed25519 secret key")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8080", help="Kernel base URL")
    args = parser.parse_args()

    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = REPO_ROOT / contract_path
    contract = _load_contract(contract_path)

    secret_bytes = _decode_base64url(args.secret)
    if len(secret_bytes) != 32:
        raise SystemExit("secret key must decode to 32 bytes")

    from nacl.signing import SigningKey  # noqa: E402

    signing_key = SigningKey(secret_bytes)

    endpoint = args.endpoint.rstrip("/")

    with httpx.Client(base_url=endpoint, timeout=httpx.Timeout(10.0, read=30.0)) as client:
        results: dict[str, Any] = {}
        results["command"] = _invoke_command(client, endpoint, contract, signing_key)
        results["query"] = _invoke_query(client, contract)
        results["driver"] = _invoke_driver_handshake(client, contract)
        results["sse"] = _invoke_sse(client, contract)

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
