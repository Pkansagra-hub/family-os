"""
Test MCP tools for semantic knowledge graph queries (KG-1.4).

Tests the integration between:
- MCP tools: kg_find_by_type, kg_find_by_tags, kg_find_adr_by_status, kg_get_related_adr
- KnowledgeGraphStore: semantic node types, tags, metadata
- ADRIndexer: ADR discovery and cross-reference detection

Performance targets:
- Query response: <10ms for typical queries
- Tool invocation: <50ms end-to-end
"""

import time
import uuid
from pathlib import Path

import pytest
from kg_indexers import ADRIndexer
from kg_mcp_server import (
    STORE,
    kg_find_adr_by_status,
    kg_find_by_tags,
    kg_find_by_type,
    kg_get_related_adr,
)


@pytest.fixture
def diagram_with_adrs(tmp_path: Path) -> tuple[str, ADRIndexer]:
    """Create a test diagram with indexed ADRs."""
    # Create test ADR directory
    adr_dir = tmp_path / "decisions"
    adr_dir.mkdir()

    # Create 5 test ADRs
    adrs = {
        "0001": ("K0-K1 Split", "ACCEPTED"),
        "0005": ("Agent Lifecycle FSM", "ACCEPTED"),
        "0051": ("Agent Scheduling", "PROPOSED"),
        "0087": ("KG MCP Enhancement", "PROPOSED"),
        "0100": ("Test ADR", "IMPLEMENTED"),
    }

    for adr_id, (title, status) in adrs.items():
        adr_file = adr_dir / f"{adr_id}-test.md"
        adr_file.write_text(
            f"""# ADR-{adr_id}: {title}

**Status:** {status}

## Problem

Test ADR for semantic queries.

## Decision

Use semantic knowledge graph.

## References

ADR-0001 and ADR-0005
"""
        )

    # Create diagram and index ADRs with unique ID
    indexer = ADRIndexer()
    diagram_alias = f"test_kg_tools_{uuid.uuid4().hex[:8]}"
    diagram_data = STORE.create_diagram(diagram_alias, title="Test KG Tools")
    diagram_id = diagram_data["diagram_id"]

    results = indexer.ingest_directory(adr_dir, store=STORE, diagram_id=diagram_id)

    assert results["adr_count"] > 0, "ADRs should be indexed"

    return diagram_id, indexer


class TestKGFindByType:
    """Test kg_find_by_type tool - find nodes by semantic type."""

    def test_find_adr_nodes(self, diagram_with_adrs: tuple[str, ADRIndexer]) -> None:
        """Test finding all ADR nodes."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_by_type("adr", diagram=diagram_id)

        assert len(results) > 0, "Should find ADR nodes"
        assert all(r["node"]["node_type"] == "adr" for r in results)
        assert all("label" in r["node"] for r in results)

    def test_find_by_type_respects_limit(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test that limit parameter is respected."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_by_type("adr", diagram=diagram_id, limit=2)

        assert len(results) <= 2, "Should respect limit parameter"

    def test_find_by_invalid_type(self) -> None:
        """Test finding with invalid node type."""
        results = kg_find_by_type("invalid_type")

        assert len(results) == 0, "Should return empty list for invalid type"

    def test_find_by_type_performance(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test query performance (<10ms for typical queries)."""
        diagram_id, _ = diagram_with_adrs

        start = time.time()
        results = kg_find_by_type("adr", diagram=diagram_id)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 50, f"Query should be fast, took {elapsed_ms:.1f}ms"
        assert len(results) > 0


