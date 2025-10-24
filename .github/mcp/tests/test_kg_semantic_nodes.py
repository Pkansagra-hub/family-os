"""
Tests for KG semantic node system (Issue KG-1.1).

Tests the addition of semantic typing to KG nodes, including:
- Node type support ("adr", "module", "file", "contract", etc.)
- Semantic tags for classification
- Rich metadata for node-specific information
- File path tracking
- Creation metadata

Reference: Issue KG-1.1: Add Semantic Node Type System
"""

import tempfile
import time
from pathlib import Path

import pytest
from kg_mcp_server import NODE_TYPES, KnowledgeGraphStore


@pytest.fixture
def temp_store():
    """Create a temporary KG store for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kg_test.json"
        store = KnowledgeGraphStore(db_path)
        yield store


@pytest.fixture
def sample_diagram(temp_store):
    """Create a sample diagram for testing."""
    diagram = temp_store.create_diagram(
        alias="test_semantic",
        title="Test Semantic Diagram",
        description="Diagram for semantic node testing",
    )
    return diagram


class TestSemanticNodeTypes:
    """Test semantic node type system."""

    def test_add_node_with_type(self, temp_store, sample_diagram):
        """Test adding a node with a semantic type."""
        diagram_id = sample_diagram["diagram_id"]

        node = temp_store.add_or_update_node(
            diagram_id,
            "adr_0051",
            label="Agent Scheduling ADR",
            node_type="adr",
        )

        assert node["id"] == "adr_0051"
        assert node["node_type"] == "adr"
        assert node["label"] == "Agent Scheduling ADR"

    def test_all_valid_node_types(self, temp_store, sample_diagram):
        """Test all valid node types can be created."""
        diagram_id = sample_diagram["diagram_id"]

        for node_type in NODE_TYPES.keys():
            node = temp_store.add_or_update_node(
                diagram_id,
                f"node_{node_type}",
                node_type=node_type,
            )
            assert node["node_type"] == node_type

    def test_node_type_default(self, temp_store, sample_diagram):
        """Test that node_type defaults to 'unknown'."""
        diagram_id = sample_diagram["diagram_id"]

        node = temp_store.add_or_update_node(
            diagram_id,
            "test_node",
        )

        assert node["node_type"] == "unknown"

    def test_invalid_node_type_logged(self, temp_store, sample_diagram, caplog):
        """Test that invalid node types are logged but accepted."""
        diagram_id = sample_diagram["diagram_id"]

        node = temp_store.add_or_update_node(
            diagram_id,
            "test_node",
            node_type="invalid_type",
        )

        # Node should still be created with invalid type
        assert node["node_type"] == "invalid_type"
        # Warning should be logged
        assert "Unknown node_type" in caplog.text


class TestSemanticTags:
    """Test semantic tagging system."""

    def test_add_node_with_tags(self, temp_store, sample_diagram):
        """Test adding a node with semantic tags."""
        diagram_id = sample_diagram["diagram_id"]

        node = temp_store.add_or_update_node(
            diagram_id,
            "agent_scheduler",
            node_type="module",
            semantic_tags=["scheduling", "agents", "k1_l2"],
        )

        assert set(node["semantic_tags"]) == {"scheduling", "agents", "k1_l2"}

    def test_tag_deduplication(self, temp_store, sample_diagram):
        """Test that duplicate tags are removed."""
        diagram_id = sample_diagram["diagram_id"]

        node = temp_store.add_or_update_node(
            diagram_id,
            "test_node",
            semantic_tags=["tag1", "tag2", "tag1", "tag3", "tag2"],
        )

        assert set(node["semantic_tags"]) == {"tag1", "tag2", "tag3"}
        assert len(node["semantic_tags"]) == 3

    def test_add_tags_on_update(self, temp_store, sample_diagram):
        """Test adding tags during node update."""
        diagram_id = sample_diagram["diagram_id"]

        # Create node without tags
        node1 = temp_store.add_or_update_node(
            diagram_id,
            "test_node",
        )
        assert node1["semantic_tags"] == []

        # Add tags
        node2 = temp_store.add_or_update_node(
            diagram_id,
            "test_node",
            semantic_tags=["new_tag"],
        )

        assert "new_tag" in node2["semantic_tags"]


class TestNodeMetadata:
    """Test rich metadata support."""

    def test_add_node_with_metadata(self, temp_store, sample_diagram):
        """Test adding a node with metadata."""
        diagram_id = sample_diagram["diagram_id"]

        metadata = {
            "status": "ACCEPTED",
            "version": "1.0",
            "author": "K1 Team",
        }

        node = temp_store.add_or_update_node(
            diagram_id,
            "adr_0051",
            node_type="adr",
            metadata=metadata,
        )

        assert node["metadata"]["status"] == "ACCEPTED"
        assert node["metadata"]["version"] == "1.0"
        assert node["metadata"]["author"] == "K1 Team"

    def test_metadata_merge_on_update(self, temp_store, sample_diagram):
        """Test that metadata merges during updates."""
        diagram_id = sample_diagram["diagram_id"]

        # Initial metadata
        node1 = temp_store.add_or_update_node(
            diagram_id,
            "test_node",
            metadata={"key1": "value1", "key2": "value2"},
        )

        # Update with additional metadata
        node2 = temp_store.add_or_update_node(
            diagram_id,
            "test_node",
            metadata={"key2": "updated", "key3": "new"},
        )

        assert node2["metadata"]["key1"] == "value1"
        assert node2["metadata"]["key2"] == "updated"
        assert node2["metadata"]["key3"] == "new"


class TestFilePathTracking:
    """Test file path tracking for code references."""

    def test_add_node_with_file_path(self, temp_store, sample_diagram):
        """Test adding a node with file path."""
        diagram_id = sample_diagram["diagram_id"]

        node = temp_store.add_or_update_node(
            diagram_id,
            "agent_scheduler",
            node_type="module",
            file_path="k1/l2_orchestration/agent_scheduler.py",
        )

        assert node["file_path"] == "k1/l2_orchestration/agent_scheduler.py"

    def test_add_node_with_code_snippet(self, temp_store, sample_diagram):
        """Test adding a node with source code snippet."""
        diagram_id = sample_diagram["diagram_id"]

        snippet = """class AgentScheduler:
    def schedule_agent(self, agent_id):
        # Implementation
        pass"""

        node = temp_store.add_or_update_node(
            diagram_id,
            "agent_scheduler_class",
            node_type="file",
            source_code_snippet=snippet,
        )

        assert snippet in node["source_code_snippet"]


class TestCreationMetadata:
    """Test creation metadata (created_by, created_at)."""

    def test_default_creation_metadata(self, temp_store, sample_diagram):
        """Test default creation metadata."""
        diagram_id = sample_diagram["diagram_id"]

        before_time = time.time()
        node = temp_store.add_or_update_node(
            diagram_id,
            "test_node",
        )
        after_time = time.time()

        assert node["created_by"] == "system"
        assert before_time <= node["created_at"] <= after_time

    def test_custom_created_by(self, temp_store, sample_diagram):
        """Test custom created_by value."""
        diagram_id = sample_diagram["diagram_id"]

        node = temp_store.add_or_update_node(
            diagram_id,
            "test_node",
            created_by="adr_indexer",
        )

        assert node["created_by"] == "adr_indexer"


class TestSemanticNodeQueries:
    """Test semantic node search and retrieval."""

    def test_find_nodes_by_type(self, temp_store, sample_diagram):
        """Test finding nodes by type."""
        diagram_id = sample_diagram["diagram_id"]

        # Create multiple typed nodes
        temp_store.add_or_update_node(diagram_id, "adr_001", node_type="adr")
        temp_store.add_or_update_node(diagram_id, "adr_002", node_type="adr")
        temp_store.add_or_update_node(diagram_id, "mod_001", node_type="module")

        # Search for ADRs
        results = temp_store.search("adr_", ref=diagram_id)
        adr_count = sum(
            1
            for r in results
            if r.get("node") == "adr_001" or r.get("node") == "adr_002"
        )

        assert adr_count > 0


class TestBackwardCompatibility:
    """Test backward compatibility with existing diagram system."""

    def test_mermaid_ingestion_preserves_semantic_fields(
        self, temp_store, sample_diagram
    ):
        """Test that ingesting Mermaid diagrams preserves semantic fields."""
        diagram_id = sample_diagram["diagram_id"]

        # Add a node with semantic fields
        original = temp_store.add_or_update_node(
            diagram_id,
            "original_node",
            node_type="module",
            semantic_tags=["important"],
            metadata={"custom": "data"},
        )

        # Retrieve and verify
        graph = temp_store.graph(diagram_id)
        node = next((n for n in graph["nodes"] if n["id"] == "original_node"), None)

        assert node is not None
        assert node["node_type"] == "module"
        assert "important" in node["semantic_tags"]
        assert node["metadata"]["custom"] == "data"

    def test_old_nodes_still_work(self, temp_store, sample_diagram):
        """Test that nodes without semantic fields still work."""
        diagram_id = sample_diagram["diagram_id"]

        # Add node using old-style (no semantic fields)
        node = temp_store.add_or_update_node(
            diagram_id,
            "old_style_node",
            label="Old Style",
            shape="box",
        )

        # Verify it has default semantic fields
        assert node["node_type"] == "unknown"
        assert node["semantic_tags"] == []
        assert node["metadata"] == {}
        assert node["created_by"] == "system"


class TestPerformance:
    """Test performance characteristics of semantic nodes."""

    def test_add_node_performance(self, temp_store, sample_diagram):
        """Test that adding nodes with semantic fields meets performance budget (<10ms)."""
        diagram_id = sample_diagram["diagram_id"]

        import timeit

        def add_node():
            temp_store.add_or_update_node(
                diagram_id,
                f"perf_test_{time.time()}",
                node_type="module",
                semantic_tags=["tag1", "tag2", "tag3"],
                metadata={"key": "value"},
            )

        # Time 10 iterations
        times = timeit.repeat(add_node, number=1, repeat=10)
        avg_time = (sum(times) / len(times)) * 1000  # Convert to ms

        # Should be well under 10ms per operation
        assert avg_time < 10, f"Add node took {avg_time:.2f}ms (budget: 10ms)"


class TestIntegration:
    """Integration tests for semantic node system."""

    def test_complete_semantic_node_workflow(self, temp_store):
        """Test a complete workflow of creating and querying semantic nodes."""
        # Create diagram
        diagram = temp_store.create_diagram(
            alias="k1_architecture",
            title="K1 Architecture",
        )
        diagram_id = diagram["diagram_id"]

        # Add ADR node
        adr_node = temp_store.add_or_update_node(
            diagram_id,
            "adr_0051",
            node_type="adr",
            semantic_tags=["scheduling", "agents"],
            metadata={"status": "ACCEPTED"},
        )

        # Add module node
        module_node = temp_store.add_or_update_node(
            diagram_id,
            "agent_scheduler",
            node_type="module",
            semantic_tags=["scheduling", "k1_l2"],
            file_path="k1/l2_orchestration/agent_scheduler.py",
        )

        # Add relation
        edge = temp_store.add_or_update_edge(
            diagram_id,
            "agent_scheduler",
            "adr_0051",
            kind="arrow",
            label="implements",
        )

        # Verify all created
        graph = temp_store.graph(diagram_id)
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1

        # Verify node properties
        assert adr_node["node_type"] == "adr"
        assert module_node["node_type"] == "module"
        assert edge is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
