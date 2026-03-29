"""
0084 — Add narrative_thread_completed to st_epi.

Epic 5.2 (GAP-002 Milestone 5): Goal Completion Detection.

New column:
    - narrative_thread_completed BOOLEAN DEFAULT FALSE — True if this episode
      completes a narrative goal arc (CLIMAX/RESOLUTION after buildup).

Revision ID: 0084
Revises: 0083
"""

import sqlalchemy as sa
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "st_epi",
        sa.Column(
            "narrative_thread_completed",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True if this episode completes a narrative goal arc (CLIMAX/RESOLUTION after buildup)",
        ),
    )


def downgrade() -> None:
    op.drop_column("st_epi", "narrative_thread_completed")
