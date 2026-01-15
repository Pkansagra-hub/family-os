"""
Submit real-life events to K0 simulating an actual person's daily schedule.

Unlike submit_diverse_events.py which uses simple time offsets, this script
simulates realistic timing patterns based on:
- Daily routines (wake up, work blocks, meals, gym, wind-down)
- Location-based time windows (gym = evening, office = work hours)
- Event type patterns (routines = morning, reflections = evening)

Events are spread across multiple days with realistic temporal distribution.
"""

import base64
import hashlib
import json
import random
import secrets
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from nacl.signing import SigningKey

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from k0.security import canonical_envelope, canonical_json, compute_envelope_sha256, hash_payload
from k0.security.crypto import encode_base64url

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://localhost:8080"
TENANT_ID = "tenant-test"
SPACE_ID = "space-home"
DEVICE_ID = "device-reallife-1"
SCHEMA_URI = "schema://memory.delta"
SCHEMA_VERSION = "1.0"
PG_USER = "k0user"
PG_DB = "k0_kernel"

# Memory Model: Single-User Mode - All events from ONE person
PRIMARY_ACTOR_ID = "Prince"

# Simulation Configuration
DAYS_TO_SIMULATE = 10  # Spread events across 10 days (realistic week+ window)
EVENTS_PER_DAY_RANGE = (40, 80)  # Random events per day
SUBMISSION_DELAY_MS = 30  # Delay between event submissions


# =============================================================================
# DAILY SCHEDULE TIMETABLE
# =============================================================================
# This defines realistic time windows for different activities
# Format: (start_hour, end_hour) - 24-hour format

SCHEDULE = {
    # Morning Routine (6:00 AM - 8:00 AM)
    "morning_routine": {
        "hours": (6, 8),
        "locations": ["Home"],
        "keywords": ["wake", "routine", "morning", "nasal rinse"],
    },
    # Breakfast / Early Work Prep (7:30 AM - 9:00 AM)
    "breakfast": {"hours": (7.5, 9), "locations": ["Home"], "keywords": ["breakfast", "coffee"]},
    # Deep Work Block 1 (9:00 AM - 12:00 PM)
    "work_morning": {
        "hours": (9, 12),
        "locations": ["Home Office"],
        "keywords": [
            "code",
            "debug",
            "schema",
            "pipeline",
            "P0",
            "K0",
            "K1",
            "FamilyOS",
            "deploy",
            "build",
            "test",
            "refactor",
            "migration",
            "API",
            "database",
        ],
    },
    # Lunch (12:00 PM - 1:00 PM)
    "lunch": {"hours": (12, 13), "locations": ["Home", "Starbucks"], "keywords": ["lunch", "eat"]},
    # Deep Work Block 2 (1:00 PM - 5:00 PM)
    "work_afternoon": {
        "hours": (13, 17),
        "locations": ["Home Office"],
        "keywords": [
            "code",
            "debug",
            "schema",
            "pipeline",
            "P0",
            "K0",
            "K1",
            "FamilyOS",
            "deploy",
            "build",
            "test",
            "refactor",
            "meeting",
            "review",
        ],
    },
    # Gym / Exercise (5:30 PM - 7:30 PM)
    "gym": {
        "hours": (17.5, 19.5),
        "locations": ["Gym"],
        "keywords": ["gym", "workout", "cardio", "leg", "chest", "back", "push", "pull"],
    },
    # Dinner / Family Time (7:00 PM - 9:00 PM)
    "dinner": {
        "hours": (19, 21),
        "locations": ["Home"],
        "keywords": ["dinner", "Panda", "family", "cook"],
    },
    # Evening Wind-Down (9:00 PM - 11:00 PM)
    "evening": {
        "hours": (21, 23),
        "locations": ["Home", "Home Office"],
        "keywords": ["evening", "wind-down", "relax", "read", "reflect"],
    },
    # Late Night Work (occasional) (10:00 PM - 1:00 AM)
    "late_work": {
        "hours": (22, 25),
        "locations": ["Home Office"],
        "keywords": ["late", "night", "staying up", "overtime"],
    },
}

