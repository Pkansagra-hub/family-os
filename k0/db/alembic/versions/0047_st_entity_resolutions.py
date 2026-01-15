"""Add st_entity_resolutions for P03 entity resolution audit trail.

Revision ID: 0047
Revises: 0046
Create Date: 2026-01-03

P03 Pipeline - Entity Resolution Audit Trail

Issue: 4.4.4 - Implement ambiguous entity resolution with context hierarchy
Issue: 4.4.5 - Implement confidence bands + P06 gap emission

Creates st_entity_resolutions table to track entity resolution decisions:
- Records each resolution attempt (AUTO, FLAG, GAP outcomes)
- Stores confidence breakdown for debugging
- Tracks user feedback for learning loop (P21 → P03)
- Enables analysis of resolution accuracy over time

Table Purpose:
1. Audit trail for all entity resolutions
2. Training data for future ML improvements
3. Feedback loop with P21 for corrections
4. Performance monitoring and metrics

P03 Flow:
1. AmbiguousEntityResolver resolves mention with candidates
2. Resolution outcome recorded here (auto/flag/gap)
3. P21 may later provide correction (corrected_entity_id)
4. P03 feedback consumer reads corrections for learning

Dossier Reference: P03 Consolidation Dossier v2, Section 4.5.1.2
Spec Reference: M4_EXECUTION.md, Issues 4.4.4, 4.4.5
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# Revision identifiers
revision: str = "0047"
down_revision: str = "0046"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_entity_resolutions table for P03 entity resolution audit."""
    # ============================================================
    # Create st_entity_resolutions table (Issue 4.4.4, 4.4.5)
    # ============================================================

    op.create_table(
        "st_entity_resolutions",
        # Primary key
        sa.Column(
            "resolution_id",
            sa.String(36),
            primary_key=True,
            comment="Unique resolution identifier (ULID/UUID)",
        ),
        # Tenant isolation
        sa.Column(
            "tenant_id",
            sa.String(64),
            nullable=False,
            index=True,
            comment="Tenant isolation key",
        ),
        sa.Column(
            "space_id",
            sa.String(64),
            nullable=False,
            index=True,
            comment="Space isolation key",
        ),
        # Resolution details
        sa.Column(
            "mention",
            sa.String(255),
            nullable=False,
            comment="The ambiguous mention text (e.g., 'John')",
        ),
        sa.Column(
            "selected_entity_id",
            sa.String(36),
            nullable=True,
            index=True,
            comment="Resolved entity ID (NULL if GAP_EMITTED)",
        ),
        sa.Column(
            "confidence",
            sa.Float,
            nullable=False,
            comment="Final confidence score [0, 1]",
        ),
        sa.Column(
            "outcome",
            sa.String(32),
            nullable=False,
            index=True,
            comment="Resolution outcome (auto_resolved, resolved_flagged, gap_emitted)",
        ),
        # Score breakdown
        sa.Column(
            "breakdown_json",
            sa.Text,
            nullable=True,
            comment="JSON breakdown of score components",
        ),
        # Candidate info
        sa.Column(
            "candidates_count",
            sa.Integer,
            nullable=False,
            default=0,
            comment="Number of candidates considered",
        ),
        # Session context
        sa.Column(
            "session_id",
            sa.String(64),
            nullable=True,
            index=True,
            comment="Session where resolution occurred",
        ),
        sa.Column(
            "event_id",
            sa.String(36),
            nullable=True,
            index=True,
            comment="Source event ID from st_hipp_events",
        ),
        # Feedback tracking (P21 integration)
        sa.Column(
            "feedback_received",
            sa.Boolean,
            nullable=False,
            default=False,
            comment="Whether user feedback was received",
        ),
        sa.Column(
            "corrected_entity_id",
            sa.String(36),
            nullable=True,
            comment="User-corrected entity ID (if feedback received)",
        ),
        sa.Column(
            "feedback_at_ms",
            sa.BigInteger,
            nullable=True,
            comment="Timestamp of feedback receipt (epoch ms)",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.BigInteger,
            nullable=False,
            index=True,
            comment="Resolution timestamp (epoch ms)",
        ),
        sa.Column(
            "updated_at",
            sa.BigInteger,
            nullable=True,
            comment="Last update timestamp (epoch ms)",
        ),
        comment="P03 entity resolution audit trail for learning and feedback",
    )

    # ============================================================
    # Create indexes for common query patterns
    # ============================================================

    # Index for finding flagged resolutions that need review
    op.create_index(
        "ix_st_entity_resolutions_outcome_created",
        "st_entity_resolutions",
        ["outcome", "created_at"],
        postgresql_where=sa.text("outcome = 'resolved_flagged'"),
    )

    # Index for finding resolutions pending feedback
    op.create_index(
        "ix_st_entity_resolutions_feedback_pending",
        "st_entity_resolutions",
        ["tenant_id", "feedback_received", "created_at"],
        postgresql_where=sa.text("feedback_received = false"),
    )

    # Index for mention-based lookups (learning patterns)
    op.create_index(
        "ix_st_entity_resolutions_mention",
        "st_entity_resolutions",
        ["tenant_id", "mention"],
    )

    # Index for entity-based lookups (verifying resolution accuracy)
    op.create_index(
        "ix_st_entity_resolutions_entity",
        "st_entity_resolutions",
        ["tenant_id", "selected_entity_id"],
    )


def downgrade() -> None:
    """Drop st_entity_resolutions table."""
    op.drop_index(
        "ix_st_entity_resolutions_entity",
        table_name="st_entity_resolutions",
    )
    op.drop_index(
        "ix_st_entity_resolutions_mention",
        table_name="st_entity_resolutions",
    )
    op.drop_index(
        "ix_st_entity_resolutions_feedback_pending",
        table_name="st_entity_resolutions",
    )
    op.drop_index(
        "ix_st_entity_resolutions_outcome_created",
        table_name="st_entity_resolutions",
    )
    op.drop_table("st_entity_resolutions")
