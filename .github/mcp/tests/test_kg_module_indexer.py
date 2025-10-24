"""
Test ModuleIndexer for KG-2.1 - Module Indexing.

Tests comprehensive module discovery, import parsing, and dependency graph extraction.

Performance targets:
- Module extraction: <5ms per file
- Full k0/k1 indexing: <2 seconds
- Circular dependency detection: <100ms
"""

import time
from pathlib import Path

import pytest
from kg_indexers import ModuleIndexer, ModuleMetadata


class TestModuleMetadata:
    """Test ModuleMetadata structure."""

    def test_module_metadata_structure(self) -> None:
        """Test that ModuleMetadata has expected fields."""
        metadata = ModuleMetadata(
            module_id="k0.kernel.core",
            module_name="Core",
            module_type="file",
            file_path="/path/to/core.py",
            docstring="Core module",
            imports=["k0.bus"],
            extracted_at=time.time(),
        )

        assert metadata.module_id == "k0.kernel.core"
        assert metadata.module_name == "Core"
        assert metadata.module_type == "file"
        assert metadata.file_path == "/path/to/core.py"
        assert metadata.docstring == "Core module"
        assert metadata.imports == ["k0.bus"]

    def test_module_metadata_optional_fields(self) -> None:
        """Test that optional fields work correctly."""
        metadata = ModuleMetadata(
            module_id="k1.l2_orchestration",
            module_name="Orchestration",
            module_type="package",
            file_path="/path/to/__init__.py",
            docstring=None,
            imports=[],
            extracted_at=time.time(),
            package_path="/path/to/__init__.py",
        )

        assert metadata.package_path == "/path/to/__init__.py"


class TestModuleIndexerInitialization:
    """Test ModuleIndexer initialization."""

    def test_indexer_initialization(self) -> None:
        """Test indexer is properly initialized."""
        indexer = ModuleIndexer()

        assert indexer.indexed_modules == {}
        assert indexer.import_graph == {}
        assert indexer.reverse_import_graph == {}

    def test_indexer_state_isolation(self) -> None:
        """Test that multiple indexers have isolated state."""
        indexer1 = ModuleIndexer()
        indexer2 = ModuleIndexer()

        indexer1.indexed_modules["test"] = ModuleMetadata(
            module_id="test",
            module_name="Test",
            module_type="file",
            file_path="test.py",
            docstring=None,
            imports=[],
            extracted_at=time.time(),
        )

        assert "test" in indexer1.indexed_modules
        assert "test" not in indexer2.indexed_modules


class TestPathToModuleId:
    """Test conversion of file paths to module IDs."""

    def test_simple_module(self, tmp_path: Path) -> None:
        """Test simple module path conversion."""
        indexer = ModuleIndexer()

        # k0/kernel/core.py -> k0.kernel.core
        relative_path = Path("kernel/core.py")
        module_id = indexer._path_to_module_id(relative_path, "k0")

        assert module_id == "k0.kernel.core"

    def test_nested_module(self, tmp_path: Path) -> None:
        """Test nested module path conversion."""
        indexer = ModuleIndexer()

        # k1/l2_orchestration/agent_scheduler.py -> k1.l2_orchestration.agent_scheduler
        relative_path = Path("l2_orchestration/agent_scheduler.py")
        module_id = indexer._path_to_module_id(relative_path, "k1")

        assert module_id == "k1.l2_orchestration.agent_scheduler"

    def test_init_file_removed(self, tmp_path: Path) -> None:
        """Test that __init__ is removed from module ID."""
        indexer = ModuleIndexer()

        # k0/kernel/__init__.py -> k0.kernel (not k0.kernel.__init__)
        relative_path = Path("kernel/__init__.py")
        module_id = indexer._path_to_module_id(relative_path, "k0")

        assert module_id == "k0.kernel"
        assert "__init__" not in module_id

    def test_no_prefix(self, tmp_path: Path) -> None:
        """Test module ID without prefix."""
        indexer = ModuleIndexer()

        # core.py -> core (when no prefix)
        relative_path = Path("core.py")
        module_id = indexer._path_to_module_id(relative_path, "")

        assert module_id == "core"


