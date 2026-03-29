"""
Family Life Event Submitter -- JSONL-backed MW v2 replay for K0 Kernel.

Loads real-life event envelopes from life_events.jsonl, extracts the event bodies,
and submits them through the same K0 command port used by the previous synthetic
generator. The submission path still provisions the local test device and signs
each request locally, so the dataset can be replayed without depending on stale
embedded signatures.

Usage:
    python family_life_events.py [--n 80] [--sleep-sec 0.2] [--skip-p03] [--dry-run]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from nacl.signing import SigningKey

# Project root: k0/deploy/scripts/events/<this> -> familyos
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from k0.security import canonical_envelope, canonical_json, compute_envelope_sha256, hash_payload
from k0.security.crypto import encode_base64url

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "http://localhost:8080"
TENANT_ID = "tenant-test"
SPACE_ID = "space-home"
DEVICE_ID = "device-test-1"
PRIMARY_ACTOR_ID = "Prince"

SCHEMA_URI = "schema://k0/topics/memory_write.body.json"
SCHEMA_VERSION = "2.2"
POLICY_VERSION = "2025-09-28"
DATASET_PATH = Path(__file__).with_name("life_events.jsonl")

PG_CONTAINER = "k0-postgres"
PG_DATABASE = "k0_kernel"
PG_USER = "k0user"

EPOCH_MS_THRESHOLD = 1_000_000_000_000


def _normalize_epoch_ms(value: int | float) -> int:
    """Normalize epoch values to milliseconds.

    Values below the shared threshold are treated as seconds, otherwise as
    milliseconds. This matches the repo-wide conversation_anchor convention.
    """
    epoch_value = int(value)
    if epoch_value < EPOCH_MS_THRESHOLD:
        return epoch_value * 1000
    return epoch_value


def load_event_records(filepath: Path) -> list[dict[str, Any]]:
    """Load JSON objects from a JSONL dataset."""
    records: list[dict[str, Any]] = []

    with filepath.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {filepath} at line {line_number}: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"Expected object in {filepath} at line {line_number}, got {type(record).__name__}"
                )

            records.append(record)

    return records


_IDENTITY_DOMAIN_FIXES: dict[str, str] = {
    "family_caretaker": "parent",
    "sibling": "social_self",
}

_ENUM_FIXES: dict[str, dict[str, str]] = {
    "intent_type": {"set_preference": "other"},
    "location_type": {"medical": "hospital", "outdoor": "park"},
    "novelty": {"BREAKTHROUGH": "SURPRISING"},
    "sentiment_label": {"mixed": "neutral"},
}

MAX_TOPICS = 3


def extract_event_body(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a dataset row into the body submitted to memory.write."""
    body = record.get("body", record)
    if not isinstance(body, dict):
        raise ValueError("Each dataset record must be an object or contain an object body")
    # Upgrade body schema_version to 2.2 for v2.2 correction signal fields
    if body.get("schema_version") in ("2.0", "2.1"):
        body["schema_version"] = SCHEMA_VERSION
    _sanitize_body(body)
    return body


def _sanitize_body(body: dict[str, Any]) -> None:
    """Fix enum values and list lengths that violate memory_atom.v2 schema."""
    # Trim topics to schema max
    topics = body.get("topics")
    if isinstance(topics, list) and len(topics) > MAX_TOPICS:
        body["topics"] = topics[:MAX_TOPICS]

    # Fix identity_domains enum values
    domains = body.get("identity_domains")
    if isinstance(domains, list):
        body["identity_domains"] = [
            _IDENTITY_DOMAIN_FIXES.get(d, d) for d in domains
        ]

    # Fix scalar enum fields
    for field, mapping in _ENUM_FIXES.items():
        val = body.get(field)
        if val in mapping:
            body[field] = mapping[val]


