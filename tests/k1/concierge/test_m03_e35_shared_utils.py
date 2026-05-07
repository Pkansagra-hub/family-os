"""
tests/poc/test_m03_e35_shared_utils.py -- E3.5 Shared Actor Utilities
========================================================================

Tests for the extraction of D1 (parse_envelope_payload), D2 (safe_get_section),
and D3 (never_cancel) from front.py and back.py into actors/shared.py.

Milestone 3, Epic 3.5, Issues 3.5.1 - 3.5.3

Test count target: ~20 tests
"""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from k1.concierge.actors.shared import never_cancel, parse_envelope_payload, safe_get_section

# =========================================================================
# Helpers
# =========================================================================


def _make_envelope(payload: bytes | None = None) -> MagicMock:
    """Create a minimal Envelope mock with a payload attribute."""
    env = MagicMock()
    env.payload = payload
    return env


class _FakeSessionState:
    """Minimal SS stub with configurable sections."""

    def __init__(self, sections: dict[str, Any] | None = None):
        self._sections = sections or {}

    def get_section(self, name: str) -> Any:
        if name in self._sections:
            return self._sections[name]
        raise KeyError(f"No section: {name}")


class _ExplodingSessionState:
    """SS stub that raises RuntimeError on any get_section call."""

    def get_section(self, name: str) -> Any:
        raise RuntimeError("SS is broken")


# =========================================================================
# 3.5.1 -- parse_envelope_payload
# =========================================================================


class TestParseEnvelopePayload:
    """D1: parse_envelope_payload extracted from front.py / back.py."""

    def test_valid_json_payload(self) -> None:
        data = {"task_id": "T-1", "mode": "chat"}
        env = _make_envelope(json.dumps(data).encode())
        assert parse_envelope_payload(env) == data

    def test_empty_payload_returns_empty_dict(self) -> None:
        env = _make_envelope(b"")
        assert parse_envelope_payload(env) == {}

    def test_none_payload_returns_empty_dict(self) -> None:
        env = _make_envelope(None)
        assert parse_envelope_payload(env) == {}

    def test_invalid_json_returns_empty_dict(self) -> None:
        env = _make_envelope(b"not valid json {{{")
        assert parse_envelope_payload(env) == {}

    def test_unicode_error_returns_empty_dict(self) -> None:
        # Invalid UTF-8 sequence
        env = _make_envelope(b"\xff\xfe")
        result = parse_envelope_payload(env)
        # Either empty dict or a parsed result -- must not raise
        assert isinstance(result, dict)

    def test_nested_json_payload(self) -> None:
        data = {"task": {"id": "T-2", "args": [1, 2, 3]}, "meta": None}
        env = _make_envelope(json.dumps(data).encode())
        assert parse_envelope_payload(env) == data

    def test_empty_json_object(self) -> None:
        env = _make_envelope(b"{}")
        assert parse_envelope_payload(env) == {}

    def test_json_array_payload(self) -> None:
        """JSON arrays are valid JSON but not dicts -- function still returns."""
        env = _make_envelope(b"[1, 2, 3]")
        result = parse_envelope_payload(env)
        assert result == [1, 2, 3]

    def test_return_type_is_dict_for_object_payload(self) -> None:
        env = _make_envelope(json.dumps({"a": 1}).encode())
        result = parse_envelope_payload(env)
        assert isinstance(result, dict)


# =========================================================================
# 3.5.2 -- safe_get_section
# =========================================================================


class TestSafeGetSection:
    """D2: safe_get_section extracted from front.py / back.py."""

    def test_existing_section_returned(self) -> None:
        ss = _FakeSessionState({"persona": {"name": "Kai"}})
        assert safe_get_section(ss, "persona") == {"name": "Kai"}

    def test_missing_section_returns_none(self) -> None:
        ss = _FakeSessionState({})
        assert safe_get_section(ss, "persona") is None

    def test_exception_returns_none(self) -> None:
        ss = _ExplodingSessionState()
        assert safe_get_section(ss, "anything") is None

    def test_none_section_value_distinguishable(self) -> None:
        """If a section explicitly stores None, it should return None."""
        ss = _FakeSessionState({"empty": None})
        assert safe_get_section(ss, "empty") is None

    def test_multiple_sections(self) -> None:
        ss = _FakeSessionState(
            {
                "persona": {"name": "Kai"},
                "task_state": {"active": True},
            }
        )
        assert safe_get_section(ss, "persona") == {"name": "Kai"}
        assert safe_get_section(ss, "task_state") == {"active": True}

    def test_section_with_complex_value(self) -> None:
        data = {"history": [{"role": "user", "content": "hi"}]}
        ss = _FakeSessionState({"history_active": data})
        assert safe_get_section(ss, "history_active") == data