class TestDocstringExtraction:
    """Test extraction of module-level docstrings."""

    def test_extract_triple_quoted_docstring(self) -> None:
        """Test extraction of triple-quoted docstring."""
        indexer = ModuleIndexer()
        content = '''"""
This is a module docstring.
It provides core functionality.
"""

import something
'''
        docstring = indexer._extract_docstring(content)

        assert docstring is not None
        assert "module docstring" in docstring
        assert "core functionality" in docstring

    def test_extract_single_quoted_docstring(self) -> None:
        """Test extraction of single-quoted docstring."""
        indexer = ModuleIndexer()
        content = """'''
This is a module.
'''

def foo():
    pass
"""
        docstring = indexer._extract_docstring(content)

        assert docstring is not None
        assert "This is a module" in docstring

    def test_extract_long_docstring_truncated(self) -> None:
        """Test that long docstrings are truncated to 200 chars."""
        indexer = ModuleIndexer()
        long_text = "x" * 300
        content = f'"""{long_text}"""'
        docstring = indexer._extract_docstring(content)

        assert docstring is not None
        assert len(docstring) == 200
        assert docstring.endswith("x" * 200)

    def test_no_docstring(self) -> None:
        """Test module with no docstring."""
        indexer = ModuleIndexer()
        content = """
import something

def foo():
    '''Function docstring'''
    pass
"""
        docstring = indexer._extract_docstring(content)

        assert docstring is None


class TestImportExtraction:
    """Test extraction of Python imports."""

    def test_extract_from_import(self) -> None:
        """Test extraction of 'from X import Y' statements."""
        indexer = ModuleIndexer()
        metadata = ModuleMetadata(
            module_id="k0.kernel.core",
            module_name="Core",
            module_type="file",
            file_path="/tmp/test.py",
            docstring=None,
            imports=[],
            extracted_at=time.time(),
        )

        # Write test module with imports
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
from k0.bus import MessageBus
from k0.storage import Store
import other_lib
"""
            )
            f.flush()
            metadata.file_path = f.name

            imports = indexer._extract_imports(metadata)

        assert "k0.bus" in imports
        assert "k0.storage" in imports
        assert "other_lib" not in imports  # Not k0 or k1

    def test_extract_direct_import(self) -> None:
        """Test extraction of direct 'import X' statements."""
        indexer = ModuleIndexer()
        metadata = ModuleMetadata(
            module_id="k1.l2_orchestration.planner",
            module_name="Planner",
            module_type="file",
            file_path="/tmp/test.py",
            docstring=None,
            imports=[],
            extracted_at=time.time(),
        )

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
import k0.kernel
import k1.l3_execution
import sys
"""
            )
            f.flush()
            metadata.file_path = f.name

            imports = indexer._extract_imports(metadata)

        assert "k0.kernel" in imports
        assert "k1.l3_execution" in imports
        assert "sys" not in imports

    def test_no_k0_k1_imports(self) -> None:
        """Test module with no k0/k1 imports."""
        indexer = ModuleIndexer()
        metadata = ModuleMetadata(
            module_id="k0.bus",
            module_name="Bus",
            module_type="file",
            file_path="/tmp/test.py",
            docstring=None,
            imports=[],
            extracted_at=time.time(),
        )

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
import asyncio
import json
from typing import Dict, List
"""
            )
            f.flush()
            metadata.file_path = f.name

            imports = indexer._extract_imports(metadata)

        assert len(imports) == 0

    def test_deduplicate_imports(self) -> None:
        """Test that duplicate imports are deduplicated."""
        indexer = ModuleIndexer()
        metadata = ModuleMetadata(
            module_id="k0.kernel",
            module_name="Kernel",
            module_type="file",
            file_path="/tmp/test.py",
            docstring=None,
            imports=[],
            extracted_at=time.time(),
        )

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
from k0.bus import MessageBus
from k0.bus import EventBus
from k0.bus import AsyncBus
"""
            )
            f.flush()
            metadata.file_path = f.name

            imports = indexer._extract_imports(metadata)

        assert "k0.bus" in imports
        assert len(imports) == 1


