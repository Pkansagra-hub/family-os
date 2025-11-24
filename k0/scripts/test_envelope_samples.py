#!/usr/bin/env python3
"""
Test Envelope Sample Generator
===============================
Creates realistic test envelopes for different scenarios.

Usage:
    python k0/scripts/test_envelope_samples.py --scenario memory_write
    python k0/scripts/test_envelope_samples.py --scenario observation
    python k0/scripts/test_envelope_samples.py --all --output samples/
"""

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def create_memory_write_envelope(
    trace_id: str = None, text: str = "Test memory event", **kwargs
) -> Dict[str, Any]:
    """Create memory.delta write envelope"""
    now = datetime.now(timezone.utc)
    trace_id = trace_id or str(uuid.uuid4())

    return {
        "cognitive_trace_id": trace_id,
        "tenant_id": kwargs.get("tenant_id", "tenant-test"),
        "space_id": kwargs.get("space_id", "space-home"),
        "topic": "memory.delta",
        "schema_uri": "schema://memory.delta",
        "schema_version": "1.0",
        "actor": kwargs.get("actor", "actor-test-user"),
        "device_id": kwargs.get("device_id", "device-test-phone"),
        "band": kwargs.get("band", "GREEN"),
        "policy_version": "2025-09-28",
        "ts": now.isoformat(),
        "payload_sha256": "test-sha256-hash",
        "sig_alg": "Ed25519SHA512",
        "sig_kid": kwargs.get("device_id", "device-test-phone"),
        "sig": "test-signature",
        "envelope_sha256": "test-envelope-hash",
        "body": {
            "operation": "UPSERT",
            "text": text,
            "timestamp": now.isoformat(),
            "value": kwargs.get("value", 42),
        },
        "event": {
            "event_time_utc": now.isoformat(),
            "event_type": "observation",
        },
        "wal_pos": kwargs.get("wal_pos", 1000),
        "bus_topic": "cognitive.memory.write.committed.v1",
        "bus_offset": kwargs.get("bus_offset", 1),
    }


def create_observation_envelope(
    trace_id: str = None, observation_text: str = "User observed something interesting", **kwargs
) -> Dict[str, Any]:
    """Create cognitive.observation.captured envelope"""
    now = datetime.now(timezone.utc)
    trace_id = trace_id or str(uuid.uuid4())

    return {
        "cognitive_trace_id": trace_id,
        "tenant_id": kwargs.get("tenant_id", "tenant-test"),
        "space_id": kwargs.get("space_id", "space-home"),
        "topic": "observation.captured",
        "schema_uri": "schema://observation.captured",
        "schema_version": "1.0",
        "actor": kwargs.get("actor", "actor-test-user"),
        "device_id": kwargs.get("device_id", "device-test-phone"),
        "band": kwargs.get("band", "GREEN"),
        "policy_version": "2025-09-28",
        "ts": now.isoformat(),
        "payload_sha256": "test-sha256-hash",
        "sig_alg": "Ed25519SHA512",
        "sig_kid": kwargs.get("device_id", "device-test-phone"),
        "sig": "test-signature",
        "envelope_sha256": "test-envelope-hash",
        "body": {
            "observation": observation_text,
            "timestamp": now.isoformat(),
            "confidence": 0.85,
            "source": "user_input",
        },
        "event": {
            "event_time_utc": now.isoformat(),
            "event_type": "observation",
        },
        "wal_pos": kwargs.get("wal_pos", 1000),
        "bus_topic": "cognitive.observation.captured.v1",
        "bus_offset": kwargs.get("bus_offset", 1),
    }


def create_social_interaction_envelope(
    trace_id: str = None,
    interaction_text: str = "Had coffee with Alice",
    participants: list = None,
    **kwargs,
) -> Dict[str, Any]:
    """Create social interaction envelope"""
    now = datetime.now(timezone.utc)
    trace_id = trace_id or str(uuid.uuid4())
    participants = participants or ["Alice"]

    return {
        "cognitive_trace_id": trace_id,
        "tenant_id": kwargs.get("tenant_id", "tenant-test"),
        "space_id": kwargs.get("space_id", "space-home"),
        "topic": "memory.delta",
        "schema_uri": "schema://memory.delta",
        "schema_version": "1.0",
        "actor": kwargs.get("actor", "actor-test-user"),
        "device_id": kwargs.get("device_id", "device-test-phone"),
        "band": kwargs.get("band", "GREEN"),
        "policy_version": "2025-09-28",
        "ts": now.isoformat(),
        "payload_sha256": "test-sha256-hash",
        "sig_alg": "Ed25519SHA512",
        "sig_kid": kwargs.get("device_id", "device-test-phone"),
        "sig": "test-signature",
        "envelope_sha256": "test-envelope-hash",
        "body": {
            "operation": "UPSERT",
            "text": interaction_text,
            "timestamp": now.isoformat(),
            "participants": participants,
            "interaction_type": "casual_meeting",
        },
        "event": {
            "event_time_utc": now.isoformat(),
            "event_type": "social_interaction",
        },
        "wal_pos": kwargs.get("wal_pos", 1000),
        "bus_topic": "cognitive.memory.write.committed.v1",
        "bus_offset": kwargs.get("bus_offset", 1),
    }


