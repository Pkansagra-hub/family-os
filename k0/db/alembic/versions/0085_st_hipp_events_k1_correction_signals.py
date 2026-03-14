"""
0085 -- Add K1 correction signal columns to st_hipp_events.

R2 Epic 7.2: K1 EVOLVE/CONTRADICT Signal Delegation.

K1 LLM detects corrections and contradictions in conversation and flags
them on the Memory Writer atom. These 5 columns carry that signal through
P02 into st_hipp_events so P03 R3 reconciliation can route EVOLVE/CONTRADICT
without attempting cosine-based detection (which fails at similarity floor ~0.92).

New columns:
    - correction_signal     BOOLEAN DEFAULT FALSE
    - contradiction_signal  BOOLEAN DEFAULT FALSE
    - supersedes_concept    TEXT NULL
    - correction_source     TEXT NULL  (user_explicit, user_implicit, context_change)
    - session_context_id    TEXT NULL

Revision ID: 0085
Revises: 0084
"""

import sqlalchemy as sa
from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "st_hipp_events",
        sa.Column(
            "correction_signal",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="K1 LLM detected this atom corrects a previously stored fact (EVOLVE candidate)",
        ),
    )
    op.add_column(
        "st_hipp_events",
        sa.Column(
            "contradiction_signal",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="K1 LLM detected this atom contradicts stored knowledge (CONTRADICT candidate)",
        ),
    )
    op.add_column(
        "st_hipp_events",
        sa.Column(
            "supersedes_concept",
            sa.Text(),
            nullable=True,
            comment="Namespaced concept key being replaced (e.g. cuisine_preference:thai)",
        ),
    )
    op.add_column(
        "st_hipp_events",
        sa.Column(
            "correction_source",
            sa.Text(),
            nullable=True,
            comment="How correction detected: user_explicit, user_implicit, context_change",
        ),
    )
    op.add_column(
        "st_hipp_events",
        sa.Column(
            "session_context_id",
            sa.Text(),
            nullable=True,
            comment="Session UUID where correction was detected (audit trail for P03)",
        ),
    )

    # CHECK constraint for correction_source enum
    op.create_check_constraint(
        "ck_hipp_correction_source",
        "st_hipp_events",
        "correction_source IS NULL OR correction_source IN ('user_explicit', 'user_implicit', 'context_change')",
    )

    # Partial index: find correction-flagged events for P03 R3
    op.create_index(
        "idx_hipp_events_correction_signal",
        "st_hipp_events",
        ["event_time_utc"],
        postgresql_where=sa.text("correction_signal = true"),
    )

    # Partial index: find contradiction-flagged events for P03 R3
    op.create_index(
        "idx_hipp_events_contradiction_signal",
        "st_hipp_events",
        ["event_time_utc"],
        postgresql_where=sa.text("contradiction_signal = true"),
    )


def downgrade() -> None:
    op.drop_index("idx_hipp_events_contradiction_signal", table_name="st_hipp_events")
    op.drop_index("idx_hipp_events_correction_signal", table_name="st_hipp_events")
    op.drop_constraint("ck_hipp_correction_source", "st_hipp_events", type_="check")
    op.drop_column("st_hipp_events", "session_context_id")
    op.drop_column("st_hipp_events", "correction_source")
    op.drop_column("st_hipp_events", "supersedes_concept")
    op.drop_column("st_hipp_events", "contradiction_signal")
    op.drop_column("st_hipp_events", "correction_signal")
