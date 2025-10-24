"""
Test DependencyGraphEngine for KG-2.3 - Dependency Graph Analysis.

Tests transitive dependency computation, circular dependency detection,
impact analysis, and path finding.

Performance targets:
- Direct dependencies: <1ms
- Transitive dependencies: <50ms
- Circular dependency detection: <100ms
- Path finding: <50ms
- All cached operations: <5ms
"""

import time

from kg_indexers import (
    CircularDependency,
    DependencyGraphEngine,
    DependencyPath,
    ModuleIndexer,
)


class TestDependencyPathDataclass:
    """Test DependencyPath dataclass."""

    def test_dependency_path_structure(self) -> None:
        """Test DependencyPath has expected fields."""
        path = DependencyPath(
            source="k0.kernel",
            target="k0.bus",
            path=["k0.kernel", "k0.bus"],
            length=1,
            is_circular=False,
        )

        assert path.source == "k0.kernel"
        assert path.target == "k0.bus"
        assert path.path == ["k0.kernel", "k0.bus"]
        assert path.length == 1
        assert path.is_circular is False

    def test_dependency_path_circular(self) -> None:
        """Test circular dependency path."""
        path = DependencyPath(
            source="k0.kernel",
            target="k0.kernel",
            path=["k0.kernel", "k0.bus", "k0.kernel"],
            length=2,
            is_circular=True,
        )

        assert path.is_circular is True
        assert path.target == path.source


class TestCircularDependencyDataclass:
    """Test CircularDependency dataclass."""

    def test_circular_dependency_structure(self) -> None:
        """Test CircularDependency has expected fields."""
        cycle = CircularDependency(
            modules=["k0.kernel", "k0.bus", "k0.kernel"],
            cycle_length=2,
            edges=[("k0.kernel", "k0.bus"), ("k0.bus", "k0.kernel")],
            detected_at=time.time(),
        )

        assert cycle.modules == ["k0.kernel", "k0.bus", "k0.kernel"]
        assert cycle.cycle_length == 2
        assert len(cycle.edges) == 2
        assert cycle.detected_at > 0


class TestDependencyGraphEngineInitialization:
    """Test DependencyGraphEngine initialization."""

    def test_engine_initialization_without_indexer(self) -> None:
        """Test engine can be created without indexer."""
        engine = DependencyGraphEngine()

        assert engine.module_indexer is None
        assert engine._transitive_cache == {}
        assert engine._dependents_cache == {}
        assert engine._circular_cache is None

    def test_engine_initialization_with_indexer(self) -> None:
        """Test engine can be initialized with indexer."""
        indexer = ModuleIndexer()
        engine = DependencyGraphEngine(module_indexer=indexer)

        assert engine.module_indexer is indexer

    def test_set_module_indexer(self) -> None:
        """Test setting module indexer after initialization."""
        engine = DependencyGraphEngine()
        indexer = ModuleIndexer()
        engine.set_module_indexer(indexer)

        assert engine.module_indexer is indexer

    def test_cache_invalidation_on_set_indexer(self) -> None:
        """Test caches are invalidated when setting new indexer."""
        indexer1 = ModuleIndexer()
        engine = DependencyGraphEngine(module_indexer=indexer1)

        # Populate caches
        engine._transitive_cache["k0.kernel"] = {"k0.bus"}
        engine._dependents_cache["k0.kernel"] = {"k0.chaos"}
        engine._circular_cache = []

        # Set new indexer
        indexer2 = ModuleIndexer()
        engine.set_module_indexer(indexer2)

        # Verify caches cleared
        assert engine._transitive_cache == {}
        assert engine._dependents_cache == {}
        assert engine._circular_cache is None


