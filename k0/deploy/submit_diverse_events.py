"""
Submit multiple diverse test events to K0 for P03 consolidation testing.

Uses the same envelope building logic as provision_and_submit.py.
"""

import base64
import hashlib
import secrets
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
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


# =============================================================================
# DIVERSE TEST EVENTS - Designed to test P03 algorithms
# =============================================================================

TEST_EVENTS = [
    # CLUSTER 1: Family Events
    {
        "text": "Picked up Emma from soccer practice at City Sports Complex. She scored 2 goals today!",
        "participants": ["Emma"],
        "location_name": "City Sports Complex",
        "activity_type": "FAMILY",
    },
    {
        "text": "Emma's piano recital at Lincoln School. She played Fur Elise beautifully.",
        "participants": ["Emma"],
        "location_name": "Lincoln School",
        "activity_type": "FAMILY",
    },
    {
        "text": "Family dinner with Emma and Jake at home. Made lasagna together.",
        "participants": ["Emma", "Jake"],
        "location_name": "Home",
        "activity_type": "FAMILY",
    },
    {
        "text": "Drove Emma to her friend Sofia's birthday party at Chuck E Cheese.",
        "participants": ["Emma", "Sofia"],
        "location_name": "Chuck E Cheese",
        "activity_type": "FAMILY",
    },
    # CLUSTER 2: Work Events
    {
        "text": "Team standup meeting with John, Lisa, and Mike. Discussed Q2 roadmap priorities.",
        "participants": ["John", "Lisa", "Mike"],
        "location_name": "Office Conference Room B",
        "activity_type": "WORK",
    },
    {
        "text": "One-on-one with manager Sarah about promotion timeline and career goals.",
        "participants": ["Sarah"],
        "location_name": "Sarah's Office",
        "activity_type": "WORK",
    },
    {
        "text": "Presented quarterly results to the executive team. CEO David was impressed.",
        "participants": ["David"],
        "location_name": "Main Boardroom",
        "activity_type": "WORK",
    },
    {
        "text": "Code review session with Mike. Fixed critical bug in authentication module.",
        "participants": ["Mike"],
        "location_name": "Office",
        "activity_type": "WORK",
    },
    {
        "text": "Lunch with coworkers at Chipotle. Discussed the new project deadline.",
        "participants": ["John", "Lisa"],
        "location_name": "Chipotle",
        "activity_type": "WORK",
    },
    # CLUSTER 3: Health & Fitness
    {
        "text": "Morning run at Central Park. 5 miles in 42 minutes, feeling great!",
        "participants": [],
        "location_name": "Central Park",
        "activity_type": "HEALTH",
    },
    {
        "text": "Doctor appointment with Dr. Smith for annual checkup. Blood pressure 120/80.",
        "participants": ["Dr. Smith"],
        "location_name": "Medical Center",
        "activity_type": "HEALTH",
    },
    {
        "text": "Yoga class with instructor Maria. Worked on flexibility and breathing.",
        "participants": ["Maria"],
        "location_name": "Downtown Yoga Studio",
        "activity_type": "HEALTH",
    },
    {
        "text": "Dentist checkup with Dr. Johnson. No cavities, scheduled cleaning for next month.",
        "participants": ["Dr. Johnson"],
        "location_name": "Smile Dental Clinic",
        "activity_type": "HEALTH",
    },
    # CLUSTER 4: Social Events
    {
        "text": "Coffee with best friend Rachel at Starbucks. She's excited about her new job at Google.",
        "participants": ["Rachel"],
        "location_name": "Starbucks Downtown",
        "activity_type": "SOCIAL",
    },
    {
        "text": "Birthday party for Tom at his apartment. About 20 people showed up.",
        "participants": ["Tom"],
        "location_name": "Tom's Apartment",
        "activity_type": "SOCIAL",
    },
    {
        "text": "Dinner with college friends at Italian restaurant Bella Notte. Great pasta!",
        "participants": ["Alex", "Chris", "Sam"],
        "location_name": "Bella Notte",
        "activity_type": "SOCIAL",
    },
    {
        "text": "Movie night watching Inception with roommate Kevin. Still confused about the ending.",
        "participants": ["Kevin"],
        "location_name": "Home",
        "activity_type": "SOCIAL",
    },
    # CLUSTER 5: Learning & Personal Development
    {
        "text": "Finished reading 'Atomic Habits' by James Clear. Key insight: systems over goals.",
        "participants": [],
        "location_name": "Home",
        "activity_type": "LEARNING",
    },
    {
        "text": "Online Python course on Coursera. Completed module on machine learning basics.",
        "participants": [],
        "location_name": "Home",
        "activity_type": "LEARNING",
    },
    {
        "text": "Attended webinar on AI and the future of work by Stanford professor Andrew Ng.",
        "participants": ["Andrew Ng"],
        "location_name": "Online",
        "activity_type": "LEARNING",
    },
    # NEAR-DUPLICATES: To test R3 deduplication
    {
        "text": "Had coffee with Rachel at Starbucks. She mentioned her new position at Google.",
        "participants": ["Rachel"],
        "location_name": "Starbucks",
        "activity_type": "SOCIAL",
    },
    {
        "text": "Met Rachel for coffee at the Starbucks downtown. Talked about her Google job.",
        "participants": ["Rachel"],
        "location_name": "Starbucks Downtown",
        "activity_type": "SOCIAL",
    },
    # HIGH IMPORTANCE: Critical life events (MILESTONES)
    {
        "text": "Got promoted to Senior Engineer! Celebrated with team. 15% salary increase.",
        "participants": ["Team"],
        "location_name": "Office",
        "activity_type": "MILESTONE",
    },
    {
        "text": "Signed lease for new apartment in Brooklyn. Moving in next month.",
        "participants": [],
        "location_name": "Brooklyn",
        "activity_type": "MILESTONE",
    },
    {
        "text": "Emma's first day of kindergarten at Lincoln Elementary. She was so brave!",
        "participants": ["Emma"],
        "location_name": "Lincoln Elementary",
        "activity_type": "MILESTONE",
    },
    # TRAVEL EVENTS: Geographic diversity
    {
        "text": "Flight to San Francisco for tech conference. Staying at Marriott Union Square.",
        "participants": [],
        "location_name": "San Francisco",
        "activity_type": "TRAVEL",
    },
    {
        "text": "Visited Golden Gate Bridge. Amazing views of the bay and Alcatraz.",
        "participants": [],
        "location_name": "Golden Gate Bridge",
        "activity_type": "TRAVEL",
    },
    {
        "text": "Weekend trip to Boston with family. Walked the Freedom Trail.",
        "participants": ["Emma", "Jake"],
        "location_name": "Boston",
        "activity_type": "TRAVEL",
    },
    # FINANCIAL EVENTS
    {
        "text": "Paid off student loans! 10 years of payments finally done.",
        "participants": [],
        "location_name": "Home",
        "activity_type": "FINANCIAL",
    },
    {
        "text": "Met with financial advisor Jennifer about retirement planning and 401k.",
        "participants": ["Jennifer"],
        "location_name": "Fidelity Office",
        "activity_type": "FINANCIAL",
    },
    # ==========================================================================
    # INTENT-BASED EVENTS: For testing GAP-001 Intent & Ingress Matrix
    # UltraBERT will detect: intent, emotions, NER, temporal expressions
    # ==========================================================================
    # SET_REMINDER intents → UltraBERT should detect "set_reminder"
    {
        "text": "Remind me to call Mom tomorrow at 3pm for her birthday.",
        "participants": ["Mom"],
        "location_name": "Home",
        "activity_type": "REMINDER",
    },
    {
        "text": "Need to remember to submit the quarterly report by Friday at 5pm.",
        "participants": [],
        "location_name": "Office",
        "activity_type": "REMINDER",
    },
    {
        "text": "Set a reminder to pick up Emma from soccer practice at 4:30pm.",
        "participants": ["Emma"],
        "location_name": "City Sports Complex",
        "activity_type": "REMINDER",
    },
    {
        "text": "Don't let me forget to water the plants in 2 hours.",
        "participants": [],
        "location_name": "Home",
        "activity_type": "REMINDER",
    },
    {
        "text": "Remind me next Monday to schedule the dentist appointment.",
        "participants": ["Dr. Johnson"],
        "location_name": "Home",
        "activity_type": "REMINDER",
    },
    # SEEK_ADVICE intents → UltraBERT should detect "seek_advice"
    {
        "text": "Should I take the new job offer from Google or stay at my current company?",
        "participants": [],
        "location_name": "Home",
        "activity_type": "DECISION",
    },
    {
        "text": "I'm trying to decide between buying a house in Brooklyn or renting in Manhattan.",
        "participants": [],
        "location_name": "Home",
        "activity_type": "DECISION",
    },
    {
        "text": "What do you think - should Emma switch from soccer to basketball?",
        "participants": ["Emma"],
        "location_name": "Home",
        "activity_type": "DECISION",
    },
    {
        "text": "I need advice on whether to invest in stocks or bonds right now.",
        "participants": ["Jennifer"],
        "location_name": "Fidelity Office",
        "activity_type": "DECISION",
    },
    # REFLECT intents → UltraBERT should detect "reflect"
    {
        "text": "I learned that consistency beats intensity. My daily 20-minute workouts are more effective than occasional 2-hour sessions.",
        "participants": [],
        "location_name": "Central Park",
        "activity_type": "REFLECTION",
    },
    {
        "text": "Looking back, I realize that setting clear boundaries at work has made me much happier.",
        "participants": [],
        "location_name": "Home",
        "activity_type": "REFLECTION",
    },
    {
        "text": "Today I understood that listening more and talking less makes conversations richer.",
        "participants": ["Rachel"],
        "location_name": "Starbucks",
        "activity_type": "REFLECTION",
    },
    {
        "text": "The key insight from the parenting book is that quality time matters more than quantity.",
        "participants": ["Emma", "Jake"],
        "location_name": "Home",
        "activity_type": "REFLECTION",
    },
    # EXPRESS_FEELING intents → UltraBERT should detect "express_feeling" + emotions
    {
        "text": "I'm feeling so grateful for my family today. They always support me.",
        "participants": ["Emma", "Jake"],
        "location_name": "Home",
        "activity_type": "EMOTIONAL",
    },
    {
        "text": "Really anxious about the presentation tomorrow. What if I mess up?",
        "participants": [],
        "location_name": "Office",
        "activity_type": "EMOTIONAL",
    },
    {
        "text": "I'm so happy about getting the promotion! All the hard work paid off.",
        "participants": ["Sarah", "Team"],
        "location_name": "Office",
        "activity_type": "EMOTIONAL",
    },
    {
        "text": "Feeling nostalgic looking at old photos from college with Alex and Chris.",
        "participants": ["Alex", "Chris"],
        "location_name": "Home",
        "activity_type": "EMOTIONAL",
    },
    {
        "text": "I'm frustrated that the project deadline got moved up again.",
        "participants": ["John", "Mike"],
        "location_name": "Office",
        "activity_type": "EMOTIONAL",
    },
    # SHARE_NEWS intents → UltraBERT should detect "share_news" + NER entities
    {
        "text": "Exciting news! Emma got accepted into the gifted program at school!",
        "participants": ["Emma"],
        "location_name": "Lincoln Elementary",
        "activity_type": "NEWS",
    },
    {
        "text": "Rachel just told me she's getting married to Tom in June!",
        "participants": ["Rachel", "Tom"],
        "location_name": "Starbucks",
        "activity_type": "NEWS",
    },
    {
        "text": "My brother Jake just had his first baby - a girl named Sophie!",
        "participants": ["Jake", "Sophie"],
        "location_name": "Hospital",
        "activity_type": "NEWS",
    },
    {
        "text": "The company announced we're expanding to London next year!",
        "participants": ["David"],
        "location_name": "Main Boardroom",
        "activity_type": "NEWS",
    },
    # QUERY_MEMORY intents → UltraBERT should detect "query_memory" + NER entities
    {
        "text": "What was that recipe Mom shared last Thanksgiving?",
        "participants": ["Mom"],
        "location_name": "Home",
        "activity_type": "QUERY",
    },
    {
        "text": "When did Emma have her piano recital at Lincoln School?",
        "participants": ["Emma"],
        "location_name": "Home",
        "activity_type": "QUERY",
    },
    {
        "text": "What did Dr. Smith say about my blood pressure at the last checkup?",
        "participants": ["Dr. Smith"],
        "location_name": "Home",
        "activity_type": "QUERY",
    },
    {
        "text": "How much did we spend on the San Francisco trip last month?",
        "participants": [],
        "location_name": "Home",
        "activity_type": "QUERY",
    },
]


