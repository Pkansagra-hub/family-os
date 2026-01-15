"""
Submit multiple diverse test events to K0 for P03 consolidation testing.

This script creates events that will exercise different P03 algorithms:
- R2 Clustering: Events with similar/different embeddings
- R3 Deduplication: Near-duplicate and unique events
- R4 Entity Extraction: Events with people, places, organizations
- Decay/Importance: Events with varying importance levels
"""

import base64
import hashlib
import random
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

# Memory Model: Single-User Mode
# All events are attributed to ONE user (the owner of this memory system)
# For household mode, this would be read from device config
PRIMARY_ACTOR_ID = "Prince"


def execute_sql(sql_statements):
    full_sql = "; ".join(sql_statements)
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
    process = subprocess.run(cmd, capture_output=True, check=True)
    return process.stdout.decode("utf-8")


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


# =============================================================================
# DIVERSE TEST EVENTS - Designed to test P03 algorithms
# =============================================================================

TEST_EVENTS = [
    # --------------------------------------------------------------------------
    # CLUSTER 1: Family Events (should cluster together)
    # --------------------------------------------------------------------------
    {
        "text": "Picked up Emma from soccer practice at City Sports Complex. She scored 2 goals today!",
        "participants": ["Emma"],
        "location_name": "City Sports Complex",
        "activity_type": "FAMILY",
        "entities": ["Emma", "City Sports Complex"],
    },
    {
        "text": "Emma's piano recital at Lincoln School. She played Fur Elise beautifully.",
        "participants": ["Emma"],
        "location_name": "Lincoln School",
        "activity_type": "FAMILY",
        "entities": ["Emma", "Lincoln School", "Fur Elise"],
    },
    {
        "text": "Family dinner with Emma and Jake at home. Made lasagna together.",
        "participants": ["Emma", "Jake"],
        "location_name": "Home",
        "activity_type": "FAMILY",
        "entities": ["Emma", "Jake"],
    },
    {
        "text": "Drove Emma to her friend Sofia's birthday party at Chuck E Cheese.",
        "participants": ["Emma", "Sofia"],
        "location_name": "Chuck E Cheese",
        "activity_type": "FAMILY",
        "entities": ["Emma", "Sofia", "Chuck E Cheese"],
    },
    # --------------------------------------------------------------------------
    # CLUSTER 2: Work Events (should cluster together)
    # --------------------------------------------------------------------------
    {
        "text": "Team standup meeting with John, Lisa, and Mike. Discussed Q2 roadmap priorities.",
        "participants": ["John", "Lisa", "Mike"],
        "location_name": "Office Conference Room B",
        "activity_type": "WORK",
        "entities": ["John", "Lisa", "Mike", "Office Conference Room B"],
    },
    {
        "text": "One-on-one with manager Sarah about promotion timeline and career goals.",
        "participants": ["Sarah"],
        "location_name": "Sarah's Office",
        "activity_type": "WORK",
        "entities": ["Sarah"],
    },
    {
        "text": "Presented quarterly results to the executive team. CEO David was impressed.",
        "participants": ["David", "Executive Team"],
        "location_name": "Main Boardroom",
        "activity_type": "WORK",
        "entities": ["David", "Main Boardroom"],
    },
    {
        "text": "Code review session with Mike. Fixed critical bug in authentication module.",
        "participants": ["Mike"],
        "location_name": "Office",
        "activity_type": "WORK",
        "entities": ["Mike"],
    },
    {
        "text": "Lunch with coworkers at Chipotle. Discussed the new project deadline.",
        "participants": ["John", "Lisa"],
        "location_name": "Chipotle",
        "activity_type": "WORK",
        "entities": ["John", "Lisa", "Chipotle"],
    },
    # --------------------------------------------------------------------------
    # CLUSTER 3: Health & Fitness (should cluster together)
    # --------------------------------------------------------------------------
    {
        "text": "Morning run at Central Park. 5 miles in 42 minutes, feeling great!",
        "participants": [],
        "location_name": "Central Park",
        "activity_type": "HEALTH",
        "entities": ["Central Park"],
    },
    {
        "text": "Doctor appointment with Dr. Smith for annual checkup. Blood pressure 120/80.",
        "participants": ["Dr. Smith"],
        "location_name": "Medical Center",
        "activity_type": "HEALTH",
        "entities": ["Dr. Smith", "Medical Center"],
    },
    {
        "text": "Yoga class with instructor Maria. Worked on flexibility and breathing.",
        "participants": ["Maria"],
        "location_name": "Downtown Yoga Studio",
        "activity_type": "HEALTH",
        "entities": ["Maria", "Downtown Yoga Studio"],
    },
    {
        "text": "Dentist checkup with Dr. Johnson. No cavities, scheduled cleaning for next month.",
        "participants": ["Dr. Johnson"],
        "location_name": "Smile Dental Clinic",
        "activity_type": "HEALTH",
        "entities": ["Dr. Johnson", "Smile Dental Clinic"],
    },
    # --------------------------------------------------------------------------
    # CLUSTER 4: Social Events (should cluster together)
    # --------------------------------------------------------------------------
    {
        "text": "Coffee with best friend Rachel at Starbucks. She's excited about her new job at Google.",
        "participants": ["Rachel"],
        "location_name": "Starbucks Downtown",
        "activity_type": "SOCIAL",
        "entities": ["Rachel", "Starbucks", "Google"],
    },
    {
        "text": "Birthday party for Tom at his apartment. About 20 people showed up.",
        "participants": ["Tom"],
        "location_name": "Tom's Apartment",
        "activity_type": "SOCIAL",
        "entities": ["Tom"],
    },
    {
        "text": "Dinner with college friends at Italian restaurant Bella Notte. Great pasta!",
        "participants": ["Alex", "Chris", "Sam"],
        "location_name": "Bella Notte",
        "activity_type": "SOCIAL",
        "entities": ["Alex", "Chris", "Sam", "Bella Notte"],
    },
    {
        "text": "Movie night watching Inception with roommate Kevin. Still confused about the ending.",
        "participants": ["Kevin"],
        "location_name": "Home",
        "activity_type": "SOCIAL",
        "entities": ["Kevin", "Inception"],
    },
    # --------------------------------------------------------------------------
    # CLUSTER 5: Learning & Personal Development
    # --------------------------------------------------------------------------
    {
        "text": "Finished reading 'Atomic Habits' by James Clear. Key insight: systems over goals.",
        "participants": [],
        "location_name": "Home",
        "activity_type": "LEARNING",
        "entities": ["Atomic Habits", "James Clear"],
    },
    {
        "text": "Online Python course on Coursera. Completed module on machine learning basics.",
        "participants": [],
        "location_name": "Home",
        "activity_type": "LEARNING",
        "entities": ["Python", "Coursera"],
    },
    {
        "text": "Attended webinar on AI and the future of work by Stanford professor Andrew Ng.",
        "participants": ["Andrew Ng"],
        "location_name": "Online",
        "activity_type": "LEARNING",
        "entities": ["Andrew Ng", "Stanford", "AI"],
    },
    # --------------------------------------------------------------------------
    # NEAR-DUPLICATES: To test R3 deduplication
    # --------------------------------------------------------------------------
    {
        "text": "Had coffee with Rachel at Starbucks. She mentioned her new position at Google.",
        "participants": ["Rachel"],
        "location_name": "Starbucks",
        "activity_type": "SOCIAL",
        "entities": ["Rachel", "Starbucks", "Google"],
    },
    {
        "text": "Met Rachel for coffee at the Starbucks downtown. Talked about her Google job.",
        "participants": ["Rachel"],
        "location_name": "Starbucks Downtown",
        "activity_type": "SOCIAL",
        "entities": ["Rachel", "Starbucks", "Google"],
    },
    # --------------------------------------------------------------------------
    # HIGH IMPORTANCE: Critical life events
    # --------------------------------------------------------------------------
    {
        "text": "Got promoted to Senior Engineer! Celebrated with team. 15% salary increase.",
        "participants": ["Team"],
        "location_name": "Office",
        "activity_type": "MILESTONE",
        "entities": ["Senior Engineer"],
    },
    {
        "text": "Signed lease for new apartment in Brooklyn. Moving in next month.",
        "participants": [],
        "location_name": "Brooklyn",
        "activity_type": "MILESTONE",
        "entities": ["Brooklyn"],
    },
    {
        "text": "Emma's first day of kindergarten at Lincoln Elementary. She was so brave!",
        "participants": ["Emma"],
        "location_name": "Lincoln Elementary",
        "activity_type": "MILESTONE",
        "entities": ["Emma", "Lincoln Elementary"],
    },
    # --------------------------------------------------------------------------
    # TRAVEL EVENTS: Geographic diversity
    # --------------------------------------------------------------------------
    {
        "text": "Flight to San Francisco for tech conference. Staying at Marriott Union Square.",
        "participants": [],
        "location_name": "San Francisco",
        "activity_type": "TRAVEL",
        "entities": ["San Francisco", "Marriott", "Union Square"],
    },
    {
        "text": "Visited Golden Gate Bridge. Amazing views of the bay and Alcatraz.",
        "participants": [],
        "location_name": "Golden Gate Bridge",
        "activity_type": "TRAVEL",
        "entities": ["Golden Gate Bridge", "Alcatraz"],
    },
    {
        "text": "Weekend trip to Boston with family. Walked the Freedom Trail.",
        "participants": ["Emma", "Jake"],
        "location_name": "Boston",
        "activity_type": "TRAVEL",
        "entities": ["Boston", "Freedom Trail", "Emma", "Jake"],
    },
    # --------------------------------------------------------------------------
    # FINANCIAL EVENTS
    # --------------------------------------------------------------------------
    {
        "text": "Paid off student loans! 10 years of payments finally done.",
        "participants": [],
        "location_name": "Home",
        "activity_type": "FINANCIAL",
        "entities": [],
    },
    {
        "text": "Met with financial advisor Jennifer about retirement planning and 401k.",
        "participants": ["Jennifer"],
        "location_name": "Fidelity Office",
        "activity_type": "FINANCIAL",
        "entities": ["Jennifer", "Fidelity", "401k"],
    },
]


