"""
Comprehensive test suite for KG-1.2: Semantic Relation Types

Tests for:
- Relation type system (implements, depends_on, tests, documents, etc.)
- Strength confidence levels (0.0-1.0)
- Evidence field for traceability
- Edge schema extensions
- Merge logic for relation metadata
- Query tools for finding edges by relation type/strength
- Backward compatibility with unlabeled edges
- Performance targets (<10ms per operation)
- Integration with existing node system

Performance Targets:
- Edge creation: <5ms
- Edge updates: <5ms
- Relation queries: <10ms
- Strength filtering: <10ms
- Stats generation: <10ms

Test Coverage: 90%+ of semantic relation functionality
"""

import time
from pathlib import Path

import pytest
from kg_mcp_server import SEMANTIC_RELATIONS, KnowledgeGraphStore


class TestSemanticRelationTypes:
    """Test semantic relation type system and validation."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        """Create isolated KnowledgeGraphStore for testing."""
        return KnowledgeGraphStore(tmp_path / "test.kg")

    @pytest.fixture
    def sample_diagram(self, store: KnowledgeGraphStore) -> str:
        """Create sample diagram with nodes for relation testing."""
        record = store.create_diagram("test_relations", "Relation Test")
        diagram_id = record["diagram_id"]

        # Add sample nodes
        store.add_or_update_node(
            diagram_id, "adr_0051", label="Agent Scheduling", node_type="adr"
        )
        store.add_or_update_node(
            diagram_id,
            "module_scheduler",
            label="Agent Scheduler Module",
            node_type="module",
        )
        store.add_or_update_node(
            diagram_id, "test_scheduler", label="Scheduler Tests", node_type="file"
        )
        store.add_or_update_node(
            diagram_id,
            "contract_sched",
            label="Scheduler Contract",
            node_type="contract",
        )

        return diagram_id

    def test_relation_type_validation(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test that only valid relation types are accepted."""
        # Valid relation types should work
        for rel_type in SEMANTIC_RELATIONS.keys():
            edge = store.add_or_update_edge(
                sample_diagram, "adr_0051", "module_scheduler", relation_type=rel_type
            )
            assert edge.get("relation_type") == rel_type

        # Invalid relation type should raise ValueError
        with pytest.raises(ValueError, match="invalid_relation_type"):
            store.add_or_update_edge(
                sample_diagram,
                "adr_0051",
                "module_scheduler",
                relation_type="invalid_type",
            )

    def test_relation_types_coverage(self) -> None:
        """Test that all expected relation types are defined."""
        expected_types = [
            "implements",
            "depends_on",
            "tests",
            "documents",
            "requires",
            "violates",
            "contradicts",
            "mitigates",
            "relates_to",
            "extends",
            "references",
        ]
        for expected in expected_types:
            assert expected in SEMANTIC_RELATIONS, f"Missing relation type: {expected}"

        assert len(SEMANTIC_RELATIONS) >= 10, "Should have at least 10 relation types"

    def test_create_edge_with_relation_type(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test creating edges with semantic relation types."""
        edge = store.add_or_update_edge(
            sample_diagram, "adr_0051", "module_scheduler", relation_type="implements"
        )

        assert edge["src"] == "adr_0051"
        assert edge["dst"] == "module_scheduler"
        assert edge["relation_type"] == "implements"
        assert edge["origin"] == "manual"

    def test_edge_without_relation_type_still_works(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test backward compatibility: edges without relation_type should still work."""
        edge = store.add_or_update_edge(sample_diagram, "adr_0051", "module_scheduler")

        assert edge["src"] == "adr_0051"
        assert edge["dst"] == "module_scheduler"
        assert (
            "relation_type" not in edge
        )  # Should not have relation_type if not provided


class TestRelationStrength:
    """Test relation strength confidence levels (0.0-1.0)."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test.kg")

    @pytest.fixture
    def sample_diagram(self, store: KnowledgeGraphStore) -> str:
        record = store.create_diagram("test_strength")
        diagram_id = record["diagram_id"]
        store.add_or_update_node(diagram_id, "node_a")
        store.add_or_update_node(diagram_id, "node_b")
        store.add_or_update_node(diagram_id, "node_c")
        return diagram_id

    def test_strength_validation_range(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test that strength must be between 0.0 and 1.0."""
        # Valid strengths
        for strength in [0.0, 0.5, 0.95, 1.0]:
            edge = store.add_or_update_edge(
                sample_diagram,
                "node_a",
                "node_b",
                relation_type="depends_on",
                strength=strength,
            )
            assert edge["strength"] == strength

        # Invalid strengths
        with pytest.raises(ValueError, match="strength_out_of_range"):
            store.add_or_update_edge(sample_diagram, "node_a", "node_b", strength=-0.1)

        with pytest.raises(ValueError, match="strength_out_of_range"):
            store.add_or_update_edge(sample_diagram, "node_a", "node_b", strength=1.1)

    def test_strength_optional(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test that strength is optional."""
        edge = store.add_or_update_edge(
            sample_diagram, "node_a", "node_b", relation_type="depends_on"
        )
        assert "strength" not in edge

    def test_strength_with_relation_type(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test strength in combination with relation type."""
        edge = store.add_or_update_edge(
            sample_diagram,
            "node_a",
            "node_b",
            relation_type="implements",
            strength=0.95,
        )
        assert edge["relation_type"] == "implements"
        assert edge["strength"] == 0.95


class TestRelationEvidence:
    """Test evidence field for traceability."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test.kg")

    @pytest.fixture
    def sample_diagram(self, store: KnowledgeGraphStore) -> str:
        record = store.create_diagram("test_evidence")
        diagram_id = record["diagram_id"]
        store.add_or_update_node(diagram_id, "adr_0051", node_type="adr")
        store.add_or_update_node(diagram_id, "module_x", node_type="module")
        return diagram_id

    def test_evidence_field_optional(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test that evidence field is optional."""
        edge = store.add_or_update_edge(
            sample_diagram, "adr_0051", "module_x", relation_type="implements"
        )
        assert "evidence" not in edge

    def test_evidence_string(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test evidence as a string field."""
        evidence_text = "k1/l2_orchestration/agent_scheduler.py:42"
        edge = store.add_or_update_edge(
            sample_diagram,
            "adr_0051",
            "module_x",
            relation_type="implements",
            evidence=evidence_text,
        )
        assert edge["evidence"] == evidence_text

    def test_evidence_with_strength(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test evidence combined with strength."""
        edge = store.add_or_update_edge(
            sample_diagram,
            "adr_0051",
            "module_x",
            relation_type="implements",
            strength=0.9,
            evidence="Found in code review",
        )
        assert edge["relation_type"] == "implements"
        assert edge["strength"] == 0.9
        assert edge["evidence"] == "Found in code review"


class TestEdgeSchema:
    """Test edge schema with semantic extensions."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test.kg")

    @pytest.fixture
    def sample_diagram(self, store: KnowledgeGraphStore) -> str:
        record = store.create_diagram("test_schema")
        diagram_id = record["diagram_id"]
        store.add_or_update_node(diagram_id, "n1")
        store.add_or_update_node(diagram_id, "n2")
        return diagram_id

    def test_edge_has_all_fields(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test that edges include all expected fields."""
        edge = store.add_or_update_edge(
            sample_diagram,
            "n1",
            "n2",
            kind="arrow",
            label="test",
            props={"custom": "value"},
            relation_type="depends_on",
            strength=0.8,
            evidence="test evidence",
        )

        # Check standard fields
        assert edge["src"] == "n1"
        assert edge["dst"] == "n2"
        assert edge["kind"] == "arrow"
        assert edge["label"] == "test"
        assert edge["props"]["custom"] == "value"
        assert edge["origin"] == "manual"

        # Check semantic fields
        assert edge["relation_type"] == "depends_on"
        assert edge["strength"] == 0.8
        assert edge["evidence"] == "test evidence"

    def test_edge_retrieval_preserves_semantic_fields(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test that semantic fields are preserved when retrieving edges."""
        store.add_or_update_edge(
            sample_diagram,
            "n1",
            "n2",
            relation_type="implements",
            strength=0.95,
            evidence="code analysis",
        )

        graph = store.graph(sample_diagram)
        edges = graph["edges"]
        assert len(edges) > 0

        edge = edges[0]
        assert edge["relation_type"] == "implements"
        assert edge["strength"] == 0.95
        assert edge["evidence"] == "code analysis"


class TestMergeEdgesLogic:
    """Test edge merging with semantic metadata."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test.kg")

    @pytest.fixture
    def sample_diagram(self, store: KnowledgeGraphStore) -> str:
        record = store.create_diagram("test_merge")
        diagram_id = record["diagram_id"]
        store.add_or_update_node(diagram_id, "n1")
        store.add_or_update_node(diagram_id, "n2")
        return diagram_id

    def test_merge_preserves_relation_type(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test that merging edges preserves semantic relation metadata."""
        # Create initial edge with relation type
        store.add_or_update_edge(
            sample_diagram, "n1", "n2", relation_type="depends_on", strength=0.8
        )

        # Update with additional props (simulates re-ingestion)
        store.add_or_update_edge(sample_diagram, "n1", "n2", props={"extra": "value"})

        # Check that relation metadata is still there
        graph = store.graph(sample_diagram)
        edge = graph["edges"][0]
        assert edge["relation_type"] == "depends_on"
        assert edge["strength"] == 0.8
        assert edge["props"]["extra"] == "value"


class TestFindEdgesByRelationType:
    """Test queries to find edges by relation type."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test.kg")

    @pytest.fixture
    def sample_diagram_with_relations(self, store: KnowledgeGraphStore) -> str:
        """Create diagram with multiple relation types."""
        record = store.create_diagram("test_find_relations")
        diagram_id = record["diagram_id"]

        # Create nodes
        for i in range(5):
            store.add_or_update_node(diagram_id, f"node_{i}")

        # Create edges with different relation types
        store.add_or_update_edge(
            diagram_id, "node_0", "node_1", relation_type="implements"
        )
        store.add_or_update_edge(
            diagram_id, "node_0", "node_2", relation_type="implements"
        )
        store.add_or_update_edge(
            diagram_id, "node_1", "node_2", relation_type="depends_on"
        )
        store.add_or_update_edge(diagram_id, "node_2", "node_3", relation_type="tests")
        store.add_or_update_edge(diagram_id, "node_3", "node_4")  # No relation type

        return diagram_id

    def test_find_edges_by_relation_type_implements(
        self, store: KnowledgeGraphStore, sample_diagram_with_relations: str
    ) -> None:
        """Test finding edges with 'implements' relation type."""
        edges = store.find_edges_by_relation_type(
            sample_diagram_with_relations, "implements"
        )

        assert len(edges) == 2
        for edge in edges:
            assert edge["relation_type"] == "implements"
            assert edge["src"] in ["node_0"]

    def test_find_edges_by_relation_type_depends_on(
        self, store: KnowledgeGraphStore, sample_diagram_with_relations: str
    ) -> None:
        """Test finding edges with 'depends_on' relation type."""
        edges = store.find_edges_by_relation_type(
            sample_diagram_with_relations, "depends_on"
        )

        assert len(edges) == 1
        assert edges[0]["src"] == "node_1"
        assert edges[0]["dst"] == "node_2"

    def test_find_edges_by_relation_type_invalid(
        self, store: KnowledgeGraphStore, sample_diagram_with_relations: str
    ) -> None:
        """Test that invalid relation type raises error."""
        with pytest.raises(ValueError, match="invalid_relation_type"):
            store.find_edges_by_relation_type(sample_diagram_with_relations, "bad_type")

    def test_find_edges_relation_type_with_no_matches(
        self, store: KnowledgeGraphStore, sample_diagram_with_relations: str
    ) -> None:
        """Test finding relation type that doesn't exist in diagram."""
        edges = store.find_edges_by_relation_type(
            sample_diagram_with_relations, "violates"
        )
        assert len(edges) == 0


class TestFindEdgesByStrength:
    """Test queries to filter edges by strength confidence."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test.kg")

    @pytest.fixture
    def sample_diagram_with_strengths(self, store: KnowledgeGraphStore) -> str:
        """Create diagram with edges having various strength levels."""
        record = store.create_diagram("test_find_strength")
        diagram_id = record["diagram_id"]

        for i in range(5):
            store.add_or_update_node(diagram_id, f"node_{i}")

        # Create edges with different strengths
        store.add_or_update_edge(diagram_id, "node_0", "node_1", strength=0.1)
        store.add_or_update_edge(diagram_id, "node_0", "node_2", strength=0.5)
        store.add_or_update_edge(diagram_id, "node_1", "node_3", strength=0.8)
        store.add_or_update_edge(diagram_id, "node_2", "node_4", strength=0.95)
        store.add_or_update_edge(diagram_id, "node_3", "node_0")  # No strength

        return diagram_id

    def test_find_high_confidence_edges(
        self, store: KnowledgeGraphStore, sample_diagram_with_strengths: str
    ) -> None:
        """Test finding high-confidence edges (strength > 0.8)."""
        edges = store.find_edges_by_strength(sample_diagram_with_strengths, 0.8, 1.0)

        assert len(edges) == 2
        strengths = [e["strength"] for e in edges]
        assert all(0.8 <= s <= 1.0 for s in strengths)

    def test_find_medium_confidence_edges(
        self, store: KnowledgeGraphStore, sample_diagram_with_strengths: str
    ) -> None:
        """Test finding medium-confidence edges."""
        edges = store.find_edges_by_strength(sample_diagram_with_strengths, 0.4, 0.7)

        assert len(edges) == 1
        assert edges[0]["strength"] == 0.5

    def test_find_edges_strength_full_range(
        self, store: KnowledgeGraphStore, sample_diagram_with_strengths: str
    ) -> None:
        """Test finding all edges with strength."""
        edges = store.find_edges_by_strength(sample_diagram_with_strengths, 0.0, 1.0)

        assert len(edges) == 4  # Only edges with strength, not the one without

    def test_find_edges_strength_no_matches(
        self, store: KnowledgeGraphStore, sample_diagram_with_strengths: str
    ) -> None:
        """Test finding strength range with no matches."""
        edges = store.find_edges_by_strength(sample_diagram_with_strengths, 0.3, 0.4)
        assert len(edges) == 0


class TestFindRelatedNodes:
    """Test finding nodes related by semantic relations."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test.kg")

    @pytest.fixture
    def sample_diagram_with_relations(self, store: KnowledgeGraphStore) -> str:
        """Create diagram with related nodes."""
        record = store.create_diagram("test_find_related")
        diagram_id = record["diagram_id"]

        # Create semantic nodes
        store.add_or_update_node(
            diagram_id, "adr_0051", node_type="adr", label="ADR 51"
        )
        store.add_or_update_node(
            diagram_id, "module_a", node_type="module", label="Module A"
        )
        store.add_or_update_node(
            diagram_id, "module_b", node_type="module", label="Module B"
        )
        store.add_or_update_node(diagram_id, "test_a", node_type="file", label="Test A")
        store.add_or_update_node(
            diagram_id, "contract_a", node_type="contract", label="Contract A"
        )

        # Create semantic relations
        store.add_or_update_edge(
            diagram_id,
            "adr_0051",
            "module_a",
            relation_type="implements",
            strength=0.95,
            evidence="primary impl",
        )
        store.add_or_update_edge(
            diagram_id,
            "adr_0051",
            "module_b",
            relation_type="implements",
            strength=0.8,
            evidence="secondary impl",
        )
        store.add_or_update_edge(
            diagram_id, "module_a", "test_a", relation_type="tests", strength=0.9
        )
        store.add_or_update_edge(
            diagram_id, "module_a", "contract_a", relation_type="requires"
        )
        store.add_or_update_edge(
            diagram_id, "test_a", "adr_0051", relation_type="documents"
        )

        return diagram_id

    def test_find_related_nodes_outgoing(
        self, store: KnowledgeGraphStore, sample_diagram_with_relations: str
    ) -> None:
        """Test finding outgoing relations from a node."""
        result = store.find_related_nodes(sample_diagram_with_relations, "adr_0051")

        assert result["node"] == "adr_0051"
        assert len(result["outgoing"]) == 2
        assert len(result["incoming"]) == 1

    def test_find_related_nodes_by_relation_type(
        self, store: KnowledgeGraphStore, sample_diagram_with_relations: str
    ) -> None:
        """Test filtering related nodes by relation type."""
        result = store.find_related_nodes(
            sample_diagram_with_relations, "adr_0051", relation_types=["implements"]
        )

        assert len(result["outgoing"]) == 2
        assert all(r["relation_type"] == "implements" for r in result["outgoing"])

    def test_find_related_nodes_with_metadata(
        self, store: KnowledgeGraphStore, sample_diagram_with_relations: str
    ) -> None:
        """Test that related nodes include metadata."""
        result = store.find_related_nodes(sample_diagram_with_relations, "adr_0051")

        outgoing = result["outgoing"]
        for rel in outgoing:
            assert "target" in rel
            assert "relation_type" in rel
            assert "strength" in rel
            assert "evidence" in rel


class TestRelationTypeStats:
    """Test statistics about relation types in a diagram."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test.kg")

    @pytest.fixture
    def sample_diagram_with_mixed_edges(self, store: KnowledgeGraphStore) -> str:
        """Create diagram with various relation types and strengths."""
        record = store.create_diagram("test_stats")
        diagram_id = record["diagram_id"]

        for i in range(6):
            store.add_or_update_node(diagram_id, f"n{i}")

        # Mix of typed and untyped, with and without strength/evidence
        store.add_or_update_edge(
            diagram_id, "n0", "n1", relation_type="implements", strength=0.9
        )
        store.add_or_update_edge(
            diagram_id,
            "n0",
            "n2",
            relation_type="implements",
            strength=0.8,
            evidence="test",
        )
        store.add_or_update_edge(
            diagram_id, "n1", "n3", relation_type="depends_on", evidence="code"
        )
        store.add_or_update_edge(diagram_id, "n2", "n4", relation_type="tests")
        store.add_or_update_edge(diagram_id, "n3", "n5")  # No relation type

        return diagram_id

    def test_relation_type_stats_basic(
        self, store: KnowledgeGraphStore, sample_diagram_with_mixed_edges: str
    ) -> None:
        """Test basic stats structure."""
        stats = store.get_relation_type_stats(sample_diagram_with_mixed_edges)

        assert "total_edges" in stats
        assert "relation_type_distribution" in stats
        assert "strength_distribution" in stats
        assert "edges_with_evidence" in stats
        assert "labeled_relations" in stats

    def test_relation_type_stats_counts(
        self, store: KnowledgeGraphStore, sample_diagram_with_mixed_edges: str
    ) -> None:
        """Test that stats counts are correct."""
        stats = store.get_relation_type_stats(sample_diagram_with_mixed_edges)

        assert stats["total_edges"] == 5
        assert stats["edges_with_evidence"] == 2
        assert stats["labeled_relations"] == 4
        assert stats["relation_type_distribution"]["implements"] == 2
        assert stats["relation_type_distribution"]["depends_on"] == 1
        assert stats["relation_type_distribution"]["tests"] == 1
        assert stats["relation_type_distribution"]["unlabeled"] == 1

    def test_relation_type_stats_strength_distribution(
        self, store: KnowledgeGraphStore, sample_diagram_with_mixed_edges: str
    ) -> None:
        """Test strength distribution in stats."""
        stats = store.get_relation_type_stats(sample_diagram_with_mixed_edges)

        strength_dist = stats["strength_distribution"]
        assert strength_dist[0.9] == 1
        assert strength_dist[0.8] == 1
        assert len(strength_dist) == 2  # Only 2 edges have strength


class TestPerformance:
    """Test performance targets for semantic relation operations."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test_perf.kg")

    @pytest.fixture
    def large_diagram(self, store: KnowledgeGraphStore) -> str:
        """Create larger diagram for performance testing."""
        record = store.create_diagram("perf_test")
        diagram_id = record["diagram_id"]

        # Create 100 nodes
        for i in range(100):
            store.add_or_update_node(diagram_id, f"node_{i:03d}")

        # Create 500 edges with various relation types
        rel_types = list(SEMANTIC_RELATIONS.keys())
        for i in range(500):
            src = f"node_{i % 100:03d}"
            dst = f"node_{(i + 1) % 100:03d}"
            rel_type = rel_types[i % len(rel_types)]
            strength = (i % 100) / 100.0  # 0.0 to 0.99
            store.add_or_update_edge(
                diagram_id, src, dst, relation_type=rel_type, strength=strength
            )

        return diagram_id

    def test_edge_creation_performance(
        self, store: KnowledgeGraphStore, large_diagram: str
    ) -> None:
        """Test edge creation is fast (<5ms)."""
        start = time.time()
        for i in range(10):
            store.add_or_update_edge(
                large_diagram,
                f"node_{i:03d}",
                f"node_{(i+1) % 100:03d}",
                relation_type="implements",
                strength=0.9,
            )
        elapsed = (time.time() - start) * 1000  # Convert to ms

        avg_per_edge = elapsed / 10
        assert (
            avg_per_edge < 5
        ), f"Edge creation too slow: {avg_per_edge:.2f}ms per edge"

    def test_find_by_relation_type_performance(
        self, store: KnowledgeGraphStore, large_diagram: str
    ) -> None:
        """Test finding edges by relation type is fast (<10ms)."""
        start = time.time()
        edges = store.find_edges_by_relation_type(large_diagram, "implements")
        elapsed = (time.time() - start) * 1000

        assert elapsed < 10, f"Relation type query too slow: {elapsed:.2f}ms"
        assert len(edges) > 0

    def test_find_by_strength_performance(
        self, store: KnowledgeGraphStore, large_diagram: str
    ) -> None:
        """Test finding edges by strength is fast (<10ms)."""
        start = time.time()
        edges = store.find_edges_by_strength(large_diagram, 0.7, 0.9)
        elapsed = (time.time() - start) * 1000

        assert elapsed < 10, f"Strength query too slow: {elapsed:.2f}ms"
        assert len(edges) > 0

    def test_find_related_nodes_performance(
        self, store: KnowledgeGraphStore, large_diagram: str
    ) -> None:
        """Test finding related nodes is fast (<10ms)."""
        start = time.time()
        store.find_related_nodes(large_diagram, "node_000")
        elapsed = (time.time() - start) * 1000

        assert elapsed < 10, f"Related nodes query too slow: {elapsed:.2f}ms"

    def test_stats_generation_performance(
        self, store: KnowledgeGraphStore, large_diagram: str
    ) -> None:
        """Test stats generation is fast (<10ms)."""
        start = time.time()
        stats = store.get_relation_type_stats(large_diagram)
        elapsed = (time.time() - start) * 1000

        assert elapsed < 10, f"Stats generation too slow: {elapsed:.2f}ms"
        assert stats["total_edges"] > 0


class TestBackwardCompatibility:
    """Test backward compatibility with edges without semantic metadata."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test_compat.kg")

    @pytest.fixture
    def sample_diagram(self, store: KnowledgeGraphStore) -> str:
        record = store.create_diagram("compat_test")
        diagram_id = record["diagram_id"]
        store.add_or_update_node(diagram_id, "a")
        store.add_or_update_node(diagram_id, "b")
        store.add_or_update_node(diagram_id, "c")
        return diagram_id

    def test_old_edges_without_relation_type(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test that old edges without relation_type still work."""
        # Create edge without relation type (old style)
        store.add_or_update_edge(sample_diagram, "a", "b")

        # Should be retrievable
        graph = store.graph(sample_diagram)
        assert len(graph["edges"]) == 1
        assert graph["edges"][0]["src"] == "a"
        assert graph["edges"][0]["dst"] == "b"

    def test_mixed_old_and_new_edges(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test diagram with both old and new style edges."""
        # Old style
        store.add_or_update_edge(sample_diagram, "a", "b")

        # New style
        store.add_or_update_edge(
            sample_diagram, "b", "c", relation_type="implements", strength=0.9
        )

        graph = store.graph(sample_diagram)
        assert len(graph["edges"]) == 2

        # Old edge has no relation_type
        old_edge = next(e for e in graph["edges"] if e["src"] == "a")
        assert "relation_type" not in old_edge

        # New edge has relation_type
        new_edge = next(e for e in graph["edges"] if e["src"] == "b")
        assert new_edge["relation_type"] == "implements"

    def test_find_by_relation_type_ignores_old_edges(
        self, store: KnowledgeGraphStore, sample_diagram: str
    ) -> None:
        """Test that queries for relation types ignore old-style edges."""
        store.add_or_update_edge(sample_diagram, "a", "b")
        store.add_or_update_edge(sample_diagram, "b", "c", relation_type="implements")

        edges = store.find_edges_by_relation_type(sample_diagram, "implements")
        assert len(edges) == 1
        assert edges[0]["src"] == "b"


class TestIntegration:
    """Integration tests for semantic relations with full workflow."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> KnowledgeGraphStore:
        return KnowledgeGraphStore(tmp_path / "test_integration.kg")

    def test_full_workflow_building_semantic_graph(
        self, store: KnowledgeGraphStore
    ) -> None:
        """Test complete workflow: create diagram, add nodes, add semantic relations."""
        # Create diagram
        diagram = store.create_diagram("workflow_test", "Complete Workflow Test")
        diagram_id = diagram["diagram_id"]

        # Add ADR
        store.add_or_update_node(
            diagram_id,
            "adr_0051",
            node_type="adr",
            label="Agent Scheduling",
            metadata={"status": "ACCEPTED"},
        )

        # Add implementation modules
        store.add_or_update_node(diagram_id, "module_scheduler", node_type="module")
        store.add_or_update_node(diagram_id, "module_queue", node_type="module")

        # Add tests
        store.add_or_update_node(diagram_id, "test_scheduler", node_type="file")

        # Add contracts
        store.add_or_update_node(diagram_id, "contract_sched", node_type="contract")

        # Create semantic relations
        store.add_or_update_edge(
            diagram_id,
            "adr_0051",
            "module_scheduler",
            relation_type="implements",
            strength=0.95,
            evidence="primary implementation",
        )
        store.add_or_update_edge(
            diagram_id,
            "adr_0051",
            "module_queue",
            relation_type="implements",
            strength=0.8,
            evidence="secondary implementation",
        )
        store.add_or_update_edge(
            diagram_id,
            "module_scheduler",
            "test_scheduler",
            relation_type="tests",
            strength=0.9,
        )
        store.add_or_update_edge(
            diagram_id, "module_scheduler", "contract_sched", relation_type="requires"
        )

        # Query and verify
        graph = store.graph(diagram_id)
        assert len(graph["nodes"]) == 5
        assert len(graph["edges"]) == 4

        # Find implementations
        impls = store.find_edges_by_relation_type(diagram_id, "implements")
        assert len(impls) == 2

        # Find high-confidence relations
        high_conf = store.find_edges_by_strength(diagram_id, 0.9, 1.0)
        assert len(high_conf) >= 1

        # Find related to ADR
        related = store.find_related_nodes(diagram_id, "adr_0051")
        assert len(related["outgoing"]) == 2

        # Get stats
        stats = store.get_relation_type_stats(diagram_id)
        assert stats["total_edges"] == 4
        assert stats["labeled_relations"] == 4
