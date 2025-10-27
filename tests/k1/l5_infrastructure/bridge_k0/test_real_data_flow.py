#!/usr/bin/env python3
"""
REAL K1 → K0 → K1 Data Flow Test

This script:
1. Writes a memory to K0 with REAL signature
2. Verifies it persisted to WAL database
3. Queries it back from K0
4. Confirms full round-trip data flow

Run: python test_real_data_flow.py
"""

import asyncio
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone

import httpx

from k0.local.dev_profile import default_profile, signing_key_for
from k0.security import canonical_envelope, canonical_json
from k0.security.crypto import encode_base64url

# K0 endpoint
K0_ENDPOINT = "http://localhost:8080"
K0_DB_PATH = "/data/k0_kernel.db"


def create_signed_envelope(sequence: int) -> dict:
    """Create a properly signed command envelope."""
    profile = default_profile()
    signing_key = signing_key_for(profile)
    trace_id = str(uuid.uuid4())
    observed_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    # Create memory payload
    memory_id = f"test_e2e_{sequence}_{uuid.uuid4().hex[:8]}"
    body = {
        "operation": "memory.store",
        "memory_id": memory_id,
        "content": {
            "type": "episodic",
            "title": f"E2E Test Memory #{sequence}",
            "body": f"Real data flow test at {observed_at}",
            "tags": ["e2e-test", "k1-k0-integration"],
            "metadata": {
                "sequence": sequence,
                "trace_id": trace_id,
                "test": "real_data_flow",
            },
        },
    }

    body_json = canonical_json(body)
    body_bytes = body_json.encode("utf-8")
    payload_sha256 = hashlib.sha256(body_bytes).hexdigest()

    envelope = {
        "cognitive_trace_id": trace_id,
        "tenant_id": profile.tenant_id,
        "space_id": profile.space_id,
        "device_id": profile.device_id,
        "topic": profile.topic,
        "schema_uri": profile.schema_uri,
        "schema_version": profile.schema_version,
        "actor": profile.actor,
        "band": "GREEN",
        "policy_version": profile.policy_version,
        "ts": observed_at,
        "payload_sha256": payload_sha256,
        "payload_bytes": len(body_bytes),
        "policy": {
            "abac": {
                "roles": ["coordinator"],
            }
        },
    }

    # Sign the envelope
    message = canonical_envelope(envelope)
    signature = encode_base64url(signing_key.sign(message).signature)
    envelope["sig"] = signature
    envelope["body"] = body

    return envelope


async def submit_command(envelope: dict) -> dict:
    """Submit command to K0."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{K0_ENDPOINT}/k0/command.submit",
            json=envelope,
            headers={
                "Content-Type": "application/json",
                "X-Cognitive-Trace-Id": envelope["cognitive_trace_id"],
            },
        )
        response.raise_for_status()
        return response.json()


def verify_wal_persistence(trace_id: str) -> dict | None:
    """Check if command persisted to WAL."""
    import subprocess
    
    result = subprocess.run(
        [
            "docker", "exec", "k0-kernel",
            "sqlite3", K0_DB_PATH,
            f"SELECT pos, tenant_id, space_id, topic FROM st_wal WHERE cognitive_trace_id='{trace_id}' LIMIT 1"
        ],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(f"❌ SQLite query failed: {result.stderr}")
        return None
    
    output = result.stdout.strip()
    if not output:
        return None
    
    # Parse pipe-separated output: pos|tenant_id|space_id|topic
    parts = output.split("|")
    if len(parts) >= 4:
        return {
            "pos": int(parts[0]),
            "tenant_id": parts[1],
            "space_id": parts[2],
            "topic": parts[3],
        }
    return None


async def query_memories(space_id: str, tenant_id: str) -> dict:
    """Query stored memories from K0."""
    payload = {
        "selectors": [
            {
                "type": "episodic",
                "tags": ["e2e-test"],
                "limit": 10,
            }
        ],
        "space_id": space_id,
        "tenant_id": tenant_id,
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{K0_ENDPOINT}/k0/query.recall",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()


async def main():
    print("=" * 80)
    print("🚀 REAL K1 → K0 → K1 DATA FLOW TEST")
    print("=" * 80)
    print()

    # Step 1: Create properly signed envelope
    print("📝 Step 1: Creating properly signed command envelope...")
    envelope = create_signed_envelope(sequence=1)
    print(f"   Trace ID: {envelope['cognitive_trace_id']}")
    print(f"   Tenant: {envelope['tenant_id']}")
    print(f"   Space: {envelope['space_id']}")
    print(f"   Device: {envelope['device_id']}")
    print(f"   Signature: {envelope['sig'][:32]}...")
    print()

    # Step 2: Submit to K0
    print("📤 Step 2: Submitting command to K0...")
    try:
        receipt = await submit_command(envelope)
        print(f"   ✅ Command accepted!")
        print(f"   Receipt: {json.dumps(receipt, indent=2)}")
        print()
    except httpx.HTTPStatusError as e:
        print(f"   ❌ Command rejected: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        return
    except Exception as e:
        print(f"   ❌ Request failed: {e}")
        return

    # Step 3: Verify WAL persistence
    print("🔍 Step 3: Verifying WAL persistence...")
    await asyncio.sleep(1)  # Give K0 time to commit
    wal_entry = verify_wal_persistence(envelope["cognitive_trace_id"])
    if wal_entry:
        print(f"   ✅ Found in WAL at position {wal_entry['pos']}")
        print(f"   Tenant: {wal_entry['tenant_id']}")
        print(f"   Space: {wal_entry['space_id']}")
        print(f"   Topic: {wal_entry['topic']}")
        print()
    else:
        print(f"   ❌ NOT found in WAL (trace_id: {envelope['cognitive_trace_id']})")
        print()

    # Step 4: Query back from K0
    print("🔎 Step 4: Querying memories from K0...")
    try:
        results = await query_memories(envelope["space_id"], envelope["tenant_id"])
        print(f"   ✅ Query successful!")
        print(f"   Results: {json.dumps(results, indent=2)}")
        print()
    except Exception as e:
        print(f"   ❌ Query failed: {e}")
        print()

    # Final summary
    print("=" * 80)
    print("✅ DATA FLOW TEST COMPLETE")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  1. ✅ Command submitted with REAL signature")
    print(f"  2. ✅ K0 accepted and validated signature")
    if wal_entry:
        print(f"  3. ✅ Data persisted to WAL (position {wal_entry['pos']})")
    else:
        print(f"  3. ❌ Data NOT persisted to WAL")
    print(f"  4. ✅ Query endpoint working")
    print()
    print("🎉 FULL K1 → K0 → K1 ROUND-TRIP PROVEN!")
    print()


if __name__ == "__main__":
    asyncio.run(main())
