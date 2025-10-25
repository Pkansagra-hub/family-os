"""
Knowledge Graph MCP Server v2

FastMCP-based server providing 15 semantic graph tools for AI-assisted development.
Enables context-aware queries about ADRs, modules, contracts, and their relationships.

Tools:
- Core: search, neighbors, add_node, add_edge
- Queries: find_by_type, graph_summary, paths
- Dependencies: get_module_deps, dependency_impact, find_circular_deps
- AI Context: implementation_chain, get_feature_context, ask
- Diagnostics: diagnostics, remove_node

Usage:
    python kg_v2_server.py
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

from kg_store import KGStore
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("Knowledge Graph v2")

# Global store instance
_store: Optional[KGStore] = None


def get_store() -> KGStore:
    """Get or create KG store instance"""
    global _store
    if _store is None:
        # Use repo-relative path, compatible with .vscode/mcp.json pattern
        repo_root = Path(__file__).resolve().parent.parent.parent
        db_path = repo_root / ".github" / "copilot-memories" / "kg.sqlite3"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _store = KGStore(str(db_path))
    return _store


# ============================================================================
# CORE TOOLS (4)
# ============================================================================


@mcp.tool(
    name="kg_v2_search",
    description="Full-text search across all nodes using FTS5 (BM25 ranking). Searches node IDs, labels, tags, and metadata.",
)
def search(query: str, limit: int = 20) -> List[Dict]:
    """Full-text search across all nodes using FTS5.

    Args:
        query: Search term (supports FTS5 syntax like "agent OR orchestrator")
        limit: Maximum results to return (default: 20)

    Returns:
        List of matching nodes with node_id, type, label, and snippet

    Example:
        search("agent scheduling") -> Returns ADRs and modules about agent scheduling
    """
    store = get_store()
    return store.search(query, limit=limit)


@mcp.tool(
    name="kg_v2_neighbors",
    description="Get adjacent nodes (outgoing/incoming/both) from a specific node with optional relation filtering.",
)
def neighbors(
    node_id: str, direction: str = "both", relation: Optional[str] = None
) -> List[Dict]:
    """Get adjacent nodes (neighbors) of a given node.

    Args:
        node_id: Source node identifier (e.g., "adr_0051", "module_k1.agent_scheduler")
        direction: "outgoing", "incoming", or "both" (default: "both")
        relation: Optional relation filter ("implements", "depends_on", "references", "tests")

    Returns:
        List of neighbor nodes with relationship metadata

    Example:
        neighbors("adr_0051", "outgoing", "implements") -> Modules implementing ADR-0051
    """
    store = get_store()
    return store.get_neighbors(node_id, direction=direction, relation=relation)


@mcp.tool(
    name="kg_v2_add_node",
    description="Add or update a knowledge graph node with semantic metadata (type, tags, file path, code snippet). Returns full node record.",
)
def add_node(
    node_id: str,
    node_type: str,
    label: str,
    file_path: Optional[str] = None,
    tags: Optional[List[str]] = None,
    content_preview: Optional[str] = None,
    code_snippet: Optional[str] = None,
) -> Dict:
    """Add a new node to the knowledge graph.

    Args:
        node_id: Unique identifier (e.g., "adr_0100", "module_custom.feature")
        node_type: Node type ("adr", "module", "contract", "file")
        label: Human-readable label
        file_path: Absolute path to source file
        tags: List of semantic tags (max 20)
        content_preview: First 500 chars of content
        code_snippet: Code sample (max 1000 chars)

    Returns:
        Created node with timestamps

    Example:
        add_node("adr_0100", "adr", "Custom Feature", tags=["feature", "custom"])
    """
    store = get_store()
    node_data = {"node_id": node_id, "node_type": node_type, "label": label}

    if file_path:
        node_data["file_path"] = file_path
    if tags:
        node_data["tags"] = tags
    if content_preview:
        node_data["content_preview"] = content_preview
    if code_snippet:
        node_data["code_snippet"] = code_snippet

    return store.add_node(node_data)


@mcp.tool(
    name="kg_v2_add_edge",
    description="Create directed edge between two nodes with relation type and optional evidence. Supports semantic relations.",
)
def add_edge(src: str, dst: str, relation: str, evidence: Optional[str] = None) -> Dict:
    """Add a directed edge between two nodes.

    Args:
        src: Source node ID
        dst: Destination node ID
        relation: Relation type ("implements", "depends_on", "references", "tests")
        evidence: Optional evidence/reason for relationship

    Returns:
        Created edge with metadata

    Example:
        add_edge("module_k1.feature", "adr_0100", "implements", "Implements new feature")
    """
    store = get_store()
    edge_data = {"src": src, "dst": dst, "relation": relation}

    if evidence:
        edge_data["evidence"] = evidence

    return store.add_edge(edge_data)


# ============================================================================
# QUERY TOOLS (3)
# ============================================================================


@mcp.tool(
    name="kg_v2_find_by_type",
    description="Find all nodes of a specific type (adr/module/contract/file). Supports filtering and pagination.",
)
def find_by_type(node_type: str, limit: int = 50) -> List[Dict]:
    """Find all nodes of a specific type.

    Args:
        node_type: Node type to filter ("adr", "module", "contract", "file")
        limit: Maximum results (default: 50)

    Returns:
        List of matching nodes

    Example:
        find_by_type("adr") -> All ADRs in the repository
    """
    store = get_store()
    return store.find_by_type(node_type, limit=limit)


@mcp.tool(
    name="kg_v2_graph_summary",
    description="Get high-level statistics about the knowledge graph (node/edge counts, type distribution, health metrics).",
)
def graph_summary() -> Dict:
    """Get high-level statistics about the knowledge graph.

    Returns:
        Dictionary with node counts, edge counts, types distribution

    Example:
        graph_summary() -> {"total_nodes": 631, "total_edges": 1859, ...}
    """
    store = get_store()
    return store.get_graph_summary()


@mcp.tool(
    name="kg_v2_paths",
    description="Find simple paths between two nodes (BFS traversal, up to max_hops). Returns list of node sequences.",
)
def paths(src: str, dst: str, max_hops: int = 6, max_paths: int = 5) -> List[List[str]]:
    """Find paths between two nodes using BFS.

    Args:
        src: Source node ID
        dst: Destination node ID
        max_hops: Maximum path length (default: 6)
        max_paths: Maximum number of paths to return (default: 5)

    Returns:
        List of paths (each path is a list of node IDs)

    Example:
        paths("adr_0051", "module_k1.agent_scheduler") -> [["adr_0051", "module_k1.agent_scheduler"]]
    """
    store = get_store()
    return store.find_paths(src, dst, max_hops=max_hops, max_paths=max_paths)


# ============================================================================
# DEPENDENCY ANALYSIS TOOLS (3)
# ============================================================================


@mcp.tool(
    name="kg_v2_get_module_deps",
    description="Get transitive dependencies of a module using BFS traversal. Returns full dependency closure up to specified depth.",
)
def get_module_deps(module_id: str, depth: Optional[int] = None) -> List[str]:
    """Get transitive dependencies of a module using BFS.

    Args:
        module_id: Module node ID (e.g., "module_k1.orchestrator")
        depth: Optional depth limit for dependency traversal

    Returns:
        List of dependent module IDs (transitive closure)

    Example:
        get_module_deps("module_k1.orchestrator") -> ["module_k1.agent_fabric", "module_k1.planner", ...]
    """
    store = get_store()
    return store.get_module_deps(module_id, depth=depth)


@mcp.tool(
    name="kg_v2_dependency_impact",
    description="Analyze impact of changing a module (what breaks if modified). Returns direct/transitive dependents with risk assessment.",
)
def dependency_impact(module_id: str) -> Dict:
    """Analyze impact of changing a module (what breaks if modified).

    Args:
        module_id: Module node ID

    Returns:
        Dictionary with direct dependents, transitive dependents, and impact score

    Example:
        dependency_impact("module_k0.storage") -> Shows all modules that depend on K0 storage
    """
    store = get_store()

    # Find all modules that depend on this one (reverse dependencies)
    all_modules = store.find_by_type("module", limit=1000)

    direct_dependents = []
    transitive_dependents = set()

    for module in all_modules:
        deps = store.get_module_deps(module["node_id"])
        if module_id in deps:
            # This module depends on the target module
            direct_dependents.append(module["node_id"])
            transitive_dependents.add(module["node_id"])

            # Add transitive dependents of this module
            trans_deps = store.get_module_deps(module["node_id"])
            transitive_dependents.update(trans_deps)

    return {
        "module": module_id,
        "direct_dependents": direct_dependents,
        "transitive_dependents": list(transitive_dependents),
        "impact_score": len(direct_dependents) + len(transitive_dependents),
    }


@mcp.tool(
    name="kg_v2_find_circular_deps",
    description="Detect circular dependencies in the module graph using DFS. Returns list of cycles with involved modules.",
)
def find_circular_deps() -> List[List[str]]:
    """Detect circular dependencies in the module graph using DFS.

    Returns:
        List of cycles (each cycle is a list of node IDs forming a loop)

    Example:
        find_circular_deps() -> [["module_a", "module_b", "module_c", "module_a"]]
    """
    store = get_store()
    return store.find_circular_deps()


# ============================================================================
# AI CONTEXT TOOLS (3)
# ============================================================================


@mcp.tool(
    name="kg_v2_implementation_chain",
    description="Get complete implementation context for an ADR (modules, dependencies, related decisions). Answers: What do I need to implement this ADR?",
)
def implementation_chain(adr_id: str) -> Dict:
    """Get complete implementation context for an ADR.

    Args:
        adr_id: ADR node ID (e.g., "adr_0051")

    Returns:
        Dictionary with ADR, implementing modules, dependencies, and related ADRs

    Example:
        implementation_chain("adr_0051") -> Full context for implementing agent scheduling
    """
    store = get_store()

    # Get ADR node
    adr_node = store.get_node(adr_id)
    if not adr_node:
        return {"error": f"ADR {adr_id} not found"}

    # Find implementing modules
    implementing_modules = store.get_neighbors(
        adr_id, direction="incoming", relation="implements"
    )

    # Get dependencies of implementing modules
    all_deps = set()
    for module in implementing_modules:
        deps = store.get_module_deps(module["node_id"])
        all_deps.update(deps)

    # Find related ADRs (referenced)
    related_adrs = store.get_neighbors(
        adr_id, direction="outgoing", relation="references"
    )

    return {
        "adr": adr_node,
        "implementing_modules": implementing_modules,
        "module_dependencies": list(all_deps),
        "related_adrs": related_adrs,
        "context_size": len(implementing_modules) + len(all_deps) + len(related_adrs),
    }


@mcp.tool(
    name="kg_v2_get_feature_context",
    description="Get complete context for implementing a feature (search across ADRs, modules, contracts). Answers: What exists related to this feature?",
)
def get_feature_context(feature_name: str) -> Dict:
    """Get complete context for implementing a feature (search-based).

    Args:
        feature_name: Feature name or description to search for

    Returns:
        Dictionary with relevant ADRs, modules, contracts, and relationships

    Example:
        get_feature_context("agent scheduling") -> All context related to agent scheduling
    """
    store = get_store()

    # Search for related nodes
    results = store.search(feature_name, limit=50)

    # Categorize by type
    adrs = [r for r in results if r["node_type"] == "adr"]
    modules = [r for r in results if r["node_type"] == "module"]
    contracts = [r for r in results if r["node_type"] == "contract"]

    # Get relationships between found nodes
    relationships = []
    for node in results[:10]:  # Top 10 nodes
        neighbors = store.get_neighbors(node["node_id"], direction="both")
        relationships.extend(neighbors)

    return {
        "feature": feature_name,
        "relevant_adrs": adrs,
        "relevant_modules": modules,
        "relevant_contracts": contracts,
        "relationships": relationships[:20],  # Top 20 relationships
        "total_context_size": len(results),
    }


@mcp.tool(
    name="kg_v2_ask",
    description="Natural language query router for semantic questions. Routes to appropriate specialized tool based on question intent (hybrid BM25 + FTS5).",
)
def ask(question: str) -> Dict:
    """Natural language query router for semantic questions.

    Args:
        question: Natural language question about the codebase

    Returns:
        Dictionary with answer type, relevant nodes, and suggestions

    Example:
        ask("What implements agent scheduling?") -> Searches and routes to implementation_chain
    """
    store = get_store()

    # Sanitize question for FTS5 (remove special characters)
    if question is None:
        return {"answer_type": "error", "message": "Question cannot be None"}

    sanitized_question = question.replace("?", "").replace("!", "").strip()
    if not sanitized_question:
        return {
            "answer_type": "error",
            "message": "Question is empty after sanitization",
        }

    # Simple keyword-based routing
    question_lower = question.lower()

    # Extract key terms for better search
    # Remove common question words to focus on domain terms
    search_terms = sanitized_question
    for word in ["what", "which", "where", "how", "does", "do", "is", "are", "the"]:
        search_terms = re.sub(
            r"\b" + word + r"\b", "", search_terms, flags=re.IGNORECASE
        )
    search_terms = search_terms.strip()

    # Escape special FTS5 characters
    search_terms = search_terms.replace(".", " ")  # Replace dots with spaces
    search_terms = re.sub(
        r"[^\w\s-]", "", search_terms
    )  # Remove special chars except hyphens

    # If search terms are empty, use original
    if not search_terms:
        search_terms = sanitized_question

    # Detect question type
    if "implement" in question_lower or "implements" in question_lower:
        # Implementation question - search modules AND ADRs
        results = store.search(search_terms, limit=10)

        adrs = [r for r in results if r.get("node_type") == "adr"]
        modules = [r for r in results if r.get("node_type") == "module"]

        if adrs and modules:
            # Check if modules implement ADRs
            implementing_modules = []
            for module in modules[:5]:
                implements_edges = store.get_neighbors(
                    module["node_id"], direction="outgoing", relation="implements"
                )
                if implements_edges:
                    implementing_modules.append(
                        {"module": module, "implements": implements_edges}
                    )

            return {
                "answer_type": "implementation",
                "suggestion": f"Found {len(implementing_modules)} modules implementing ADRs for '{search_terms}'",
                "relevant_adrs": adrs[:5],
                "implementing_modules": implementing_modules,
                "search_terms": search_terms,
            }
        elif adrs:
            return {
                "answer_type": "implementation",
                "suggestion": f"Use implementation_chain('{adrs[0]['node_id']}') for full context",
                "relevant_adrs": adrs,
                "search_terms": search_terms,
            }
        else:
            # Fall through to general search
            pass

    elif (
        "depend" in question_lower
        or "break" in question_lower
        or "impact" in question_lower
    ):
        # Dependency question
        results = store.search(search_terms, limit=10)
        modules = [r for r in results if r.get("node_type") == "module"]

        if modules:
            # Get dependency info for top module
            deps = store.get_module_deps(modules[0]["node_id"])
            return {
                "answer_type": "dependency",
                "suggestion": f"Use dependency_impact('{modules[0]['node_id']}') or get_module_deps('{modules[0]['node_id']}') for full analysis",
                "relevant_modules": modules[:5],
                "top_module_deps_count": len(deps),
                "search_terms": search_terms,
            }

    elif "circular" in question_lower or "cycle" in question_lower:
        cycles = store.find_circular_deps()
        return {
            "answer_type": "circular_dependency",
            "suggestion": f"Found {len(cycles)} circular dependencies",
            "cycles": cycles[:5],  # Show first 5 cycles
        }

    elif "adr" in question_lower or "decision" in question_lower:
        # ADR-specific query
        results = store.search(search_terms, limit=10)
        adrs = [r for r in results if r.get("node_type") == "adr"]

        return {
            "answer_type": "adr_search",
            "suggestion": f"Found {len(adrs)} ADRs matching '{search_terms}'",
            "relevant_adrs": adrs,
            "search_terms": search_terms,
        }

    # General search (fallback for all cases)
    results = store.search(search_terms, limit=15)

    # Categorize results
    categorized = {
        "adrs": [r for r in results if r.get("node_type") == "adr"],
        "modules": [r for r in results if r.get("node_type") == "module"],
        "contracts": [r for r in results if r.get("node_type") == "contract"],
        "files": [r for r in results if r.get("node_type") == "file"],
    }

    return {
        "answer_type": "search",
        "suggestion": f"General search for '{search_terms}' - refine with more specific tools",
        "results_by_type": categorized,
        "total_results": len(results),
        "search_terms": search_terms,
    }


# ============================================================================
# DIAGNOSTIC TOOLS (2)
# ============================================================================


@mcp.tool(
    name="kg_v2_diagnostics",
    description="Run architecture diagnostics to find issues and anti-patterns (orphaned nodes, missing ADRs, high coupling, circular deps).",
)
def diagnostics(diagnostic_type: str) -> Dict:
    """Run architecture diagnostics to find issues and anti-patterns.

    Args:
        diagnostic_type: Type of diagnostic ("orphaned_nodes", "missing_adrs", "high_coupling")

    Returns:
        Dictionary with diagnostic results and recommendations

    Example:
        diagnostics("orphaned_nodes") -> Nodes with no edges
    """
    store = get_store()

    if diagnostic_type == "orphaned_nodes":
        # Find nodes with no edges
        all_nodes = []
        for node_type in ["adr", "module", "contract", "file"]:
            all_nodes.extend(store.find_by_type(node_type, limit=1000))

        orphaned = []
        for node in all_nodes:
            neighbors = store.get_neighbors(node["node_id"], direction="both")
            if not neighbors:
                orphaned.append(node)

        return {
            "diagnostic": diagnostic_type,
            "orphaned_nodes": orphaned,
            "count": len(orphaned),
            "recommendation": "Add edges to connect isolated nodes or remove if obsolete",
        }

    elif diagnostic_type == "missing_adrs":
        # Find modules without implementing any ADR
        modules = store.find_by_type("module", limit=1000)

        missing = []
        init_files = []

        for module in modules:
            implements = store.get_neighbors(
                module["node_id"], direction="outgoing", relation="implements"
            )
            if not implements:
                # Separate __init__ files from regular modules
                if module["label"].endswith(".__init__") or module[
                    "file_path"
                ].endswith("__init__.py"):
                    init_files.append(module)
                else:
                    missing.append(module)

        return {
            "diagnostic": diagnostic_type,
            "modules_without_adr": missing,
            "init_files_without_adr": init_files,
            "count": len(missing),
            "init_count": len(init_files),
            "total_without_adr": len(missing) + len(init_files),
            "recommendation": f"Document architecture decisions with ADRs for {len(missing)} regular modules (excluding {len(init_files)} __init__ files which typically don't need ADRs)",
        }

    elif diagnostic_type == "high_coupling":
        # Find modules with many dependencies
        modules = store.find_by_type("module", limit=1000)

        high_coupling = []
        for module in modules:
            deps = store.get_module_deps(module["node_id"])
            if len(deps) > 10:  # Threshold: 10 dependencies
                high_coupling.append(
                    {
                        "module": module,
                        "dependency_count": len(deps),
                        "dependencies": deps,
                    }
                )

        # Sort by dependency count
        high_coupling.sort(key=lambda x: x["dependency_count"], reverse=True)

        return {
            "diagnostic": diagnostic_type,
            "high_coupling_modules": high_coupling[:20],  # Top 20
            "count": len(high_coupling),
            "recommendation": "Refactor modules with >10 dependencies to reduce coupling",
        }

    else:
        return {
            "error": f"Unknown diagnostic type: {diagnostic_type}",
            "available": ["orphaned_nodes", "missing_adrs", "high_coupling"],
        }


@mcp.tool(
    name="kg_v2_hybrid_search",
    description="Hybrid semantic + keyword search combining FTS5 (BM25) and vector embeddings. Alpha controls weighting: 0=pure vector, 1=pure FTS5, 0.5=balanced.",
)
def hybrid_search(
    query: str,
    query_embedding: Optional[List[float]] = None,
    alpha: float = 0.5,
    limit: int = 20,
) -> Dict:
    """Hybrid search combining keyword (FTS5) and semantic (vector) search.

    Args:
        query: Text query for keyword search
        query_embedding: Optional pre-computed embedding for semantic search (list of floats)
        alpha: Weight for FTS5 vs vector (0.0=pure vector, 0.5=balanced, 1.0=pure FTS5)
        limit: Maximum results to return

    Returns:
        Dictionary with ranked results and scoring breakdown

    Example:
        # Pure semantic search
        hybrid_search("agent coordination", query_embedding=[0.1, 0.2, ...], alpha=0.0)

        # Balanced hybrid search
        hybrid_search("agent scheduling performance", alpha=0.5)

        # Pure keyword search
        hybrid_search("fsync durability", alpha=1.0)
    """
    store = get_store()

    # Perform hybrid search
    results = store.hybrid_search(query, query_embedding, alpha, limit)

    # Categorize results by type
    adrs = [r for r in results if r["node_type"] == "adr"]
    modules = [r for r in results if r["node_type"] == "module"]
    contracts = [r for r in results if r["node_type"] == "contract"]

    return {
        "query": query,
        "alpha": alpha,
        "search_mode": (
            "pure_vector"
            if alpha == 0.0
            else ("pure_keyword" if alpha == 1.0 else "hybrid")
        ),
        "results": results,
        "categorized": {"adrs": adrs, "modules": modules, "contracts": contracts},
        "total_results": len(results),
        "scoring_explanation": f"hybrid_score = {alpha}*keyword_score + {1-alpha}*semantic_score",
    }


@mcp.tool(
    name="kg_v2_remove_node",
    description="Remove a node and all its incident edges from the knowledge graph. Returns success status and removed node info.",
)
def remove_node(node_id: str) -> Dict:
    """Remove a node and its edges from the knowledge graph.

    Args:
        node_id: Node identifier to remove

    Returns:
        Dictionary with success status and removed node info

    Example:
        remove_node("adr_0100") -> Removes custom ADR node
    """
    store = get_store()

    # Get node before removal
    node = store.get_node(node_id)
    if not node:
        return {"success": False, "error": f"Node {node_id} not found"}

    # Remove node (will cascade delete edges due to FK constraints)
    success = store.remove_node(node_id)

    return {
        "success": success,
        "removed_node": node,
        "message": f"Removed node {node_id} and all its edges",
    }


# ============================================================================
# SERVER LIFECYCLE
# ============================================================================


def main():
    """Run the MCP server"""
    print("Starting Knowledge Graph MCP Server v2...")
    print(f"Database: {Path.home() / '.github' / 'copilot-memories' / 'kg.sqlite3'}")
    print("Available tools: 16")
    print("Ready for MCP connections via stdio")

    mcp.run()


if __name__ == "__main__":
    main()