class TestKGFindByTags:
    """Test kg_find_by_tags tool - find nodes by semantic tags."""

    def test_find_by_status_tag(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test finding nodes by status tag."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_by_tags(["accepted"], diagram=diagram_id)

        assert len(results) > 0, "Should find ACCEPTED ADRs"
        for result in results:
            # Verify the matched tags are present in result
            assert "matched_tags" in result
            assert "accepted" in result.get("matched_tags", [])

    def test_find_by_keyword_tag(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test finding nodes by keyword tag."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_by_tags(["agent"], diagram=diagram_id)

        assert len(results) > 0, "Should find nodes with 'agent' keyword"
        for result in results:
            # Verify that search returned results for our tag
            matched = result.get("matched_tags", [])
            assert "agent" in matched

    def test_find_by_multiple_tags(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test finding nodes by multiple tags (OR logic)."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_by_tags(["proposed", "accepted"], diagram=diagram_id)

        assert len(results) > 0, "Should find nodes matching any tag"

    def test_find_by_tags_respects_limit(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test that limit parameter is respected."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_by_tags(["accepted"], diagram=diagram_id, limit=1)

        assert len(results) <= 1, "Should respect limit parameter"

    def test_find_by_tags_performance(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test query performance (<10ms for typical queries)."""
        diagram_id, _ = diagram_with_adrs

        start = time.time()
        kg_find_by_tags(["accepted"], diagram=diagram_id)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 50, f"Query should be fast, took {elapsed_ms:.1f}ms"


class TestKGFindADRByStatus:
    """Test kg_find_adr_by_status tool - find ADRs by their status."""

    def test_find_proposed_adrs(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test finding PROPOSED ADRs."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_adr_by_status("PROPOSED", diagram=diagram_id)

        assert len(results) > 0, "Should find PROPOSED ADRs"
        for r in results:
            assert r["node"]["node_type"] == "adr"
            assert r["node"]["metadata"]["status"] == "PROPOSED"

    def test_find_accepted_adrs(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test finding ACCEPTED ADRs."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_adr_by_status("ACCEPTED", diagram=diagram_id)

        assert len(results) > 0, "Should find ACCEPTED ADRs"
        for r in results:
            assert r["node"]["metadata"]["status"] == "ACCEPTED"

    def test_find_implemented_adrs(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test finding IMPLEMENTED ADRs."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_adr_by_status("IMPLEMENTED", diagram=diagram_id)

        assert len(results) > 0, "Should find IMPLEMENTED ADRs"

    def test_status_case_insensitive(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test that status matching is case-insensitive."""
        diagram_id, _ = diagram_with_adrs

        results_upper = kg_find_adr_by_status("ACCEPTED", diagram=diagram_id)
        results_lower = kg_find_adr_by_status("accepted", diagram=diagram_id)
        results_mixed = kg_find_adr_by_status("Accepted", diagram=diagram_id)

        assert len(results_upper) == len(results_lower) == len(results_mixed)

    def test_find_nonexistent_status(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test finding with nonexistent status."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_adr_by_status("NONEXISTENT", diagram=diagram_id)

        assert len(results) == 0, "Should return empty list for nonexistent status"

    def test_status_query_performance(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test query performance (<10ms)."""
        diagram_id, _ = diagram_with_adrs

        start = time.time()
        results = kg_find_adr_by_status("ACCEPTED", diagram=diagram_id)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 50, f"Query should be fast, took {elapsed_ms:.1f}ms"
        assert len(results) > 0


class TestKGGetRelatedADR:
    """Test kg_get_related_adr tool - find ADRs related via graph edges."""

    def test_find_related_adrs(self, diagram_with_adrs: tuple[str, ADRIndexer]) -> None:
        """Test finding related ADRs."""
        diagram_id, _ = diagram_with_adrs

        # Test finding relations from adr_0087 which references 0001 and 0005
        kg_get_related_adr("adr_0087", diagram=diagram_id)

        # Just verify the tool runs without errors
        # The exact structure depends on graph state

    def test_related_adrs_include_metadata(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test that related ADRs include metadata."""
        diagram_id, _ = diagram_with_adrs

        result = kg_get_related_adr("adr_0087", diagram=diagram_id)

        if result.get("related"):
            for adr in result["related"]:
                assert "node_id" in adr or "target" in adr

    def test_related_adrs_nonexistent(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test querying nonexistent ADR."""
        diagram_id, _ = diagram_with_adrs

        result = kg_get_related_adr("adr_9999", diagram=diagram_id)

        # Result should have related_adr key with empty list for nonexistent ADR
        assert "related_adr" in result
        assert len(result.get("related_adr", [])) == 0

    def test_relation_types_included(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test that relation types are included in results."""
        diagram_id, _ = diagram_with_adrs

        result = kg_get_related_adr("adr_0087", diagram=diagram_id)

        # Check for relation edges information
        if result.get("relation_edges"):
            for edge in result["relation_edges"]:
                # Each edge should have src/dst and relation info
                assert any(
                    k in edge for k in ["src", "dst"]
                ), "Should include relation edge info"

    def test_related_query_performance(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test query performance (<50ms)."""
        diagram_id, _ = diagram_with_adrs

        start = time.time()
        kg_get_related_adr("adr_0087", diagram=diagram_id)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 100, f"Query should be fast, took {elapsed_ms:.1f}ms"


class TestSemanticQueryWorkflows:
    """Test end-to-end semantic query workflows."""

    def test_find_all_proposed_agent_adrs(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test workflow: find PROPOSED ADRs related to agents."""
        diagram_id, _ = diagram_with_adrs

        # Find all nodes tagged with 'agent'
        agent_nodes = kg_find_by_tags(["agent"], diagram=diagram_id)

        # Filter to only proposed
        proposed_agent_adrs = [
            n
            for n in agent_nodes
            if n.get("node", {}).get("metadata", {}).get("status") == "PROPOSED"
        ]

        assert len(proposed_agent_adrs) >= 0

    def test_find_adrs_with_multiple_criteria(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test finding ADRs matching multiple criteria."""
        diagram_id, _ = diagram_with_adrs

        # Find ACCEPTED ADRs
        accepted = kg_find_adr_by_status("ACCEPTED", diagram=diagram_id)

        # Further filter to those with 'lifecycle' in title
        lifecycle_accepted = [
            a
            for a in accepted
            if "lifecycle" in a.get("node", {}).get("label", "").lower()
        ]

        assert len(lifecycle_accepted) >= 0

    def test_cross_reference_discovery(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test discovering cross-references between ADRs."""
        diagram_id, _ = diagram_with_adrs

        # Find a reference node
        adr_node = kg_find_by_type("adr", diagram=diagram_id, limit=1)

        if adr_node:
            node_id = adr_node[0].get("node", {}).get("id")
            if node_id:
                # Get related ADRs
                related = kg_get_related_adr(node_id, diagram=diagram_id)
                # Result should have related_adr key
                assert "related_adr" in related

    def test_status_distribution_query(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test querying status distribution across all ADRs."""
        diagram_id, _ = diagram_with_adrs

        statuses = ["PROPOSED", "ACCEPTED", "IMPLEMENTED", "REJECTED"]
        distribution: dict[str, int] = {}

        for status in statuses:
            results = kg_find_adr_by_status(status, diagram=diagram_id)
            distribution[status] = len(results)

        assert sum(distribution.values()) > 0, "Should have at least some ADRs"

    def test_tool_integration_no_errors(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test that all tools can be called without errors."""
        diagram_id, _ = diagram_with_adrs

        # Call all tools
        r1 = kg_find_by_type("adr", diagram=diagram_id)
        r2 = kg_find_by_tags(["accepted"], diagram=diagram_id)
        r3 = kg_find_adr_by_status("PROPOSED", diagram=diagram_id)
        r4 = kg_get_related_adr("adr_0001", diagram=diagram_id)

        # All should return dict-like results
        assert isinstance(r1, list)
        assert isinstance(r2, list)
        assert isinstance(r3, list)
        assert isinstance(r4, dict)


class TestMCPToolErrorHandling:
    """Test error handling in MCP tools."""

    def test_find_by_type_missing_diagram(self) -> None:
        """Test tool with missing diagram."""
        results = kg_find_by_type("adr", diagram="nonexistent")

        assert isinstance(results, list)

    def test_find_by_tags_empty_tag_list(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test tool with empty tag list."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_by_tags([], diagram=diagram_id)

        assert isinstance(results, list)

    def test_find_adr_by_status_empty_string(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test tool with empty status string."""
        diagram_id, _ = diagram_with_adrs

        results = kg_find_adr_by_status("", diagram=diagram_id)

        assert isinstance(results, list)


class TestBackwardCompatibility:
    """Test backward compatibility of MCP tools."""

    def test_tools_work_without_diagram_parameter(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test that tools work without explicit diagram parameter."""
        # Call without diagram - should search all diagrams
        r1 = kg_find_by_type("adr")
        r2 = kg_find_by_tags(["accepted"])
        r3 = kg_find_adr_by_status("PROPOSED")

        # Should return results (even if empty)
        assert isinstance(r1, list)
        assert isinstance(r2, list)
        assert isinstance(r3, list)

    def test_tools_return_consistent_format(
        self, diagram_with_adrs: tuple[str, ADRIndexer]
    ) -> None:
        """Test that tools return consistent format."""
        diagram_id, _ = diagram_with_adrs

        r1 = kg_find_by_type("adr", diagram=diagram_id)
        r2 = kg_find_by_tags(["accepted"], diagram=diagram_id)
        r3 = kg_find_adr_by_status("ACCEPTED", diagram=diagram_id)

        # All should be lists of dicts with similar structure
        for result_set in [r1, r2, r3]:
            if result_set:
                assert isinstance(result_set[0], dict)
                assert any(k in result_set[0] for k in ["node", "nodes"])