# Location-based default time slots
LOCATION_SCHEDULES = {
    "Home Office": [(9, 12), (13, 17), (21, 24)],  # Work hours + evening coding
    "Gym": [(17.5, 19.5), (6, 7.5)],  # Evening gym or early morning
    "Home": [(6, 9), (12, 13), (19, 23)],  # Morning, lunch, evening
    "Starbucks": [(10, 14), (15, 17)],  # Coffee breaks
    "Neighborhood": [(18, 20), (7, 8)],  # Walks
    "Medical Center": [(9, 16)],  # Business hours
    "DMV": [(9, 16)],  # Business hours
    "UTD": [(10, 16)],  # University hours
}

# Event type patterns for timing
EVENT_TYPE_PATTERNS = {
    "Routine": {"prefer_hours": [(6, 8), (21, 23)], "weight": 1.5},  # Morning/evening routines
    "Remind": {"prefer_hours": [(8, 10), (17, 19)], "weight": 1.0},  # Start/end of day
    "Emotional": {"prefer_hours": [(20, 23)], "weight": 1.2},  # Evening reflections
    "Reflection": {"prefer_hours": [(21, 23)], "weight": 1.3},  # Evening
    "Milestone": {"prefer_hours": [(14, 18)], "weight": 1.0},  # Afternoon achievements
    "Gym": {"prefer_hours": [(17.5, 19.5), (6, 7.5)], "weight": 2.0},  # Strict gym times
    "Learning": {"prefer_hours": [(9, 12), (20, 22)], "weight": 1.0},  # Focus times
    "Query": {"prefer_hours": [(9, 21)], "weight": 0.8},  # Any time
    "News": {"prefer_hours": [(8, 10), (17, 19)], "weight": 1.0},  # Morning/evening
    "Decision": {"prefer_hours": [(10, 15)], "weight": 1.0},  # Mid-day clarity
    "Travel": {"prefer_hours": [(6, 22)], "weight": 0.5},  # Variable
}


# =============================================================================
# EVENT LOADING AND CLASSIFICATION
# =============================================================================


def load_events_from_jsonl(filepath: Path) -> list[dict[str, Any]]:
    """Load events from JSONL file (one JSON object per line)."""
    events = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError:
                    # Try parsing as comma-separated objects (old format)
                    clean = line.lstrip(",").strip()
                    if clean:
                        try:
                            event = json.loads(clean)
                            events.append(event)
                        except json.JSONDecodeError:
                            pass

    # If no events parsed as JSONL, try old format
    if not events:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            content = content.strip()
            if not content.startswith("["):
                content = "[" + content + "]"
            content = content.replace(",\n]", "\n]").replace(",]", "]")
            events = json.loads(content)
        except json.JSONDecodeError:
            pass

    return events