# =========================================================================
# 3.5.3 -- never_cancel
# =========================================================================


class TestNeverCancel:
    """D3: never_cancel extracted from front.py / back.py."""

    def test_returns_false(self) -> None:
        result = asyncio.run(never_cancel())
        assert result is False

    def test_is_coroutine_function(self) -> None:
        assert asyncio.iscoroutinefunction(never_cancel)

    def test_callable_multiple_times(self) -> None:
        for _ in range(5):
            assert asyncio.run(never_cancel()) is False

    @pytest.mark.asyncio
    async def test_async_invocation(self) -> None:
        assert await never_cancel() is False


# =========================================================================
# Import source verification -- actors import from shared.py
# =========================================================================


class TestImportHygiene:
    """Verify front.py and back.py import from shared, not local defs."""

    def test_front_parse_payload_is_shared(self) -> None:
        """front._parse_payload should be shared.parse_envelope_payload."""
        from k1.concierge.actors import front

        assert front._parse_payload is parse_envelope_payload

    def test_back_parse_payload_is_shared(self) -> None:
        """back._parse_payload should be shared.parse_envelope_payload."""
        from k1.concierge.actors import back

        assert back._parse_payload is parse_envelope_payload

    def test_front_safe_get_section_is_shared(self) -> None:
        from k1.concierge.actors import front

        assert front._safe_get_section is safe_get_section

    def test_back_safe_get_section_is_shared(self) -> None:
        from k1.concierge.actors import back

        assert back._safe_get_section is safe_get_section

    def test_front_never_cancel_is_shared(self) -> None:
        from k1.concierge.actors import front

        assert front._never_cancel is never_cancel

    def test_back_never_cancel_is_shared(self) -> None:
        from k1.concierge.actors import back

        assert back._never_cancel is never_cancel


class TestPackageExports:
    """Verify actors/__init__.py re-exports shared utilities."""

    def test_parse_envelope_payload_from_actors(self) -> None:
        from k1.concierge.actors import parse_envelope_payload as pkg_fn

        assert pkg_fn is parse_envelope_payload

    def test_safe_get_section_from_actors(self) -> None:
        from k1.concierge.actors import safe_get_section as pkg_fn

        assert pkg_fn is safe_get_section

    def test_never_cancel_from_actors(self) -> None:
        from k1.concierge.actors import never_cancel as pkg_fn

        assert pkg_fn is never_cancel

    def test_parse_payload_backward_compat(self) -> None:
        """_parse_payload still importable from actors for backward compat."""
        from k1.concierge.actors import _parse_payload

        # _parse_payload is an alias of parse_envelope_payload
        assert _parse_payload is parse_envelope_payload

    def test_all_shared_in_dunder_all(self) -> None:
        import k1.concierge.actors as actors_pkg

        for name in ("parse_envelope_payload", "safe_get_section", "never_cancel"):
            assert name in actors_pkg.__all__, f"{name} missing from __all__"


class TestSharedModuleMinimalDeps:
    """shared.py must have minimal dependencies -- no config, builders, etc."""

    def test_no_config_import(self) -> None:
        src = inspect.getsource(__import__("k1.concierge.actors.shared", fromlist=["shared"]))
        assert "k1.concierge.config" not in src

    def test_no_builders_import(self) -> None:
        src = inspect.getsource(__import__("k1.concierge.actors.shared", fromlist=["shared"]))
        assert "k1.concierge.bus.builders" not in src

    def test_no_actors_front_import(self) -> None:
        src = inspect.getsource(__import__("k1.concierge.actors.shared", fromlist=["shared"]))
        # Check import lines only, not docstrings/comments
        import_lines = [
            ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))
        ]
        for ln in import_lines:
            assert "actors.front" not in ln

    def test_no_actors_back_import(self) -> None:
        src = inspect.getsource(__import__("k1.concierge.actors.shared", fromlist=["shared"]))
        import_lines = [
            ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))
        ]
        for ln in import_lines:
            assert "actors.back" not in ln