def provision_device(signing_key):
    """Provision device in PostgreSQL."""
    verify_key_b64 = encode_base64url(signing_key.verify_key.encode())
    now = datetime.now(timezone.utc).isoformat()
    hmac_secret_hex = secrets.token_bytes(32).hex()

    print("\nProvisioning device...")
    try:
        # Delete existing
        execute_sql(
            [
                f"DELETE FROM st_device_keys WHERE device_id = '{DEVICE_ID}'",
                f"DELETE FROM st_devices WHERE device_id = '{DEVICE_ID}'",
            ]
        )

        # Insert device
        execute_sql(
            [
                f"INSERT INTO st_devices (device_id, tenant_id, space_id, mls_group_id, provisioned_ts, hmac_secret) "
                f"VALUES ('{DEVICE_ID}', '{TENANT_ID}', '{SPACE_ID}', 'mls-group-1', '{now}', '\\x{hmac_secret_hex}')"
            ]
        )

        # Insert device key
        execute_sql(
            [
                f"INSERT INTO st_device_keys (device_id, key_version, verify_key, key_state, registered_ts, activated_ts) "
                f"VALUES ('{DEVICE_ID}', '1', '{verify_key_b64}', 'ACTIVE', '{now}', '{now}')"
            ]
        )

        # Register schema
        schema_sha = hashlib.sha256(f"{SCHEMA_URI}@{SCHEMA_VERSION}".encode("utf-8")).hexdigest()
        execute_sql(
            [
                f"INSERT INTO schema_registry (schema_uri, version, sha256, status) "
                f"VALUES ('{SCHEMA_URI}', '{SCHEMA_VERSION}', '{schema_sha}', 'ACTIVE') "
                f"ON CONFLICT (schema_uri, version) DO NOTHING"
            ]
        )

        print("Device provisioned successfully!")
        return True
    except Exception as e:
        print(f"Provisioning error: {e}")
        return False


