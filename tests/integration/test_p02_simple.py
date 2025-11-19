"""
P02 Simple Integration Test - Trace envelope through full DAG

Validates that the P02 pipeline can process a single envelope through all modules.
"""

from typing import Any

import pytest


class MockMessage:
    """Mock message for Phase 2 module testing"""

    def __init__(self, envelope: dict[str, Any], trace_id: str | None = None):
        self.payload = envelope
        self.trace_id = trace_id or envelope.get("cognitive_trace_id", "test_trace")
        self.offset = envelope.get("wal_pos", 0)
        self.event_type = "cognitive.memory.write.committed.v1"


@pytest.mark.asyncio
async def test_p02_envelope_flow_through_modules(mock_context):
    """
    Trace a single envelope through the P02 DAG.

    Input: Minimal P02 envelope (flat structure per dossier)
    Output: Fully enriched envelope after all 15 modules

    DAG Order (per P02 dossier):
    Stage 10: M01 (pattern_separate)
    Stage 20: M02 (semantic_project)
    Stage 30: M04 (affect_analyze)
    Stage 31: M05 (resolve_visibility)
    Stage 32: M07 (family_graph_resolve)
    Stage 33: M08 (temporal_profile)
    Stage 40: M09 (device_profile)
    Stage 41: M10 (ingress_classify)
    Stage 42: M11 (geo_metadata)
    Stage 43: M12 (spatial_minimal)
    Stage 50: M15 (retention_lookup)
    Stage 55: M06 (salience_score)
    Stage 60: M13 (hipp_events_row)
    Stage 61: M14 (embedding_queue_write)
    Stage 70: M16 (hipp_events_writer) - SKIP in integration test
    Stage 80: M17 (event_emitter) - SKIP in integration test
    """
    # Import modules
    # Step 1: Create input envelope (flat structure per P02 dossier)
    import uuid
    from datetime import datetime, timezone

    from k0.modules.affect import analyze as affect_analyze
    from k0.modules.builders import embedding_queue_write, hipp_events_row
    from k0.modules.context import (
        device_profile,
        geo_metadata,
        ingress_classify,
        retention_lookup,
        spatial_minimal,
        temporal_profile,
    )
    from k0.modules.hippocampus import pattern_separate, semantic_project
    from k0.modules.salience import score as salience_score
    from k0.modules.social import family_graph_resolve
    from k0.modules.space import resolve_visibility

    cognitive_trace_id = str(uuid.uuid4())
    timestamp = int(datetime.now(timezone.utc).timestamp())

    envelope = {
        # Identity & Trace (cognitive_trace_id is primary identifier per P02 dossier)
        "cognitive_trace_id": cognitive_trace_id,
        "wal_pos": 1000,
        "tenant_id": "test_tenant",
        "space_id": "test_space",
        "topic": "memory.episodic.formation",
        "schema_version": "1.0.0",
        # Policy
        "band": "GREEN",
        "policy_version": "2025-11-01",
        "policy_decision": "ALLOW",
        "policy_stamp": {
            "visible_to": ["test_actor"],
            "obligations": [],
        },
        # Actor
        "actor_id": "test_actor",
        "device_id": "test_device",
        # Timestamps
        "ts": timestamp,
        "ingested_at": timestamp,
        # Body
        "body": {
            "text": "Family dinner at home with kids",
            "activity_type": "dinner",
            "event_time": datetime.now(timezone.utc).isoformat(),
        },
        # Context fields (needed by various modules)
        "participants": ["person_dad", "person_mom"],
        "location_name": "Home",
        "location_geohash": "9q8yyk",
    }

    print(f"\n{'='*80}")
    print("STEP 1: INPUT ENVELOPE")
    print(f"{'='*80}")
    print(f"cognitive_trace_id: {envelope['cognitive_trace_id']}")
    print(f"text: {envelope['body']['text']}")
    print(f"actor_id: {envelope['actor_id']}")
    print(f"space_id: {envelope['space_id']}")

    # Step 2: Execute modules in DAG order
    message = MockMessage(envelope)

    # Stage 10: M01 - Pattern Separation
    print(f"\n{'='*80}")
    print("STAGE 10: M01 (pattern_separate)")
    print(f"{'='*80}")
    envelope = await pattern_separate.run(message, mock_context)
    print(f"✓ Added: simhash_hex={envelope.get('simhash_hex', 'N/A')[:16]}...")
    print(f"✓ Added: minhash32 ({len(envelope.get('minhash32', '[]'))} bytes)")
    message = MockMessage(envelope)

    # Stage 20: M02 - Semantic Projection
    print(f"\n{'='*80}")
    print("STAGE 20: M02 (semantic_project)")
    print(f"{'='*80}")
    envelope = await semantic_project.run(message, mock_context)
    print(f"✓ Added: embedding_id={envelope.get('embedding_id', 'N/A')}")
    print(f"✓ Added: entities_json ({len(envelope.get('entities_json', '[]'))} bytes)")
    print(f"✓ Added: kg_triples_json ({len(envelope.get('kg_triples_json', '[]'))} bytes)")
    message = MockMessage(envelope)

    # Stage 30: M04 - Affect Analysis
    print(f"\n{'='*80}")
    print("STAGE 30: M04 (affect_analyze)")
    print(f"{'='*80}")
    envelope = await affect_analyze.run(message, mock_context)
    print(f"✓ Added: affect_valence={envelope.get('affect_valence', 'N/A')}")
    print(f"✓ Added: affect_arousal={envelope.get('affect_arousal', 'N/A')}")
    print(f"✓ Added: affect_band={envelope.get('affect_band', 'N/A')}")
    message = MockMessage(envelope)

    # Stage 31: M05 - Space Resolution
    print(f"\n{'='*80}")
    print("STAGE 31: M05 (resolve_visibility)")
    print(f"{'='*80}")
    envelope = await resolve_visibility.run(message, mock_context)
    print(
        f"✓ Added: space_resolve with owner_id={envelope.get('space_resolve', {}).get('owner_id', 'N/A')}"
    )
    message = MockMessage(envelope)

    # Stage 32: M07 - Family Graph Resolution
    print(f"\n{'='*80}")
    print("STAGE 32: M07 (family_graph_resolve)")
    print(f"{'='*80}")
    envelope = await family_graph_resolve.run(message, mock_context)
    print(f"✓ Added: num_participants={envelope.get('num_participants', 'N/A')}")
    print(f"✓ Added: social_context={envelope.get('social_context', 'N/A')}")
    message = MockMessage(envelope)

    # Stage 33: M08 - Temporal Profile
    print(f"\n{'='*80}")
    print("STAGE 33: M08 (temporal_profile)")
    print(f"{'='*80}")
    envelope = await temporal_profile.run(message, mock_context)
    print(f"✓ Added: event_time_utc={envelope.get('event_time_utc', 'N/A')}")
    print(f"✓ Added: time_of_day_bucket={envelope.get('time_of_day_bucket', 'N/A')}")
    message = MockMessage(envelope)

    # Stage 40: M09 - Device Profile
    print(f"\n{'='*80}")
    print("STAGE 40: M09 (device_profile)")
    print(f"{'='*80}")
    envelope = await device_profile.run(message, mock_context)
    print(f"✓ Added: device_kind={envelope.get('device_kind', 'N/A')}")
    message = MockMessage(envelope)

    # Stage 41: M10 - Ingress Classify
    print(f"\n{'='*80}")
    print("STAGE 41: M10 (ingress_classify)")
    print(f"{'='*80}")
    envelope = await ingress_classify.run(message, mock_context)
    print(f"✓ Added: ingress_channel={envelope.get('ingress_channel', 'N/A')}")
    message = MockMessage(envelope)

    # Stage 42: M11 - Geo Metadata
    print(f"\n{'='*80}")
    print("STAGE 42: M11 (geo_metadata)")
    print(f"{'='*80}")
    envelope = await geo_metadata.run(message, mock_context)
    print(f"✓ Added: geo_precision_external={envelope.get('geo_precision_external', 'N/A')}")
    message = MockMessage(envelope)

    # Stage 43: M12 - Spatial Minimal
    print(f"\n{'='*80}")
    print("STAGE 43: M12 (spatial_minimal)")
    print(f"{'='*80}")
    envelope = await spatial_minimal.run(message, mock_context)
    print(f"✓ Added: geohash_6={envelope.get('geohash_6', 'N/A')}")
    message = MockMessage(envelope)

    # Stage 50: M15 - Retention Lookup
    print(f"\n{'='*80}")
    print("STAGE 50: M15 (retention_lookup)")
    print(f"{'='*80}")
    envelope = await retention_lookup.run(message, mock_context)
    print(f"✓ Added: retention_policy_id={envelope.get('retention_policy_id', 'N/A')}")
    message = MockMessage(envelope)

    # Stage 55: M06 - Salience Score
    print(f"\n{'='*80}")
    print("STAGE 55: M06 (salience_score)")
    print(f"{'='*80}")
    envelope = await salience_score.run(message, mock_context)
    print(f"✓ Added: salience_score={envelope.get('salience_score', 'N/A')}")
    message = MockMessage(envelope)

    # Stage 60: M13 - Build Hipp Events Row
    print(f"\n{'='*80}")
    print("STAGE 60: M13 (hipp_events_row)")
    print(f"{'='*80}")
    envelope = await hipp_events_row.run(message, mock_context)
    print(f"✓ Added: hipp_events_row with {len(envelope.get('hipp_events_row', {}))} fields")
    message = MockMessage(envelope)

    # Stage 61: M14 - Build Embedding Queue Job
    print(f"\n{'='*80}")
    print("STAGE 61: M14 (embedding_queue_write)")
    print(f"{'='*80}")
    envelope = await embedding_queue_write.run(message, mock_context)
    print("✓ Added: embedding_queue_job")

    # Step 3: Validate final output
    print(f"\n{'='*80}")
    print("FINAL OUTPUT: Enriched Envelope")
    print(f"{'='*80}")
    print("Original fields preserved:")
    print(f"  - cognitive_trace_id: {envelope.get('cognitive_trace_id', 'MISSING')}")
    print(f"  - tenant_id: {envelope.get('tenant_id', 'MISSING')}")
    print(f"  - space_id: {envelope.get('space_id', 'MISSING')}")
    print(f"  - text: {envelope.get('body', {}).get('text', 'MISSING')}")
    print("\nEnrichments added by P02 modules:")
    enrichments = [
        "simhash_hex",
        "minhash32",
        "embedding_id",
        "entities_json",
        "kg_triples_json",
        "affect_valence",
        "affect_arousal",
        "affect_band",
        "space_resolve",
        "num_participants",
        "social_context",
        "event_time_utc",
        "time_of_day_bucket",
        "device_kind",
        "ingress_topic",
        "geo_precision_external",
        "geohash_6",
        "retention_policy_id",
        "salience_score",
        "hipp_events_row",
        "embedding_queue_write",
    ]

    present = []
    missing = []
    for field in enrichments:
        if field in envelope:
            present.append(field)
        else:
            missing.append(field)

    print(f"\nPresent ({len(present)}/{len(enrichments)}):")
    for field in present:
        print(f"  ✓ {field}")

    if missing:
        print(f"\nMissing ({len(missing)}/{len(enrichments)}):")
        for field in missing:
            print(f"  ✗ {field}")

    # Assertions
    assert envelope["cognitive_trace_id"] == cognitive_trace_id, "Original cognitive_trace_id lost"
    assert "body" in envelope, "Original body lost"
    assert envelope["body"]["text"] == "Family dinner at home with kids", "Original text lost"

    # Check critical enrichments
    assert "simhash_hex" in envelope, "M01 output missing"
    assert "embedding_id" in envelope, "M02 output missing"
    assert "affect_valence" in envelope, "M04 output missing"
    assert "hipp_events_row" in envelope, "M13 output missing"
    assert "embedding_queue_write" in envelope, "M14 output missing"

    print(f"\n{'='*80}")
    print("✅ SUCCESS: Envelope flowed through all 14 modules")
    print(f"{'='*80}\n")
    print(f"{'='*80}\n")