class TestExtractModuleMetadata:
    """Test extraction of module metadata from files."""

    def test_extract_metadata_simple(self, tmp_path: Path) -> None:
        """Test extracting metadata from a simple module."""
        indexer = ModuleIndexer()

        py_file = tmp_path / "core.py"
        py_file.write_text(
            '''"""
Core kernel module.
"""
import k0.bus
'''
        )

        metadata = indexer.extract_module_metadata(py_file, "k0.kernel.core")

        assert metadata is not None
        assert metadata.module_id == "k0.kernel.core"
        assert metadata.module_name == "Core"
        assert metadata.module_type == "file"
        assert "Core kernel" in (metadata.docstring or "")

    def test_extract_metadata_no_docstring(self, tmp_path: Path) -> None:
        """Test extracting metadata from module without docstring."""
        indexer = ModuleIndexer()

        py_file = tmp_path / "util.py"
        py_file.write_text("def helper(): pass")

        metadata = indexer.extract_module_metadata(py_file, "k0.kernel.util")

        assert metadata is not None
        assert metadata.docstring is None

    def test_extract_metadata_nonexistent_file(self, tmp_path: Path) -> None:
        """Test extracting metadata from nonexistent file."""
        indexer = ModuleIndexer()

        py_file = tmp_path / "nonexistent.py"
        metadata = indexer.extract_module_metadata(py_file, "k0.nonexistent")

        assert metadata is None


class TestModuleTagGeneration:
    """Test semantic tag generation for modules."""

    def test_tags_include_layer_k1(self) -> None:
        """Test that K1 layer tags are extracted."""
        indexer = ModuleIndexer()
        metadata = ModuleMetadata(
            module_id="k1.l2_orchestration.scheduler",
            module_name="Scheduler",
            module_type="file",
            file_path="/tmp/test.py",
            docstring="Async scheduler",
            imports=[],
            extracted_at=time.time(),
        )

        tags = indexer._extract_module_tags(metadata)

        assert "l2_orchestration" in tags
        assert "scheduler" in tags
        assert "async" in tags

    def test_tags_include_keywords(self) -> None:
        """Test that module name keywords are in tags."""
        indexer = ModuleIndexer()
        metadata = ModuleMetadata(
            module_id="k0.kernel.agent_scheduler",
            module_name="Agent Scheduler",
            module_type="file",
            file_path="/tmp/test.py",
            docstring=None,
            imports=[],
            extracted_at=time.time(),
        )

        tags = indexer._extract_module_tags(metadata)

        assert "agent" in tags
        assert "scheduler" in tags

    def test_tags_deduplicated(self) -> None:
        """Test that tags are deduplicated."""
        indexer = ModuleIndexer()
        metadata = ModuleMetadata(
            module_id="k1.l2_orchestration.orchestrator",
            module_name="Orchestrator",
            module_type="file",
            file_path="/tmp/test.py",
            docstring="Orchestrator module for orchestration",
            imports=[],
            extracted_at=time.time(),
        )

        tags = indexer._extract_module_tags(metadata)

        # Count occurrences
        for tag in tags:
            assert tags.count(tag) == 1


