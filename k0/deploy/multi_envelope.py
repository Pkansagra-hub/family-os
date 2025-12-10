"""
K0 Device Provisioning and Envelope Submission
Provisions a test device and submits multiple envelopes to K0 kernel.

Usage: python k0/provision_and_submit.py
"""

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to Python path
project_root = (
    Path(__file__).resolve().parent.parent.parent
)  # k0/deploy/provision_and_submit.py -> k0/deploy -> k0 -> familyos
sys.path.insert(0, str(project_root))

import uuid

import requests
from nacl.signing import SigningKey

from k0.idem import derive_idem_key
from k0.security import canonical_json, hash_payload
from k0.security.crypto import encode_base64url

# Configuration
DB_PATH = project_root / "k0" / "deploy" / "data" / "k0_kernel.db"
BASE_URL = "http://localhost:8080"
TENANT_ID = "tenant-test"
SPACE_ID = "space-home"
DEVICE_ID = "device-test-1"
SCHEMA_URI = "schema://memory.delta"
SCHEMA_VERSION = "1.0"


def execute_sql_in_docker(sql_statements):
    """Execute SQL statements inside the docker container."""
    # Join statements with semicolons
    full_sql = "; ".join(sql_statements)

    cmd = ["docker", "exec", "-i", "k0-kernel", "sqlite3", "/data/k0_kernel.db"]

    try:
        process = subprocess.run(
            cmd, input=full_sql.encode("utf-8"), capture_output=True, check=True
        )
        return process.stdout.decode("utf-8")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Docker SQL execution failed: {e.stderr.decode('utf-8')}")


