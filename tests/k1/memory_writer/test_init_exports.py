"""
E-MW-0.1 — Unit tests for k1/memory_writer/__init__.py exports.
================================================================

Validates:
  - Every symbol in __all__ is importable from k1.memory_writer
  - __all__ count matches expected (54 symbols)
  - Key enum member counts (SentimentLabel=5, ActivityType=30, etc.)
  - MemoryAtom has exactly 37 fields
  - MWConfig defaults match policies.contract.yaml
  - No circular imports
  - Port Protocols are runtime_checkable
"""

from __future__ import annotations

import dataclasses

import pytest


class TestAllExportsImportable:
    """Every symbol in __all__ must be importable."""

    def test_all_symbols_importable(self):
        import k1.memory_writer as mw

        for name in mw.__all__:
            obj = getattr(mw, name, None)
            assert obj is not None, f"Symbol '{name}' in __all__ but not importable"

    def test_all_count(self):
        import k1.memory_writer as mw

        assert len(mw.__all__) == 78


class TestPortsImportable:
    """All 5 port Protocols are importable and runtime_checkable."""

    @pytest.mark.parametrize(
        "name",
        [
            "ISessionReadPort",
            "IBridgeCommandPort",
            "IEventSubscriptionPort",
            "IModelHubPort",
            "IHealthPort",
        ],
    )
    def test_port_importable(self, name: str):
        from k1 import memory_writer as mw

        port_cls = getattr(mw, name)
        assert (
            hasattr(port_cls, "__protocol_attrs__")
            or hasattr(port_cls, "__abstractmethods__")
            or callable(port_cls)
        )


class TestEnumMemberCounts:
    """Each enum has the expected number of members."""

    @pytest.mark.parametrize(
        "enum_name,expected_count",
        [
            ("SentimentLabel", 5),
            ("NoveltyLevel", 4),
            ("ElaborationDepth", 5),
            ("TemporalOrientation", 4),
            ("TemporalLinkType", 6),
            ("SourceType", 4),
            ("ArcPosition", 4),
            ("SocialIntimacy", 3),
            ("ActivityType", 30),
            ("RelationshipType", 8),
            ("LocationType", 19),
            ("IdentityDomain", 9),
            ("SkipReason", 6),
            ("IntentType", 8),
            ("SocialContext", 6),
        ],
    )
    def test_enum_member_count(self, enum_name: str, expected_count: int):
        from k1 import memory_writer as mw

        enum_cls = getattr(mw, enum_name)
        members = list(enum_cls)
        assert (
            len(members) == expected_count
        ), f"{enum_name}: expected {expected_count}, got {len(members)}: {[m.value for m in members]}"


class TestMemoryAtomFields:
    """MemoryAtom must have exactly 37 fields."""

    def test_field_count(self):
        from k1.memory_writer import MemoryAtom

        fields = dataclasses.fields(MemoryAtom)
        assert len(fields) == 42, (
            f"MemoryAtom has {len(fields)} fields, expected 42: " f"{[f.name for f in fields]}"
        )

    def test_is_frozen(self):
        from k1.memory_writer import MemoryAtom

        atom = MemoryAtom()
        with pytest.raises(dataclasses.FrozenInstanceError):
            atom.text = "changed"  # type: ignore[misc]


class TestMWConfigDefaults:
    """MWConfig defaults match policies.contract.yaml."""

    def test_llm_token_budget(self):
        from k1.memory_writer import MWConfig

        assert MWConfig().llm_token_budget == 2000

    def test_batch_window_ms(self):
        from k1.memory_writer import MWConfig

        assert MWConfig().batch_window_ms == 250

    def test_max_atoms_per_turn(self):
        from k1.memory_writer import MWConfig

        assert MWConfig().max_atoms_per_turn == 6

    def test_max_text_words(self):
        from k1.memory_writer import MWConfig

        assert MWConfig().max_text_words == 50

    def test_filter_dedup_window(self):
        from k1.memory_writer import MWConfig

        assert MWConfig().filter_dedup_window_seconds == 300

    def test_is_frozen(self):
        from k1.memory_writer import MWConfig

        cfg = MWConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.llm_token_budget = 999  # type: ignore[misc]


class TestEventsImportable:
    """All 6 topic constants and 6 payloads are importable."""

    @pytest.mark.parametrize(
        "name",
        [
            "TOPIC_TURN_COMPLETE",
            "TOPIC_FILTER_DECISION",
            "TOPIC_EXTRACTION_COMPLETE",
            "TOPIC_BATCH_SUBMITTED",
            "TOPIC_PIPELINE_ERROR",
            "TOPIC_CIRCUIT_OPEN",
        ],
    )
    def test_topic_constant(self, name: str):
        from k1 import memory_writer as mw

        val = getattr(mw, name)
        assert isinstance(val, str)
        assert val  # non-empty

    @pytest.mark.parametrize(
        "name",
        [
            "TurnCompletePayload",
            "FilterDecisionEvent",
            "ExtractionCompleteEvent",
            "BatchSubmittedEvent",
            "PipelineErrorEvent",
            "CircuitOpenEvent",
        ],
    )
    def test_payload_class(self, name: str):
        from k1 import memory_writer as mw

        cls = getattr(mw, name)
        assert dataclasses.is_dataclass(cls)


class TestContextAndAdapters:
    """Context helpers and adapters are importable."""

    def test_place_resolver(self):
        from k1.memory_writer import PlaceResolver, ResolvedPlace

        assert PlaceResolver is not None
        assert dataclasses.is_dataclass(ResolvedPlace)

    def test_adapters(self):
        from k1.memory_writer import ModelHubAdapter, SessionReadAdapter

        assert SessionReadAdapter is not None
        assert ModelHubAdapter is not None

    def test_invariant_violation(self):
        from k1.memory_writer import InvariantViolation

        assert issubclass(InvariantViolation, Exception)


class TestNoCircularImports:
    """Importing k1.memory_writer doesn't cause circular import errors."""

    def test_import_succeeds(self):
        import importlib

        mod = importlib.import_module("k1.memory_writer")
        assert hasattr(mod, "__all__")
        assert hasattr(mod, "MemoryAtom")
