"""
Epic 6.5: Metadata Preservation In Truth Writer Tests.

Tests that R2-computed metadata (centroid_metadata, ambiguity_score,
entity_ids, sentiment, emotion, salience, social_context,
activity_type_ultrabert) flows through to st_epi record_data
via _build_epi_record_data() and is included in the INSERT SQL.

Issues covered:
    6.5.1: centroid_metadata persisted
    6.5.2: ambiguity_score persisted
    6.5.3: enriched metadata fields (sentiment, emotion, entities, etc.)
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

import pytest

from k0.modules.consolidation.staging.idempotency import IdempotencyKeyGenerator
from k0.modules.consolidation.staging.truth_write_assembler import TruthWriteAssembler
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.phase_outputs import EpisodeCluster

# =============================================================================
# Fixtures
# =============================================================================

TEST_ULID = "01HXYZ654321METADATAEPIC65"


@pytest.fixture
def assembler() -> TruthWriteAssembler:
    return TruthWriteAssembler(
        idempotency_gen=IdempotencyKeyGenerator(cycle_ulid=TEST_ULID),
    )


def _make_cluster(
    cluster_id: str = "epi_m65",
    event_ids: Optional[List[str]] = None,
    centroid_metadata: Optional[Dict] = None,
    ambiguity_score: float = 0.0,
    entity_ids: Optional[List[str]] = None,
    dominant_sentiment: float = 0.0,
    dominant_emotion: str = "",
    aggregated_sentiment: Optional[float] = None,
    aggregated_salience: Optional[float] = None,
    dominant_social_context: Optional[str] = None,
    activity_type_ultrabert: str = "",
) -> EpisodeCluster:
    return EpisodeCluster(
        cluster_id=cluster_id,
        member_event_ids=event_ids or ["evt_001", "evt_002"],
        centroid_embedding_id="emb_001",
        centroid_metadata=centroid_metadata,
        ambiguity_score=ambiguity_score,
        entity_ids=entity_ids or [],
        dominant_sentiment=dominant_sentiment,
        dominant_emotion=dominant_emotion,
        aggregated_sentiment=aggregated_sentiment,
        aggregated_salience=aggregated_salience,
        dominant_social_context=dominant_social_context,
        activity_type_ultrabert=activity_type_ultrabert,
        temporal_start=1_700_000_000_000,
        temporal_end=1_700_003_600_000,
        location_hint="home",
        participants_json='["mom"]',
        activity_type="SOCIAL",
        cohesion_score=0.85,
        title="Test Episode",
        summary="A test episode for metadata preservation",
    )


def _make_event_state(event_id: str) -> P03EventState:
    return P03EventState(event_id=event_id)


# =============================================================================
# 6.5.1: centroid_metadata preservation
# =============================================================================


class TestCentroidMetadata:
    def test_centroid_metadata_persisted(self, assembler: TruthWriteAssembler):
        """centroid_metadata from EpisodeCluster flows to record_data."""
        metadata = {
            "version": 1,
            "centroids": {
                "start": {"event_id": "evt_001"},
                "end": {"event_id": "evt_002"},
                "emotional_peak": {"event_id": "evt_001"},
                "narrative_anchor": {"event_id": "evt_002"},
            },
        }
        cluster = _make_cluster(centroid_metadata=metadata)
        writes = assembler.assemble_epi_writes([cluster], {})
        data = writes[0].record_data
        assert data["centroid_metadata_json"] is not None
        parsed = json.loads(data["centroid_metadata_json"])
        assert parsed["version"] == 1
        assert "emotional_peak" in parsed["centroids"]
        assert parsed["centroids"]["start"]["event_id"] == "evt_001"

    def test_centroid_metadata_none_when_absent(self, assembler: TruthWriteAssembler):
        """No centroid_metadata produces None."""
        cluster = _make_cluster(centroid_metadata=None)
        writes = assembler.assemble_epi_writes([cluster], {})
        data = writes[0].record_data
        assert data["centroid_metadata_json"] is None

    def test_centroid_metadata_serialized_as_json(self, assembler: TruthWriteAssembler):
        """centroid_metadata is valid JSON string."""
        metadata = {"version": 1, "centroids": {"start": {"event_id": "e1"}}}
        cluster = _make_cluster(centroid_metadata=metadata)
        writes = assembler.assemble_epi_writes([cluster], {})
        raw = writes[0].record_data["centroid_metadata_json"]
        assert isinstance(raw, str)
        assert json.loads(raw) == metadata


# =============================================================================
# 6.5.2: ambiguity_score preservation
# =============================================================================


class TestAmbiguityScore:
    def test_ambiguity_score_persisted(self, assembler: TruthWriteAssembler):
        """ambiguity_score from EpisodeCluster flows to record_data."""
        cluster = _make_cluster(ambiguity_score=0.42)
        writes = assembler.assemble_epi_writes([cluster], {})
        data = writes[0].record_data
        assert data["ambiguity_score"] == pytest.approx(0.42)

    def test_ambiguity_score_zero_is_none(self, assembler: TruthWriteAssembler):
        """ambiguity_score of 0.0 (falsy) maps to None."""
        cluster = _make_cluster(ambiguity_score=0.0)
        writes = assembler.assemble_epi_writes([cluster], {})
        data = writes[0].record_data
        assert data["ambiguity_score"] is None


# =============================================================================
# 6.5.3: Enriched metadata fields
# =============================================================================


class TestEntityIds:
    def test_entity_ids_persisted(self, assembler: TruthWriteAssembler):
        """entity_ids from EpisodeCluster flows as sorted JSON."""
        cluster = _make_cluster(entity_ids=["ent_b", "ent_a", "ent_c"])
        writes = assembler.assemble_epi_writes([cluster], {})
        data = writes[0].record_data
        assert data["entity_ids_json"] is not None
        parsed = json.loads(data["entity_ids_json"])
        assert parsed == ["ent_a", "ent_b", "ent_c"]  # sorted

    def test_entity_ids_empty_is_none(self, assembler: TruthWriteAssembler):
        """Empty entity_ids maps to None."""
        cluster = _make_cluster(entity_ids=[])
        writes = assembler.assemble_epi_writes([cluster], {})
        data = writes[0].record_data
        assert data["entity_ids_json"] is None


class TestSentimentAndEmotion:
    def test_dominant_sentiment_persisted(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(dominant_sentiment=0.75)
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["dominant_sentiment"] == pytest.approx(0.75)

    def test_dominant_sentiment_zero_is_none(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(dominant_sentiment=0.0)
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["dominant_sentiment"] is None

    def test_dominant_emotion_persisted(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(dominant_emotion="joy")
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["dominant_emotion"] == "joy"

    def test_dominant_emotion_empty_is_none(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(dominant_emotion="")
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["dominant_emotion"] is None

    def test_aggregated_sentiment_persisted(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(aggregated_sentiment=0.55)
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["aggregated_sentiment"] == pytest.approx(0.55)

    def test_aggregated_sentiment_none_preserved(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(aggregated_sentiment=None)
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["aggregated_sentiment"] is None

    def test_aggregated_salience_persisted(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(aggregated_salience=0.88)
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["aggregated_salience"] == pytest.approx(0.88)


class TestSocialContext:
    def test_dominant_social_context_persisted(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(dominant_social_context="family_gathering")
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["dominant_social_context"] == "family_gathering"

    def test_dominant_social_context_none_preserved(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(dominant_social_context=None)
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["dominant_social_context"] is None


class TestActivityTypeUltrabert:
    def test_ultrabert_type_persisted(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(activity_type_ultrabert="RELATIONSHIP")
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["activity_type_ultrabert"] == "RELATIONSHIP"

    def test_ultrabert_type_empty_is_none(self, assembler: TruthWriteAssembler):
        cluster = _make_cluster(activity_type_ultrabert="")
        writes = assembler.assemble_epi_writes([cluster], {})
        assert writes[0].record_data["activity_type_ultrabert"] is None


# =============================================================================
# Full metadata round-trip
# =============================================================================


class TestFullMetadataRoundTrip:
    def test_all_metadata_fields_present(self, assembler: TruthWriteAssembler):
        """All 9 Epic 6.5 fields flow from EpisodeCluster to record_data."""
        cluster = _make_cluster(
            centroid_metadata={"version": 1, "centroids": {"start": {"event_id": "e1"}}},
            ambiguity_score=0.35,
            entity_ids=["ent_1", "ent_2"],
            dominant_sentiment=0.7,
            dominant_emotion="gratitude",
            aggregated_sentiment=0.65,
            aggregated_salience=0.8,
            dominant_social_context="family",
            activity_type_ultrabert="CELEBRATION",
        )
        writes = assembler.assemble_epi_writes([cluster], {})
        data = writes[0].record_data

        assert data["centroid_metadata_json"] is not None
        assert data["ambiguity_score"] == pytest.approx(0.35)
        assert json.loads(data["entity_ids_json"]) == ["ent_1", "ent_2"]
        assert data["dominant_sentiment"] == pytest.approx(0.7)
        assert data["dominant_emotion"] == "gratitude"
        assert data["aggregated_sentiment"] == pytest.approx(0.65)
        assert data["aggregated_salience"] == pytest.approx(0.8)
        assert data["dominant_social_context"] == "family"
        assert data["activity_type_ultrabert"] == "CELEBRATION"

    def test_all_metadata_absent_produces_nones(self, assembler: TruthWriteAssembler):
        """Default EpisodeCluster produces None for all 9 metadata fields."""
        cluster = _make_cluster()
        writes = assembler.assemble_epi_writes([cluster], {})
        data = writes[0].record_data

        assert data["centroid_metadata_json"] is None
        assert data["ambiguity_score"] is None
        assert data["entity_ids_json"] is None
        assert data["dominant_sentiment"] is None
        assert data["dominant_emotion"] is None
        assert data["aggregated_sentiment"] is None
        assert data["aggregated_salience"] is None
        assert data["dominant_social_context"] is None
        assert data["activity_type_ultrabert"] is None

    def test_existing_fields_unchanged(self, assembler: TruthWriteAssembler):
        """Pre-existing fields are unaffected by new metadata fields."""
        cluster = _make_cluster(
            ambiguity_score=0.5,
            dominant_sentiment=0.9,
        )
        writes = assembler.assemble_epi_writes([cluster], {})
        data = writes[0].record_data

        # Pre-existing fields still correct
        assert data["episode_id"] == "epi_m65"
        assert data["episode_summary"] == "A test episode for metadata preservation"
        assert data["episode_type"] == "SOCIAL"
        assert data["start_time_utc"] == 1_700_000_000_000
        assert data["cluster_confidence"] == 0.85
        assert data["primary_location"] == "home"


# =============================================================================
# Migration column verification
# =============================================================================


class TestMigration0086:
    def test_migration_file_exists(self):
        """Migration 0086 exists and has correct revision chain."""
        import importlib

        m = importlib.import_module("k0.db.alembic.versions.0086_st_epi_metadata_preservation")
        assert m.revision == "0086"
        assert m.down_revision == "0085"
