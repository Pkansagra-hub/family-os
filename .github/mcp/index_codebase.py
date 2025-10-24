#!/usr/bin/env python3
"""
Comprehensive codebase indexing script.

This script indexes the entire codebase:
1. ADRs from docs/architecture/decisions/
2. Python modules from k0/ and k1/
3. Contracts from k0/contracts/ and k1/contracts/
4. Builds dependency graph
5. Creates semantic knowledge graph

Usage:
    cd .github/mcp
    python index_codebase.py [--reset]

Performance:
    Total indexing time: ~5-10 seconds
    ADRs: <500ms, Modules: <2s, Contracts: <1s
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Set KG_STORE_PATH before importing kg_mcp_server
workspace_root = Path(__file__).parent.parent.parent
copilot_memories = workspace_root / ".github" / "copilot-memories"
copilot_memories.mkdir(parents=True, exist_ok=True)
kg_store_path = copilot_memories / "kg_store.json"
os.environ["KG_STORE_PATH"] = str(kg_store_path)

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from kg_indexers import (
    ADRIndexer,
    ContractIndexer,
    DependencyGraphEngine,
    ModuleIndexer,
)
from kg_mcp_server import STORE, KnowledgeGraphStore


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_result(key: str, value) -> None:
    """Print a formatted result line."""
    if isinstance(value, dict):
        print(f"  {key}:")
        for k, v in value.items():
            print(f"    {k}: {v}")
    else:
        print(f"  {key}: {value}")


def index_adrs(store: KnowledgeGraphStore) -> dict:
    """Index all ADRs from docs/architecture/decisions/."""
    print_section("Indexing ADRs")

    # Use absolute path relative to workspace root
    adr_dir = (
        Path(__file__).parent.parent.parent / "docs" / "architecture" / "decisions"
    )
    if not adr_dir.exists():
        print(f"  [WARN] ADR directory not found: {adr_dir}")
        return {}

    start_time = time.time()
    indexer = ADRIndexer()

    print(f"  Scanning: {adr_dir.resolve()}")
    results = indexer.ingest_directory(adr_dir, store=store, diagram_id=None)

    elapsed_ms = (time.time() - start_time) * 1000

    print_result("ADR Count", results["adr_count"])
    print_result("Created Nodes", results["created_nodes"])
    print_result("Extracted Relations", results["extracted_relations"])
    print_result("Elapsed Time", f"{elapsed_ms:.1f}ms")

    if results["errors"]:
        print(f"  Errors: {len(results['errors'])}")
        for error in results["errors"][:3]:
            print(f"    - {error}")

    print(f"  Status: {'[OK]' if results['performance_ok'] else '[SLOW]'}")

    return results


def index_modules(store: KnowledgeGraphStore) -> dict:
    """Index all Python modules from k0/ and k1/."""
    print_section("Indexing Python Modules")

    all_results = {
        "k0": {},
        "k1": {},
        "total": {
            "module_count": 0,
            "file_count": 0,
            "extracted_imports": 0,
            "errors": [],
        },
    }

    root = Path(__file__).parent.parent.parent

    for prefix in ["k0", "k1"]:
        module_dir = root / prefix

        if not module_dir.exists():
            print(f"  [WARN] Module directory not found: {module_dir}")
            continue

        print(f"\n  Scanning: {module_dir.resolve()} (prefix: {prefix})")
        start_time = time.time()

        indexer = ModuleIndexer()
        results = indexer.ingest_directory(
            module_dir, store=store, diagram_id=None, prefix=prefix
        )

        elapsed_ms = (time.time() - start_time) * 1000

        all_results[prefix] = results
        all_results["total"]["module_count"] += results["module_count"]
        all_results["total"]["file_count"] += results["file_count"]
        all_results["total"]["extracted_imports"] += results["extracted_imports"]
        all_results["total"]["errors"].extend(results["errors"])

        print_result("  Module Count", results["module_count"])
        print_result("  File Count", results["file_count"])
        print_result("  Extracted Imports", results["extracted_imports"])
        print_result("  Created Nodes", results["created_nodes"])
        print_result("  Elapsed Time", f"{elapsed_ms:.1f}ms")
        print(f"    Status: {'[OK]' if results['performance_ok'] else '[SLOW]'}")

    # Print totals
    print(f"\n  Total Modules: {all_results['total']['module_count']}")
    print(f"  Total Files: {all_results['total']['file_count']}")
    print(f"  Total Imports: {all_results['total']['extracted_imports']}")

    return all_results


def index_contracts(store: KnowledgeGraphStore) -> dict:
    """Index all contracts from k0/contracts/ and k1/contracts/."""
    print_section("Indexing Contracts")

    all_results = {
        "k0": {},
        "k1": {},
        "total": {
            "contract_count": 0,
            "openapi_count": 0,
            "asyncapi_count": 0,
            "jsonschema_count": 0,
            "extracted_schemas": 0,
            "errors": [],
        },
    }

    root = Path(__file__).parent.parent.parent

    for prefix in ["k0", "k1"]:
        contract_dir = root / prefix / "contracts"

        if not contract_dir.exists():
            print(f"  [WARN] Contract directory not found: {contract_dir}")
            continue

        print(f"\n  Scanning: {contract_dir.resolve()} (prefix: {prefix})")
        start_time = time.time()

        indexer = ContractIndexer()
        results = indexer.ingest_directory(
            contract_dir, store=store, diagram_id=None, prefix=prefix
        )

        elapsed_ms = (time.time() - start_time) * 1000

        all_results[prefix] = results
        all_results["total"]["contract_count"] += results["contract_count"]
        all_results["total"]["openapi_count"] += results["openapi_count"]
        all_results["total"]["asyncapi_count"] += results["asyncapi_count"]
        all_results["total"]["jsonschema_count"] += results["jsonschema_count"]
        all_results["total"]["extracted_schemas"] += results["extracted_schemas"]
        all_results["total"]["errors"].extend(results["errors"])

        print_result("  Contract Count", results["contract_count"])
        print_result("  OpenAPI Specs", results["openapi_count"])
        print_result("  AsyncAPI Specs", results["asyncapi_count"])
        print_result("  JSON Schemas", results["jsonschema_count"])
        print_result("  FlatBuffers", results.get("flatbuffers_count", 0))
        print_result("  Extracted Schemas", results["extracted_schemas"])
        print_result("  Created Nodes", results["created_nodes"])
        print_result("  Elapsed Time", f"{elapsed_ms:.1f}ms")
        # DEBUG
        if "_debug_total_files" in results:
            print(
                f"    [DEBUG] Total files: {results.get('_debug_total_files', 0)}, Valid ext: {results.get('_debug_valid_ext', 0)}, Detected: {results.get('_debug_files_detected', 0)}"
            )
        print(f"    Status: {'[OK]' if results['performance_ok'] else '[SLOW]'}")

    # Print totals
    print(f"\n  Total Contracts: {all_results['total']['contract_count']}")
    print(f"    OpenAPI: {all_results['total']['openapi_count']}")
    print(f"    AsyncAPI: {all_results['total']['asyncapi_count']}")
    print(f"    JSON Schema: {all_results['total']['jsonschema_count']}")
    print(f"  Total Schemas: {all_results['total']['extracted_schemas']}")

    return all_results


def build_dependency_graph(module_results: dict) -> DependencyGraphEngine:
    """Build the dependency graph engine."""
    print_section("Building Dependency Graph")

    start_time = time.time()

    # Create indexers to get the import graphs
    k0_indexer = ModuleIndexer()
    k1_indexer = ModuleIndexer()

    # Re-index modules to populate the import graphs
    k0_dir = Path("k0")
    k1_dir = Path("k1")

    if k0_dir.exists():
        print("  Scanning K0 for dependencies...")
        k0_indexer.ingest_directory(k0_dir, prefix="k0")

    if k1_dir.exists():
        print("  Scanning K1 for dependencies...")
        k1_indexer.ingest_directory(k1_dir, prefix="k1")

    # Create combined engine
    engine = DependencyGraphEngine()

    # Merge graphs (simplified - in real implementation would merge properly)
    combined_graph = {}
    for module_id, metadata in k0_indexer.indexed_modules.items():
        combined_graph[module_id] = k0_indexer.import_graph.get(module_id, set())
    for module_id, metadata in k1_indexer.indexed_modules.items():
        combined_graph[module_id] = k1_indexer.import_graph.get(module_id, set())

    # Set the indexer (use k0 as primary, could be improved)
    engine.set_module_indexer(k0_indexer)

    elapsed_ms = (time.time() - start_time) * 1000

    # Detect circular dependencies
    cycles = engine.find_circular_dependencies()

    print_result("Modules Indexed", len(combined_graph))
    print_result("Circular Dependencies Found", len(cycles))
    print_result("Elapsed Time", f"{elapsed_ms:.1f}ms")

    if cycles:
        print("\n  [WARN] Circular dependencies detected:")
        for i, cycle in enumerate(cycles[:5]):  # Show first 5
            modules_str = " -> ".join(cycle.modules[:4])
            if len(cycle.modules) > 4:
                modules_str += f" -> ... ({len(cycle.modules)} total)"
            print(f"    {i+1}. {modules_str}")
        if len(cycles) > 5:
            print(f"    ... and {len(cycles) - 5} more")

    return engine


def query_sample_results(
    store: KnowledgeGraphStore, engine: DependencyGraphEngine
) -> None:
    """Run sample queries to verify indexing."""
    print_section("Sample Queries")

    # Query 1: Find all ADRs
    print("\n  Query 1: Find all ADRs by type")
    with store._lock:
        diagram_ids = list(store._data.get("diagrams", {}).keys())

    total_adrs = 0
    total_modules = 0
    total_contracts = 0

    with store._lock:
        for diagram_id in diagram_ids:
            record = store._data["diagrams"][diagram_id]
            for node in record.get("nodes", {}).values():
                if node.get("node_type") == "adr":
                    total_adrs += 1
                elif node.get("node_type") == "module":
                    total_modules += 1
                elif node.get("node_type") == "contract":
                    total_contracts += 1

    print(f"    Total ADRs: {total_adrs}")
    print(f"    Total Modules: {total_modules}")
    print(f"    Total Contracts: {total_contracts}")

    # Query 2: Sample dependency
    print("\n  Query 2: Sample dependency queries")
    try:
        # Try to find a common module
        k0_kernel_deps = engine.get_direct_dependencies("k0.kernel")
        if k0_kernel_deps:
            print(f"    k0.kernel imports: {len(k0_kernel_deps)} modules")
            print(f"      Sample: {', '.join(list(k0_kernel_deps)[:3])}")
    except Exception as e:
        print(f"    [WARN] Could not query k0.kernel: {e}")

    # Query 3: Check graph size
    print("\n  Query 3: Knowledge graph stats")
    with store._lock:
        total_edges = 0
        total_nodes = 0
        for diagram_id in diagram_ids:
            record = store._data["diagrams"][diagram_id]
            total_nodes += len(record.get("nodes", {}))
            total_edges += len(record.get("edges", []))

    print(f"    Total Nodes: {total_nodes}")
    print(f"    Total Edges: {total_edges}")


def main() -> int:
    """Main indexing orchestration."""
    parser = argparse.ArgumentParser(
        description="Index the entire codebase into the Knowledge Graph"
    )
    parser.add_argument(
        "--reset", action="store_true", help="Reset the KG store before indexing"
    )

    args = parser.parse_args()

    # Optional: reset store
    if args.reset:
        print("Resetting KG store...")
        STORE.db_path.unlink(missing_ok=True)
        STORE._data = {
            "version": 2,
            "created_at": time.time(),
            "updated_at": time.time(),
            "nodes": {},
            "edges": [],
            "relations": {},
        }
        STORE._alias_index = {}
        STORE._path_index = {}

    print_section("FamilyOS Codebase Indexing")
    print(f"  Store path: {STORE.db_path}")

    total_start = time.time()

    # Run all indexers (no diagram_id needed anymore)
    adr_results = index_adrs(STORE)
    module_results = index_modules(STORE)
    contract_results = index_contracts(STORE)
    engine = build_dependency_graph(module_results)
    query_sample_results(STORE, engine)

    # Summary
    total_elapsed = time.time() - total_start

    print_section("Indexing Complete")
    print(f"  Total time: {total_elapsed:.2f}s")
    print(f"  ADRs: {adr_results.get('adr_count', 0)}")
    print(f"  Modules: {module_results.get('total', {}).get('module_count', 0)}")
    print(f"  Contracts: {contract_results.get('total', {}).get('contract_count', 0)}")

    print("\n  Next steps:")
    print("  1. Use MCP tools to query the indexed knowledge graph")
    print("  2. Run: kg_implementation_chain('adr_0051')")
    print("  3. Run: kg_get_module_deps('k0.kernel')")
    print("  4. Run: kg_find_circular_deps()")
    print("  5. Run: kg_trace_import_chain('k1.l2_orchestration', 'k0.kernel')")

    return 0


if __name__ == "__main__":
    sys.exit(main())