def create_location_update_envelope(
    trace_id: str = None,
    location_name: str = "Home",
    lat: float = 37.7749,
    lon: float = -122.4194,
    **kwargs,
) -> Dict[str, Any]:
    """Create location update envelope"""
    now = datetime.now(timezone.utc)
    trace_id = trace_id or str(uuid.uuid4())

    return {
        "cognitive_trace_id": trace_id,
        "tenant_id": kwargs.get("tenant_id", "tenant-test"),
        "space_id": kwargs.get("space_id", "space-home"),
        "topic": "memory.delta",
        "schema_uri": "schema://memory.delta",
        "schema_version": "1.0",
        "actor": kwargs.get("actor", "actor-test-user"),
        "device_id": kwargs.get("device_id", "device-test-phone"),
        "band": kwargs.get("band", "GREEN"),
        "policy_version": "2025-09-28",
        "ts": now.isoformat(),
        "payload_sha256": "test-sha256-hash",
        "sig_alg": "Ed25519SHA512",
        "sig_kid": kwargs.get("device_id", "device-test-phone"),
        "sig": "test-signature",
        "envelope_sha256": "test-envelope-hash",
        "body": {
            "operation": "UPSERT",
            "text": f"Arrived at {location_name}",
            "timestamp": now.isoformat(),
            "location": {
                "name": location_name,
                "lat": lat,
                "lon": lon,
                "accuracy": 10.0,
            },
        },
        "event": {
            "event_time_utc": now.isoformat(),
            "event_type": "location_update",
        },
        "wal_pos": kwargs.get("wal_pos", 1000),
        "bus_topic": "cognitive.memory.write.committed.v1",
        "bus_offset": kwargs.get("bus_offset", 1),
    }


SCENARIOS = {
    "memory_write": create_memory_write_envelope,
    "observation": create_observation_envelope,
    "social_interaction": create_social_interaction_envelope,
    "location_update": create_location_update_envelope,
}


def main():
    parser = argparse.ArgumentParser(
        description="Generate test envelope samples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available scenarios:
  {', '.join(SCENARIOS.keys())}

Examples:
  # Generate single scenario
  python k0/scripts/test_envelope_samples.py --scenario memory_write

  # Generate all scenarios
  python k0/scripts/test_envelope_samples.py --all

  # Save to directory
  python k0/scripts/test_envelope_samples.py --all --output samples/
        """,
    )

    parser.add_argument(
        "--scenario", choices=list(SCENARIOS.keys()), help="Generate specific scenario"
    )
    parser.add_argument("--all", action="store_true", help="Generate all scenarios")
    parser.add_argument("--output", type=Path, help="Output directory for samples")

    args = parser.parse_args()

    if not args.scenario and not args.all:
        parser.error("Must specify --scenario or --all")

    # Determine which scenarios to generate
    if args.all:
        scenarios_to_generate = list(SCENARIOS.keys())
    else:
        scenarios_to_generate = [args.scenario]

    # Create output directory if specified
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)

    # Generate envelopes
    for scenario_name in scenarios_to_generate:
        envelope = SCENARIOS[scenario_name]()

        if args.output:
            output_file = args.output / f"envelope_{scenario_name}.json"
            with open(output_file, "w") as f:
                json.dump(envelope, f, indent=2)
            print(f"✓ Generated: {output_file}")
        else:
            print(f"\n{scenario_name}:")
            print(json.dumps(envelope, indent=2))

    if args.output:
        print(f"\n✓ Generated {len(scenarios_to_generate)} envelope samples in {args.output}")


if __name__ == "__main__":
    main()
