"""M1-E11 public SessionState facade no-POC temporal exports."""

from __future__ import annotations

import importlib
import importlib.util


def test_public_types_does_not_export_temporal_poc_symbols() -> None:
    public_types = importlib.import_module("k1.sessionstate.public_types")

    assert "compute_temporal_anchor" not in public_types.__all__
    assert "TemporalAnchor" not in public_types.__all__
    assert not hasattr(public_types, "compute_temporal_anchor")
    assert not hasattr(public_types, "TemporalAnchor")


def test_legacy_temporal_context_module_removed() -> None:
    assert importlib.util.find_spec("k1.sessionstate.sections.temporal_context") is None
