"""Create st_feedback_quarantine table (Issue 6.2.10).

Revision ID: 0072
Revises: 0071
Create Date: 2026-01-04

Dossier Reference: Section 6.21 st_feedback_quarantine

Copied from k0/db/migrations/versions/0050_st_feedback_quarantine.py
Renumbered to fit alembic chain (0071 -> 0072 -> 0073).
"""

from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create st_feedback_quarantine table with indexes and RLS."""
    # Drop pre-existing table from old migration 0050 (different schema)
    op.execute("DROP TABLE IF EXISTS st_feedback_quarantine CASCADE")

    # Create table
    op.execute(
        """
        CREATE TABLE st_feedback_quarantine (
            -- Identity
            quarantine_id TEXT PRIMARY KEY,
            signal_id TEXT NOT NULL,

            -- Context
            space_id TEXT NOT NULL,

            -- Detection details
            reason TEXT NOT NULL CHECK (reason IN (
                'RATE_LIMIT', 'VELOCITY_SPIKE', 'ANOMALY', 'ENTROPY'
            )),
            severity TEXT NOT NULL CHECK (severity IN (
                'LOW', 'MEDIUM', 'HIGH'
            )),
            detected_at BIGINT NOT NULL,

            -- Review process
            reviewed_at BIGINT,
            reviewed_by TEXT,
            decision TEXT CHECK (decision IN (
                'RELEASE', 'DISCARD'
            ) OR decision IS NULL),

            -- Auto-release
            auto_release_at BIGINT NOT NULL
        )
    """
    )

    # Indexes for efficient quarantine management

    # Index for pending quarantines by space
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quarantine_space_status
        ON st_feedback_quarantine(space_id, decision)
        WHERE decision IS NULL
    """
    )

    # Index for auto-release scheduling
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quarantine_auto_release
        ON st_feedback_quarantine(auto_release_at)
        WHERE decision IS NULL
    """
    )

    # Index for signal lookup
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quarantine_signal
        ON st_feedback_quarantine(signal_id)
    """
    )

    # Index for severity-based triage
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quarantine_severity
        ON st_feedback_quarantine(severity, detected_at DESC)
        WHERE decision IS NULL
    """
    )

    # RLS policy for multi-tenant isolation
    op.execute(
        """
        ALTER TABLE st_feedback_quarantine ENABLE ROW LEVEL SECURITY
    """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'st_feedback_quarantine'
                AND policyname = 'quarantine_isolation'
            ) THEN
                CREATE POLICY quarantine_isolation
                ON st_feedback_quarantine
                FOR ALL
                USING (space_id = current_setting('app.current_space_id', true)::TEXT);
            END IF;
        END $$
    """
    )

    # Grant permissions (only if roles exist)
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'p03_role') THEN
                GRANT SELECT, INSERT, UPDATE ON st_feedback_quarantine TO p03_role;
            END IF;
        END $$
    """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'security_role') THEN
                GRANT SELECT ON st_feedback_quarantine TO security_role;
            END IF;
        END $$
    """
    )


def downgrade() -> None:
    """Drop st_feedback_quarantine table."""
    op.execute("DROP TABLE IF EXISTS st_feedback_quarantine CASCADE")
