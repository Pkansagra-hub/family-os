"""
Submit clarifying events to resolve learning queue gaps.

These events contain SPECIFIC entity names that should match and resolve
the ambiguous entity gaps in st_learning_queue.
"""

import base64
import hashlib
import secrets
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from nacl.signing import SigningKey

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from k0.security import canonical_envelope, canonical_json, compute_envelope_sha256, hash_payload
from k0.security.crypto import encode_base64url

# Config
BASE_URL = "http://localhost:8080"
TENANT_ID = "tenant-test"
SPACE_ID = "space-home"
DEVICE_ID = "device-test-1"
SCHEMA_URI = "schema://memory.delta"
SCHEMA_VERSION = "1.0"
PG_USER = "k0user"
PG_DB = "k0_kernel"


# =============================================================================
# CLARIFYING EVENTS - Specifically designed to resolve ambiguous entity gaps
# =============================================================================
# These events provide SPECIFIC entity names to disambiguate gaps like:
#   - "lincoln school" -> "Lincoln Elementary School"
#   - "central park" -> "Central Park NYC"
#   - "city sports complex" -> "City Sports Complex on Main Street"
#   - "chuck e cheese" -> "Chuck E Cheese Pizza Restaurant"
#   - "fur elise" -> "Fur Elise by Beethoven"
# =============================================================================

CLARIFYING_EVENTS = [
    # Clarify "lincoln school" -> Lincoln Elementary School
    {
        "text": "Emma had her spelling bee at Lincoln Elementary School today. She got 2nd place! The school's full name is Lincoln Elementary School on Oak Street.",
        "participants": ["Emma"],
        "location_name": "Lincoln Elementary School",
        "activity_type": "FAMILY",
    },
    {
        "text": "Parent-teacher conference at Lincoln Elementary School. Ms. Johnson said Emma is doing great in math.",
        "participants": ["Emma", "Ms. Johnson"],
        "location_name": "Lincoln Elementary School",
        "activity_type": "FAMILY",
    },
    # Clarify "central park" -> Central Park NYC
    {
        "text": "Beautiful morning jog through Central Park NYC. Ran past the Great Lawn and Bethesda Fountain.",
        "participants": [],
        "location_name": "Central Park NYC",
        "activity_type": "HEALTH",
    },
    {
        "text": "Picnic in Central Park NYC near Sheep Meadow. The weather was perfect for outdoor activities.",
        "participants": ["Jake", "Emma"],
        "location_name": "Central Park NYC",
        "activity_type": "SOCIAL",
    },
    # Clarify "city sports complex" -> City Sports Complex on Main Street
    {
        "text": "Emma's basketball game at City Sports Complex on Main Street. Her team won 24-18!",
        "participants": ["Emma"],
        "location_name": "City Sports Complex on Main Street",
        "activity_type": "FAMILY",
    },
    {
        "text": "Signed Emma up for summer camp at City Sports Complex on Main Street. They have great programs.",
        "participants": ["Emma"],
        "location_name": "City Sports Complex on Main Street",
        "activity_type": "FAMILY",
    },
    # Clarify "chuck e cheese" -> Chuck E Cheese Pizza Restaurant
    {
        "text": "Jake's birthday party at Chuck E Cheese Pizza Restaurant. The kids loved the arcade games!",
        "participants": ["Jake", "Emma"],
        "location_name": "Chuck E Cheese Pizza Restaurant",
        "activity_type": "SOCIAL",
    },
    {
        "text": "Quick dinner at Chuck E Cheese Pizza Restaurant after soccer practice. Kids earned tokens for games.",
        "participants": ["Emma", "Jake"],
        "location_name": "Chuck E Cheese Pizza Restaurant",
        "activity_type": "FAMILY",
    },
    # Clarify "fur elise" -> Fur Elise by Beethoven
    {
        "text": "Emma practiced Fur Elise by Beethoven for 2 hours today. She's really mastering this classical piano piece.",
        "participants": ["Emma"],
        "location_name": "Home",
        "activity_type": "LEARNING",
    },
    {
        "text": "Piano recital at the community center. Emma performed Fur Elise by Beethoven beautifully. Standing ovation!",
        "participants": ["Emma"],
        "location_name": "Community Center",
        "activity_type": "MILESTONE",
    },
]


