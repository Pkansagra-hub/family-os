"""
tests.poc.test_m04_e43_session_bundle -- E4.3 Session Bundle Tool (Post-Migration).

The update_session_bundle tool was migrated to ``k1.concierge.section_update``
(M4 front deloading). This test file verifies the migration was clean:

  - The tool is NOT registered in TOOL_REGISTRY
  - The schema is NOT in FRONT_TOOL_SCHEMAS
  - The bundle functionality now lives in section_update.apply

Test count target: ~10 tests (verifying absence, not exercising the old tool).
"""

from __future__ import annotations

from k1.concierge.tools.implementations import TOOL_REGISTRY
from k1.concierge.tools.schemas_front import FRONT_TOOL_SCHEMAS

# =========================================================================
# Helpers
# =========================================================================


def _tool_names(schemas: list[object]) -> set[str]:
    return {str(getattr(s, "name")) for s in schemas}


# =========================================================================
# Post-migration verification
# =========================================================================


class TestBundleToolRemoved:
    """update_session_bundle is cleanly removed from Front tool surface (Tier 2)."""

    def test_not_in_tool_registry(self) -> None:
        """Tool is NOT in TOOL_REGISTRY after migration."""
        assert "update_session_bundle" not in TOOL_REGISTRY

    def test_not_in_front_tool_schemas(self) -> None:
        """Schema is NOT in FRONT_TOOL_SCHEMAS after migration."""
        names = _tool_names(FRONT_TOOL_SCHEMAS)
        assert "update_session_bundle" not in names

    def test_front_tool_count_is_five(self) -> None:
        """FRONT_TOOL_SCHEMAS has 5 schemas post-migration
        (recall_memory, summarize_context, dispatch_task,
         discover_capabilities, invoke_capability)."""
        assert len(FRONT_TOOL_SCHEMAS) == 5

    def test_active_tools_are_read_and_control_only(self) -> None:
        """Only read, control, and fabric tools remain in FRONT_TOOL_SCHEMAS."""
        names = _tool_names(FRONT_TOOL_SCHEMAS)
        assert names == {
            "recall_memory",
            "summarize_context",
            "dispatch_task",
            "discover_capabilities",
            "invoke_capability",
        }

    def test_no_cognitive_write_tools_remain(self) -> None:
        """No cognitive write tools remain in FRONT_TOOL_SCHEMAS."""
        names = _tool_names(FRONT_TOOL_SCHEMAS)
        cognitive = {
            "update_beliefs",
            "update_scoreboard",
            "update_clarifications",
            "update_narrative",
            "refine_affect",
            "promote_belief",
            "update_session_bundle",
        }
        assert not names & cognitive

    def test_cannot_import_bundle_schema(self) -> None:
        """UPDATE_SESSION_BUNDLE_SCHEMA is no longer exported."""
        with __import__("pytest").raises(ImportError):
            from k1.concierge.tools.schemas_front import UPDATE_SESSION_BUNDLE_SCHEMA  # noqa: F401

    def test_cannot_import_bundle_impl(self) -> None:
        """execute_update_session_bundle is no longer exported."""
        with __import__("pytest").raises(ImportError):
            from k1.concierge.tools.implementations import (  # noqa: F401
                execute_update_session_bundle,
            )

    def test_tool_registry_has_only_non_cognitive(self) -> None:
        """TOOL_REGISTRY contains no cognitive write tools."""
        cognitive = {
            "update_beliefs",
            "update_scoreboard",
            "update_clarifications",
            "update_narrative",
            "refine_affect",
            "promote_belief",
            "update_session_bundle",
        }
        assert not set(TOOL_REGISTRY.keys()) & cognitive

    def test_recall_memory_still_registered(self) -> None:
        """recall_memory (shared read tool) survives the migration."""
        assert "recall_memory" in TOOL_REGISTRY

    def test_dispatch_task_still_registered(self) -> None:
        """dispatch_task (control tool) survives the migration."""
        assert "dispatch_task" in TOOL_REGISTRY


# =========================================================================
# Section update migration reference
# =========================================================================


class TestSectionUpdateMigration:
    """Bundle functionality is now in k1.concierge.section_update."""

    def test_section_update_module_exists(self) -> None:
        """section_update module is importable."""
        import k1.concierge.section_update  # noqa: F401

    def test_apply_module_has_batch_function(self) -> None:
        """apply_section_update_plan is available for batch writes."""
        from k1.concierge.section_update.apply import apply_section_update_plan

        assert callable(apply_section_update_plan)

    def test_vocabulary_defines_writable_sections(self) -> None:
        """LLM_WRITABLE_SECTIONS defines sections previously handled by bundle."""
        from k1.concierge.section_update.vocabulary import LLM_WRITABLE_SECTIONS

        assert isinstance(LLM_WRITABLE_SECTIONS, (frozenset, tuple))
        assert "beliefs_active" in LLM_WRITABLE_SECTIONS

        assert isinstance(LLM_WRITABLE_SECTIONS, (frozenset, tuple))
        assert "beliefs_active" in LLM_WRITABLE_SECTIONS
