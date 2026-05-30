"""Tests for DST-safe window building."""

from __future__ import annotations

from datetime import datetime

from k1.temporal.service.window_builder import build_standard_windows
from tests.k1.temporal.helpers import sample_anchor


def test_today_window_handles_spring_dst_boundary() -> None:
    windows = build_standard_windows(sample_anchor())
    today = windows["today"]
    start = datetime.fromisoformat(today.start_utc)
    end = datetime.fromisoformat(today.end_utc)
    assert int((end - start).total_seconds() / 3600) == 23
    assert today.timezone == "America/Los_Angeles"