def clear_existing_events():
    """Clear existing test events to start fresh."""
    print("\nClearing existing events...")
    try:
        execute_sql(
            [
                f"DELETE FROM st_vec WHERE tenant_id = '{TENANT_ID}' AND space_id = '{SPACE_ID}'",
                f"DELETE FROM st_hipp_events WHERE tenant_id = '{TENANT_ID}' AND space_id = '{SPACE_ID}'",
                f"DELETE FROM st_p03_consolidation_offsets WHERE tenant_id = '{TENANT_ID}' AND space_id = '{SPACE_ID}'",
            ]
        )
        print("Cleared existing events!")
        return True
    except Exception as e:
        print(f"Clear error: {e}")
        return False


def submit_event(signing_key, event_data, index):
    """Submit a single event envelope."""
    # Spread events over past 24 hours
    hours_ago = random.uniform(0, 24)
    now_utc = datetime.now(timezone.utc) - timedelta(hours=hours_ago)

    body = {
        "operation": "UPSERT",
        "text": event_data["text"],
        "value": index * 10,
        "timestamp": now_utc.isoformat(),
        "event_time_utc": now_utc.isoformat(),
        "participants": event_data.get("participants", []),
        "location_name": event_data.get("location_name", "Unknown"),
        "activity_type": event_data.get("activity_type", "GENERAL"),
        "entities": event_data.get("entities", []),
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
        "actor": PRIMARY_ACTOR_ID,  # Single-user mode: all events from ONE user
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
            "reason": "test_events_verification",
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


def check_database_stats():
    """Check database statistics after processing."""
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)

    try:
        # Count events
        result = execute_sql(
            [f"SELECT COUNT(*) as total FROM st_hipp_events WHERE tenant_id = '{TENANT_ID}'"]
        )
        print(f"\nEvents in st_hipp_events: {result}")

        # Count embeddings
        result = execute_sql(
            [f"SELECT COUNT(*) as total FROM st_vec WHERE tenant_id = '{TENANT_ID}'"]
        )
        print(f"Embeddings in st_vec: {result}")

        # Check consolidation offset
        result = execute_sql(
            [f"SELECT * FROM st_p03_consolidation_offsets WHERE tenant_id = '{TENANT_ID}'"]
        )
        print(f"Consolidation offsets: {result}")

    except Exception as e:
        print(f"Stats error: {e}")