class TestDirectoryIndexing:
    """Test full directory indexing."""

    def test_ingest_directory_creates_nodes(self, tmp_path: Path) -> None:
        """Test that directory indexing creates module nodes."""
        indexer = ModuleIndexer()

        # Create test module structure
        k0_dir = tmp_path / "k0"
        k0_dir.mkdir()
        (k0_dir / "kernel").mkdir()
        (k0_dir / "kernel" / "__init__.py").write_text('"""Kernel package"""')
        (k0_dir / "kernel" / "core.py").write_text(
            '''"""
Core module.
"""
from k0.bus import MessageBus
'''
        )
        (k0_dir / "bus.py").write_text(
            '''"""
Bus module.
"""'''
        )

        results = indexer.ingest_directory(k0_dir, prefix="k0")

        assert results["file_count"] >= 2
        assert results["module_count"] >= 2
        # __init__ creates k0.kernel not k0.kernel.
        assert any("kernel" in m for m in indexer.indexed_modules.keys())
        assert "k0.kernel.core" in indexer.indexed_modules

    def test_ingest_directory_extracts_imports(self, tmp_path: Path) -> None:
        """Test that directory indexing extracts imports."""
        indexer = ModuleIndexer()

        k0_dir = tmp_path / "k0"
        k0_dir.mkdir()
        (k0_dir / "bus.py").write_text('"""Bus"""')
        (k0_dir / "kernel.py").write_text(
            '''"""Kernel"""
from k0.bus import MessageBus
'''
        )

        results = indexer.ingest_directory(k0_dir, prefix="k0")

        assert results["extracted_imports"] > 0
        assert "k0.kernel" in indexer.import_graph
        assert "k0.bus" in indexer.import_graph["k0.kernel"]

    def test_ingest_directory_skips_pycache(self, tmp_path: Path) -> None:
        """Test that __pycache__ is skipped."""
        indexer = ModuleIndexer()

        k0_dir = tmp_path / "k0"
        k0_dir.mkdir()
        (k0_dir / "module.py").write_text('"""Module"""')

        # Create __pycache__
        cache_dir = k0_dir / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "module.cpython-39.pyc").write_text("fake")

        results = indexer.ingest_directory(k0_dir, prefix="k0")

        assert results["file_count"] == 1
        assert "module.cpython-39" not in indexer.indexed_modules

    def test_ingest_directory_nonexistent(self, tmp_path: Path) -> None:
        """Test indexing nonexistent directory."""
        indexer = ModuleIndexer()

        results = indexer.ingest_directory(tmp_path / "nonexistent", prefix="k0")

        assert len(results["errors"]) > 0
        assert "Directory not found" in results["errors"][0]

    def test_ingest_directory_performance(self, tmp_path: Path) -> None:
        """Test directory indexing performance (<2 seconds)."""
        indexer = ModuleIndexer()

        # Create test structure
        k0_dir = tmp_path / "k0"
        k0_dir.mkdir()

        # Create 20 modules
        for i in range(20):
            module_dir = k0_dir / f"module_{i}"
            module_dir.mkdir()
            (module_dir / "__init__.py").write_text(f'"""Module {i}"""')
            (module_dir / "core.py").write_text(
                f'''"""Core {i}"""
from k0.module_{(i-1) % 20} import something
'''
            )

        start = time.time()
        results = indexer.ingest_directory(k0_dir, prefix="k0")
        elapsed_ms = (time.time() - start) * 1000

        assert (
            results["performance_ok"] or elapsed_ms < 2000
        )  # <2 seconds for 20 modules


class TestModuleDependencies:
    """Test module dependency queries."""

    def test_get_module_dependencies_outgoing(self, tmp_path: Path) -> None:
        """Test getting outgoing dependencies."""
        indexer = ModuleIndexer()

        k0_dir = tmp_path / "k0"
        k0_dir.mkdir()
        (k0_dir / "bus.py").write_text('"""Bus"""')
        (k0_dir / "kernel.py").write_text(
            '''"""Kernel"""
from k0.bus import MessageBus
'''
        )

        indexer.ingest_directory(k0_dir, prefix="k0")

        deps = indexer.get_module_dependencies("k0.kernel")

        assert "k0.bus" in deps["imports"]
        assert deps["module_id"] == "k0.kernel"

    def test_get_module_dependencies_incoming(self, tmp_path: Path) -> None:
        """Test getting incoming dependencies."""
        indexer = ModuleIndexer()

        k0_dir = tmp_path / "k0"
        k0_dir.mkdir()
        (k0_dir / "bus.py").write_text('"""Bus"""')
        (k0_dir / "kernel.py").write_text(
            '''"""Kernel"""
from k0.bus import MessageBus
'''
        )

        indexer.ingest_directory(k0_dir, prefix="k0")

        deps = indexer.get_module_dependencies("k0.bus")

        assert "k0.kernel" in deps["imported_by"]

    def test_get_module_dependencies_nonexistent(self) -> None:
        """Test getting dependencies for nonexistent module."""
        indexer = ModuleIndexer()

        deps = indexer.get_module_dependencies("k0.nonexistent")

        assert deps == {}