def classify_event(event: dict) -> dict:
    """Classify event and infer activity type from text content."""
    text = event.get("text", "").lower()
    location = event.get("location_name", "Home")

    # Detect activity type from text patterns
    activity_type = "GENERAL"

    if any(
        kw in text
        for kw in [
            "gym",
            "workout",
            "cardio",
            "leg day",
            "chest",
            "back",
            "push day",
            "pull day",
            "biceps",
            "triceps",
            "shoulders",
            "abs",
        ]
    ):
        activity_type = "GYM"
    elif any(
        kw in text
        for kw in ["remind me", "don't let me forget", "don't forget", "need to remember"]
    ):
        activity_type = "REMINDER"
    elif any(
        kw in text
        for kw in ["routine:", "routine", "every morning", "every evening", "every day", "weekly"]
    ):
        activity_type = "ROUTINE"
    elif any(
        kw in text for kw in ["reflection:", "i learned", "looking back", "key insight", "realized"]
    ):
        activity_type = "REFLECTION"
    elif any(
        kw in text
        for kw in [
            "emotional:",
            "feeling",
            "anxious",
            "stressed",
            "happy",
            "grateful",
            "proud",
            "overwhelmed",
            "burnt out",
        ]
    ):
        activity_type = "EMOTIONAL"
    elif any(
        kw in text for kw in ["milestone:", "first", "launched", "reached", "completed", "achieved"]
    ):
        activity_type = "MILESTONE"
    elif any(
        kw in text for kw in ["query:", "what was", "when was", "what did", "where did", "how much"]
    ):
        activity_type = "QUERY"
    elif any(kw in text for kw in ["news:", "announced", "found out", "just told", "breaking"]):
        activity_type = "NEWS"
    elif any(
        kw in text
        for kw in ["should i", "should we", "decision:", "trying to decide", "need to decide"]
    ):
        activity_type = "DECISION"
    elif any(
        kw in text for kw in ["learning", "course", "tutorial", "watched", "studying", "read about"]
    ):
        activity_type = "LEARNING"
    elif any(kw in text for kw in ["travel", "flight", "trip", "booked", "visiting", "vacation"]):
        activity_type = "TRAVEL"
    elif any(
        kw in text
        for kw in ["financial", "budget", "investment", "price", "cost", "payment", "subscription"]
    ):
        activity_type = "FINANCIAL"
    elif any(kw in text for kw in ["panda", "mom", "dad", "family"]):
        activity_type = "FAMILY"
    elif any(
        kw in text
        for kw in [
            "code",
            "debug",
            "schema",
            "pipeline",
            "p0",
            "k0",
            "k1",
            "familyos",
            "deploy",
            "build",
            "test",
            "refactor",
            "api",
            "database",
            "migration",
            "commit",
            "branch",
            "merge",
        ]
    ):
        activity_type = "WORK"
    elif any(
        kw in text
        for kw in [
            "gerd",
            "sleep",
            "headache",
            "health",
            "medical",
            "doctor",
            "prescription",
            "nasal",
        ]
    ):
        activity_type = "HEALTH"

    # Enrich event with classification
    enriched = event.copy()
    enriched["activity_type"] = activity_type
    enriched["inferred_location"] = location

    return enriched


def expand_events(base_events: list[dict], target_count: int = 2000) -> list[dict]:
    """Expand events to target count with slight variations (if needed)."""
    expanded = []

    # First, add all base events with classification
    for event in base_events:
        expanded.append(classify_event(event))

    # If we already have enough events, just return them
    if len(expanded) >= target_count:
        return expanded[:target_count]

    # Then duplicate with minor variations to reach target
    while len(expanded) < target_count:
        base_event = random.choice(base_events)
        new_event = base_event.copy()

        # Add slight variations to prevent exact duplicates
        text = new_event.get("text", "")

        # Randomly add time qualifiers
        time_prefixes = [
            "Earlier today, ",
            "Just now, ",
            "A moment ago, ",
            "This morning, ",
            "This afternoon, ",
            "",
        ]
        text = random.choice(time_prefixes) + text[0].lower() + text[1:] if text else text

        new_event["text"] = text
        expanded.append(classify_event(new_event))

    return expanded[:target_count]


# =============================================================================
# REALISTIC TIME ASSIGNMENT
# =============================================================================

# Map from "routine time slot" field in JSONL to hour ranges
ROUTINE_TIME_SLOTS = {
    # Morning slots
    "Morning Routine": (6, 8),
    "Morning Work": (8, 12),
    # Afternoon slots
    "Lunch": (12, 13.5),
    "Afternoon Work": (13, 17),
    # Evening slots
    "Gym": (17.5, 19.5),
    "Evening": (19, 22),
    "Dinner": (18.5, 20.5),
    # Night slots
    "Night": (21, 23.5),
    "Late Night": (23, 24),
    # Weekend slots
    "Weekend": (10, 18),
    # Reflection (typically evening)
    "Reflection": (20, 23),
}