def execute_sql(sql_statements):
    full_sql = "; ".join(sql_statements)
    import os

    if os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST"):
        cmd = ["psql", "postgresql://postgres:postgres@pgbouncer:6432/k0_kernel", "-c", full_sql]
    else:
        cmd = [
            "docker",
            "exec",
            "-i",
            "k0-postgres",
            "psql",
            "-U",
            PG_USER,
            "-d",
            PG_DB,
            "-c",
            full_sql,
        ]
    process = subprocess.run(cmd, capture_output=True)
    return process.stdout.decode("utf-8") if process.returncode == 0 else None


def get_signing_key():
    key_file = project_root / "k0" / "deploy" / "data" / "test_device_key.b64"
    if key_file.exists():
        key_b64 = key_file.read_text().strip()
        padding = "=" * (-len(key_b64) % 4)
        key_bytes = base64.urlsafe_b64decode(f"{key_b64}{padding}".encode("ascii"))
        return SigningKey(key_bytes)
    else:
        signing_key = SigningKey.generate()
        key_b64 = encode_base64url(bytes(signing_key))
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key_b64)
        return signing_key


def provision_device(signing_key):
    """Provision device in PostgreSQL."""
    verify_key_b64 = encode_base64url(signing_key.verify_key.encode())
    now = datetime.now(timezone.utc).isoformat()
    hmac_secret_hex = secrets.token_bytes(32).hex()

    print("\nProvisioning device...")
    try:
        execute_sql(
            [
                f"DELETE FROM st_device_keys WHERE device_id = '{DEVICE_ID}'",
                f"DELETE FROM st_devices WHERE device_id = '{DEVICE_ID}'",
            ]
        )
        execute_sql(
            [
                f"INSERT INTO st_devices (device_id, tenant_id, space_id, mls_group_id, provisioned_ts, hmac_secret) "
                f"VALUES ('{DEVICE_ID}', '{TENANT_ID}', '{SPACE_ID}', 'mls-group-1', '{now}', '\\x{hmac_secret_hex}')"
            ]
        )
        execute_sql(
            [
                f"INSERT INTO st_device_keys (device_id, key_version, verify_key, key_state, registered_ts, activated_ts) "
                f"VALUES ('{DEVICE_ID}', '1', '{verify_key_b64}', 'ACTIVE', '{now}', '{now}')"
            ]
        )
        schema_sha = hashlib.sha256(f"{SCHEMA_URI}@{SCHEMA_VERSION}".encode("utf-8")).hexdigest()
        execute_sql(
            [
                f"INSERT INTO schema_registry (schema_uri, version, sha256, status) "
                f"VALUES ('{SCHEMA_URI}', '{SCHEMA_VERSION}', '{schema_sha}', 'ACTIVE') "
                f"ON CONFLICT (schema_uri, version) DO NOTHING"
            ]
        )
        print("Device provisioned!")
        return True
    except Exception as e:
        print(f"Provisioning error: {e}")
        return False


def submit_event(signing_key, event_data, index):
    """Submit a single event using correct envelope format."""
    import random

    now_utc = datetime.now(timezone.utc)
    hour_offset = random.uniform(0, 2)
    event_time = now_utc - timedelta(hours=hour_offset)

    body = {
        "operation": "UPSERT",
        "text": event_data["text"],
        "value": index * 10,
        "timestamp": event_time.isoformat(),
        "event_time": event_time.isoformat(),
        "event_time_utc": event_time.isoformat(),
        "participants": event_data.get("participants", []),
        "location_name": event_data.get("location_name", "Unknown"),
        "activity_type": event_data.get("activity_type", "GENERAL"),
    }

    body_json = canonical_json(body)
    body_bytes = body_json.encode("utf-8")
    payload_hash = hash_payload(body_bytes)

    trace_id = str(uuid.uuid4())
    timestamp_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    envelope = {
        "cognitive_trace_id": trace_id,
        "tenant_id": TENANT_ID,
        "space_id": SPACE_ID,
        "topic": "memory.delta",
        "schema_uri": SCHEMA_URI,
        "schema_version": SCHEMA_VERSION,
        "actor": f"actor-clarify-{index}",
        "device_id": DEVICE_ID,
        "band": "GREEN",
        "policy_version": "2025-09-28",
        "ts": timestamp_iso,
        "payload_sha256": payload_hash,
        "sig_alg": "Ed25519SHA512",
        "sig_kid": f"{DEVICE_ID}#1",
        "body": body,
        "policy": {"abac": {"roles": ["guest"]}},
    }

    envelope_sha256 = compute_envelope_sha256(envelope)
    envelope["envelope_sha256"] = envelope_sha256

    message = canonical_envelope(envelope)
    signature = encode_base64url(signing_key.sign(message).signature)

    request_payload = dict(envelope)
    request_payload["sig"] = signature

    response = requests.post(
        f"{BASE_URL}/k0/command.submit",
        json=request_payload,
        headers={"Content-Type": "application/json"},
    )

    return response