class TestCircularDependencies:
    """Test circular dependency detection."""

    def test_find_no_circular_dependencies(self, tmp_path: Path) -> None:
        """Test that acyclic graph has no cycles."""
        indexer = ModuleIndexer()

        k0_dir = tmp_path / "k0"
        k0_dir.mkdir()
        (k0_dir / "a.py").write_text('"""A"""')
        (k0_dir / "b.py").write_text('"""B"""\nfrom k0.a import A')
        (k0_dir / "c.py").write_text('"""C"""\nfrom k0.b import B')

        indexer.ingest_directory(k0_dir, prefix="k0")

        cycles = indexer.find_circular_dependencies()

        assert len(cycles) == 0

    def test_find_simple_circular_dependency(self, tmp_path: Path) -> None:
        """Test detection of simple circular dependency."""
        indexer = ModuleIndexer()

        k0_dir = tmp_path / "k0"
        k0_dir.mkdir()
        (k0_dir / "a.py").write_text('"""A"""\nfrom k0.b import B')
        (k0_dir / "b.py").write_text('"""B"""\nfrom k0.a import A')

        indexer.ingest_directory(k0_dir, prefix="k0")

        cycles = indexer.find_circular_dependencies()

        assert len(cycles) > 0
        # Cycle should be A -> B -> A
        assert any("k0.a" in cycle and "k0.b" in cycle for cycle in cycles)

    def test_find_circular_dependencies_performance(self, tmp_path: Path) -> None:
        """Test circular dependency detection performance (<100ms)."""
        indexer = ModuleIndexer()

        # Create 50 modules with no cycles
        k0_dir = tmp_path / "k0"
        k0_dir.mkdir()

        for i in range(50):
            module_dir = k0_dir / f"module_{i}"
            module_dir.mkdir()
            (module_dir / "__init__.py").write_text(f'"""Module {i}"""')
            if i > 0:
                (module_dir / "core.py").write_text(
                    f'''"""Core {i}"""
from k0.module_{i-1} import something
'''
                )
            else:
                (module_dir / "core.py").write_text(f'"""Core {i}"""')

        indexer.ingest_directory(k0_dir, prefix="k0")

        start = time.time()
        cycles = indexer.find_circular_dependencies()
        elapsed_ms = (time.time() - start) * 1000

        assert len(cycles) == 0
        assert elapsed_ms < 100


class TestIntegration:
    """Integration tests for ModuleIndexer."""

    def test_index_real_k0_structure(self) -> None:
        """Test indexing real K0 structure."""
        import os

        k0_path = Path(os.environ.get("K0_PATH", "d:/familyos/k0"))

        if not k0_path.exists():
            pytest.skip("K0 path not available")

        indexer = ModuleIndexer()
        results = indexer.ingest_directory(k0_path, prefix="k0")

        assert results["module_count"] > 10
        assert results["file_count"] > 10
        assert results["performance_ok"]
        # At least some kernel modules should be indexed
        assert any("kernel" in m for m in indexer.indexed_modules.keys())

    def test_index_real_k1_structure(self) -> None:
        """Test indexing real K1 structure."""
        import os

        k1_path = Path(os.environ.get("K1_PATH", "d:/familyos/k1"))

        if not k1_path.exists():
            pytest.skip("K1 path not available")

        indexer = ModuleIndexer()
        results = indexer.ingest_directory(k1_path, prefix="k1")

        assert results["module_count"] > 5
        assert results["file_count"] > 5
        assert results["performance_ok"]
