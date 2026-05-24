"""Tests for temporal kernel bundle."""

from __future__ import annotations

from k1.temporal.kernel import TemporalServiceBundle, build_temporal_bundle


def test_build_temporal_bundle_defaults() -> None:
    bundle = build_temporal_bundle()
    assert isinstance(bundle, TemporalServiceBundle)
    assert bundle.health().ready is True


def test_bundle_shutdown_marks_unready() -> None:
    bundle = build_temporal_bundle()
    bundle.shutdown()
    assert bundle.health().ready is False
