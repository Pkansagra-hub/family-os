"""Add UltraBERT enrichment columns to st_social.

Revision ID: 0054
Revises: 0053
Create Date: 2026-01-08

P03 Consolidation Pipeline - Social Relationship Enrichment

Brain Analog: Enhanced Social Cognition
Role: Capture UltraBERT-derived relationship semantics

Adds columns for richer social understanding:
- ultrabert_relation_types: Direct UltraBERT relation labels (parent_of, spouse_of, etc.)
- emotional_role: Social function (MENTOR, CONFIDANT, ENERGY_SOURCE, SUPPORT_GIVER)
- emotional_valence_avg: Average sentiment in interactions with this person
- emotional_valence_trend: Relationship warming (+) or cooling (-) trajectory
- relationship_phase: FORMING, STABLE, DEEPENING, COOLING, DORMANT
- interaction_modalities_json: How we interact (in_person, phone, text, video)
- typical_activities_json: What we do together (meal, work, recreation)
- sentiment_trajectory_json: Recent sentiment scores for trend analysis
- emotions_json: Aggregated emotions from interactions
- dominant_emotion: Most frequent emotion in interactions
- canonical_entity_id: Link to KG entity cluster

UltraBERT Capabilities Used:
- relations: parent_of, child_of, spouse_of, sibling_of, friend_of, colleague_of, lives_at
- sentiment: very_negative, negative, neutral, positive, very_positive
- emotions: 44 labels including family-specific (nostalgia, protectiveness, togetherness)
- ner_family: PERSON, KINSHIP (mom, dad, sister), NICKNAME

Dossier Reference: P03 Consolidation Dossier Section 6.6
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision: str = "0054"
down_revision: str = "0053"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add UltraBERT enrichment columns to st_social."""
    # ============================================================
    # UltraBERT Relation Types (direct from extracted_relations_json)
    # ============================================================

    # Direct UltraBERT relation labels - no inference needed
    # Values: parent_of, child_of, spouse_of, sibling_of, grandparent_of,
    #         grandchild_of, aunt_uncle_of, niece_nephew_of, cousin_of,
    #         pet_of, friend_of, colleague_of, lives_at, owns, no_relation
    # Format: JSON array allowing multiple types
    # Example: ["parent_of"], ["friend_of", "colleague_of"]
    op.add_column(
        "st_social",
        sa.Column("ultrabert_relation_types", sa.Text, nullable=True),
    )

    # ============================================================
    # Emotional Role & Significance
    # ============================================================

    # Social function this person plays in your life
    # Derived from interaction patterns and emotions
    # Values: MENTOR, CONFIDANT, ENERGY_SOURCE, SUPPORT_GIVER, SUPPORT_SEEKER,
    #         PLAYMATE, CARETAKER, CARE_RECEIVER, COLLABORATOR, COMPANION
    op.add_column(
        "st_social",
        sa.Column("emotional_role", sa.Text, nullable=True),
    )

    # Average emotional valence across all interactions
    # Derived from UltraBERT sentiment: -1.0 (very_negative) to +1.0 (very_positive)
    op.add_column(
        "st_social",
        sa.Column("emotional_valence_avg", sa.Float, nullable=True),
    )

    # Relationship trajectory: warming (+) or cooling (-)
    # Computed from sentiment trend over recent interactions
    op.add_column(
        "st_social",
        sa.Column("emotional_valence_trend", sa.Float, nullable=True),
    )

    # ============================================================
    # Relationship Phase & Evolution
    # ============================================================

    # Current phase of the relationship
    # Values: FORMING, STABLE, DEEPENING, COOLING, DORMANT, ESTRANGED
    op.add_column(
        "st_social",
        sa.Column("relationship_phase", sa.Text, nullable=True),
    )

    # Check constraint for valid relationship phases
    op.execute(
        """
        ALTER TABLE st_social
        ADD CONSTRAINT ck_social_relationship_phase
        CHECK (relationship_phase IS NULL OR relationship_phase IN
            ('FORMING', 'STABLE', 'DEEPENING', 'COOLING', 'DORMANT', 'ESTRANGED'))
        """
    )

    # ============================================================
    # Interaction Patterns
    # ============================================================

    # How we typically interact
    # Format: JSON array of modalities
    # Values: in_person, phone, text, video, email, social_media
    op.add_column(
        "st_social",
        sa.Column("interaction_modalities_json", sa.Text, nullable=True),
    )

    # What we typically do together
    # Format: JSON array of activities
    # Values: meal, work, recreation, childcare, travel, celebration, support
    op.add_column(
        "st_social",
        sa.Column("typical_activities_json", sa.Text, nullable=True),
    )

    # ============================================================
    # Emotional History & Trending
    # ============================================================

    # Recent sentiment scores for trend calculation
    # Format: JSON array of {event_id, sentiment, timestamp} objects
    # Used for emotional_valence_trend computation
    op.add_column(
        "st_social",
        sa.Column("sentiment_trajectory_json", sa.Text, nullable=True),
    )

    # Aggregated emotions from all interactions
    # Format: JSON object of emotion -> count
    # Example: {"joy": 15, "gratitude": 8, "nostalgia": 3}
    op.add_column(
        "st_social",
        sa.Column("emotions_json", sa.Text, nullable=True),
    )

    # Most frequent emotion in interactions
    # Derived from emotions_json
    op.add_column(
        "st_social",
        sa.Column("dominant_emotion", sa.Text, nullable=True),
    )

    # ============================================================
    # KG Entity Linkage
    # ============================================================

    # Link to canonical entity in st_kg_dom
    # Used for entity resolution and deduplication
    op.add_column(
        "st_social",
        sa.Column("canonical_entity_id", sa.Text, nullable=True),
    )

    # ============================================================
    # Indexes for new query patterns
    # ============================================================

    # Index for emotional role queries
    # "Who are my mentors?" "Who do I support?"
    op.create_index(
        "idx_social_emotional_role",
        "st_social",
        ["tenant_id", "emotional_role"],
    )

    # Index for relationship phase queries
    # "Which relationships are cooling?" "New friendships?"
    op.create_index(
        "idx_social_relationship_phase",
        "st_social",
        ["tenant_id", "relationship_phase"],
    )

    # Index for dominant emotion queries
    # "Who brings me joy?" "Stressful relationships?"
    op.create_index(
        "idx_social_dominant_emotion",
        "st_social",
        ["tenant_id", "dominant_emotion"],
    )


def downgrade() -> None:
    """Remove UltraBERT enrichment columns from st_social."""
    # Drop indexes first
    op.drop_index("idx_social_dominant_emotion", table_name="st_social")
    op.drop_index("idx_social_relationship_phase", table_name="st_social")
    op.drop_index("idx_social_emotional_role", table_name="st_social")

    # Drop check constraint
    op.execute("ALTER TABLE st_social DROP CONSTRAINT IF EXISTS ck_social_relationship_phase")

    # Drop columns in reverse order
    op.drop_column("st_social", "canonical_entity_id")
    op.drop_column("st_social", "dominant_emotion")
    op.drop_column("st_social", "emotions_json")
    op.drop_column("st_social", "sentiment_trajectory_json")
    op.drop_column("st_social", "typical_activities_json")
    op.drop_column("st_social", "interaction_modalities_json")
    op.drop_column("st_social", "relationship_phase")
    op.drop_column("st_social", "emotional_valence_trend")
    op.drop_column("st_social", "emotional_valence_avg")
    op.drop_column("st_social", "emotional_role")
    op.drop_column("st_social", "ultrabert_relation_types")