def main():
    print("=" * 60)
    print("P03 CONSOLIDATION ALGORITHM TEST")
    print(f"Submitting {len(TEST_EVENTS)} diverse events")
    print("=" * 60)

    signing_key = get_signing_key()

    # Provision device
    if not provision_device(signing_key):
        print("Failed to provision device. Exiting.")
        return

    # Clear existing events
    clear_existing_events()

    time.sleep(0.5)

    # Submit all events
    print(f"\nSubmitting {len(TEST_EVENTS)} events...")
    success_count = 0

    categories = {}
    for i, event_data in enumerate(TEST_EVENTS, 1):
        try:
            response = submit_event(signing_key, event_data, i)
            activity = event_data.get("activity_type", "UNKNOWN")

            if response.status_code == 200:
                text_preview = (
                    event_data["text"][:50] + "..."
                    if len(event_data["text"]) > 50
                    else event_data["text"]
                )
                print(f"  [{i:2}] OK {activity:10} | {text_preview}")
                success_count += 1
                categories[activity] = categories.get(activity, 0) + 1
            else:
                print(f"  [{i:2}] FAILED ({response.status_code}): {response.text[:80]}")
        except Exception as e:
            print(f"  [{i:2}] ERROR: {e}")

        time.sleep(0.05)  # Small delay between submissions

    # Summary
    print(f"\n{'=' * 60}")
    print(f"SUBMISSION SUMMARY: {success_count}/{len(TEST_EVENTS)} events")
    print("=" * 60)
    print("\nEvents by category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat:12}: {count}")

    # Wait for embeddings to be generated
    print("\nWaiting 5 seconds for P02 embedding generation...")
    time.sleep(5)

    # Trigger P03
    trigger_p03()

    # Wait and check results
    print("\nWaiting 3 seconds for P03 processing...")
    time.sleep(3)

    check_database_stats()

    print("\n" + "=" * 60)
    print("To see P03 logs, run:")
    print(
        "  docker logs k0-kernel --tail 100 | Select-String 'R0:|R1:|R2:|R3:|R4:|R5:|R6:|R7:|R8:'"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