def provision_device(signing_key: SigningKey):
    """Provision device and register its public key in K0 via Docker."""
    print("\n" + "=" * 60)
    print("Step 1: Provisioning Device (via Docker)")
    print("=" * 60)

    verify_key_b64 = encode_base64url(signing_key.verify_key.encode())
    now = datetime.now(timezone.utc).isoformat()

    print("\nDevice Configuration:")
    print(f"  Device ID: {DEVICE_ID}")
    print(f"  Tenant ID: {TENANT_ID}")
    print(f"  Space ID: {SPACE_ID}")
    print(f"  Verify Key: {verify_key_b64[:32]}...")
    print("  Target: Docker container 'k0-kernel'")

    try:
        sql_statements = []

        # CRITICAL: Delete existing device keys and device to force cache invalidation
        sql_statements.append(f"DELETE FROM st_device_keys WHERE device_id = '{DEVICE_ID}'")
        sql_statements.append(f"DELETE FROM st_devices WHERE device_id = '{DEVICE_ID}'")

        # Insert fresh device
        sql_statements.append(
            f"INSERT INTO st_devices (device_id, tenant_id, space_id, mls_group_id, provisioned_ts) VALUES ('{DEVICE_ID}', '{TENANT_ID}', '{SPACE_ID}', 'mls-group-1', '{now}')"
        )

        # Insert fresh device key
        sql_statements.append(
            f"INSERT INTO st_device_keys (device_id, key_version, verify_key, key_state, registered_ts, activated_ts) VALUES ('{DEVICE_ID}', '1', '{verify_key_b64}', 'ACTIVE', '{now}', '{now}')"
        )

        # Schema registration
        import hashlib

        schema_sha = hashlib.sha256(f"{SCHEMA_URI}@{SCHEMA_VERSION}".encode("utf-8")).hexdigest()

        # Use INSERT OR IGNORE for schema
        sql_statements.append(
            f"INSERT OR IGNORE INTO schema_registry (schema_uri, version, sha256, status) VALUES ('{SCHEMA_URI}', '{SCHEMA_VERSION}', '{schema_sha}', 'ACTIVE')"
        )

        print("\nExecuting SQL in Docker container...")
        execute_sql_in_docker(sql_statements)

        print("\n✓ Device provisioned")
        print("✓ Device key registered")
        print("✓ Schema registered (if not exists)")

        # Small delay to ensure kernel has seen the update
        import time

        time.sleep(0.5)

        print("\n✓ Device provisioning complete!")
        return True

    except Exception as e:
        print(f"\n✗ Provisioning failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def submit_envelope(signing_key: SigningKey, body: dict, *, verbose: bool = True):
    """
    Build and submit a single envelope to K0 with the provided body.

    `body` MUST already contain a `timestamp` in ISO-8601 form.
    """
    if verbose:
        print("\n" + "=" * 60)
        print("Step 2: Submitting Envelope")
        print("=" * 60)

    # Canonicalize body
    body_json = canonical_json(body)
    body_bytes = body_json.encode("utf-8")
    payload_hash = hash_payload(body_bytes)

    if verbose:
        print("\n✓ Created body payload")
        print(f"  Size: {len(body_bytes)} bytes")
        print(f"  Hash: {payload_hash[:32]}...")

    # Step 1: Build envelope WITH sig_alg and sig_kid, but WITHOUT envelope_sha256 and sig
    trace_id = str(uuid.uuid4())
    timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # envelope ts

    envelope = {
        "cognitive_trace_id": trace_id,
        "tenant_id": TENANT_ID,
        "space_id": SPACE_ID,
        "topic": "memory.delta",
        "schema_uri": SCHEMA_URI,
        "schema_version": SCHEMA_VERSION,
        "actor": "actor-test-123",
        "device_id": DEVICE_ID,
        "band": "GREEN",
        "policy_version": "2025-09-28",
        "ts": timestamp_iso,  # envelope ts (separate from body["timestamp"])
        "payload_sha256": payload_hash,
        "sig_alg": "Ed25519SHA512",  # V1 REQUIRED: Exact value from tests
        "sig_kid": f"{DEVICE_ID}#1",  # V1 REQUIRED: Key ID (device_id#key_version)
        "body": body,  # body is included in envelope_sha256
        "policy": {
            "abac": {
                "roles": ["guest"],  # Try guest role instead of coordinator
            }
        },
    }

    if verbose:
        print("\n✓ Built envelope")
        print(f"  Trace ID: {trace_id}")
        print(f"  Timestamp: {timestamp_iso}")
        print(f"  Fields in envelope before hash: {sorted(envelope.keys())}")

    # Step 2: Compute envelope_sha256 (includes sig_alg, sig_kid, but NOT envelope_sha256 or sig)
    from k0.security import canonical_envelope, compute_envelope_sha256

    if verbose:
        canonical_dict = {k: v for k, v in envelope.items() if k not in {"sig", "envelope_sha256"}}
        print(
            f"\nDEBUG - Keys after excluding sig+envelope_sha256: "
            f"{sorted(canonical_dict.keys())}"
        )

        canonical_str = canonical_json(canonical_dict)
        print(f"DEBUG - Canonical JSON (first 500 chars): {canonical_str[:500]}")

        canonical_bytes = canonical_envelope(envelope, exclude_signature=True)
        print(f"DEBUG - Canonical envelope for hash ({len(canonical_bytes)} bytes):")
        print(canonical_bytes[:300].decode("utf-8", errors="replace"))

    envelope_sha256 = compute_envelope_sha256(envelope)
    envelope["envelope_sha256"] = envelope_sha256
    if verbose:
        print(f"  Envelope SHA256: {envelope_sha256[:32]}...")

    # Compute idem_key
    idem_key = derive_idem_key(envelope, payload_hash=payload_hash)
    if verbose:
        print(f"  Idem Key: {idem_key[:32]}...")

    # Step 3: Sign the envelope (canonical form with ALL fields except sig)
    from k0.security import canonical_envelope as canonical_env_for_sign

    message = canonical_env_for_sign(envelope)
    signature = encode_base64url(signing_key.sign(message).signature)

    if verbose:
        print("\n✓ Signed envelope")
        print(f"  Signature: {signature[:32]}...")

    # Build final request payload (body is already in envelope)
    request_payload = dict(envelope)
    request_payload["sig"] = signature

    # Submit to K0
    url = f"{BASE_URL}/k0/command.submit"
    if verbose:
        print(f"\n→ Submitting to {url}...")
        print("\nDEBUG - Request payload keys:")
        print(f"  {sorted(request_payload.keys())}")
        print("\nDEBUG - Request payload (first 500 chars):")
        import json as json_module

        payload_str = json_module.dumps(request_payload, indent=2)
        print(payload_str[:500] + "..." if len(payload_str) > 500 else payload_str)

    try:
        response = requests.post(
            url, json=request_payload, headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            if verbose:
                print("\n✓ SUCCESS!")
                print(f"  Receipt ID: {result.get('receipt_id')}")
                idem_from_result = result.get("idem_key") or ""
                print(f"  Idem Key: {idem_from_result[:32]}...")
                print(f"  Commit TS: {result.get('commit_ts')}")
                print(f"  Offsets: {result.get('offsets')}")
            return True
        else:
            if verbose:
                print(f"\n✗ FAILED: {response.status_code}")
                print(f"  Response: {response.text}")
            else:
                print(
                    f"✗ Envelope failed (HTTP {response.status_code}) "
                    f"text={response.text[:200]}"
                )
            return False

    except Exception as e:
        if verbose:
            print(f"\n✗ ERROR: {e}")
            import traceback

            traceback.print_exc()
        else:
            print(f"✗ Envelope error: {e}")
        return False


# ---------- Real-life sample bodies (50–60 envelopes) ----------


def generate_sample_bodies(n: int = 60) -> list[dict]:
    """
    Generate n sample bodies that look like real FamilyOS memories.

    Body schema kept simple to match current memory.delta:
      - operation: "UPSERT"
      - text: natural language description
      - value: small int (e.g., rating or importance)
      - timestamp: ISO-8601 (UTC)
    """
    now = datetime.now(timezone.utc)

    # Base templates representing different "kinds" of memories
    templates = [
        # Morning / routine
        "Morning log: Woke up at 7:10, made coffee, feeling focused.",
        "Breakfast with family: pancakes and fruit, everyone at the table.",
        "Quick meditation: 10 minutes breathing exercise before work.",
        "Workout session: 25-minute home workout, light cardio.",
        "Took dog for a walk around the block, sunny weather.",
        # Work / productivity
        "Started deep work block on K0 pipeline P02 design.",
        "Finished debugging WAL dispatcher bug in bus.core.",
        "Quick standup with team: discussed release timeline and blockers.",
        "Reviewed PR for security policy enforcement in K0.",
        "Sketched architecture for FamilyOS device hub and sync.",
        # Relationships / social
        "Called mom to check in, talked for 25 minutes about weekend plans.",
        "Video call with fiancee, planned next month’s visit.",
        "Sent birthday message to close friend with photo and voice note.",
        "Helped sibling debug a resume and job application.",
        "Chatted with neighbor about HOA meeting and parking issues.",
        # Errands / tasks
        "Grocery run: bought vegetables, milk, oats, and snacks.",
        "Refilled car gas tank, checked tire pressure.",
        "Paid electricity and internet bills online.",
        "Scheduled dentist appointment for next month.",
        "Cleaned kitchen and living room after dinner.",
        # Learning / media
        "Watched a talk about memory-augmented neural networks.",
        "Read 3 pages of a book about personal finance and compounding.",
        "Listened to podcast episode on startup founder journeys.",
        "Skimmed article about energy-efficient home design.",
        "Watched highlights of today’s football game.",
        # Health / mood
        "Afternoon slump: felt tired around 3pm, took a short break.",
        "Logged headache after long screen time, drank water and stretched.",
        "Felt proud after shipping a stable build of K0.",
        "Evening walk to clear mind, listened to calm music.",
        "Noted mild anxiety about future but also strong motivation.",
        # Planning / future
        "Added goal: finish K0 P02 pipeline end-to-end this week.",
        "Brainstormed ideas for FamilyOS device form factor.",
        "Drafted outline for investor narrative for 2027.",
        "Planned weekend schedule: cleaning, coding, movie night.",
        "Made list of people to reconnect with over next month.",
        # Home / environment
        "Reorganized desk and cable management around workstation.",
        "Adjusted fan setup for laptop cooling during long training runs.",
        "Tested backup power strip and surge protector.",
        "Did quick inspection of smoke detector and batteries.",
        "Watered indoor plants and balcony planters.",
        # Finance / admin
        "Reviewed monthly spending and updated budget tracker.",
        "Checked stock portfolio performance for the week.",
        "Updated spreadsheet for FamilyOS runway and funding plan.",
        "Paid credit card bill and verified transactions.",
        "Saved new paycheck breakdown for future reference.",
        # Reflection / gratitude
        "Grateful moment: parents’ health is stable this month.",
        "Reflection: progress on FamilyOS feels slow but steady.",
        "Noted that consistent 8–12 hour workdays are paying off.",
        "Wrote down affirmation about staying patient and persistent.",
        "Captured idea: home as sanctuary with 24/7 kitchen for guests.",
    ]

    bodies: list[dict] = []
    num_templates = len(templates)

    for i in range(n):
        text = templates[i % num_templates]
        # Spread timestamps over the last 3 days, 30-minute spacing
        delta_minutes = i * 30
        ts = now - timedelta(minutes=delta_minutes)
        bodies.append(
            {
                "operation": "UPSERT",
                "text": text,
                "value": (i % 5) + 1,  # simple importance / rating 1–5
                "timestamp": ts.isoformat(),
            }
        )

    return bodies


def submit_sample_envelopes(signing_key: SigningKey, bodies: list[dict]):
    """
    Submit a batch of envelopes. Uses minimal logging per event.
    """
    import time

    print("\n" + "=" * 60)
    print(f"Step 2: Submitting {len(bodies)} Envelopes (batch)")
    print("=" * 60)

    success = 0
    fail = 0

    for idx, body in enumerate(bodies, start=1):
        ok = submit_envelope(signing_key, body, verbose=False)
        if ok:
            success += 1
            print(f"✓ [{idx}/{len(bodies)}] Submitted envelope")
        else:
            fail += 1
            print(f"✗ [{idx}/{len(bodies)}] Failed envelope")
        # Delay to avoid SQLite DB lock contention - pipeline takes ~100ms per envelope
        time.sleep(0.5)

    print("\n" + "=" * 60)
    print(f"Batch complete: {success} succeeded, {fail} failed")
    print("=" * 60)


def _get_or_create_persistent_key() -> SigningKey:
    """Load persistent test signing key from file, or generate and save if missing."""
    import base64

    key_file = project_root / "k0" / "deploy" / "data" / "test_device_key.b64"

    if key_file.exists():
        # Load existing key from base64url encoded bytes
        key_b64 = key_file.read_text().strip()
        # Decode base64url (add padding if needed)
        padding = "=" * (-len(key_b64) % 4)
        key_bytes = base64.urlsafe_b64decode(f"{key_b64}{padding}".encode("ascii"))
        signing_key = SigningKey(key_bytes)
        print("\n✓ Loaded persistent Ed25519 signing key from file")
        return signing_key
    else:
        # Generate new key and save it
        signing_key = SigningKey.generate()
        key_b64 = encode_base64url(bytes(signing_key))
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key_b64)
        print("\n✓ Generated new persistent Ed25519 signing key (saved for future runs)")
        return signing_key


def main():
    """Main entry point."""
    print("=" * 60)
    print("K0 Device Provisioning and Envelope Submission")
    print("=" * 60)

    # Load persistent signing key (same key across test runs)
    signing_key = _get_or_create_persistent_key()

    # Step 1: Provision device
    if not provision_device(signing_key):
        print("\n✗ Failed to provision device. Exiting.")
        return

    # --- Option A: Single debug envelope (keeps your original behavior) ---
    # body = {
    #     "operation": "UPSERT",
    #     "text": "Hello from K0!",
    #     "value": 42,
    #     "timestamp": datetime.now(timezone.utc).isoformat(),
    # }
    # submit_envelope(signing_key, body, verbose=True)

    # --- Option B: Real-life batch of 50–60 envelopes ---
    bodies = generate_sample_bodies(n=60)
    submit_sample_envelopes(signing_key, bodies)


if __name__ == "__main__":
    main()