def record_timestamp(record: dict[str, Any], body: dict[str, Any]) -> str:
    """Pick the envelope timestamp to preserve from the dataset when available."""
    timestamp = record.get("ts")
    if isinstance(timestamp, str) and timestamp:
        return timestamp

    anchor_ms = body.get("conversation_anchor_ms")
    if isinstance(anchor_ms, (int, float)) and anchor_ms > 0:
        normalized_anchor_ms = _normalize_epoch_ms(anchor_ms)
        return datetime.fromtimestamp(normalized_anchor_ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def narrative_threads(records: list[dict[str, Any]]) -> list[str]:
    """Collect unique narrative thread ids present in the dataset."""
    threads = set()
    for record in records:
        body = extract_event_body(record)
        narrative = body.get("narrative")
        if isinstance(narrative, dict):
            thread_id = narrative.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                threads.add(thread_id)
    return sorted(threads)


def dataset_time_span(records: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    """Return min/max conversation anchor timestamps in milliseconds."""
    anchors: list[int] = []
    for record in records:
        body = extract_event_body(record)
        anchor_ms = body.get("conversation_anchor_ms")
        if isinstance(anchor_ms, (int, float)) and anchor_ms > 0:
            anchors.append(_normalize_epoch_ms(anchor_ms))

    if not anchors:
        return None, None

    return min(anchors), max(anchors)


def execute_sql_in_docker(sql_statements: list[str]) -> str:
    """Execute SQL statements in PostgreSQL (auto-detects container vs host execution)."""
    full_sql = "; ".join(sql_statements)

    try:
        cmd = [
            "psql",
            "-h",
            "pgbouncer",
            "-p",
            "6432",
            "-U",
            PG_USER,
            "-d",
            PG_DATABASE,
            "-c",
            full_sql,
        ]
        env = {**os.environ, "PGPASSWORD": "k0pass"}
        process = subprocess.run(cmd, capture_output=True, check=True, env=env)
        return process.stdout.decode("utf-8")
    except FileNotFoundError:
        pass

    cmd = [
        "docker",
        "exec",
        "-i",
        PG_CONTAINER,
        "psql",
        "-U",
        PG_USER,
        "-d",
        PG_DATABASE,
        "-c",
        full_sql,
    ]
    try:
        process = subprocess.run(cmd, capture_output=True, check=True)
        return process.stdout.decode("utf-8")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Docker PostgreSQL execution failed: {stderr}") from exc


def provision_device(signing_key: SigningKey) -> bool:
    """Provision device and register public key in K0 via Docker PostgreSQL."""
    print("\n" + "=" * 60)
    print("STEP 1: Provisioning Device")
    print("=" * 60)

    verify_key_b64 = encode_base64url(signing_key.verify_key.encode())
    now = datetime.now(timezone.utc).isoformat()

    print(f"  Device ID: {DEVICE_ID}")
    print(f"  Tenant ID: {TENANT_ID}")
    print(f"  Actor: {PRIMARY_ACTOR_ID}")

    try:
        sql = [
            f"DELETE FROM st_device_keys WHERE device_id = '{DEVICE_ID}'",
            f"DELETE FROM st_devices WHERE device_id = '{DEVICE_ID}'",
            (
                "INSERT INTO st_devices "
                "(device_id, tenant_id, space_id, mls_group_id, provisioned_ts) "
                f"VALUES ('{DEVICE_ID}', '{TENANT_ID}', '{SPACE_ID}', 'mls-group-1', '{now}')"
            ),
            (
                "INSERT INTO st_device_keys "
                "(device_id, key_version, verify_key, key_state, registered_ts, activated_ts) "
                f"VALUES ('{DEVICE_ID}', '1', '{verify_key_b64}', 'ACTIVE', '{now}', '{now}')"
            ),
        ]
        schema_sha = hashlib.sha256(f"{SCHEMA_URI}@{SCHEMA_VERSION}".encode("utf-8")).hexdigest()
        sql.append(
            (
                "INSERT INTO schema_registry (schema_uri, version, sha256, status) "
                f"VALUES ('{SCHEMA_URI}', '{SCHEMA_VERSION}', '{schema_sha}', 'ACTIVE') "
                "ON CONFLICT DO NOTHING"
            )
        )

        execute_sql_in_docker(sql)
        time.sleep(0.5)
        print("  [OK] Device provisioned, key registered, schema registered")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] Provisioning failed: {exc}")
        return False


def build_request_payload(
    signing_key: SigningKey,
    body: dict[str, Any],
    source_record: dict[str, Any],
) -> dict[str, Any]:
    """Build a signed envelope from a dataset body."""
    body_json = canonical_json(body)
    body_bytes = body_json.encode("utf-8")
    payload_hash = hash_payload(body_bytes)

    envelope = {
        "cognitive_trace_id": str(uuid.uuid4()),
        "tenant_id": TENANT_ID,
        "space_id": SPACE_ID,
        "topic": source_record.get("topic", "memory.write"),
        "schema_uri": source_record.get("schema_uri", SCHEMA_URI),
        "schema_version": SCHEMA_VERSION,
        "actor": source_record.get("actor", PRIMARY_ACTOR_ID),
        "device_id": DEVICE_ID,
        "band": source_record.get("band", "GREEN"),
        "policy_version": source_record.get("policy_version", POLICY_VERSION),
        "ts": record_timestamp(source_record, body),
        "payload_sha256": payload_hash,
        "sig_alg": "Ed25519SHA512",
        "sig_kid": f"{DEVICE_ID}#1",
        "body": body,
        "policy": source_record.get("policy", {"abac": {"roles": ["guest"]}}),
    }

    envelope["envelope_sha256"] = compute_envelope_sha256(envelope)
    signature = encode_base64url(signing_key.sign(canonical_envelope(envelope)).signature)

    request_payload = dict(envelope)
    request_payload["sig"] = signature
    return request_payload


def submit_record(
    signing_key: SigningKey,
    record: dict[str, Any],
) -> tuple[bool, float | None, dict[str, Any]]:
    """Submit one dataset record to the K0 command port."""
    body = extract_event_body(record)
    request_payload = build_request_payload(signing_key, body, record)

    url = f"{BASE_URL}/k0/command.submit"
    try:
        t0 = time.perf_counter()
        response = requests.post(
            url,
            json=request_payload,
            headers={"Content-Type": "application/json"},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if response.status_code == 200:
            return True, elapsed_ms, body

        if response.status_code == 409:
            try:
                conflict_payload = response.json()
            except ValueError:
                conflict_payload = {}

            # Replay runs are intentionally idempotent. If the kernel reports an
            # existing idempotent receipt, treat it as an already-accepted event.
            if isinstance(conflict_payload, dict) and conflict_payload.get("idem_key"):
                return True, elapsed_ms, body

        print(f"    [FAIL] HTTP {response.status_code}: {response.text[:500]}")
        return False, elapsed_ms, body
    except Exception as exc:  # noqa: BLE001
        print(f"    [ERROR] {exc}")
        return False, None, body


def submit_all_events(
    signing_key: SigningKey,
    records: list[dict[str, Any]],
    sleep_sec: float = 0.2,
) -> tuple[int, int]:
    """Submit all dataset records to K0."""
    import statistics

    print("\n" + "=" * 60)
    print(f"STEP 2: Submitting {len(records)} Family Events")
    print("=" * 60)

    success = 0
    fail = 0
    latencies: list[float] = []

    for idx, record in enumerate(records, start=1):
        ok, elapsed, body = submit_record(signing_key, record)
        if ok:
            success += 1
            if elapsed is not None:
                latencies.append(elapsed)
            text_preview = body.get("text", "")[:60]
            print(f"  [{idx:3d}/{len(records)}] OK  {text_preview}...")
        else:
            fail += 1
            print(f"  [{idx:3d}/{len(records)}] FAIL")
        time.sleep(max(0.0, sleep_sec))

    print("\n" + "-" * 60)
    print(f"  Submitted: {success} OK, {fail} FAIL out of {len(records)} total")
    if latencies:
        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(min(len(latencies) * 0.95, len(latencies) - 1))]
        print(
            f"  Latency: min={min(latencies):.0f}ms "
            f"p50={p50:.0f}ms p95={p95:.0f}ms "
            f"max={max(latencies):.0f}ms mean={statistics.mean(latencies):.0f}ms"
        )
    print("-" * 60)
    return success, fail


def trigger_p03_consolidation(batch_size: int = 100) -> bool:
    """Trigger P03 consolidation pipeline via admin API."""
    print("\n" + "=" * 60)
    print("STEP 3: Triggering P03 Consolidation")
    print("=" * 60)

    url = f"{BASE_URL}/k0/admin/pipelines/P03_CONSOLIDATION/trigger"
    payload = {
        "reason": "Family life events batch consolidation",
        "options": {
            "max_events": batch_size,
            "tenant_id": TENANT_ID,
            "space_id": SPACE_ID,
        },
    }

    try:
        print(f"  POST {url}")
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        if response.status_code == 200:
            result = response.json()
            print(f"  [OK] P03 triggered: {json.dumps(result, indent=2)[:500]}")
            return True

        print(f"  [FAIL] HTTP {response.status_code}: {response.text[:300]}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  [ERROR] {exc}")
        return False


def _get_or_create_persistent_key() -> SigningKey:
    """Load persistent test signing key from file, or generate and save if missing."""
    key_file = project_root / "k0" / "deploy" / "data" / "test_device_key.b64"
    if key_file.exists():
        key_b64 = key_file.read_text().strip()
        padding = "=" * (-len(key_b64) % 4)
        key_bytes = base64.urlsafe_b64decode(f"{key_b64}{padding}".encode("ascii"))
        return SigningKey(key_bytes)

    signing_key = SigningKey.generate()
    key_b64 = encode_base64url(bytes(signing_key))
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key_b64)
    print("  [NEW] Generated persistent Ed25519 signing key")
    return signing_key