def get_time_slot_for_event(event: dict, base_date: datetime) -> datetime:
    """Assign a realistic time to an event based on its characteristics.

    Priority order:
    1. "routine time slot" field from JSONL (highest priority - user's timetable)
    2. Location-based scheduling
    3. Activity type patterns
    4. Text-based hints
    """
    location = event.get("location_name", event.get("inferred_location", "Home"))
    activity_type = event.get("activity_type", "GENERAL")
    text = event.get("text", "").lower()
    routine_slot = event.get("routine time slot", "")

    # Priority 0: Use "routine time slot" from JSONL if present
    if routine_slot and routine_slot in ROUTINE_TIME_SLOTS:
        start_hour, end_hour = ROUTINE_TIME_SLOTS[routine_slot]
    # Priority 1: Location-based scheduling
    elif location in LOCATION_SCHEDULES:
        time_slots = LOCATION_SCHEDULES[location]
        chosen_slot = random.choice(time_slots)
        start_hour, end_hour = chosen_slot
    else:
        # Default to work hours for unknown locations
        start_hour, end_hour = 9, 18

    # Priority 2: Refine by activity type (only if no routine slot specified)
    if not routine_slot:
        for pattern_key, pattern in EVENT_TYPE_PATTERNS.items():
            if pattern_key.lower() in activity_type.lower() or pattern_key.lower() in text:
                prefer_hours = pattern.get("prefer_hours", [])
                if prefer_hours and random.random() < pattern.get("weight", 1.0):
                    chosen_slot = random.choice(prefer_hours)
                    start_hour, end_hour = chosen_slot
                    break

    # Priority 3: Text-based hints (override if explicit time mentioned)
    if "morning" in text and "routine" not in routine_slot.lower():
        start_hour, end_hour = 6, 10
    elif ("evening" in text or "night" in text) and "evening" not in routine_slot.lower():
        start_hour, end_hour = 19, 23
    elif "lunch" in text:
        start_hour, end_hour = 12, 13
    elif "dinner" in text:
        start_hour, end_hour = 19, 21
    elif "6:30 am" in text or "6:30am" in text:
        start_hour, end_hour = 6.5, 7
    elif "10 pm" in text or "10pm" in text:
        start_hour, end_hour = 22, 23
    elif "7 pm" in text or "7pm" in text:
        start_hour, end_hour = 19, 20

    # Generate random time within the slot
    if end_hour > 24:
        end_hour = 24  # Cap at midnight for simplicity

    random_hour = random.uniform(start_hour, end_hour)
    hours = int(random_hour)
    minutes = int((random_hour - hours) * 60)

    event_time = base_date.replace(
        hour=hours % 24, minute=minutes, second=random.randint(0, 59), microsecond=0
    )

    return event_time


def distribute_events_across_days(
    events: list[dict], days: int = 30
) -> list[tuple[dict, datetime]]:
    """Distribute events across multiple days with realistic daily patterns."""
    now = datetime.now(timezone.utc)
    distributed = []

    # Group events by type for better daily distribution
    events_by_type = {}
    for event in events:
        activity = event.get("activity_type", "GENERAL")
        if activity not in events_by_type:
            events_by_type[activity] = []
        events_by_type[activity].append(event)

    # Calculate events per day
    total_events = len(events)
    events_per_day = total_events // days
    remainder = total_events % days

    event_index = 0
    shuffled_events = events.copy()
    random.shuffle(shuffled_events)

    for day_offset in range(days):
        # Calculate base date for this day (going back in time)
        base_date = now - timedelta(days=days - day_offset - 1)

        # How many events for this day
        day_events_count = events_per_day + (1 if day_offset < remainder else 0)

        # Get events for this day
        day_events = shuffled_events[event_index : event_index + day_events_count]
        event_index += day_events_count

        # Assign times to each event
        for event in day_events:
            event_time = get_time_slot_for_event(event, base_date)
            distributed.append((event, event_time))

    # Sort by timestamp
    distributed.sort(key=lambda x: x[1])

    return distributed


