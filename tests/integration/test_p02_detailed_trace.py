"""
P02 Pipeline Detailed Trace - Show All Stages, Processing, Inputs, and Outputs

This test provides comprehensive visibility into:
- Each stage's input envelope
- Processing performed by each module
- Output enrichments added
- Field-by-field comparison before/after
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest


class MockMessage:
    """Mock message for Phase 2 module testing"""

    def __init__(self, envelope: dict[str, Any], trace_id: str | None = None):
        self.payload = envelope
        self.trace_id = trace_id or envelope.get("cognitive_trace_id", "test_trace")
        self.offset = envelope.get("wal_pos", 0)
        self.event_type = "cognitive.memory.write.committed.v1"


def print_separator(char="=", length=100):
    """Print a separator line"""
    print(f"\n{char * length}")


def print_header(title: str, stage: str = ""):
    """Print a section header"""
    print_separator()
    if stage:
        print(f"{stage}: {title}")
    else:
        print(title)
    print_separator()


def print_dict(data: dict, indent: int = 2, max_str_len: int = 80):
    """Pretty print dictionary with indentation"""
    for key, value in data.items():
        spaces = " " * indent
        if isinstance(value, dict):
            print(f"{spaces}{key}:")
            print_dict(value, indent + 2, max_str_len)
        elif isinstance(value, list):
            print(f"{spaces}{key}: [{len(value)} items]")
        elif isinstance(value, str) and len(value) > max_str_len:
            print(f"{spaces}{key}: {value[:max_str_len]}... ({len(value)} chars)")
        else:
            print(f"{spaces}{key}: {value}")


def compare_envelopes(before: dict, after: dict, stage_name: str):
    """Show what changed between before and after"""
    print(f"\n📊 CHANGES MADE BY {stage_name}:")
    print("-" * 100)

    # Find new fields
    new_fields = set(after.keys()) - set(before.keys())
    modified_fields = []

    # Find modified fields (that existed before)
    for key in set(before.keys()) & set(after.keys()):
        if before[key] != after[key]:
            modified_fields.append(key)

    if new_fields:
        print(f"\n✨ NEW FIELDS ADDED ({len(new_fields)}):")
        for field in sorted(new_fields):
            value = after[field]
            if isinstance(value, dict):
                print(f"  + {field}: <dict with {len(value)} keys>")
            elif isinstance(value, list):
                print(f"  + {field}: <list with {len(value)} items>")
            elif isinstance(value, str) and len(value) > 60:
                print(f"  + {field}: {value[:60]}... ({len(value)} chars)")
            else:
                print(f"  + {field}: {value}")

    if modified_fields:
        print(f"\n🔄 MODIFIED FIELDS ({len(modified_fields)}):")
        for field in sorted(modified_fields):
            print(f"  ~ {field}")
            print(f"    Before: {before[field]}")
            print(f"    After:  {after[field]}")

    if not new_fields and not modified_fields:
        print("  (No changes - module may have skipped processing)")

    print(f"\n📈 TOTAL FIELDS: {len(before)} → {len(after)} (added {len(new_fields)})")


@pytest.mark.asyncio
async def test_p02_pipeline_detailed_trace(mock_context):
    """
    Detailed trace of P02 pipeline execution.

    Shows:
    1. Initial input envelope structure
    2. Each module's processing stage
    3. What each module adds/modifies
    4. Final enriched output

    Pipeline stages (per P02 dossier):
    - Stage 10: M01 (pattern_separate) - DG fingerprints
    - Stage 20: M02 (semantic_project) - Entity extraction, embedding ID
    - Stage 30: M04 (affect_analyze) - Sentiment, emotion, valence/arousal
    - Stage 31: M05 (resolve_visibility) - Space ownership, ACLs
    - Stage 32: M07 (family_graph_resolve) - Social context
    - Stage 33: M08 (temporal_profile) - Time analysis
    - Stage 40: M09 (device_profile) - Device metadata
    - Stage 41: M10 (ingress_classify) - Content classification
    - Stage 42: M11 (geo_metadata) - Location enrichment
    - Stage 43: M12 (spatial_minimal) - Geohash processing
    - Stage 50: M15 (retention_lookup) - Policy lookup
    - Stage 55: M06 (salience_score) - Importance scoring
    - Stage 60: M13 (hipp_events_row) - Build st_hipp_events row (86 fields)
    - Stage 61: M14 (embedding_queue_write) - Queue for P08
    """

    # Import all modules
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

    # =========================================================================
    # STEP 0: CREATE INPUT ENVELOPE
    # =========================================================================
    print_header("P02 PIPELINE DETAILED TRACE", "")
    print("\n🎬 Starting P02 pipeline trace with realistic input envelope...")

    cognitive_trace_id = str(uuid.uuid4())
    timestamp = int(datetime.now(timezone.utc).timestamp())

    envelope = {
        # Identity & Trace (cognitive_trace_id is primary identifier per P02 dossier)
        "cognitive_trace_id": cognitive_trace_id,
        "wal_pos": 1000,
        "tenant_id": "family-smith",
        "space_id": "personal:dad",
        "topic": "memory.episodic.formation",
        "schema_version": "1.0.0",
        # Policy (already validated by Command Port hot path)
        "band": "GREEN",
        "policy_version": "2025-11-01",
        "policy_decision": "ALLOW",
        "policy_stamp": {
            "visible_to": ["person_dad"],
            "obligations": [],
        },
        # Actor & Device
        "actor_id": "person_dad",
        "device_id": "device-dad-phone",
        # Timestamps
        "ts": timestamp,
        "ingested_at": timestamp,
        # Body (actual memory content)
        "body": {
            "text": "We had dinner at Olive Garden with Mom and it was great",
            "activity_type": "dinner",
            "event_time": datetime.now(timezone.utc).isoformat(),
        },
        # Context fields (for downstream modules)
        "participants": ["person_dad", "person_mom"],
        "location_name": "Olive Garden",
        "location_geohash": "9q8yy",
    }

    print_header("INPUT ENVELOPE (from WAL after Command Port hot path)", "STAGE 0")
    print("\n📥 This is what P02 receives after:")
    print("   - Gate validation")
    print("   - PEP policy enforcement")
    print("   - WAL commit (durable)")
    print("   - Outbox enqueue")
    print()
    print_dict(envelope)
    print(f"\n📊 Input envelope: {len(envelope)} top-level fields")

    # =========================================================================
    # STAGE 10: M01 - PATTERN SEPARATION (DG)
    # =========================================================================
    print_header("M01: PATTERN SEPARATION (Hippocampus DG)", "STAGE 10")
    print("\n🧠 PURPOSE: Generate deduplication fingerprints")
    print("   - SimHash: 64-bit locality-sensitive hash")
    print("   - MinHash: 32 x 64-bit hashes for similarity")
    print("   - Used by P03 for near-duplicate detection")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await pattern_separate.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M01")

    # =========================================================================
    # STAGE 20: M02 - SEMANTIC PROJECTION (CA1)
    # =========================================================================
    print_header("M02: SEMANTIC PROJECTION (Hippocampus CA1)", "STAGE 20")
    print("\n🔍 PURPOSE: Entity extraction and embedding allocation")
    print("   - Extract entities (people, places, activities)")
    print("   - Generate unique embedding_id")
    print("   - Create knowledge graph triples")
    print("   - Queue for P08 vector generation")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await semantic_project.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M02")

    # =========================================================================
    # STAGE 30: M04 - AFFECT ANALYSIS
    # =========================================================================
    print_header("M04: AFFECT ANALYSIS", "STAGE 30")
    print("\n😊 PURPOSE: Emotion and sentiment classification")
    print("   - Valence: Pleasant (+1) to Unpleasant (-1)")
    print("   - Arousal: Calm (0) to Excited (1)")
    print("   - Affect band: GREEN/AMBER/RED")
    print("   - Dominant emotions detected")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await affect_analyze.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M04")

    # =========================================================================
    # STAGE 31: M05 - SPACE RESOLUTION
    # =========================================================================
    print_header("M05: SPACE VISIBILITY RESOLUTION", "STAGE 31")
    print("\n🔒 PURPOSE: Resolve space ownership and ACLs")
    print("   - Determine owner_id from space_id")
    print("   - Set visibility scope (OWNER_ONLY, SPACE_DEFAULT, etc.)")
    print("   - Resolve co-owners")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await resolve_visibility.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M05")

    # =========================================================================
    # STAGE 32: M07 - FAMILY GRAPH RESOLUTION
    # =========================================================================
    print_header("M07: FAMILY GRAPH RESOLUTION", "STAGE 32")
    print("\n👨‍👩‍👧‍👦 PURPOSE: Social context from family relationships")
    print("   - Count participants")
    print("   - Detect partner/parent presence")
    print("   - Classify social context (solo, dyad, family, etc.)")
    print("   - Determine social intimacy level")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await family_graph_resolve.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M07")

    # =========================================================================
    # STAGE 33: M08 - TEMPORAL PROFILE
    # =========================================================================
    print_header("M08: TEMPORAL PROFILE", "STAGE 33")
    print("\n⏰ PURPOSE: Time analysis and circadian context")
    print("   - Parse event_time_utc")
    print("   - Compute local time with timezone")
    print("   - Classify time of day (morning, afternoon, evening, night)")
    print("   - Determine circadian slot (breakfast, lunch, dinner, etc.)")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await temporal_profile.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M08")

    # =========================================================================
    # STAGE 40: M09 - DEVICE PROFILE
    # =========================================================================
    print_header("M09: DEVICE PROFILE", "STAGE 40")
    print("\n📱 PURPOSE: Extract device metadata")
    print("   - Device kind (phone, tablet, watch, etc.)")
    print("   - Device OS and platform")
    print("   - Client version and build")
    print("   - Input method (text, voice, etc.)")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await device_profile.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M09")

    # =========================================================================
    # STAGE 41: M10 - INGRESS CLASSIFY
    # =========================================================================
    print_header("M10: INGRESS CLASSIFICATION", "STAGE 41")
    print("\n📝 PURPOSE: Classify content type and source")
    print("   - Activity type (meal, task, conversation, etc.)")
    print("   - Content type (episodic, semantic, procedural)")
    print("   - Ingress source (mobile_app, connector, api)")
    print("   - User-initiated vs system-generated")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await ingress_classify.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M10")

    # =========================================================================
    # STAGE 42: M11 - GEO METADATA
    # =========================================================================
    print_header("M11: GEO METADATA EXTRACTION", "STAGE 42")
    print("\n🌍 PURPOSE: Location enrichment")
    print("   - Extract geohash precision")
    print("   - Determine location type")
    print("   - Apply geo masking (AMBER/RED bands)")
    print("   - Record masking reason")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await geo_metadata.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M11")

    # =========================================================================
    # STAGE 43: M12 - SPATIAL MINIMAL
    # =========================================================================
    print_header("M12: SPATIAL MINIMIZATION", "STAGE 43")
    print("\n📍 PURPOSE: Reduce geohash precision for privacy")
    print("   - Truncate to 6-char geohash (~600m radius)")
    print("   - Apply band-specific precision rules")
    print("   - Preserve location_name if provided")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await spatial_minimal.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M12")

    # =========================================================================
    # STAGE 50: M15 - RETENTION LOOKUP
    # =========================================================================
    print_header("M15: RETENTION POLICY LOOKUP", "STAGE 50")
    print("\n🗄️ PURPOSE: Determine retention policy")
    print("   - Lookup policy by (band, topic, device_kind)")
    print("   - Set retention_policy_id")
    print("   - Classify retention bucket (STANDARD, SENSITIVE, EPHEMERAL)")
    print("   - Used by P10 for data minimization")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await retention_lookup.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M15")

    # =========================================================================
    # STAGE 55: M06 - SALIENCE SCORE
    # =========================================================================
    print_header("M06: SALIENCE SCORING", "STAGE 55")
    print("\n⭐ PURPOSE: Compute importance score")
    print("   - Combine: recency + novelty + affect + social + goals")
    print("   - Range: 0.0 (low) to 1.0 (high)")
    print("   - Classify salience band (HIGH, MED, LOW)")
    print("   - Used by P04 arbitration and working memory")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await salience_score.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M06")

    # =========================================================================
    # STAGE 60: M13 - BUILD HIPP_EVENTS ROW
    # =========================================================================
    print_header("M13: BUILD ST_HIPP_EVENTS ROW", "STAGE 60")
    print("\n🏗️ PURPOSE: Assemble final database row")
    print("   - Collect all module outputs")
    print("   - Map cognitive_trace_id → event_id")
    print("   - Build 86-field row for st_hipp_events table")
    print("   - Validate required fields and ranges")
    print("   - Ready for M16 to write to database")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await hipp_events_row.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M13")

    # Show row structure
    if "hipp_events_row" in envelope:
        row = envelope["hipp_events_row"]
        print(f"\n📋 ST_HIPP_EVENTS ROW STRUCTURE ({len(row)} fields):")
        print("-" * 100)

        # Group by category
        groups = {
            "Identity": ["event_id", "cognitive_trace_id", "tenant_id", "space_id", "topic"],
            "Policy": ["policy_decision", "policy_band", "visibility_scope", "owner_id"],
            "Actor": ["actor_id", "actor_role", "device_id", "device_kind"],
            "Temporal": ["event_time_utc", "local_date", "local_time", "time_of_day_bucket"],
            "Social": ["num_participants", "social_context", "social_intimacy"],
            "Hippocampus": ["simhash_hex", "minhash32", "embedding_id"],
            "Affect": ["affect_valence", "affect_arousal", "affect_band"],
            "Salience": ["salience_score", "salience_band"],
        }

        for group_name, fields in groups.items():
            print(f"\n  {group_name}:")
            for field in fields:
                if field in row:
                    value = row[field]
                    if isinstance(value, str) and len(value) > 60:
                        print(f"    {field}: {value[:60]}...")
                    else:
                        print(f"    {field}: {value}")

    # =========================================================================
    # STAGE 61: M14 - EMBEDDING QUEUE WRITE
    # =========================================================================
    print_header("M14: EMBEDDING QUEUE WRITE", "STAGE 61")
    print("\n📤 PURPOSE: Queue for P08 vector generation")
    print("   - Create st_embedding_queue record")
    print("   - Include embedding_id, text, entities, triples")
    print("   - Set status=PENDING, priority=NORMAL")
    print("   - P08 will claim and process")

    envelope_before = envelope.copy()
    message = MockMessage(envelope)
    envelope = await embedding_queue_write.run(message, mock_context)

    compare_envelopes(envelope_before, envelope, "M14")

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print_header("FINAL ENRICHED ENVELOPE", "SUMMARY")

    print("\n✅ Pipeline execution complete!")
    print(f"   Total fields in final envelope: {len(envelope)}")
    print("   Modules executed: 14")
    print("   Stages completed: Stage 10 → Stage 61")

    print("\n🎯 KEY OUTPUTS:")
    key_outputs = {
        "DG Fingerprints": ["simhash_hex", "minhash32"],
        "Semantic": ["embedding_id", "entities_json", "kg_triples_json"],
        "Affect": ["affect_valence", "affect_arousal", "affect_band"],
        "Social": ["num_participants", "social_context", "social_intimacy"],
        "Temporal": ["event_time_utc", "local_date", "time_of_day_bucket"],
        "Salience": ["salience_score", "salience_band"],
        "Database": ["hipp_events_row", "embedding_queue_write"],
    }

    for category, fields in key_outputs.items():
        print(f"\n  {category}:")
        for field in fields:
            if field in envelope:
                value = envelope[field]
                if isinstance(value, dict):
                    print(f"    ✓ {field} ({len(value)} fields)")
                elif isinstance(value, str) and len(value) > 50:
                    print(f"    ✓ {field} ({len(value)} chars)")
                elif isinstance(value, list):
                    print(f"    ✓ {field} ({len(value)} items)")
                else:
                    print(f"    ✓ {field}: {value}")
            else:
                print(f"    ✗ {field}: MISSING")

    print("\n" + "=" * 100)
    print("🎉 P02 PIPELINE TRACE COMPLETE")
    print("=" * 100 + "\n")

    # Final assertions
    assert envelope["cognitive_trace_id"] == cognitive_trace_id
    assert "hipp_events_row" in envelope
    assert "embedding_queue_write" in envelope
    assert len(envelope["hipp_events_row"]) >= 80  # Should have 86+ fields