def _format_anchor(anchor_ms: int | None) -> str:
    if anchor_ms is None:
        return "unknown"
    return datetime.fromtimestamp(anchor_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load real family life events from JSONL and submit them to the K0 kernel"
    )
    parser.add_argument(
        "--n",
        type=int,
        default=0,
        help="Max events to submit (0 = all, default: all)",
    )
    parser.add_argument(
        "--sleep-sec",
        type=float,
        default=0.2,
        help="Delay between submissions in seconds (default: 0.2)",
    )
    parser.add_argument(
        "--skip-p03",
        action="store_true",
        help="Skip P03 consolidation trigger after submission",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print events without submitting")
    parser.add_argument(
        "--p03-batch-size",
        type=int,
        default=100,
        help="P03 batch size (default: 100)",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DATASET_PATH,
        help=f"Path to JSONL dataset (default: {DATASET_PATH.name})",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Family Life Event Submitter -- JSONL Replay")
    print("=" * 60)

    dataset_path = args.dataset.resolve()
    if not dataset_path.exists():
        print(f"\n[ABORT] Dataset not found: {dataset_path}")
        return

    records = load_event_records(dataset_path)
    if args.n > 0:
        records = records[: args.n]

    start_anchor, end_anchor = dataset_time_span(records)
    threads = narrative_threads(records)

    print(f"\n  Dataset: {dataset_path}")
    print(f"  Loaded {len(records)} real-life events")
    print(f"  Time span: {_format_anchor(start_anchor)} -> {_format_anchor(end_anchor)}")
    print("  Family members: Prince, Panda, Maya, Mom, Dad, Riya")
    if threads:
        print(f"  Narrative arcs: {', '.join(threads)}")

    if args.dry_run:
        print("\n--- DRY RUN: Event Preview ---")
        for index, record in enumerate(records, start=1):
            body = extract_event_body(record)
            ts = body.get("temporal", {}).get("mentioned_time", "")[:24]
            participants = ", ".join(body.get("participants", []))
            print(f"  [{index:3d}] {ts:24s} {body.get('text', '')[:65]}")
            if participants:
                print(f"        with: {participants}")
        return

    signing_key = _get_or_create_persistent_key()

    if not provision_device(signing_key):
        print("\n[ABORT] Device provisioning failed.")
        return

    ok_count, fail_count = submit_all_events(
        signing_key,
        records,
        sleep_sec=args.sleep_sec,
    )

    if ok_count == 0:
        print("\n[ABORT] No events submitted successfully.")
        return

    if not args.skip_p03:
        print("\n  Waiting 5s for P02 pipeline to process events...")
        time.sleep(5)
        trigger_p03_consolidation(batch_size=args.p03_batch_size)

    print("\n" + "=" * 60)
    print("DONE")
    print(f"  Events submitted: {ok_count}/{len(records)}")
    print(f"  Failed: {fail_count}")
    print(f"  P03 triggered: {'yes' if not args.skip_p03 else 'skipped'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