# =============================================================================
# DATABASE AND SUBMISSION FUNCTIONS
# =============================================================================


def execute_sql(sql_statements: list[str]) -> str | None:
    """Execute SQL statements against PostgreSQL."""
    full_sql = "; ".join(sql_statements)
    import os

    if os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST"):
        cmd = [
            "psql",
            "postgresql://postgres:postgres@pgbouncer:6432/k0_kernel",
            "-c",
            full_sql,
        ]
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


def get_signing_key() -> SigningKey:
    """Load or generate signing key."""
    key_file = project_root / "k0" / "deploy" / "data" / "reallife_device_key.b64"
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


def provision_device(signing_key: SigningKey) -> bool:
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


def submit_event(
    signing_key: SigningKey, event_data: dict, event_time: datetime, index: int
) -> requests.Response:
    """Submit a single event with the specified timestamp."""
    # Use NOW for envelope timestamp (clock skew check)
    now_utc = datetime.now(timezone.utc)

    body = {
        "operation": "UPSERT",
        "text": event_data["text"],
        "value": index,
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
        "actor": PRIMARY_ACTOR_ID,
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


def trigger_p03() -> bool:
    """Trigger P03 consolidation pipeline."""
    print("\n" + "=" * 70)
    print("TRIGGERING P03 CONSOLIDATION PIPELINE")
    print("=" * 70)

    response = requests.post(
        f"{BASE_URL}/k0/admin/pipelines/P03_CONSOLIDATION/trigger",
        json={
            "reason": "reallife_events_simulation",
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


def check_stats() -> None:
    """Check database statistics."""
    print("\n" + "=" * 70)
    print("DATABASE STATISTICS")
    print("=" * 70)

    result = execute_sql([f"SELECT COUNT(*) FROM st_hipp_events WHERE tenant_id = '{TENANT_ID}'"])
    if result:
        print(f"Events in st_hipp_events: {result.strip()}")

    result = execute_sql([f"SELECT COUNT(*) FROM st_vec WHERE tenant_id = '{TENANT_ID}'"])
    if result:
        print(f"Embeddings in st_vec: {result.strip()}")


def print_schedule_preview(events_with_times: list[tuple[dict, datetime]], count: int = 20) -> None:
    """Print a preview of the event schedule."""
    print("\n" + "=" * 70)
    print("SCHEDULE PREVIEW (first 20 events)")
    print("=" * 70)

    for i, (event, event_time) in enumerate(events_with_times[:count]):
        day = event_time.strftime("%a %m/%d")
        time_str = event_time.strftime("%H:%M")
        activity = event.get("activity_type", "GENERAL")[:8]
        location = event.get("location_name", "Unknown")[:15]
        text_preview = event["text"][:40] + "..." if len(event["text"]) > 40 else event["text"]
        print(f"  [{i+1:3}] {day} {time_str} | {activity:8} | {location:15} | {text_preview}")


def print_daily_summary(events_with_times: list[tuple[dict, datetime]]) -> None:
    """Print summary of events per day."""
    print("\n" + "=" * 70)
    print("DAILY DISTRIBUTION SUMMARY")
    print("=" * 70)

    days = {}
    for event, event_time in events_with_times:
        day_key = event_time.strftime("%Y-%m-%d (%a)")
        if day_key not in days:
            days[day_key] = 0
        days[day_key] += 1

    for day, count in sorted(days.items()):
        bar = "#" * (count // 5)
        print(f"  {day}: {count:3} events {bar}")


# =============================================================================
# MAIN
# =============================================================================


def main():
    print("=" * 70)
    print("REAL LIFE EVENT SIMULATION")
    print("Simulating realistic daily schedule patterns")
    print("=" * 70)

    # Load events from JSONL - prefer expanded file if available
    expanded_path = Path(__file__).parent / "real_lifedata_expanded.jsonl"
    base_path = Path(__file__).parent / "real_lifedata.jsonl"

    if expanded_path.exists():
        jsonl_path = expanded_path
    else:
        jsonl_path = base_path

    print(f"\nLoading events from: {jsonl_path}")

    base_events = load_events_from_jsonl(jsonl_path)
    print(f"Loaded {len(base_events)} base events")

    # Expand to target count
    target_count = 2000
    print(f"Expanding to {target_count} events with variations...")
    all_events = expand_events(base_events, target_count)

    # Distribute across days with realistic timing
    print(f"Distributing events across {DAYS_TO_SIMULATE} days...")
    events_with_times = distribute_events_across_days(all_events, DAYS_TO_SIMULATE)

    # Show preview and summary
    print_schedule_preview(events_with_times)
    print_daily_summary(events_with_times)

    # Count by activity type
    activity_counts = {}
    for event, _ in events_with_times:
        activity = event.get("activity_type", "GENERAL")
        activity_counts[activity] = activity_counts.get(activity, 0) + 1

    print("\n" + "=" * 70)
    print("ACTIVITY TYPE DISTRIBUTION")
    print("=" * 70)
    for activity, count in sorted(activity_counts.items(), key=lambda x: -x[1]):
        pct = count / len(events_with_times) * 100
        print(f"  {activity:12}: {count:4} ({pct:5.1f}%)")

    # Provision and submit
    signing_key = get_signing_key()

    if not provision_device(signing_key):
        print("Failed to provision device. Exiting.")
        return

    time.sleep(0.5)

    print(f"\n{'=' * 70}")
    print(f"SUBMITTING {len(events_with_times)} EVENTS")
    print("=" * 70)

    success_count = 0
    error_count = 0
    last_day = None

    for i, (event_data, event_time) in enumerate(events_with_times, 1):
        try:
            current_day = event_time.strftime("%Y-%m-%d")
            if current_day != last_day:
                print(f"\n  --- {current_day} ({event_time.strftime('%A')}) ---")
                last_day = current_day

            response = submit_event(signing_key, event_data, event_time, i)
            activity = event_data.get("activity_type", "UNKNOWN")

            if response.status_code == 200:
                time_str = event_time.strftime("%H:%M")
                text_preview = (
                    event_data["text"][:35] + "..."
                    if len(event_data["text"]) > 35
                    else event_data["text"]
                )

                # Only print every 10th event to avoid console spam
                if i % 10 == 0 or i <= 5:
                    print(f"  [{i:4}] {time_str} OK {activity[:8]:8} | {text_preview}")

                success_count += 1
            else:
                error = response.json().get("error", {}).get("reason", response.text[:50])
                print(f"  [{i:4}] FAIL {activity[:8]:8} | {error}")
                error_count += 1

        except Exception as e:
            print(f"  [{i:4}] ERROR: {e}")
            error_count += 1

        time.sleep(SUBMISSION_DELAY_MS / 1000)

        # Progress indicator every 100 events
        if i % 100 == 0:
            print(
                f"  ... Progress: {i}/{len(events_with_times)} ({i/len(events_with_times)*100:.1f}%)"
            )

    print(f"\n{'=' * 70}")
    print("SUBMISSION COMPLETE")
    print(f"  Success: {success_count}")
    print(f"  Errors:  {error_count}")
    print(f"  Total:   {len(events_with_times)}")
    print("=" * 70)

    print("\nWaiting 30s for P02 embeddings to process...")
    time.sleep(30)

    trigger_p03()

    print("\nWaiting 10s for P03 processing...")
    time.sleep(10)

    check_stats()

    print("\n" + "=" * 70)
    print("View logs: docker logs k0-kernel --tail 200 | Select-String 'R0:|R1:|R2:|R3:|R4:'")
    print("=" * 70)


if __name__ == "__main__":
    main()
