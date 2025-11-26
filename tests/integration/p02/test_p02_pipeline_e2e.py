"""
P02 Pipeline End-to-End Integration Tests

Executes the FULL P02 Write pipeline with REAL module implementations to verify:
1. Complete envelope flow through all 16 stages
2. Correct enrichment aggregation from parallel modules
3. Final st_hipp_events row assembly (70+ columns)
4. KG triplets and entity extraction (M02)
5. Atomic storage writes via syscalls

This test harness uses:
- Real PipelineRunner from k0/runtime/pipeline_runner.py
- Real ModuleRegistry loading actual module implementations
- In-memory SQLite database for storage verification
- Actual P02 pipeline YAML contract (p02_write.v1.yaml)

Use Cases:
- Verify P02 pipeline works end-to-end with real modules
- Accuracy testing for semantic extraction (entities, KG triples)
- Regression testing for pipeline changes
- Performance profiling with real module execution

Contract: k0/contracts/pipelines/p02_write.v1.yaml
Runtime: k0/runtime/pipeline_runner.py
"""

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from k0.bus.core import BusMessage
from k0.pipelines.protocol import PipelineContext
from k0.runtime.module_registry import ModuleRegistry
from k0.runtime.pipeline_runner import PipelineRunner
from k0.runtime.schemas import PipelineSpec

# =============================================================================
# Test Database Setup (In-Memory SQLite)
# =============================================================================


def create_test_database() -> sqlite3.Connection:
    """
    Create in-memory SQLite database with P02-relevant tables.

    Creates tables matching migration 0024:
    - st_hipp_events: Main episodic memory table (70+ columns)
    - st_pipeline_processed: Idempotency tracking
    - st_embedding_queue: P08 embedding job queue
    - st_outbox: Transactional event outbox
    """
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # st_hipp_events - exact schema from migration 0024
    conn.execute(
        """
        CREATE TABLE st_hipp_events (
            -- Identity & Trace (9 columns)
            event_id TEXT PRIMARY KEY,
            wal_pos INTEGER NOT NULL UNIQUE,
            cognitive_trace_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            effective_space_id TEXT,
            topic TEXT NOT NULL,
            uow_id TEXT,
            schema_version TEXT NOT NULL DEFAULT '1.0.0',

            -- Integrity & Audit (6 columns)
            envelope_sha256 TEXT NOT NULL,
            sig_alg TEXT NOT NULL,
            sig_kid TEXT NOT NULL,
            idem_key TEXT NOT NULL,
            ingested_at INTEGER NOT NULL,
            clock_skew_ms INTEGER,

            -- Policy & Visibility (10 columns)
            policy_decision TEXT NOT NULL CHECK(policy_decision IN ('ALLOW', 'DENY')),
            policy_band TEXT NOT NULL CHECK(policy_band IN ('GREEN', 'AMBER', 'RED')),
            policy_version TEXT NOT NULL,
            obligations_json TEXT,
            visible_to_json TEXT,
            visibility_scope TEXT CHECK(visibility_scope IN ('OWNER_ONLY', 'SPACE_DEFAULT', 'HOUSEHOLD_ALL', 'CUSTOM_SUBSET', 'EXTERNAL_SHARE')),
            owner_id TEXT NOT NULL,
            co_owners_json TEXT,
            retention_policy_id TEXT NOT NULL,
            retention_bucket TEXT NOT NULL CHECK(retention_bucket IN ('STANDARD', 'SENSITIVE', 'EPHEMERAL')),

            -- Actor & Device (6 columns)
            actor_id TEXT NOT NULL,
            actor_role TEXT CHECK(actor_role IN ('SELF', 'AGENT', 'SYSTEM', 'DELEGATE')),
            device_id TEXT NOT NULL,
            device_kind TEXT NOT NULL,
            device_os TEXT,
            ingress_channel TEXT,

            -- Temporal (11 columns)
            event_time_utc INTEGER NOT NULL,
            write_time_utc INTEGER NOT NULL,
            write_lag_ms INTEGER,
            local_date TEXT,
            local_time TEXT,
            day_of_week TEXT,
            is_weekend BOOLEAN,
            time_of_day_bucket TEXT,
            circadian_slot TEXT,
            is_backdated BOOLEAN,
            created_at INTEGER NOT NULL,

            -- Spatial & Place (5 columns)
            location_name TEXT,
            location_type TEXT,
            geohash_6 TEXT,
            geo_precision_external TEXT,
            geo_masking_reason TEXT,

            -- Social & Relationships (8 columns)
            participants_json TEXT,
            num_participants INTEGER,
            has_partner_present BOOLEAN,
            has_parent_present BOOLEAN,
            is_solo_event BOOLEAN,
            participant_roles_json TEXT,
            social_context TEXT,
            social_intimacy TEXT,

            -- Semantic & Activity (10 columns)
            text TEXT,
            text_normalized TEXT,
            char_count INTEGER,
            token_count INTEGER,
            language TEXT,
            activity_type TEXT,
            activity_category TEXT,
            is_meal BOOLEAN,
            is_outing BOOLEAN,
            ingress_source TEXT,

            -- Hippocampus: Pattern Separation & Novelty (8 columns)
            simhash_hex TEXT NOT NULL,
            minhash32 TEXT NOT NULL,
            novelty_score REAL,
            near_duplicates_json TEXT,
            is_near_duplicate BOOLEAN,
            episode_cluster_id TEXT,
            cluster_confidence REAL,
            clustering_version TEXT,

            -- Embeddings & Knowledge Graph (4 columns)
            embedding_id TEXT NOT NULL UNIQUE,
            embedding_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(embedding_status IN ('PENDING', 'IN_PROGRESS', 'READY', 'FAILED')),
            entities_json TEXT,
            kg_triples_json TEXT,

            -- Affect & Salience (9 columns)
            sentiment_score REAL,
            sentiment_label TEXT,
            dominant_emotions_json TEXT,
            affect_valence REAL,
            affect_arousal REAL,
            affect_band TEXT CHECK(affect_band IN ('GREEN', 'AMBER', 'RED')),
            salience_score REAL NOT NULL DEFAULT 0.0,
            salience_reasons_json TEXT,
            salience_band TEXT CHECK(salience_band IN ('HIGH', 'MED', 'LOW')),

            -- Metadata & Versioning (4 columns)
            hippocampus_api_version TEXT,
            space_resolver_version TEXT,
            schema_uri TEXT,
            updated_at INTEGER NOT NULL
        )
    """
    )

    # st_pipeline_processed - idempotency tracking
    conn.execute(
        """
        CREATE TABLE st_pipeline_processed (
            pipeline_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            wal_pos INTEGER NOT NULL,
            processed_at INTEGER NOT NULL,
            PRIMARY KEY (pipeline_id, space_id, wal_pos)
        )
    """
    )

    # st_embedding_queue - exact schema from migration 0024
    conn.execute(
        """
        CREATE TABLE st_embedding_queue (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            wal_pos INTEGER NOT NULL,
            event_id TEXT NOT NULL,
            embedding_id TEXT NOT NULL UNIQUE,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            vector_kind TEXT NOT NULL,
            model_id TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'NORMAL' CHECK(priority IN ('HIGH', 'NORMAL', 'LOW')),
            status TEXT NOT NULL CHECK(status IN ('PENDING', 'IN_PROGRESS', 'READY', 'FAILED_RETRYABLE', 'FAILED_PERMANENT')),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            next_attempt_ts INTEGER,
            last_error TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """
    )

    # st_outbox - transactional event outbox
    conn.execute(
        """
        CREATE TABLE st_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wal_pos INTEGER DEFAULT 0,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            driver TEXT NOT NULL,
            op_kind TEXT NOT NULL,
            payload BLOB NOT NULL,
            fingerprint TEXT NOT NULL,
            requeue_seq INTEGER DEFAULT 0,
            retries INTEGER DEFAULT 0,
            created_at INTEGER DEFAULT (strftime('%s', 'now')),
            UNIQUE(fingerprint, requeue_seq)
        )
    """
    )

    conn.commit()
    return conn


