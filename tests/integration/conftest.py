"""
Pytest configuration for P02 integration tests.

Exposes fixtures for test discovery.
"""

from tests.integration.fixtures.p02_fixtures import (
    SAMPLE_ENVELOPES,
    assert_embedding_job_created,
    assert_exit_events_emitted,
    assert_row_in_hipp_events,
    create_enriched_envelope,
    create_minimal_envelope,
    mock_context,
    mock_syscalls,
)

__all__ = [
    "mock_context",
    "mock_syscalls",
    "SAMPLE_ENVELOPES",
    "create_minimal_envelope",
    "create_enriched_envelope",
    "assert_row_in_hipp_events",
    "assert_exit_events_emitted",
    "assert_embedding_job_created",
]