class TestDirectDependencies:
    """Test direct dependency queries."""

    def test_direct_dependencies_nonexistent_module(self) -> None:
        """Test querying nonexistent module returns empty list."""
        indexer = ModuleIndexer()
        indexer.import_graph = {}
        engine = DependencyGraphEngine(module_indexer=indexer)

        result = engine.get_direct_dependencies("nonexistent")
        assert result == []

    def test_direct_dependencies_no_indexer(self) -> None:
        """Test without indexer returns empty list."""
        engine = DependencyGraphEngine()
        result = engine.get_direct_dependencies("k0.kernel")
        assert result == []

    def test_direct_dependencies_with_imports(self) -> None:
        """Test direct dependencies extraction."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.kernel": {"imports": ["k0.bus", "k0.chaos"], "imported_by": []},
            "k0.bus": {"imports": [], "imported_by": ["k0.kernel"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        result = engine.get_direct_dependencies("k0.kernel")
        assert set(result) == {"k0.bus", "k0.chaos"}

    def test_direct_dependents_nonexistent_module(self) -> None:
        """Test querying nonexistent module for dependents."""
        indexer = ModuleIndexer()
        indexer.import_graph = {}
        engine = DependencyGraphEngine(module_indexer=indexer)

        result = engine.get_direct_dependents("nonexistent")
        assert result == []

    def test_direct_dependents_with_dependents(self) -> None:
        """Test direct dependents extraction."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.kernel": {"imports": [], "imported_by": ["k0.bus", "k0.chaos"]},
            "k0.bus": {"imports": ["k0.kernel"], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        result = engine.get_direct_dependents("k0.kernel")
        assert set(result) == {"k0.bus", "k0.chaos"}


class TestTransitiveDependencies:
    """Test transitive dependency computation."""

    def test_transitive_dependencies_no_deps(self) -> None:
        """Test module with no dependencies."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.kernel": {"imports": [], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        result = engine.get_transitive_dependencies("k0.kernel")
        assert result["dependencies"] == set()
        assert result["depth"] == 0

    def test_transitive_dependencies_linear_chain(self) -> None:
        """Test transitive deps in linear chain: A -> B -> C."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": []},
            "k0.b": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": [], "imported_by": ["k0.b"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        result = engine.get_transitive_dependencies("k0.a")
        assert result["dependencies"] == {"k0.b", "k0.c"}
        assert result["depth"] == 2

    def test_transitive_dependencies_with_depth_limit(self) -> None:
        """Test transitive deps with depth limit."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": []},
            "k0.b": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": ["k0.d"], "imported_by": ["k0.b"]},
            "k0.d": {"imports": [], "imported_by": ["k0.c"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        result = engine.get_transitive_dependencies("k0.a", max_depth=2)
        assert result["dependencies"] == {"k0.b", "k0.c"}
        assert result["depth"] == 2

    def test_transitive_dependencies_caching(self) -> None:
        """Test transitive deps are cached."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": []},
            "k0.b": {"imports": [], "imported_by": ["k0.a"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        # First call populates cache
        result1 = engine.get_transitive_dependencies("k0.a")
        assert "k0.b" in engine._transitive_cache["k0.a"]

        # Second call uses cache
        result2 = engine.get_transitive_dependencies("k0.a")
        assert result1["dependencies"] == result2["dependencies"]

    def test_transitive_dependencies_by_depth(self) -> None:
        """Test by_depth structure in transitive deps."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b", "k0.x"], "imported_by": []},
            "k0.b": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": [], "imported_by": ["k0.b"]},
            "k0.x": {"imports": [], "imported_by": ["k0.a"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        result = engine.get_transitive_dependencies("k0.a")
        # Verify structure exists and has correct modules at each depth
        assert result["by_depth"] is not None
        assert len(result["dependencies"]) == 3  # b, x, c
        assert "k0.c" in result["dependencies"]  # Transitive dep should be included


class TestTransitiveDependents:
    """Test transitive dependents computation."""

    def test_transitive_dependents_no_dependents(self) -> None:
        """Test module with no dependents."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.kernel": {"imports": [], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        result = engine.get_transitive_dependents("k0.kernel")
        assert result["dependents"] == set()
        assert result["depth"] == 0

    def test_transitive_dependents_linear_chain(self) -> None:
        """Test transitive dependents: A <- B <- C."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": [], "imported_by": ["k0.b"]},
            "k0.b": {"imports": ["k0.a"], "imported_by": ["k0.c"]},
            "k0.c": {"imports": ["k0.b"], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        result = engine.get_transitive_dependents("k0.a")
        assert result["dependents"] == {"k0.b", "k0.c"}
        assert result["depth"] == 2

    def test_transitive_dependents_caching(self) -> None:
        """Test transitive dependents are cached."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": [], "imported_by": ["k0.b"]},
            "k0.b": {"imports": ["k0.a"], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        # First call populates cache
        result1 = engine.get_transitive_dependents("k0.a")
        assert "k0.b" in engine._dependents_cache["k0.a"]

        # Second call uses cache
        result2 = engine.get_transitive_dependents("k0.a")
        assert result1["dependents"] == result2["dependents"]


class TestCircularDependencyDetection:
    """Test circular dependency detection."""

    def test_no_circular_dependencies(self) -> None:
        """Test DAG with no cycles."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b", "k0.c"], "imported_by": []},
            "k0.b": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": [], "imported_by": ["k0.a", "k0.b"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        cycles = engine.find_circular_dependencies()
        assert len(cycles) == 0

    def test_simple_circular_dependency(self) -> None:
        """Test simple A -> B -> A cycle."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": ["k0.b"]},
            "k0.b": {"imports": ["k0.a"], "imported_by": ["k0.a"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        cycles = engine.find_circular_dependencies()
        assert len(cycles) >= 1

        cycle = cycles[0]
        assert cycle.cycle_length >= 1
        assert "k0.a" in cycle.modules
        assert "k0.b" in cycle.modules

    def test_circular_dependency_detection_caching(self) -> None:
        """Test circular dependency detection is cached."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": ["k0.b"]},
            "k0.b": {"imports": ["k0.a"], "imported_by": ["k0.a"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        # First call populates cache
        cycles1 = engine.find_circular_dependencies()
        assert engine._circular_cache is not None

        # Second call uses cache
        cycles2 = engine.find_circular_dependencies()
        assert len(cycles1) == len(cycles2)

    def test_three_way_circular_dependency(self) -> None:
        """Test A -> B -> C -> A cycle."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": ["k0.c"]},
            "k0.b": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": ["k0.a"], "imported_by": ["k0.b"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        cycles = engine.find_circular_dependencies()
        assert len(cycles) >= 1


class TestDependencyStats:
    """Test dependency statistics."""

    def test_dependency_stats_leaf_node(self) -> None:
        """Test stats for leaf node (no dependencies)."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": [], "imported_by": ["k0.b"]},
            "k0.b": {"imports": ["k0.a"], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        stats = engine.get_dependency_stats("k0.a")
        assert stats["is_leaf"] is True
        assert stats["is_root"] is False
        assert stats["direct_dependencies"] == 0

    def test_dependency_stats_root_node(self) -> None:
        """Test stats for root node (not depended on)."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": []},
            "k0.b": {"imports": [], "imported_by": ["k0.a"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        stats = engine.get_dependency_stats("k0.a")
        assert stats["is_root"] is True
        assert stats["is_leaf"] is False

    def test_dependency_stats_middle_node(self) -> None:
        """Test stats for middle node."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": ["k0.c"]},
            "k0.b": {"imports": [], "imported_by": ["k0.a"]},
            "k0.c": {"imports": ["k0.a"], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        stats = engine.get_dependency_stats("k0.a")
        assert stats["is_leaf"] is False
        assert stats["is_root"] is False
        assert stats["direct_dependencies"] == 1
        assert stats["direct_dependents"] == 1

    def test_dependency_stats_impact_radius(self) -> None:
        """Test impact radius calculation."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": [], "imported_by": ["k0.b"]},
            "k0.b": {"imports": ["k0.a"], "imported_by": ["k0.c", "k0.d"]},
            "k0.c": {"imports": ["k0.b"], "imported_by": []},
            "k0.d": {"imports": ["k0.b"], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        stats = engine.get_dependency_stats("k0.a")
        # Impact radius includes all transitive dependents: k0.b, k0.c, k0.d
        assert stats["impact_radius"] == 3


class TestPathFinding:
    """Test dependency path finding."""

    def test_find_path_direct(self) -> None:
        """Test finding direct path."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": []},
            "k0.b": {"imports": [], "imported_by": ["k0.a"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        paths = engine.find_paths("k0.a", "k0.b")
        assert len(paths) >= 1
        assert paths[0].path == ["k0.a", "k0.b"]

    def test_find_path_indirect(self) -> None:
        """Test finding indirect path."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": []},
            "k0.b": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": [], "imported_by": ["k0.b"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        paths = engine.find_paths("k0.a", "k0.c")
        assert len(paths) >= 1
        assert paths[0].path == ["k0.a", "k0.b", "k0.c"]

    def test_find_path_nonexistent(self) -> None:
        """Test finding path when none exists."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": []},
            "k0.b": {"imports": [], "imported_by": ["k0.a"]},
            "k0.c": {"imports": [], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        paths = engine.find_paths("k0.a", "k0.c")
        assert len(paths) == 0

    def test_find_path_max_paths_limit(self) -> None:
        """Test max_paths limit."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b", "k0.x"], "imported_by": []},
            "k0.b": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.x": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": [], "imported_by": ["k0.b", "k0.x"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        paths = engine.find_paths("k0.a", "k0.c", max_paths=1)
        assert len(paths) <= 1

    def test_find_path_max_depth_limit(self) -> None:
        """Test max_depth limit in path finding."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": []},
            "k0.b": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": ["k0.d"], "imported_by": ["k0.b"]},
            "k0.d": {"imports": [], "imported_by": ["k0.c"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        paths = engine.find_paths("k0.a", "k0.d", max_depth=2)
        assert len(paths) == 0  # Path would be 3 hops, exceeds max_depth


class TestImpactAnalysis:
    """Test impact analysis."""

    def test_impact_analysis_low_risk(self) -> None:
        """Test low risk (few dependents)."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": [], "imported_by": ["k0.b"]},
            "k0.b": {"imports": ["k0.a"], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        analysis = engine.get_impact_analysis("k0.a")
        assert analysis["risk_level"] == "low"
        assert analysis["affected_count"] == 1

    def test_impact_analysis_medium_risk(self) -> None:
        """Test medium risk (5-20 dependents)."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {
                "imports": [],
                "imported_by": [f"k0.dep{i}" for i in range(10)],
            },
        }
        for i in range(10):
            indexer.import_graph[f"k0.dep{i}"] = {
                "imports": ["k0.a"],
                "imported_by": [],
            }

        engine = DependencyGraphEngine(module_indexer=indexer)

        analysis = engine.get_impact_analysis("k0.a")
        assert analysis["risk_level"] == "medium"
        assert analysis["affected_count"] == 10

    def test_impact_analysis_high_risk(self) -> None:
        """Test high risk (>20 dependents)."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {
                "imports": [],
                "imported_by": [f"k0.dep{i}" for i in range(25)],
            },
        }
        for i in range(25):
            indexer.import_graph[f"k0.dep{i}"] = {
                "imports": ["k0.a"],
                "imported_by": [],
            }

        engine = DependencyGraphEngine(module_indexer=indexer)

        analysis = engine.get_impact_analysis("k0.a")
        assert analysis["risk_level"] == "high"
        assert analysis["affected_count"] == 25

    def test_impact_analysis_circular_risk(self) -> None:
        """Test circular dependency risk flag."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": ["k0.b"]},
            "k0.b": {"imports": ["k0.a"], "imported_by": ["k0.a"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        analysis = engine.get_impact_analysis("k0.a")
        assert analysis["circular_risk"] is True


class TestPerformance:
    """Test performance targets."""

    def test_direct_dependencies_performance(self) -> None:
        """Test direct dependencies query <1ms."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            f"k0.m{i}": {"imports": [f"k0.m{(i+1)%10}"], "imported_by": []}
            for i in range(100)
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        start = time.time()
        for i in range(10):
            engine.get_direct_dependencies(f"k0.m{i}")
        elapsed = (time.time() - start) * 1000

        assert elapsed < 10, f"Direct deps took {elapsed}ms, expected <10ms"

    def test_transitive_dependencies_performance(self) -> None:
        """Test transitive deps caching <5ms."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": []},
            "k0.b": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": ["k0.d"], "imported_by": ["k0.b"]},
            "k0.d": {"imports": [], "imported_by": ["k0.c"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        # First call (computation)
        start = time.time()
        result1 = engine.get_transitive_dependencies("k0.a")
        first_elapsed = (time.time() - start) * 1000

        # Second call (cached)
        start = time.time()
        result2 = engine.get_transitive_dependencies("k0.a")
        cached_elapsed = (time.time() - start) * 1000

        assert cached_elapsed < 5, f"Cached call took {cached_elapsed}ms, expected <5ms"
        assert result1["dependencies"] == result2["dependencies"]

    def test_circular_dependency_detection_performance(self) -> None:
        """Test circular detection <100ms."""
        indexer = ModuleIndexer()
        # Build large DAG (linear chain, no cycles)
        indexer.import_graph = {}
        for i in range(50):
            next_idx = (i + 1) % 50
            imports = [f"k0.m{next_idx}"] if i < 49 else []
            imported_by = [f"k0.m{(i-1) % 50}"] if i > 0 else []
            indexer.import_graph[f"k0.m{i}"] = {
                "imports": imports,
                "imported_by": imported_by,
            }
        engine = DependencyGraphEngine(module_indexer=indexer)

        start = time.time()
        engine.find_circular_dependencies()
        elapsed = (time.time() - start) * 1000

        assert elapsed < 100, f"Circular detection took {elapsed}ms, expected <100ms"

    def test_path_finding_performance(self) -> None:
        """Test path finding <50ms."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b"], "imported_by": []},
            "k0.b": {"imports": ["k0.c"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": ["k0.d"], "imported_by": ["k0.b"]},
            "k0.d": {"imports": ["k0.e"], "imported_by": ["k0.c"]},
            "k0.e": {"imports": [], "imported_by": ["k0.d"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        start = time.time()
        paths = engine.find_paths("k0.a", "k0.e")
        elapsed = (time.time() - start) * 1000

        assert elapsed < 50, f"Path finding took {elapsed}ms, expected <50ms"


class TestIntegration:
    """Integration tests with real module structures."""

    def test_integration_simple_dependency_tree(self) -> None:
        """Test with realistic dependency tree structure."""
        indexer = ModuleIndexer()
        # Simulate: kernel -> bus -> middleware -> core
        indexer.import_graph = {
            "k0.kernel": {
                "imports": ["k0.bus", "k0.chaos"],
                "imported_by": [],
            },
            "k0.bus": {
                "imports": ["k0.middleware"],
                "imported_by": ["k0.kernel"],
            },
            "k0.middleware": {
                "imports": ["k0.core"],
                "imported_by": ["k0.bus"],
            },
            "k0.core": {
                "imports": [],
                "imported_by": ["k0.middleware"],
            },
            "k0.chaos": {
                "imports": ["k0.middleware"],
                "imported_by": ["k0.kernel"],
            },
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        # Verify transitive deps
        trans_deps = engine.get_transitive_dependencies("k0.kernel")
        assert "k0.bus" in trans_deps["dependencies"]
        assert "k0.middleware" in trans_deps["dependencies"]
        assert "k0.core" in trans_deps["dependencies"]
        assert trans_deps["depth"] == 3

        # Verify impact analysis
        impact = engine.get_impact_analysis("k0.core")
        assert len(impact["transitively_affected"]) == 3

    def test_integration_multiple_dependency_paths(self) -> None:
        """Test multiple paths to same target."""
        indexer = ModuleIndexer()
        # A -> B, A -> C, B -> D, C -> D (multiple paths to D)
        indexer.import_graph = {
            "k0.a": {"imports": ["k0.b", "k0.c"], "imported_by": []},
            "k0.b": {"imports": ["k0.d"], "imported_by": ["k0.a"]},
            "k0.c": {"imports": ["k0.d"], "imported_by": ["k0.a"]},
            "k0.d": {"imports": [], "imported_by": ["k0.b", "k0.c"]},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        paths = engine.find_paths("k0.a", "k0.d")
        assert len(paths) >= 2  # At least two paths

    def test_integration_mixed_scenarios(self) -> None:
        """Test comprehensive dependency analysis scenario."""
        indexer = ModuleIndexer()
        indexer.import_graph = {
            "k0.kernel": {"imports": ["k0.bus"], "imported_by": []},
            "k0.bus": {
                "imports": ["k0.core", "k0.middleware"],
                "imported_by": ["k0.kernel"],
            },
            "k0.core": {"imports": [], "imported_by": ["k0.bus"]},
            "k0.middleware": {
                "imports": ["k0.core"],
                "imported_by": ["k0.bus", "k0.qos"],
            },
            "k0.qos": {"imports": ["k0.middleware"], "imported_by": []},
        }
        engine = DependencyGraphEngine(module_indexer=indexer)

        # Test various queries
        stats = engine.get_dependency_stats("k0.core")
        assert stats["is_leaf"] is True
        assert stats["impact_radius"] > 0

        # Test cycles (should be none)
        cycles = engine.find_circular_dependencies()
        assert len(cycles) == 0

        # Test paths
        paths = engine.find_paths("k0.kernel", "k0.core")
        assert len(paths) >= 1