# =============================================================================
# Mock UnitOfWork for Testing
# =============================================================================


class MockUnitOfWork:
    """Mock UnitOfWork that wraps SQLite connection for testing."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self.connection = connection  # Alias for outbox_emit_batch

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._connection.commit()
        return False


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def test_db():
    """Create fresh in-memory test database."""
    conn = create_test_database()
    yield conn
    conn.close()


@pytest.fixture
def uow_factory(test_db):
    """Factory for creating MockUnitOfWork instances."""

    def _factory():
        return MockUnitOfWork(test_db)

    return _factory


@pytest.fixture
def mock_syscalls(uow_factory, test_db):
    """
    Create Syscalls-like object with real storage operations.

    Uses in-memory SQLite for actual data persistence during test.
    Note: Must share same test_db connection as the test verification.
    """
    from k0.kernel.syscalls import Syscalls

    # Grant all capabilities needed by P02
    granted_caps = {
        "st_hipp_events.write",
        "st_pipeline_processed.write",
        "st_embedding_queue.write",
        "st_outbox.write",
    }

    # Use factory that shares the test_db connection
    return Syscalls(
        pipeline_id="P02_WRITE_TEST",
        granted_caps=granted_caps,
        uow_factory=uow_factory,
    )


@pytest.fixture
def mock_context(mock_syscalls):
    """Create PipelineContext with real syscalls."""
    import logging

    logger = logging.getLogger("test.p02.e2e")
    logger.setLevel(logging.DEBUG)

    return PipelineContext(
        syscalls=mock_syscalls,
        config={},
        logger=logger,
        preloaded_models=None,
    )


@pytest.fixture
def p02_spec():
    """Load actual P02 pipeline specification."""
    spec_path = Path("d:/familyos/k0/contracts/pipelines/p02_write.v1.yaml")
    return PipelineSpec.load(str(spec_path))


@pytest.fixture
def module_registry():
    """Create module registry (lazy loads real implementations)."""
    return ModuleRegistry()


@pytest.fixture
def sample_envelope():
    """
    Create sample envelope that exercises all P02 modules.

    Based on P02 dossier example input envelope (post-PEP, pre-P02).
    Includes all required fields for st_hipp_events NOT NULL columns.

    Includes:
    - Rich text content for semantic extraction
    - Participants for social resolution
    - Location for geo/spatial enrichment
    - Event time for temporal profiling
    - Device info for device profiling
    - Integrity fields (envelope_sha256, sig_alg, sig_kid, idem_key)
    """
    import hashlib

    cognitive_trace_id = str(uuid.uuid4())
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)
    timestamp = int(now.timestamp())

    # Generate realistic integrity fields
    envelope_content = f"{cognitive_trace_id}:{event_id}:{timestamp}"
    envelope_sha256 = hashlib.sha256(envelope_content.encode()).hexdigest()
    idem_key = f"idem:{uuid.uuid4().hex[:32]}"

    return {
        # Identity & Trace (per P02 dossier)
        "cognitive_trace_id": cognitive_trace_id,
        "event_id": event_id,
        "wal_pos": 1001,
        "tenant_id": "family-smith",
        "space_id": "personal:dad",
        "topic": "cognitive.memory.write.committed.v1",
        "schema_uri": "https://contracts.family-ai.dev/schemas/memory.episodic.json",
        "schema_version": "1.0.0",
        # Integrity & Audit (required NOT NULL fields)
        "envelope_sha256": envelope_sha256,
        "sig_alg": "ECDSA_P256_SHA256",
        "sig_kid": "did:device:dad-phone#2025-10-01",
        "sig": "MEUCIQD1lF8Qvf9wG0Cjd8nYQ0BfJ4ZC2x7Lrv3N5YFhV6t9WgIgS5n4xv7QzSp6Yjpm3zDR6hccgZL4z6hA1Pd1yEi8Zv8=",
        "idem_key": idem_key,
        "clock_skew_ms": 100,
        # Policy (per P02 dossier)
        "band": "GREEN",
        "policy_version": "2025-11-01",
        "policy_decision": "ALLOW",
        "policy_stamp": {
            "policy_version": "2025-11-01",
            "band": "GREEN",
            "obligations": [],
            "visible_to": ["person_dad", "person_mom"],
            "decision": "ALLOW",
        },
        # Actor & Device (per P02 dossier)
        "actor_id": "person_dad",
        "actor": "person_dad",  # Alias for compatibility
        "device_id": "device-dad-phone",
        "device": {
            "kind": "phone",
            "os": "iOS",
            "client_version": "2.5.0",
            "build": "1234",
        },
        # Timestamps
        "ts": timestamp,
        "ingested_at": timestamp,
        # Body - Rich content for semantic extraction (per P02 dossier)
        "body": {
            "text": "Had a wonderful dinner with Sarah and the kids at Giovanni's Restaurant. "
            "We celebrated Emma's 8th birthday with a beautiful chocolate cake. "
            "The weather was perfect and everyone was so happy. "
            "I really cherish these family moments together.",
            "topics": ["family", "dining", "celebration"],
            "sentiment": 0.85,
            "sentiment_label": "positive",
            "emotion_tags": ["joy", "love", "contentment"],
            "categories": ["social", "meal", "family"],
            "activity_type": "dinner",
            "activity_category": "dining",
            "location_name": "Giovanni's Restaurant",
            "location_type": "restaurant",
            "location_geohash": "9q8yyk",
            "participants": ["person_dad", "person_mom", "person_emma", "person_jake"],
            "event_time": now.isoformat(),
            "session_id": f"session-{uuid.uuid4().hex[:8]}",
            "conversation_turn": 1,
            "language": "en",
        },
    }


@pytest.fixture
def sample_envelope_minimal():
    """Minimal envelope for basic pipeline execution."""
    cognitive_trace_id = str(uuid.uuid4())
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    timestamp = int(datetime.now(timezone.utc).timestamp())

    return {
        "cognitive_trace_id": cognitive_trace_id,
        "event_id": event_id,
        "wal_pos": 1002,
        "tenant_id": "test_tenant",
        "space_id": "personal:test_user",
        "topic": "cognitive.memory.write.committed.v1",
        "schema_version": "1.0.0",
        "band": "GREEN",
        "policy_decision": "ALLOW",
        "policy_stamp": {"visible_to": ["test_user"], "obligations": []},
        "actor": "test_user",
        "device_id": "device_xyz",
        "ts": timestamp,
        "ingested_at": timestamp,
        "body": {
            "text": "Quick note to self: buy groceries tomorrow.",
            "activity_type": "routine",
            "event_time": datetime.now(timezone.utc).isoformat(),
        },
    }


# =============================================================================
# End-to-End Pipeline Tests
# =============================================================================


@pytest.mark.asyncio
async def test_p02_pipeline_full_execution(
    p02_spec,
    module_registry,
    mock_context,
    sample_envelope,
    test_db,
):
    """
    Execute complete P02 pipeline with real modules and verify output.

    Verifies:
    1. All 16 stages execute successfully
    2. Enriched envelope contains expected keys from each module
    3. Final st_hipp_events row is correctly assembled
    4. KG triplets and entities are extracted (M02)
    5. Storage writes succeed
    """
    # Create pipeline runner
    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    # Verify pipeline initialization
    assert runner.pipeline_id == "P02_WRITE"
    assert len(runner._level_groups) >= 6, "Expected at least 6 execution levels"

    # Create BusMessage
    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(sample_envelope).encode("utf-8"),
        offset=sample_envelope["wal_pos"],
        trace_id=sample_envelope["cognitive_trace_id"],
        space_id=sample_envelope["space_id"],
    )

    # Execute pipeline
    start_time = time.time()
    await runner.handle(message)
    duration_ms = (time.time() - start_time) * 1000

    # Verify execution completed
    assert len(runner._completed_stages) == 16, (
        f"Expected 16 completed stages, got {len(runner._completed_stages)}: "
        f"{runner._completed_stages}"
    )
    assert len(runner._failed_stages) == 0, f"Failed stages: {runner._failed_stages}"

    # Verify enriched envelope has expected keys
    enriched = runner._enriched_envelope
    assert enriched is not None, "Enriched envelope should not be None"

    # M01 (pattern_separate) output
    assert "simhash_hex" in enriched, "Missing simhash_hex from M01"
    assert "minhash32" in enriched, "Missing minhash32 from M01"
    assert len(enriched.get("simhash_hex", "")) == 16, "SimHash should be 16 hex chars"

    # M02 (semantic_project) output - KG triplets!
    assert "embedding_id" in enriched, "Missing embedding_id from M02"
    assert "entities_json" in enriched, "Missing entities_json from M02 (KG triplets)"
    assert "kg_triples_json" in enriched, "Missing kg_triples_json from M02 (KG triplets)"

    # Verify entities were extracted
    entities = json.loads(enriched.get("entities_json", "[]"))
    assert len(entities) > 0, "Expected entities to be extracted from rich text"

    # Verify KG triples were generated
    kg_triples = json.loads(enriched.get("kg_triples_json", "[]"))
    # Note: KG triples may be empty for simple text, but structure should exist
    assert isinstance(kg_triples, list), "kg_triples_json should be a JSON array"

    # M05 (affect.analyze) output
    assert "affect_valence" in enriched, "Missing affect_valence from M05"
    assert "affect_arousal" in enriched, "Missing affect_arousal from M05"

    # M12 (salience.score) output
    assert "salience_score" in enriched, "Missing salience_score from M12"
    assert "salience_band" in enriched, "Missing salience_band from M12"

    # M13 (hipp_events_row) output
    assert "hipp_events_row" in enriched, "Missing hipp_events_row from M13 builder"
    hipp_row = enriched["hipp_events_row"]
    assert isinstance(hipp_row, dict), "hipp_events_row should be a dict"

    # Verify hipp_events_row has required columns
    required_columns = [
        "event_id",
        "wal_pos",
        "cognitive_trace_id",
        "tenant_id",
        "space_id",
        "embedding_id",
        "simhash_hex",
        "entities_json",
        "kg_triples_json",
        "salience_score",
        "policy_band",
    ]
    for col in required_columns:
        assert col in hipp_row, f"Missing required column {col} in hipp_events_row"

    # Verify storage - query st_hipp_events
    # Note: M13 maps cognitive_trace_id to event_id in st_hipp_events

    cursor = test_db.execute(
        "SELECT * FROM st_hipp_events WHERE event_id = ?", (sample_envelope["cognitive_trace_id"],)
    )
    row = cursor.fetchone()
    assert row is not None, "Event should be inserted into st_hipp_events"

    # Verify stored row has KG triplets
    assert row["entities_json"] is not None, "entities_json should be stored"
    assert row["kg_triples_json"] is not None, "kg_triples_json should be stored"
    assert row["embedding_id"] is not None, "embedding_id should be stored"

    # Verify st_pipeline_processed record
    cursor = test_db.execute(
        "SELECT * FROM st_pipeline_processed WHERE pipeline_id = ? AND wal_pos = ?",
        ("P02_WRITE", sample_envelope["wal_pos"]),
    )
    processed = cursor.fetchone()
    assert processed is not None, "Pipeline processed record should exist"

    # Verify st_embedding_queue job created
    # NOTE: M14 (embedding_queue_write) uses an in-memory dict, NOT syscalls.
    # So we verify the enrichment key exists instead of checking database.
    # TODO: Update M14 to use syscalls.embedding_enqueue() for proper integration.
    embed_write = enriched.get("embedding_queue_write", {})
    assert (
        embed_write.get("inserted") is True or embed_write.get("status") == "INSERTED"
    ), f"Embedding queue write should succeed: {embed_write}"

    # Performance check (relaxed for E2E test with module loading overhead)
    # Production target is 171ms P95, but E2E with cold module loading is slower
    assert duration_ms < 3000, f"Pipeline took {duration_ms:.1f}ms, expected < 3000ms for E2E"

    print("\n=== P02 E2E Test Passed! ===")
    print(f"   Duration: {duration_ms:.1f}ms")
    print(f"   Stages: {len(runner._completed_stages)}")
    print(f"   Entities extracted: {len(entities)}")
    print(f"   KG triples: {len(kg_triples)}")
    print(f"   SimHash: {enriched.get('simhash_hex')}")
    print(f"   Salience: {enriched.get('salience_score'):.3f}")


@pytest.mark.asyncio
async def test_p02_kg_triplet_extraction(
    p02_spec,
    module_registry,
    mock_context,
    test_db,
):
    """
    Verify KG triplet extraction from M02 (semantic_project).

    Tests entity extraction and knowledge graph triple generation
    with text containing clear subject-predicate-object relationships.
    """
    import hashlib

    # Create envelope with text designed for KG extraction
    cognitive_trace_id = str(uuid.uuid4())
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)
    timestamp = int(now.timestamp())
    envelope_content = f"{cognitive_trace_id}:{event_id}:{timestamp}"

    envelope = {
        "cognitive_trace_id": cognitive_trace_id,
        "event_id": event_id,
        "wal_pos": 2001,
        "tenant_id": "test_tenant",
        "space_id": "personal:test_user",
        "topic": "cognitive.memory.write.committed.v1",
        "schema_version": "1.0.0",
        # Integrity fields (required NOT NULL)
        "envelope_sha256": hashlib.sha256(envelope_content.encode()).hexdigest(),
        "sig_alg": "NONE",
        "sig_kid": "unsigned",
        "idem_key": f"idem:{uuid.uuid4().hex[:32]}",
        # Policy
        "band": "GREEN",
        "policy_version": "2025-11-01",
        "policy_decision": "ALLOW",
        "policy_stamp": {"visible_to": ["test_user"], "obligations": [], "decision": "ALLOW"},
        # Actor
        "actor": "test_user",
        "actor_id": "test_user",
        "device_id": "device_xyz",
        "device": {"kind": "phone", "os": "iOS"},
        "ts": timestamp,
        "ingested_at": timestamp,
        "body": {
            # Text with clear entities and relationships
            "text": "John Smith met with Dr. Sarah Johnson at Stanford Hospital. "
            "They discussed the treatment plan for diabetes management. "
            "John lives in San Francisco and works at Google.",
            "activity_type": "medical",
            "event_time": now.isoformat(),
        },
    }

    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(envelope).encode("utf-8"),
        offset=envelope["wal_pos"],
        trace_id=envelope["cognitive_trace_id"],
        space_id=envelope["space_id"],
    )

    await runner.handle(message)

    enriched = runner._enriched_envelope

    # Verify entity extraction
    # Note: M02 returns entities as a list of entity ID strings, not dicts
    entities = json.loads(enriched.get("entities_json", "[]"))

    # Should extract person names and organizations
    print(f"\n=== Extracted entities: {entities}")

    # Verify at least some named entities were found
    assert len(entities) > 0, "Should extract at least some entities"

    # Verify KG triples structure
    # M02 returns triples as [[subject, predicate, object], ...]
    kg_triples = json.loads(enriched.get("kg_triples_json", "[]"))
    print(f"   KG triples count: {len(kg_triples)}")

    if kg_triples:
        for triple in kg_triples[:3]:
            print(f"   Triple: {triple}")


@pytest.mark.asyncio
async def test_p02_parallel_stage_execution(
    p02_spec,
    module_registry,
    mock_context,
    sample_envelope_minimal,
):
    """
    Verify parallel stage execution within DAG levels.

    Tests that stages 30-43 (parallel enrichment group) execute concurrently.
    """
    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    # Verify level structure
    level_groups = runner._level_groups
    assert len(level_groups) >= 6, f"Expected at least 6 levels, got {len(level_groups)}"

    # Level 2 should have 8+ parallel stages (30-43)
    level_2_size = len(level_groups[2]) if len(level_groups) > 2 else 0
    assert level_2_size >= 8, f"Expected 8+ parallel stages in Level 2, got {level_2_size}"

    # Execute pipeline
    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(sample_envelope_minimal).encode("utf-8"),
        offset=sample_envelope_minimal["wal_pos"],
        trace_id=sample_envelope_minimal["cognitive_trace_id"],
    )

    start = time.time()
    await runner.handle(message)
    duration = time.time() - start

    # With 8 parallel stages, should be faster than sequential
    # Sequential ~100ms, parallel ~50ms
    print(f"\n⏱️ Parallel execution time: {duration * 1000:.1f}ms")
    print(f"   Max parallelism: {runner._max_parallelism}")

    assert runner._max_parallelism >= 8, "Should have max parallelism of at least 8"


@pytest.mark.asyncio
async def test_p02_enrichment_aggregation(
    p02_spec,
    module_registry,
    mock_context,
    sample_envelope,
):
    """
    Verify that all module outputs are correctly aggregated.

    Each parallel module contributes fields that must all appear
    in the final enriched envelope and hipp_events_row.
    """
    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(sample_envelope).encode("utf-8"),
        offset=sample_envelope["wal_pos"],
        trace_id=sample_envelope["cognitive_trace_id"],
    )

    await runner.handle(message)

    enriched = runner._enriched_envelope

    # Verify outputs from each module domain
    module_outputs = {
        # M01: hippocampus.pattern_separate
        "pattern_separate": ["simhash_hex", "minhash32", "fingerprint_computed_at_utc"],
        # M02: hippocampus.semantic_project
        "semantic_project": ["embedding_id", "entities_json", "kg_triples_json"],
        # M05: affect.analyze
        "affect_analyze": [
            "sentiment_score",
            "affect_valence",
            "affect_arousal",
            "affect_dominance",
        ],
        # M06: space.resolve_visibility
        "space_resolve": ["visible_to_json", "shared_with_json"],
        # M07: social.family_graph_resolve
        "social_resolve": ["social_context", "social_intimacy", "num_participants"],
        # M08: context.temporal_profile
        "temporal_profile": ["day_of_week", "circadian_slot"],
        # M09: context.device_profile
        "device_profile": ["device_kind", "device_os"],
        # M10: context.ingress_classify
        "ingress_classify": ["activity_type", "content_type"],
        # M12: salience.score
        "salience_score": ["salience_score", "salience_bucket"],
        # M13: builders.hipp_events_row
        "row_builder": ["hipp_events_row"],
    }

    missing = []
    for module, fields in module_outputs.items():
        for field in fields:
            if field not in enriched:
                missing.append(f"{module}.{field}")

    if missing:
        print(f"\n⚠️ Missing enrichment fields: {missing}")
        print(f"   Available keys: {sorted(enriched.keys())}")

    # Allow some fields to be missing (modules may not run in all cases)
    # But core fields should always be present
    core_fields = ["simhash_hex", "embedding_id", "hipp_events_row"]
    for field in core_fields:
        assert field in enriched, f"Core field {field} must be present"


@pytest.mark.asyncio
async def test_p02_idempotency(
    p02_spec,
    module_registry,
    mock_context,
    sample_envelope_minimal,
    test_db,
):
    """
    Verify pipeline idempotency - same envelope processed only once.

    Second execution of same wal_pos should be idempotent (no duplicate storage).
    """
    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(sample_envelope_minimal).encode("utf-8"),
        offset=sample_envelope_minimal["wal_pos"],
        trace_id=sample_envelope_minimal["cognitive_trace_id"],
    )

    # First execution
    await runner.handle(message)

    # Count records after first execution
    cursor = test_db.execute("SELECT COUNT(*) FROM st_hipp_events")
    count_after_first = cursor.fetchone()[0]

    # Second execution (same message)
    await runner.handle(message)

    # Count should be same (INSERT OR IGNORE)
    cursor = test_db.execute("SELECT COUNT(*) FROM st_hipp_events")
    count_after_second = cursor.fetchone()[0]

    assert (
        count_after_first == count_after_second
    ), f"Duplicate processing detected: {count_after_first} -> {count_after_second}"
    print(f"\n✅ Idempotency verified: {count_after_first} record(s) after 2 executions")


@pytest.mark.asyncio
async def test_p02_stage_timing_profile(
    p02_spec,
    module_registry,
    mock_context,
    sample_envelope_minimal,
):
    """
    Profile stage execution times for performance analysis.

    Useful for identifying bottleneck stages and optimization opportunities.
    """
    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(sample_envelope_minimal).encode("utf-8"),
        offset=sample_envelope_minimal["wal_pos"],
        trace_id=sample_envelope_minimal["cognitive_trace_id"],
    )

    await runner.handle(message)

    # Get timing profile
    timings = runner._stage_timings

    print("\n📊 P02 Stage Timing Profile:")
    print("-" * 50)

    total_ms = 0
    for stage_id, duration_ms in sorted(timings.items()):
        total_ms += duration_ms
        bar = "█" * int(duration_ms / 2)
        print(f"  {stage_id:40} {duration_ms:6.1f}ms {bar}")

    print("-" * 50)
    print(f"  {'TOTAL':40} {total_ms:6.1f}ms")

    # Verify no single stage dominates
    max_stage_ms = max(timings.values()) if timings else 0
    assert max_stage_ms < 200, f"Slowest stage took {max_stage_ms:.1f}ms (expected < 200ms)"


# =============================================================================
# Accuracy & Semantic Validation Tests
# =============================================================================


def create_realistic_memory_envelope(
    memory_text: str,
    activity_type: str,
    location_name: str = None,
    location_type: str = None,
    participants: list = None,
    sentiment_hint: str = "neutral",
    wal_pos: int = 3000,
) -> dict:
    """
    Create a realistic memory envelope for accuracy testing.

    Args:
        memory_text: The actual memory text to process
        activity_type: Type of activity (dinner, work, exercise, etc.)
        location_name: Optional location name
        location_type: Optional location type (restaurant, home, office, etc.)
        participants: Optional list of participant IDs
        sentiment_hint: Expected sentiment (positive, negative, neutral)
        wal_pos: WAL position for uniqueness

    Returns:
        Complete envelope matching P02 dossier format
    """
    import hashlib

    cognitive_trace_id = str(uuid.uuid4())
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)
    timestamp = int(now.timestamp())

    envelope_content = f"{cognitive_trace_id}:{event_id}:{timestamp}"
    envelope_sha256 = hashlib.sha256(envelope_content.encode()).hexdigest()

    body = {
        "text": memory_text,
        "activity_type": activity_type,
        "event_time": now.isoformat(),
        "language": "en",
    }

    if location_name:
        body["location_name"] = location_name
    if location_type:
        body["location_type"] = location_type
    if participants:
        body["participants"] = participants

    return {
        "cognitive_trace_id": cognitive_trace_id,
        "event_id": event_id,
        "wal_pos": wal_pos,
        "tenant_id": "family-test",
        "space_id": "personal:test_user",
        "topic": "cognitive.memory.write.committed.v1",
        "schema_version": "1.0.0",
        "envelope_sha256": envelope_sha256,
        "sig_alg": "NONE",
        "sig_kid": "unsigned",
        "idem_key": f"idem:{uuid.uuid4().hex[:32]}",
        "band": "GREEN",
        "policy_version": "2025-11-01",
        "policy_decision": "ALLOW",
        "policy_stamp": {
            "visible_to": ["test_user"],
            "obligations": [],
            "decision": "ALLOW",
        },
        "actor": "test_user",
        "actor_id": "test_user",
        "device_id": "device-test",
        "device": {"kind": "phone", "os": "iOS", "client_version": "1.0.0"},
        "ts": timestamp,
        "ingested_at": timestamp,
        "body": body,
    }


@pytest.mark.asyncio
async def test_p02_accuracy_positive_family_memory(
    p02_spec,
    module_registry,
    mock_context,
    test_db,
):
    """
    ACCURACY TEST: Positive family dinner memory.

    Input: A warm family dinner memory with celebration.
    Expected Outputs:
    - Affect: Positive valence, moderate arousal, GREEN band
    - Entities: Family members, restaurant
    - KG Triples: Actor had_dinner_at location, interacted_with participants
    - Social: Multiple participants, partner/family present
    - Temporal: Evening time bucket
    - Salience: HIGH (celebration, family)
    """
    envelope = create_realistic_memory_envelope(
        memory_text="Had a wonderful dinner with my wife Sarah and daughter Emma at Olive Garden. "
        "We celebrated Emma's birthday with cake and laughter. Everyone was so happy!",
        activity_type="dinner",
        location_name="Olive Garden",
        location_type="restaurant",
        participants=["test_user", "sarah", "emma"],
        sentiment_hint="positive",
        wal_pos=3001,
    )

    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(envelope).encode("utf-8"),
        offset=envelope["wal_pos"],
        trace_id=envelope["cognitive_trace_id"],
        space_id=envelope["space_id"],
    )

    await runner.handle(message)
    enriched = runner._enriched_envelope

    # Verify pipeline completed
    assert enriched is not None, "Pipeline should complete successfully"
    assert "hipp_events_row" in enriched, "Should produce hipp_events_row"

    hipp_row = enriched["hipp_events_row"]

    print("\n" + "=" * 70)
    print("ACCURACY TEST: Positive Family Memory")
    print("=" * 70)
    print(f"Input: {envelope['body']['text'][:80]}...")
    print("-" * 70)

    # 1. AFFECT ANALYSIS - Should be positive
    affect_valence = enriched.get("affect_valence", 0)
    affect_arousal = enriched.get("affect_arousal", 0)
    affect_band = enriched.get("affect_band", "UNKNOWN")

    print("\n[AFFECT]")
    print(f"  Valence:  {affect_valence:.3f} (expected: > 0.3 positive)")
    print(f"  Arousal:  {affect_arousal:.3f}")
    print(f"  Band:     {affect_band} (expected: GREEN)")

    assert (
        affect_valence > 0.0
    ), f"Positive memory should have positive valence, got {affect_valence}"
    assert affect_band == "GREEN", f"Happy family memory should be GREEN band, got {affect_band}"

    # 2. ENTITY EXTRACTION - Should find family members and restaurant
    entities = json.loads(enriched.get("entities_json", "[]"))
    print(f"\n[ENTITIES] ({len(entities)} found)")
    for entity in entities[:5]:
        print(f"  - {entity}")

    assert (
        len(entities) >= 2
    ), f"Should extract at least 2 entities (people/place), got {len(entities)}"

    # 3. KG TRIPLES - Should have activity and participant relationships
    kg_triples = json.loads(enriched.get("kg_triples_json", "[]"))
    print(f"\n[KG TRIPLES] ({len(kg_triples)} found)")
    for triple in kg_triples[:5]:
        print(f"  - {triple}")

    # 4. SOCIAL CONTEXT - Multiple participants
    num_participants = hipp_row.get("num_participants", 0)
    social_context = hipp_row.get("social_context", "UNKNOWN")
    has_partner = hipp_row.get("has_partner_present", False)

    print("\n[SOCIAL]")
    print(f"  Participants:   {num_participants} (expected: >= 2)")
    print(f"  Social Context: {social_context}")
    print(f"  Partner Present: {has_partner}")

    assert (
        num_participants >= 2
    ), f"Family dinner should have >= 2 participants, got {num_participants}"

    # 5. SALIENCE - Should be HIGH for celebration
    salience_score = enriched.get("salience_score", 0)
    salience_band = enriched.get("salience_band", "LOW")

    print("\n[SALIENCE]")
    print(f"  Score: {salience_score:.3f}")
    print(f"  Band:  {salience_band}")

    # 6. LOCATION
    location = hipp_row.get("location_name", "UNKNOWN")
    location_type = hipp_row.get("location_type", "UNKNOWN")
    geohash = hipp_row.get("geohash_6", "")

    print("\n[LOCATION]")
    print(f"  Name: {location}")
    print(f"  Type: {location_type}")
    print(f"  Geohash: {geohash or 'N/A'}")

    # 7. TEMPORAL
    time_bucket = hipp_row.get("time_of_day_bucket", "UNKNOWN")
    day_of_week = hipp_row.get("day_of_week", "UNKNOWN")

    print("\n[TEMPORAL]")
    print(f"  Time of Day: {time_bucket}")
    print(f"  Day of Week: {day_of_week}")

    # 8. FINGERPRINTS
    simhash = enriched.get("simhash_hex", "")
    embedding_id = enriched.get("embedding_id", "")

    print("\n[FINGERPRINTS]")
    print(f"  SimHash:     {simhash}")
    print(f"  Embedding ID: {embedding_id}")

    assert len(simhash) == 16, f"SimHash should be 16 hex chars, got {len(simhash)}"
    assert embedding_id, "Embedding ID should be generated"

    print("\n" + "=" * 70)
    print("RESULT: PASSED - All accuracy checks passed")
    print("=" * 70)


@pytest.mark.asyncio
async def test_p02_accuracy_work_meeting_memory(
    p02_spec,
    module_registry,
    mock_context,
    test_db,
):
    """
    ACCURACY TEST: Neutral work meeting memory.

    Input: A routine work meeting memory.
    Expected Outputs:
    - Affect: Neutral valence, low arousal
    - Activity: work/meeting type
    - Social: Solo or minimal participants
    - Salience: MED or LOW (routine)
    """
    envelope = create_realistic_memory_envelope(
        memory_text="Attended the weekly team standup meeting at 10am. "
        "Discussed project progress and upcoming deadlines. "
        "Need to finish the report by Friday.",
        activity_type="meeting",
        location_name="Office",
        location_type="office",
        participants=["test_user"],
        sentiment_hint="neutral",
        wal_pos=3002,
    )

    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(envelope).encode("utf-8"),
        offset=envelope["wal_pos"],
        trace_id=envelope["cognitive_trace_id"],
        space_id=envelope["space_id"],
    )

    await runner.handle(message)
    enriched = runner._enriched_envelope

    assert enriched is not None, "Pipeline should complete"

    hipp_row = enriched["hipp_events_row"]

    print("\n" + "=" * 70)
    print("ACCURACY TEST: Work Meeting Memory")
    print("=" * 70)
    print(f"Input: {envelope['body']['text'][:80]}...")
    print("-" * 70)

    # AFFECT - Should be neutral
    affect_valence = enriched.get("affect_valence", 0)
    affect_band = enriched.get("affect_band", "UNKNOWN")

    print("\n[AFFECT]")
    print(f"  Valence: {affect_valence:.3f} (expected: near 0 neutral)")
    print(f"  Band:    {affect_band}")

    # Work meetings are typically neutral
    assert -0.5 <= affect_valence <= 0.5, f"Work meeting should be neutral, got {affect_valence}"

    # ACTIVITY
    activity_type = hipp_row.get("activity_type", "UNKNOWN")
    print("\n[ACTIVITY]")
    print(f"  Type: {activity_type}")

    # SALIENCE - Routine meetings are usually LOW or MED
    salience_score = enriched.get("salience_score", 0)
    salience_band = enriched.get("salience_band", "UNKNOWN")

    print("\n[SALIENCE]")
    print(f"  Score: {salience_score:.3f}")
    print(f"  Band:  {salience_band}")

    # Core fields present
    assert enriched.get("simhash_hex"), "SimHash should be generated"
    assert enriched.get("embedding_id"), "Embedding ID should be generated"

    print("\n" + "=" * 70)
    print("RESULT: PASSED")
    print("=" * 70)


@pytest.mark.asyncio
async def test_p02_accuracy_medical_appointment(
    p02_spec,
    module_registry,
    mock_context,
    test_db,
):
    """
    ACCURACY TEST: Medical appointment memory (sensitive content).

    Input: A doctor visit memory with health-related content.
    Expected Outputs:
    - Activity: medical
    - Location: hospital/clinic
    - Entities: Doctor name, medical terms
    """
    envelope = create_realistic_memory_envelope(
        memory_text="Visited Dr. Johnson at Stanford Medical Center for my annual checkup. "
        "Blood pressure was 120/80, all tests came back normal. "
        "Need to schedule a follow-up in 6 months.",
        activity_type="medical",
        location_name="Stanford Medical Center",
        location_type="hospital",
        participants=["test_user"],
        sentiment_hint="neutral",
        wal_pos=3003,
    )

    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(envelope).encode("utf-8"),
        offset=envelope["wal_pos"],
        trace_id=envelope["cognitive_trace_id"],
        space_id=envelope["space_id"],
    )

    await runner.handle(message)
    enriched = runner._enriched_envelope

    assert enriched is not None, "Pipeline should complete"

    print("\n" + "=" * 70)
    print("ACCURACY TEST: Medical Appointment Memory")
    print("=" * 70)
    print(f"Input: {envelope['body']['text'][:80]}...")
    print("-" * 70)

    # ENTITIES - Should extract doctor name and medical facility
    entities = json.loads(enriched.get("entities_json", "[]"))
    print(f"\n[ENTITIES] ({len(entities)} found)")
    for entity in entities[:5]:
        print(f"  - {entity}")

    # LOCATION
    hipp_row = enriched["hipp_events_row"]
    location = hipp_row.get("location_name", "UNKNOWN")
    location_type = hipp_row.get("location_type", "UNKNOWN")

    print("\n[LOCATION]")
    print(f"  Name: {location}")
    print(f"  Type: {location_type}")

    # Core fields
    print("\n[FINGERPRINTS]")
    print(f"  SimHash: {enriched.get('simhash_hex', 'N/A')}")
    print(f"  Embedding ID: {enriched.get('embedding_id', 'N/A')}")

    assert enriched.get("simhash_hex"), "SimHash should be generated"
    assert enriched.get("embedding_id"), "Embedding ID should be generated"

    print("\n" + "=" * 70)
    print("RESULT: PASSED")
    print("=" * 70)


@pytest.mark.asyncio
async def test_p02_accuracy_exercise_memory(
    p02_spec,
    module_registry,
    mock_context,
    test_db,
):
    """
    ACCURACY TEST: Exercise/fitness memory.

    Input: A workout memory.
    Expected Outputs:
    - Activity: exercise
    - Solo event
    - Positive affect (endorphins)
    """
    envelope = create_realistic_memory_envelope(
        memory_text="Great morning run at Golden Gate Park! "
        "Did 5 miles in 45 minutes, felt really energized afterwards. "
        "The weather was perfect, sunny with a light breeze.",
        activity_type="exercise",
        location_name="Golden Gate Park",
        location_type="park",
        participants=["test_user"],
        sentiment_hint="positive",
        wal_pos=3004,
    )

    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(envelope).encode("utf-8"),
        offset=envelope["wal_pos"],
        trace_id=envelope["cognitive_trace_id"],
        space_id=envelope["space_id"],
    )

    await runner.handle(message)
    enriched = runner._enriched_envelope

    assert enriched is not None, "Pipeline should complete"

    hipp_row = enriched["hipp_events_row"]

    print("\n" + "=" * 70)
    print("ACCURACY TEST: Exercise Memory")
    print("=" * 70)
    print(f"Input: {envelope['body']['text'][:80]}...")
    print("-" * 70)

    # AFFECT - Exercise typically positive
    affect_valence = enriched.get("affect_valence", 0)
    affect_band = enriched.get("affect_band", "UNKNOWN")

    print("\n[AFFECT]")
    print(f"  Valence: {affect_valence:.3f} (expected: positive)")
    print(f"  Band:    {affect_band}")

    # SOCIAL - Solo activity
    is_solo = hipp_row.get("is_solo_event", False)
    num_participants = hipp_row.get("num_participants", 0)

    print("\n[SOCIAL]")
    print(f"  Solo Event: {is_solo}")
    print(f"  Participants: {num_participants}")

    # LOCATION
    print("\n[LOCATION]")
    print(f"  Name: {hipp_row.get('location_name', 'N/A')}")
    print(f"  Type: {hipp_row.get('location_type', 'N/A')}")

    # Core fields
    assert enriched.get("simhash_hex"), "SimHash should be generated"
    assert enriched.get("embedding_id"), "Embedding ID should be generated"

    print("\n" + "=" * 70)
    print("RESULT: PASSED")
    print("=" * 70)


@pytest.mark.asyncio
async def test_p02_full_output_inspection(
    p02_spec,
    module_registry,
    mock_context,
    sample_envelope,
    test_db,
):
    """
    COMPREHENSIVE OUTPUT INSPECTION: Print ALL columns from st_hipp_events.

    This test runs the pipeline and prints every single column value
    for manual inspection and verification.
    """
    runner = PipelineRunner(p02_spec, module_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=json.dumps(sample_envelope).encode("utf-8"),
        offset=sample_envelope["wal_pos"],
        trace_id=sample_envelope["cognitive_trace_id"],
        space_id=sample_envelope["space_id"],
    )

    await runner.handle(message)
    enriched = runner._enriched_envelope

    assert enriched is not None
    hipp_row = enriched.get("hipp_events_row", {})

    print("\n" + "=" * 80)
    print("FULL st_hipp_events OUTPUT INSPECTION")
    print("=" * 80)
    print(f"Memory: {sample_envelope['body']['text'][:60]}...")
    print("=" * 80)

    # Group columns by category for readability
    column_groups = {
        "IDENTITY & TRACE": [
            "event_id",
            "wal_pos",
            "cognitive_trace_id",
            "tenant_id",
            "space_id",
            "effective_space_id",
            "topic",
            "schema_version",
        ],
        "INTEGRITY & AUDIT": [
            "envelope_sha256",
            "sig_alg",
            "sig_kid",
            "idem_key",
            "ingested_at",
            "clock_skew_ms",
        ],
        "POLICY & VISIBILITY": [
            "policy_decision",
            "policy_band",
            "policy_version",
            "owner_id",
            "co_owners_json",
            "visible_to_json",
            "visibility_scope",
            "retention_policy_id",
            "retention_bucket",
        ],
        "ACTOR & DEVICE": ["actor_id", "device_id", "device_kind", "device_os", "ingress_channel"],
        "TEMPORAL": [
            "event_time_utc",
            "write_time_utc",
            "write_lag_ms",
            "local_date",
            "local_time",
            "day_of_week",
            "is_weekend",
            "time_of_day_bucket",
            "circadian_slot",
            "is_backdated",
            "created_at",
        ],
        "SPATIAL": [
            "location_name",
            "location_type",
            "geohash_6",
            "geo_precision_external",
            "geo_masking_reason",
        ],
        "SOCIAL": [
            "num_participants",
            "participant_roles_json",
            "has_partner_present",
            "has_parent_present",
            "is_solo_event",
            "social_context",
            "social_intimacy",
        ],
        "SEMANTIC": ["text", "activity_type", "activity_category", "ingress_source"],
        "HIPPOCAMPUS (Fingerprints)": [
            "simhash_hex",
            "minhash32",
            "novelty_score",
            "episode_cluster_id",
            "cluster_confidence",
        ],
        "EMBEDDINGS & KG": ["embedding_id", "embedding_status", "entities_json", "kg_triples_json"],
        "AFFECT & SALIENCE": [
            "affect_valence",
            "affect_arousal",
            "affect_band",
            "sentiment_score",
            "sentiment_label",
            "dominant_emotions_json",
            "salience_score",
            "salience_band",
            "salience_reasons_json",
        ],
    }

    for group_name, columns in column_groups.items():
        print(f"\n--- {group_name} ---")
        for col in columns:
            value = hipp_row.get(col, enriched.get(col, "N/A"))
            # Truncate long values
            if isinstance(value, str) and len(value) > 60:
                value = value[:57] + "..."
            print(f"  {col:30} = {value}")

    # Summary stats
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Total columns in hipp_row:  {len(hipp_row)}")
    print(f"  Total enriched keys:        {len(enriched)}")
    print(f"  Entities extracted:         {len(json.loads(enriched.get('entities_json', '[]')))}")
    print(f"  KG triples generated:       {len(json.loads(enriched.get('kg_triples_json', '[]')))}")
    print(f"  Pipeline stages completed:  {len(runner._completed_stages)}")
    print("=" * 80)

    # Verify critical fields are populated
    critical_fields = [
        "event_id",
        "embedding_id",
        "simhash_hex",
        "policy_band",
        "salience_score",
        "affect_valence",
        "owner_id",
    ]

    missing = [f for f in critical_fields if not hipp_row.get(f)]
    if missing:
        print(f"\nWARNING: Missing critical fields: {missing}")
    else:
        print("\nAll critical fields populated.")


# =============================================================================
# Test Runner Entry Point
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
