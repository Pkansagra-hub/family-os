"""
C1 Issue 3.4 — State adapter behavioural tests.

Covers InMemoryStateAdapter + SSMStateAdapter behaviour.
"""

from __future__ import annotations

# ===================================================================
# InMemoryStateAdapter
# ===================================================================


class TestInMemoryStateAdapterBehaviour:
    def test_get_section_missing_returns_none(self) -> None:
        from k1.concierge.adapters.test_state import InMemoryStateAdapter

        adapter = InMemoryStateAdapter()
        assert adapter.get_section("nonexistent") is None

    def test_get_section_returns_seeded(self) -> None:
        from k1.concierge.adapters.test_state import InMemoryStateAdapter

        adapter = InMemoryStateAdapter()
        adapter.seed("control", {"intent": "greet"})
        assert adapter.get_section("control") == {"intent": "greet"}

    def test_get_snapshot_all_sections(self) -> None:
        from k1.concierge.adapters.test_state import InMemoryStateAdapter

        adapter = InMemoryStateAdapter()
        adapter.seed("a", 1)
        adapter.seed("b", 2)
        snap = adapter.get_snapshot()
        assert snap == {"a": 1, "b": 2}

    def test_seed_dict_allows_attr_access(self) -> None:
        from k1.concierge.adapters.test_state import InMemoryStateAdapter

        adapter = InMemoryStateAdapter()
        adapter.seed_dict("control", {"intent": "greet", "domain": "social"})
        section = adapter.get_section("control")
        assert section.intent == "greet"
        assert section.domain == "social"

    def test_clear(self) -> None:
        from k1.concierge.adapters.test_state import InMemoryStateAdapter

        adapter = InMemoryStateAdapter()
        adapter.seed("x", 1)
        adapter.clear()
        assert adapter.get_snapshot() == {}


# ===================================================================
# SSMStateAdapter (production)
# ===================================================================


class TestSSMStateAdapterBehaviour:
    def test_delegates_get_section(self) -> None:
        from k1.concierge.adapters.ssm_state import SSMStateAdapter
        from k1.concierge.adapters.test_state import InMemoryStateAdapter

        inner = InMemoryStateAdapter()
        inner.seed("control", {"intent": "greet"})
        adapter = SSMStateAdapter(inner)
        assert adapter.get_section("control") == {"intent": "greet"}