def execute_sql(sql_statements):
    full_sql = "; ".join(sql_statements)
    import os

    # Detect if we're inside Docker container (no docker command available)
    if os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST"):
        # Inside container - use psql directly via pgbouncer
        cmd = [
            "psql",
            "postgresql://postgres:postgres@pgbouncer:6432/k0_kernel",
            "-c",
            full_sql,
        ]
    else:
        # Outside container - use docker exec
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
    from datetime import timedelta

    # Use current time for envelope (to pass clock skew checks)
    # But use varied timestamps in the event_time_utc field within body
    now_utc = datetime.now(timezone.utc)

    # For event_time_utc in body, use diverse times within acceptable window
    # Group events by activity type with small hour offsets
    cluster_offsets = {
        "FAMILY": 0,  # Now
        "WORK": 0.5,  # 30 mins ago
        "HEALTH": 1,  # 1 hour ago
        "SOCIAL": 1.5,  # 1.5 hours ago
        "LEARNING": 2,  # 2 hours ago
        "MILESTONE": 2.5,  # 2.5 hours ago
        "TRAVEL": 3,  # 3 hours ago
        "FINANCIAL": 3.5,  # 3.5 hours ago
        "GENERAL": random.uniform(0, 4),  # Random
    }

    activity = event_data.get("activity_type", "GENERAL")
    hour_offset = cluster_offsets.get(activity, random.uniform(0, 4))

    # Add some minutes variation within the same cluster (0-15 mins)
    minute_offset = random.uniform(0, 0.25)  # 0-15 minutes in hours

    # Calculate event time (in past, but stored in body for P03)
    event_time = now_utc - timedelta(hours=hour_offset + minute_offset)

    body = {
        "operation": "UPSERT",
        "text": event_data["text"],
        "value": index * 10,
        "timestamp": event_time.isoformat(),
        "event_time": event_time.isoformat(),  # M08 looks for "event_time" in body
        "event_time_utc": event_time.isoformat(),  # Also include for compatibility
        "participants": event_data.get("participants", []),
        "location_name": event_data.get("location_name", "Unknown"),
        "activity_type": event_data.get("activity_type", "GENERAL"),
    }

    body_json = canonical_json(body)
    body_bytes = body_json.encode("utf-8")
    payload_hash = hash_payload(body_bytes)

    trace_id = str(uuid.uuid4())
    # Use NOW for envelope timestamp (clock skew check)
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

    # Compute envelope_sha256
    envelope_sha256 = compute_envelope_sha256(envelope)
    envelope["envelope_sha256"] = envelope_sha256

    # Sign
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
            "reason": "diverse_events_test",
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