def trigger_p03():
    """Trigger P03 consolidation pipeline."""
    print("\n" + "=" * 60)
    print("TRIGGERING P03 CONSOLIDATION PIPELINE")
    print("=" * 60)

    response = requests.post(
        f"{BASE_URL}/k0/admin/pipelines/P03_CONSOLIDATION/trigger",
        json={
            "reason": "gap_clarification_test",
            "options": {"tenant_id": TENANT_ID, "space_id": SPACE_ID, "batch_size": 100},
        },
        headers={"Content-Type": "application/json"},
    )

    if response.status_code == 200:
        print(f"SUCCESS: {response.json()}")
        return True
    else:
        print(f"FAILED: {response.status_code} - {response.text}")
        return False


def check_gaps_before():
    """Check learning queue gaps before clarification."""
    print("\n" + "=" * 60)
    print("LEARNING QUEUE GAPS (BEFORE)")
    print("=" * 60)
    result = execute_sql(
        [
            "SELECT entity_id, status FROM st_learning_queue WHERE gap_type = 'AMBIGUOUS_ENTITY' ORDER BY entity_id"
        ]
    )
    if result:
        print(result)
    else:
        print("No gaps found or error querying.")


def check_gaps_after():
    """Check learning queue gaps after P03."""
    print("\n" + "=" * 60)
    print("LEARNING QUEUE GAPS (AFTER)")
    print("=" * 60)
    result = execute_sql(
        [
            "SELECT entity_id, status, resolution_type FROM st_learning_queue WHERE gap_type = 'AMBIGUOUS_ENTITY' ORDER BY status, entity_id"
        ]
    )
    if result:
        print(result)
    else:
        print("No gaps found or error querying.")


def main():
    print("=" * 60)
    print("GAP CLARIFICATION - SUBMITTING SPECIFIC ENTITY EVENTS")
    print(f"Submitting {len(CLARIFYING_EVENTS)} clarifying events")
    print("=" * 60)

    # Show gaps before
    check_gaps_before()

    signing_key = get_signing_key()

    if not provision_device(signing_key):
        print("Failed to provision device. Exiting.")
        return

    time.sleep(0.5)

    print(f"\nSubmitting {len(CLARIFYING_EVENTS)} clarifying events...")
    success_count = 0

    for i, event_data in enumerate(CLARIFYING_EVENTS, 1):
        try:
            response = submit_event(signing_key, event_data, i)
            activity = event_data.get("activity_type", "UNKNOWN")
            location = event_data.get("location_name", "")[:30]

            if response.status_code == 200:
                print(f"  [{i:2}] OK {activity:10} | {location}")
                success_count += 1
            else:
                error = response.json().get("error", {}).get("reason", response.text[:50])
                print(f"  [{i:2}] FAIL {activity:10} | {error}")
        except Exception as e:
            print(f"  [{i:2}] ERROR: {e}")

        time.sleep(0.03)

    print(f"\n{'=' * 60}")
    print(f"SUBMITTED: {success_count}/{len(CLARIFYING_EVENTS)} events")
    print("=" * 60)

    print("\nWaiting 5s for P02 embeddings...")
    time.sleep(5)

    trigger_p03()

    print("\nWaiting 20s for P03 processing + gap resolution...")
    time.sleep(20)

    # Show gaps after
    check_gaps_after()

    print("\n" + "=" * 60)
    print("DONE - Check if gaps changed from PENDING to RESOLVED")
    print("=" * 60)


if __name__ == "__main__":
    main()
