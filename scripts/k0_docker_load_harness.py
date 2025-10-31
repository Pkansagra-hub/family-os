from __future__ import annotations

import argparse
import base64
import json
import sys
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from nacl.signing import SigningKey

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from k0.security import (  # noqa: E402
    canonical_envelope,
    canonical_json,
    hash_payload,
    verify_signature,
)

_DEFAULT_ENDPOINT = "http://127.0.0.1:8080"
_DEFAULT_PORTS = (
    "command",
    "query",
    "driver",
    "sse_subscribe",
    "sse_ack",
    "metrics",
)


def _decode_base64url(value: str) -> bytes:
    padding = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding))


def _load_contract(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _resolve_verify_key(contract: dict[str, Any], device_id: str) -> str:
    for device in contract.get("seed", {}).get("devices", []):
        if device.get("device_id") != device_id:
            continue
        keys = device.get("keys", [])
        if keys:
            return str(keys[0]["verify_key"])
    raise RuntimeError(f"Verify key not found for device {device_id}")


def _build_command_envelope(
    template_payload: dict[str, Any],
    signing_key: SigningKey,
    verify_key_b64: str,
    unique_value: int,
) -> dict[str, Any]:
    payload = deepcopy(template_payload)
    body = payload.get("body")
    if body is None:
        raise RuntimeError("Command envelope template missing 'body'")

    # Inject per-request mutation to avoid idempotency collisions.
    payload_state = body.get("payload")
    if isinstance(payload_state, dict):
        payload_state["value"] = unique_value

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


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_command_loop(
    client: httpx.Client,
    contract: dict[str, Any],
    signing_key: SigningKey,
    template_payload: dict[str, Any],
    verify_key_b64: str,
    iterations: int,
) -> dict[str, int]:
    route = contract["requests"]["command_submit"]["route"]
    expected_status = int(contract["requests"]["command_submit"]["expect"]["status"])
    stats = defaultdict(int)
    unique_seed = uuid.uuid4().int & 0xFFFFFFFF

    for index in range(iterations):
        envelope = _build_command_envelope(
            template_payload,
            signing_key,
            verify_key_b64,
            unique_seed + index,
        )
        try:
            response = client.post(route, json=envelope)
        except Exception:
            stats["errors"] += 1
            continue
        code = response.status_code
        if code == expected_status:
            stats["success"] += 1
        else:
            stats[f"status_{code}"] += 1
    return stats


def _load_query_loop(client: httpx.Client, contract: dict[str, Any], iterations: int) -> dict[str, int]:
    route = contract["requests"]["query_recall"]["route"]
    expected_status = int(contract["requests"]["query_recall"]["expect"]["status"])
    fixture_path = Path(contract["requests"]["query_recall"].get("envelope_fixture", ""))
    if fixture_path and not fixture_path.is_absolute():
        fixture_path = REPO_ROOT / fixture_path
    if fixture_path and fixture_path.exists():
        body = json.loads(fixture_path.read_text(encoding="utf-8"))
    else:
        body = {
            "space_id": "space-home",
            "tenant_id": "tenant-001",
            "selectors": [
                {"type": "semantic", "topic": "memory.delta", "limit": 1},
            ],
        }
    stats = defaultdict(int)
    for _ in range(iterations):
        try:
            response = client.post(route, json=body)
        except Exception:
            stats["errors"] += 1
            continue
        code = response.status_code
        if code == expected_status:
            stats["success"] += 1
        else:
            stats[f"status_{code}"] += 1
    return stats


def _load_driver_loop(client: httpx.Client, contract: dict[str, Any], iterations: int) -> dict[str, int]:
    route = contract["requests"]["driver_handshake"]["route"]
    expected_status = int(contract["requests"]["driver_handshake"]["expect"]["status"])
    fixture_path = Path(contract["requests"]["driver_handshake"].get("payload_fixture", ""))
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
    stats = defaultdict(int)
    for _ in range(iterations):
        try:
            response = client.post(route, json=payload)
        except Exception:
            stats["errors"] += 1
            continue
        code = response.status_code
        if code == expected_status:
            stats["success"] += 1
        else:
            stats[f"status_{code}"] += 1
    return stats


def _load_sse_subscribe_loop(client: httpx.Client, contract: dict[str, Any], iterations: int) -> dict[str, int]:
    route = contract["requests"]["sse_subscribe"]["route"]
    expected_status = int(contract["requests"]["sse_subscribe"]["expect"]["status"])
    params = {"topics": "memory.delta", "space_id": "space-home", "tenant_id": "tenant-001"}
    headers = {
        "Accept": "text/event-stream",
        "X-SSE-Subscriber": "load-harness",
        "X-SSE-Roles": "coordinator",
    }
    stats = defaultdict(int)
    for _ in range(iterations):
        try:
            with client.stream("GET", route, params=params, headers=headers, timeout=None) as response:
                code = response.status_code
                if code == expected_status:
                    stats["success"] += 1
                else:
                    stats[f"status_{code}"] += 1
        except Exception:
            stats["errors"] += 1
    return stats


def _load_sse_ack_loop(client: httpx.Client, iterations: int) -> dict[str, int]:
    route = "/k0/sse.ack"
    example_path = (
        REPO_ROOT
        / "k0"
        / "contracts"
        / "jsonschema"
        / "examples"
        / "sse.ack.request.json"
    )
    if not example_path.exists():
        raise RuntimeError("Missing SSE ack example payload")
    base_payload = json.loads(example_path.read_text(encoding="utf-8"))
    stats = defaultdict(int)
    offset = 0
    for _ in range(iterations):
        payload = dict(base_payload)
        payload["offset"] = offset
        payload["ack_ts"] = _now_ts()
        offset += 1
        try:
            response = client.post(route, json=payload)
        except Exception:
            stats["errors"] += 1
            continue
        code = response.status_code
        if code == 204:
            stats["success"] += 1
        else:
            stats[f"status_{code}"] += 1
    return stats


def _load_metrics_loop(client: httpx.Client, iterations: int) -> dict[str, int]:
    stats = defaultdict(int)
    for _ in range(iterations):
        try:
            response = client.get("/metrics")
        except Exception:
            stats["errors"] += 1
            continue
        code = response.status_code
        if code == 200:
            stats["success"] += 1
        else:
            stats[f"status_{code}"] += 1
    return stats


def _print_summary(summary: dict[str, dict[str, int]]) -> None:
    print("K0 docker load summary:")
    for port, stats in summary.items():
        ordered = ", ".join(f"{key}={value}" for key, value in sorted(stats.items()))
        print(f"  {port}: {ordered}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sustained load across K0 kernel ports")
    parser.add_argument("--contract", default="scripts/contracts/k0_bootstrap_harness.yml")
    parser.add_argument("--secret", required=True, help="URL-safe base64 Ed25519 secret key")
    parser.add_argument("--endpoint", default=_DEFAULT_ENDPOINT, help="Kernel base URL")
    parser.add_argument(
        "--ports",
        default=",".join(_DEFAULT_PORTS),
        help="Comma separated list of ports to load (command,query,driver,sse_subscribe,sse_ack,metrics)",
    )
    parser.add_argument("--per-port", type=int, default=10_000, help="Requests per selected port")
    args = parser.parse_args()

    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = REPO_ROOT / contract_path
    contract = _load_contract(contract_path)

    secret_bytes = _decode_base64url(args.secret)
    if len(secret_bytes) != 32:
        raise SystemExit("secret key must decode to 32 bytes")
    signing_key = SigningKey(secret_bytes)

    endpoint = args.endpoint.rstrip("/")
    ports = [token.strip() for token in args.ports.split(",") if token.strip()]
    unknown = [port for port in ports if port not in _DEFAULT_PORTS]
    if unknown:
        raise SystemExit(f"Unknown ports requested: {', '.join(unknown)}")

    verify_key_b64 = _resolve_verify_key(contract, "device-local-001")
    command_template_path = Path(contract["requests"]["command_submit"]["envelope_fixture"])
    if not command_template_path.is_absolute():
        command_template_path = REPO_ROOT / command_template_path
    command_template_payload = json.loads(command_template_path.read_text(encoding="utf-8"))

    summary: dict[str, dict[str, int]] = {}
    with httpx.Client(base_url=endpoint, timeout=httpx.Timeout(10.0, read=30.0)) as client:
        for port in ports:
            if port == "command":
                stats = _load_command_loop(
                    client,
                    contract,
                    signing_key,
                    command_template_payload,
                    verify_key_b64,
                    args.per_port,
                )
            elif port == "query":
                stats = _load_query_loop(client, contract, args.per_port)
            elif port == "driver":
                stats = _load_driver_loop(client, contract, args.per_port)
            elif port == "sse_subscribe":
                stats = _load_sse_subscribe_loop(client, contract, args.per_port)
            elif port == "sse_ack":
                stats = _load_sse_ack_loop(client, args.per_port)
            elif port == "metrics":
                stats = _load_metrics_loop(client, args.per_port)
            else:
                stats = {"skipped": args.per_port}
            summary[port] = dict(stats)

    _print_summary(summary)


if __name__ == "__main__":
    main()