def check_stats():
    """Check database statistics."""
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)

    result = execute_sql([f"SELECT COUNT(*) FROM st_hipp_events WHERE tenant_id = '{TENANT_ID}'"])
    if result:
        print(f"Events: {result.strip()}")

    result = execute_sql([f"SELECT COUNT(*) FROM st_vec WHERE tenant_id = '{TENANT_ID}'"])
    if result:
        print(f"Embeddings: {result.strip()}")


def main():
    print("=" * 60)
    print("P03 CONSOLIDATION - DIVERSE EVENTS TEST")
    print(
        f"Submitting {len(TEST_EVENTS)} events across {len(set(e['activity_type'] for e in TEST_EVENTS))} categories"
    )
    print("=" * 60)

    signing_key = get_signing_key()

    if not provision_device(signing_key):
        print("Failed to provision device. Exiting.")
        return

    time.sleep(0.5)

    print(f"\nSubmitting {len(TEST_EVENTS)} events...")
    success_count = 0
    categories = {}

    for i, event_data in enumerate(TEST_EVENTS, 1):
        try:
            response = submit_event(signing_key, event_data, i)
            activity = event_data.get("activity_type", "UNKNOWN")

            if response.status_code == 200:
                text_preview = (
                    event_data["text"][:45] + "..."
                    if len(event_data["text"]) > 45
                    else event_data["text"]
                )
                print(f"  [{i:2}] OK {activity:10} | {text_preview}")
                success_count += 1
                categories[activity] = categories.get(activity, 0) + 1
            else:
                error = response.json().get("error", {}).get("reason", response.text[:50])
                print(f"  [{i:2}] FAIL {activity:10} | {error}")
        except Exception as e:
            print(f"  [{i:2}] ERROR: {e}")

        time.sleep(0.03)

    print(f"\n{'=' * 60}")
    print(f"SUBMITTED: {success_count}/{len(TEST_EVENTS)} events")
    print("=" * 60)
    print("\nBy category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat:12}: {count}")

    print("\nWaiting 20s for P02 embeddings...")
    time.sleep(20)

    trigger_p03()

    print("\nWaiting 5s for P03 processing...")
    time.sleep(5)

    check_stats()

    print("\n" + "=" * 60)
    print("Check logs with: docker logs k0-kernel --tail 100 | Select-String 'R0:|R1:|R2:|R3:|R4:'")
    print("=" * 60)


if __name__ == "__main__":
    main()
