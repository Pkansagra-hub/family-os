"""
0083 — Add narrative columns to st_epi.

Epic 5.1 (GAP-002 Milestone 5): Cross-Episode Thread Matching.

New columns:
    - narrative_thread_id TEXT — dominant thread_id from source events (majority vote)
    - narrative_thread_ids_json TEXT — JSON array of all distinct thread_ids
    - narrative_arc_position TEXT — dominant arc position (EXPOSITION/RISING_ACTION/CLIMAX/RESOLUTION)
    - continuation_of_episode_id TEXT — previous episode_id with same thread (continuation link)

New index:
    - ix_st_epi_narrative_thread (tenant_id, narrative_thread_id) WHERE narrative_thread_id IS NOT NULL

Revision ID: 0083
Revises: 0082
"""

import sqlalchemy as sa
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "st_epi",
        sa.Column(
            "narrative_thread_id",
            sa.Text(),
            nullable=True,
            comment="Dominant narrative thread_id from source events (majority vote)",
        ),
    )
    op.add_column(
        "st_epi",
        sa.Column(
            "narrative_thread_ids_json",
            sa.Text(),
            nullable=True,
            comment="JSON array of all distinct narrative thread_ids from source events",
        ),
    )
    op.add_column(
        "st_epi",
        sa.Column(
            "narrative_arc_position",
            sa.Text(),
            nullable=True,
            comment="Dominant arc position: EXPOSITION/RISING_ACTION/CLIMAX/RESOLUTION",
        ),
    )
    op.add_column(
        "st_epi",
        sa.Column(
            "continuation_of_episode_id",
            sa.Text(),
            nullable=True,
            comment="Previous episode_id with same narrative_thread_id (continuation link)",
        ),
    )
    op.create_index(
        "ix_st_epi_narrative_thread",
        "st_epi",
        ["tenant_id", "narrative_thread_id"],
        postgresql_where=sa.text("narrative_thread_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_st_epi_narrative_thread", table_name="st_epi")
    op.drop_column("st_epi", "continuation_of_episode_id")
    op.drop_column("st_epi", "narrative_arc_position")
    op.drop_column("st_epi", "narrative_thread_ids_json")
    op.drop_column("st_epi", "narrative_thread_id")
