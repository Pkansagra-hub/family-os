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


def _light_node(node: Dict, include_file: bool = False, max_preview: int = 200) -> Dict:
    """Return a lightweight representation of a node to avoid sending large blobs to agents.

    Keeps only essential fields and truncates long previews/snippets.
    """
    if not node:
        return {}

    lite = {
        "node_id": node.get("node_id"),
        "label": node.get("label"),
        "node_type": node.get("node_type"),
    }

    # Tags: keep only up to 8 tags
    tags = node.get("tags") or []
    lite["tags"] = tags[:8]

    # Truncated preview
    preview = node.get("content_preview") or ""
    if preview and len(preview) > max_preview:
        lite["content_preview"] = preview[: max_preview - 3] + "..."
    else:
        lite["content_preview"] = preview

    # Include any scores if present
    for score_key in ("hybrid_score", "fts_score", "vector_score", "similarity_score"):
        if score_key in node:
            lite[score_key] = node[score_key]

    # Optionally include file path (can be large) and small code snippet
    if include_file:
        lite["file_path"] = node.get("file_path")

    snippet = node.get("code_snippet") or ""
    if snippet:
        lite["code_snippet_preview"] = (
            snippet[:497] + "..." if len(snippet) > 500 else snippet
        )

    return lite


# ============================================================================
# SECURITY & PERMISSIONS
# ============================================================================

# Allowlist for mutation operations
# In production, this could come from env vars or config files
MUTATION_ALLOWLIST = {
    "copilot",  # GitHub Copilot
    "admin",
    "internal",
}


def _check_mutation_permission(operation: str) -> Dict:
    """Check if mutation operation is allowed.

    Args:
        operation: Type of mutation ("add_node", "add_edge", "remove_node")

    Returns:
        {"allowed": bool, "message": str}
    """
    # For now, allow mutations with a warning comment
    # In production: validate caller identity, check allowlist, enforce quotas
    return {
        "allowed": True,
        "message": f"Mutation operation '{operation}' permitted (ensure contract compliance)",
    }


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
    # Security check
    perm_result = _check_mutation_permission("add_node")
    if not perm_result.get("allowed"):
        return {"error": perm_result.get("message")}

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
    # Security check
    perm_result = _check_mutation_permission("add_edge")
    if not perm_result.get("allowed"):
        return {"error": perm_result.get("message")}

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

    # Find implementing modules (trim payloads)
    implementing_modules_raw = store.get_neighbors(
        adr_id, direction="incoming", relation="implements"
    )
    implementing_modules = [_light_node(m) for m in implementing_modules_raw]

    # Get dependencies of implementing modules
    all_deps = set()
    for module in implementing_modules_raw:
        deps = store.get_module_deps(module["node_id"])
        all_deps.update(deps)

    # Find related ADRs (referenced) and trim
    related_adrs_raw = store.get_neighbors(
        adr_id, direction="outgoing", relation="references"
    )
    related_adrs = [_light_node(r) for r in related_adrs_raw]

    return {
        "adr": _light_node(adr_node),
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
        for n in neighbors:
            relationships.append(
                {
                    "node": _light_node(n),
                    "relation": n.get("relation"),
                    "evidence": n.get("evidence"),
                }
            )

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

    # ============================================================================
    # PHASE 3: K1 ARCHITECTURE LAYER PATTERN MATCHING
    # ============================================================================

    # Try K1 layer patterns first (highest specificity) with hybrid scoring
    best_pattern_match = None
    best_pattern_score = 0.0

    for pattern_type, pattern_def in K1_LAYER_PATTERNS.items():
        for pattern in pattern_def["patterns"]:
            if re.search(pattern, question_lower, re.IGNORECASE):
                # Extract search terms from pattern-matched question
                search_terms = sanitized_question
                for word in [
                    "what",
                    "which",
                    "where",
                    "how",
                    "does",
                    "do",
                    "is",
                    "are",
                    "the",
                ]:
                    search_terms = re.sub(
                        r"\b" + word + r"\b", "", search_terms, flags=re.IGNORECASE
                    )
                search_terms = search_terms.strip()

                # Escape special FTS5 characters
                search_terms = search_terms.replace(".", " ")
                search_terms = re.sub(r"[^\w\s-]", "", search_terms)

                # If search terms are empty, use pattern default
                if not search_terms:
                    search_terms = (
                        pattern_def["search_tags"][0]
                        if pattern_def.get("search_tags")
                        else pattern_type
                    )

                # Search with layer-relevant tags
                results = store.search(search_terms, limit=15)

                # Compute hybrid score: FTS5 + tag match bonus
                scored_results = []
                for r in results:
                    fts_score = r.get("score", 0) or 0  # FTS5 score (lower is better)

                    # Tag matching bonus (0 to 0.3)
                    tag_bonus = 0
                    if "search_tags" in pattern_def:
                        matching_tags = sum(
                            1
                            for tag in pattern_def["search_tags"]
                            if tag in (r.get("tags") or [])
                        )
                        tag_bonus = min(0.3, matching_tags * 0.15)

                    # Hybrid score: normalize FTS5 (lower=better, so negate) + tag bonus
                    hybrid_score = (1.0 / (1.0 + fts_score)) + tag_bonus
                    scored_results.append((r, hybrid_score))

                # Sort by hybrid score (highest first)
                scored_results.sort(key=lambda x: x[1], reverse=True)
                relevant_results = [r for r, _ in scored_results]

                # Calculate pattern confidence (average of top results' scores)
                if relevant_results:
                    top_scores = [score for _, score in scored_results[:5]]
                    pattern_confidence = sum(top_scores) / len(top_scores)

                    # Keep best pattern if confidence is high enough
                    if pattern_confidence > best_pattern_score:
                        best_pattern_score = pattern_confidence
                        best_pattern_match = (
                            pattern_type,
                            pattern_def,
                            pattern,
                            search_terms,
                            relevant_results,
                        )

    # If we found a high-confidence pattern match, return it
    if best_pattern_match and best_pattern_score > 0.3:  # Threshold: 0.3
        pattern_type, pattern_def, pattern, search_terms, relevant_results = (
            best_pattern_match
        )

        # Filter by pattern-matched tags if available
        if "search_tags" in pattern_def:
            tagged_results = [
                r
                for r in relevant_results
                if any(
                    tag in (r.get("tags") or []) for tag in pattern_def["search_tags"]
                )
            ]
            relevant_results = tagged_results if tagged_results else relevant_results

        # Categorize results
        categorized = {
            "adrs": [r for r in relevant_results if r.get("node_type") == "adr"],
            "modules": [r for r in relevant_results if r.get("node_type") == "module"],
            "contracts": [
                r for r in relevant_results if r.get("node_type") == "contract"
            ],
        }

        lite_results = [_light_node(r) for r in relevant_results]

        return {
            "answer_type": f"k1_layer_{pattern_type}",
            "pattern_matched": pattern_type,
            "pattern": pattern,
            "pattern_confidence": round(best_pattern_score, 3),
            "description": pattern_def.get(
                "response_template", "K1 layer-aware search"
            ),
            "suggestion": f"{pattern_def['response_template']} (Pattern: {pattern_type}, confidence: {best_pattern_score:.1%})",
            "results": lite_results,
            "results_by_type": categorized,
            "total_results": len(lite_results),
            "search_terms": search_terms,
        }

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
                    # Trim module and edge payloads
                    module_lite = _light_node(module)
                    implements_lite = []
                    for edge in implements_edges:
                        neighbor_lite = _light_node(edge)
                        implements_lite.append(
                            {
                                "node": neighbor_lite,
                                "relation": edge.get("relation"),
                                "evidence": edge.get("evidence"),
                            }
                        )

                    implementing_modules.append(
                        {"module": module_lite, "implements": implements_lite}
                    )

            return {
                "answer_type": "implementation",
                "suggestion": f"Found {len(implementing_modules)} modules implementing ADRs for '{search_terms}'",
                "relevant_adrs": adrs[:5],
                "implementing_modules": implementing_modules,
                "search_terms": search_terms,
                "total_results": len(adrs) + len(modules),
            }
        elif adrs:
            return {
                "answer_type": "implementation",
                "suggestion": f"Use implementation_chain('{adrs[0]['node_id']}') for full context",
                "relevant_adrs": adrs,
                "search_terms": search_terms,
                "total_results": len(adrs),
            }
        # ✅ FIX: Don't silently fall through - return with actual results found
        elif results:
            categorized = {
                "adrs": adrs,
                "modules": modules,
                "contracts": [r for r in results if r.get("node_type") == "contract"],
            }
            return {
                "answer_type": "implementation",
                "suggestion": f"Found {len(results)} results for '{search_terms}' (no direct module-ADR implementations)",
                "results_by_type": categorized,
                "search_terms": search_terms,
                "total_results": len(results),
            }

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
                "total_results": len(modules),
            }
        # ✅ FIX: Return results even if no modules found
        elif results:
            return {
                "answer_type": "dependency",
                "suggestion": f"Found {len(results)} results for '{search_terms}' (no modules matching dependency query)",
                "results": [_light_node(r) for r in results],
                "search_terms": search_terms,
                "total_results": len(results),
            }

    elif "circular" in question_lower or "cycle" in question_lower:
        cycles = store.find_circular_deps()
        return {
            "answer_type": "circular_dependency",
            "suggestion": f"Found {len(cycles)} circular dependencies",
            "cycles": cycles[:5],  # Show first 5 cycles
            "total_results": len(cycles),
        }

    elif "adr" in question_lower or "decision" in question_lower:
        # ADR-specific query
        results = store.search(search_terms, limit=10)
        adrs = [r for r in results if r.get("node_type") == "adr"]

        return {
            "answer_type": "adr_search",
            "suggestion": f"Found {len(adrs)} ADRs matching '{search_terms}'",
            "relevant_adrs": [_light_node(r) for r in adrs],
            "all_results": [
                _light_node(r) for r in results
            ],  # ✅ FIX: Include lightweight results, not full nodes
            "search_terms": search_terms,
            "total_results": len(results),
        }

    # General search (fallback for all cases)
    results = store.search(search_terms, limit=15)

    # Convert to lightweight results to avoid sending large text blobs
    lite_results = [_light_node(r) for r in results]

    categorized = {
        "adrs": [r for r in lite_results if r.get("node_type") == "adr"],
        "modules": [r for r in lite_results if r.get("node_type") == "module"],
        "contracts": [r for r in lite_results if r.get("node_type") == "contract"],
        "files": [r for r in lite_results if r.get("node_type") == "file"],
    }

    return {
        "answer_type": "search",
        "suggestion": (
            f"General search for '{search_terms}' - refine with more specific tools"
            if lite_results
            else f"No results found for '{search_terms}'"
        ),
        "results": lite_results,
        "results_by_type": categorized,
        "total_results": len(lite_results),
        "search_terms": search_terms,
    }


# ============================================================================
# CONTRACT SEARCH TOOLS (NEW - PHASE 1)
# ============================================================================


@mcp.tool(
    name="kg_v2_contract_search",
    description="Search contracts by type and layer. Find API definitions, schemas, error models. Supports filtering by contract type (openapi, jsonschema, flatbuffers) and layer (k0_only, k1_only, bridge).",
)
def contract_search(
    query: str = "",
    contract_type: Optional[str] = None,
    layer: Optional[str] = None,
    limit: int = 20,
) -> Dict:
    """Search contracts with type and layer filtering.

    Args:
        query: Search query (contract name, endpoint, schema field). Empty string returns all contracts.
        contract_type: Filter by type - "openapi", "jsonschema", "flatbuffers", or None (all types)
        layer: Filter by layer - "k0_only", "k1_only", "bridge", or None (all layers)
        limit: Maximum results (default 20, max 100)

    Returns:
        Dictionary with categorized lightweight contract results

    Examples:
        # Find all OpenAPI specs
        contract_search("", contract_type="openapi")

        # Find envelope schema in K0
        contract_search("envelope", contract_type="jsonschema", layer="k0_only")

        # Find K1 agent schemas
        contract_search("agent", contract_type="jsonschema", layer="k1_only")

        # Find all contracts related to orchestration
        contract_search("orchestration", layer="k1_only")
    """
    store = get_store()

    # Enforce limit bounds
    limit = min(max(limit, 1), 100)

    # Use hybrid search if query provided, otherwise just filter by type/layer
    if query:
        results = store.search_contracts_hybrid(
            query=query,
            contract_type=contract_type,
            layer=layer,
            alpha=0.5,  # Balanced FTS5 + vector search
            limit=limit,
        )
    else:
        results = store.query_contracts_by_type(
            contract_type=contract_type,
            layer=layer,
            query_text=None,
            limit=limit,
        )

    # Convert to lightweight results
    lite_results = [_light_node(r, include_file=False) for r in results]

    # Remove code snippets from contracts to reduce payload
    for result in lite_results:
        result.pop("code_snippet_preview", None)

    # Categorize by contract type
    categorized = {
        "openapi": [r for r in lite_results if "openapi" in r.get("tags", [])],
        "jsonschema": [
            r
            for r in lite_results
            if "jsonschema" in r.get("tags", []) or "schema" in r.get("tags", [])
        ],
        "flatbuffers": [r for r in lite_results if "flatbuffers" in r.get("tags", [])],
        "other": [],
    }

    # Collect uncategorized contracts
    categorized_ids = set()
    for cat in ["openapi", "jsonschema", "flatbuffers"]:
        categorized_ids.update(r["node_id"] for r in categorized[cat])

    for result in lite_results:
        if result["node_id"] not in categorized_ids:
            categorized["other"].append(result)

    # Build response
    filter_desc_parts = []
    if contract_type:
        filter_desc_parts.append(f"type={contract_type}")
    if layer:
        filter_desc_parts.append(f"layer={layer}")
    filter_desc = f" ({', '.join(filter_desc_parts)})" if filter_desc_parts else ""

    return {
        "query": query,
        "filters": {"type": contract_type, "layer": layer},
        "results": lite_results,
        "results_by_type": categorized,
        "total_results": len(lite_results),
        "suggestion": f"Found {len(lite_results)} contract(s){filter_desc}. Use contract_type='openapi'|'jsonschema'|'flatbuffers' to filter by type. Use layer='k0_only'|'k1_only'|'bridge' to filter by layer.",
    }


@mcp.tool(
    name="kg_v2_diagnostics",
    description="Run architecture diagnostics to find issues and anti-patterns (orphaned nodes, missing ADRs, high coupling, circular deps).",
)
def diagnostics(diagnostic_type: str) -> Dict:
    """Run architecture diagnostics on the knowledge graph.

    Validates graph integrity, identifies issues, and reports anti-patterns.

    Args:
        diagnostic_type: Type of diagnostic to run:
            - "graph_summary" - Basic statistics (nodes, edges, types)
            - "orphaned_nodes" - Nodes with no relationships
            - "circular_deps" - Circular dependencies in module graph
            - "high_coupling" - Modules with excessive dependencies
            - "missing_contracts" - Modules without supporting contracts
            - "fts_integrity" - Full-text search table health check
            - "all" - Run all diagnostics

    Returns:
        Diagnostic results with statistics and findings

    Examples:
        # Check for orphaned nodes
        diagnostics("orphaned_nodes")

        # Find circular dependencies
        diagnostics("circular_deps")

        # Run all diagnostics
        diagnostics("all")
    """
    store = get_store()
    results = {}

    # Graph summary (always include)
    summary = store.get_graph_summary()
    results["graph_summary"] = summary

    if diagnostic_type in ("orphaned_nodes", "all"):
        # Find nodes with no edges
        orphaned = []
        all_nodes = (
            store.find_by_type("adr", limit=1000)
            + store.find_by_type("module", limit=1000)
            + store.find_by_type("contract", limit=1000)
        )

        for node in all_nodes:
            neighbors = store.get_neighbors(node["node_id"])
            if not neighbors["incoming"] and not neighbors["outgoing"]:
                orphaned.append(node["node_id"])

        results["orphaned_nodes"] = {
            "count": len(orphaned),
            "nodes": orphaned[:20],  # Limit to 20 for readability
            "message": f"Found {len(orphaned)} orphaned nodes (no incoming/outgoing edges)",
        }

    if diagnostic_type in ("circular_deps", "all"):
        # Find circular dependencies using DFS
        circular_deps = find_circular_deps()
        results["circular_deps"] = {
            "count": len(circular_deps),
            "cycles": circular_deps[:5],  # Limit to 5 for readability
            "message": f"Found {len(circular_deps)} circular dependency paths",
        }

    if diagnostic_type in ("high_coupling", "all"):
        # Find modules with high dependency count
        all_modules = store.find_by_type("module", limit=1000)
        coupling_analysis = []

        for module in all_modules:
            deps = store.get_module_deps(module["node_id"], depth=1)
            dep_count = len(deps.get("dependencies", []))
            if dep_count > 5:  # Threshold: more than 5 direct deps
                coupling_analysis.append(
                    {"module": module["node_id"], "dependency_count": dep_count}
                )

        coupling_analysis.sort(key=lambda x: x["dependency_count"], reverse=True)
        results["high_coupling"] = {
            "count": len(coupling_analysis),
            "modules": coupling_analysis[:10],
            "message": f"Found {len(coupling_analysis)} modules with >5 direct dependencies",
        }

    if diagnostic_type in ("missing_contracts", "all"):
        # Find modules without supporting contracts
        all_modules = store.find_by_type("module", limit=1000)
        missing = []

        for module in all_modules:
            neighbors = store.get_neighbors(module["node_id"])
            contracts = [
                n
                for n in neighbors["outgoing"]
                if "contract" in n.get("node_id", "").lower()
            ]
            if not contracts:
                missing.append(module["node_id"])

        results["missing_contracts"] = {
            "count": len(missing),
            "modules": missing[:20],
            "message": f"Found {len(missing)} modules without supporting contracts",
        }

    if diagnostic_type in ("fts_integrity", "all"):
        # Check FTS5 table health
        try:
            # Try a simple FTS query to verify table exists and is functional
            test_results = store.search("test", limit=1)
            results["fts_integrity"] = {
                "status": "healthy",
                "message": "FTS5 tables functional",
                "test_query_results": len(test_results),
            }
        except Exception as e:
            results["fts_integrity"] = {
                "status": "error",
                "message": f"FTS5 integrity check failed: {str(e)}",
            }

    if diagnostic_type == "all":
        from datetime import datetime, timezone

        results["diagnostic_run"] = "complete"
        results["timestamp"] = str(datetime.now(timezone.utc))

    if diagnostic_type not in (
        "orphaned_nodes",
        "circular_deps",
        "high_coupling",
        "missing_contracts",
        "fts_integrity",
        "graph_summary",
        "all",
    ):
        results["error"] = f"Unknown diagnostic type: {diagnostic_type}"
        results["available_types"] = [
            "graph_summary",
            "orphaned_nodes",
            "circular_deps",
            "high_coupling",
            "missing_contracts",
            "fts_integrity",
            "all",
        ]

    return results


@mcp.tool(
    name="kg_v2_tools_help",
    description="Get guidance on which tools to use for different tasks. Returns tool recommendations, examples, and latency info.",
)
def tools_help(topic: Optional[str] = None) -> Dict:
    """Get guidance on which tools to use for specific tasks.

    Use this tool to discover the right MCP tools for your needs. Get recommendations,
    example queries, and performance expectations for different use cases.

    Args:
        topic: Optional topic filter. Available topics:
            - "search" - Full-text and semantic search
            - "contracts" - API definitions, schemas, error models
            - "adrs" - Architecture Decision Records
            - "modules" - Module architecture and structure
            - "dependencies" - Dependency analysis and impact
            - "architecture" - High-level architecture overview
            - "paths" - Path finding between nodes
            - "graph_operations" - Add/modify/remove nodes and edges
            - "ai_reasoning" - AI-powered reasoning tools
            If None, returns all available topics

    Returns:
        Dictionary with tool recommendations, examples, and guidance for the specified topic(s)

    Examples:
        # Get all topics
        tools_help()

        # Get contract-related tools
        tools_help("contracts")

        # Get dependency analysis tools
        tools_help("dependencies")
    """
    # If no topic specified, return all topics and categories
    if topic is None:
        return {
            "available_topics": list(TOOLS_METADATA.keys()),
            "topic_count": len(TOOLS_METADATA),
            "categories": list(TOOL_CATEGORIES.keys()),
            "suggestion": "Use tools_help(topic) to get detailed guidance for a specific topic. Example: tools_help('contracts')",
        }

    # Validate topic
    if topic not in TOOLS_METADATA:
        return {
            "error": f"Unknown topic: '{topic}'",
            "available_topics": list(TOOLS_METADATA.keys()),
            "suggestion": f"Available topics: {', '.join(TOOLS_METADATA.keys())}",
        }

    # Return metadata for specific topic
    metadata = TOOLS_METADATA[topic]

    return {
        "topic": topic,
        "description": metadata["description"],
        "best_for": metadata["best_for"],
        "tools": metadata["tools"],
        "examples": metadata["examples"],
        "recommendation": f"For {topic} tasks, recommend starting with: {metadata['tools'][0]['name']} (latency: {metadata['tools'][0]['latency']})",
    }


# ============================================================================
# DIAGNOSTIC TOOLS (2)
# ============================================================================


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
    # Convert results to lightweight representations to avoid overwhelming agents
    lite_results = [_light_node(r) for r in results]

    # Categorize lite results by type
    adrs = [r for r in lite_results if r.get("node_type") == "adr"]
    modules = [r for r in lite_results if r.get("node_type") == "module"]
    contracts = [r for r in lite_results if r.get("node_type") == "contract"]

    return {
        "query": query,
        "alpha": alpha,
        "search_mode": (
            "pure_vector"
            if alpha == 0.0
            else ("pure_keyword" if alpha == 1.0 else "hybrid")
        ),
        # Provide lightweight results + counts
        "results": lite_results,
        "categorized": {"adrs": adrs, "modules": modules, "contracts": contracts},
        "total_results": len(lite_results),
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
    # Security check
    perm_result = _check_mutation_permission("remove_node")
    if not perm_result.get("allowed"):
        return {"error": perm_result.get("message")}

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
# TOOL METADATA (For kg_v2_tools_help guidance tool - Phase 2)
# ============================================================================

TOOLS_METADATA = {
    "search": {
        "description": "Full-text and semantic search across all nodes (ADRs, modules, contracts)",
        "best_for": [
            "Finding ADRs by title or content",
            "Searching module names",
            "Keyword queries",
            "Finding related architecture decisions",
        ],
        "tools": [
            {"name": "kg_v2_search", "latency": "<2ms", "type": "keyword"},
            {"name": "kg_v2_hybrid_search", "latency": "<50ms", "type": "hybrid"},
        ],
        "examples": [
            {
                "query": "kg_v2_search('thermal management')",
                "use_case": "Find ADRs about thermal management",
            },
            {
                "query": "kg_v2_hybrid_search('agent lifecycle', alpha=0.5)",
                "use_case": "Semantic + keyword search for agent lifecycle",
            },
            {
                "query": "kg_v2_search('orchestrator coordination')",
                "use_case": "Find all mentions of orchestrator coordination",
            },
        ],
    },
    "contracts": {
        "description": "Find and filter API definitions, schemas, and error models",
        "best_for": [
            "API endpoint lookup",
            "Schema validation and examples",
            "Error reference discovery",
            "Contract type filtering",
        ],
        "tools": [
            {
                "name": "kg_v2_contract_search",
                "latency": "<100ms",
                "type": "specialized",
            },
            {"name": "kg_v2_search", "latency": "<2ms", "type": "keyword"},
            {"name": "kg_v2_find_by_type", "latency": "<2ms", "type": "filter"},
        ],
        "examples": [
            {
                "query": "kg_v2_contract_search('envelope', contract_type='jsonschema')",
                "use_case": "Find envelope schema definitions",
            },
            {
                "query": "kg_v2_contract_search('', contract_type='openapi', layer='k0_only')",
                "use_case": "Get all OpenAPI contracts in K0 layer",
            },
            {
                "query": "kg_v2_contract_search('agent', contract_type='flatbuffers', layer='k1_only')",
                "use_case": "Find agent FlatBuffers definitions in K1",
            },
        ],
    },
    "adrs": {
        "description": "Discover and navigate Architecture Decision Records",
        "best_for": [
            "Understanding design decisions",
            "Finding decision rationale",
            "Exploring alternatives considered",
            "Tracking decision status",
        ],
        "tools": [
            {"name": "kg_v2_find_by_type", "latency": "<2ms", "type": "filter"},
            {"name": "kg_v2_search", "latency": "<2ms", "type": "keyword"},
            {"name": "kg_v2_neighbors", "latency": "<5ms", "type": "navigation"},
        ],
        "examples": [
            {
                "query": "kg_v2_find_by_type('adr')",
                "use_case": "List all ADRs in the knowledge graph",
            },
            {
                "query": "kg_v2_search('dynamic agent creation')",
                "use_case": "Find ADRs about dynamic agent creation",
            },
            {
                "query": "kg_v2_neighbors('adr_0086')",
                "use_case": "Find ADRs related to ADR-0086",
            },
        ],
    },
    "modules": {
        "description": "Explore K1 module architecture and dependencies",
        "best_for": [
            "Understanding module structure",
            "Finding module dependencies",
            "Analyzing import relationships",
            "Module impact analysis",
        ],
        "tools": [
            {"name": "kg_v2_find_by_type", "latency": "<2ms", "type": "filter"},
            {
                "name": "kg_v2_get_module_deps",
                "latency": "<50ms",
                "type": "dependencies",
            },
            {"name": "kg_v2_neighbors", "latency": "<5ms", "type": "navigation"},
        ],
        "examples": [
            {
                "query": "kg_v2_find_by_type('module')",
                "use_case": "List all modules in knowledge graph",
            },
            {
                "query": "kg_v2_get_module_deps('module_k1.l3_execution.agents')",
                "use_case": "Get all dependencies of agents module",
            },
            {
                "query": "kg_v2_neighbors('module_k1.l2_orchestration.orchestrator', direction='incoming')",
                "use_case": "Find which modules depend on orchestrator",
            },
        ],
    },
    "dependencies": {
        "description": "Analyze module dependencies, impact, and circular relationships",
        "best_for": [
            "Understanding dependency chains",
            "Analyzing change impact",
            "Detecting circular dependencies",
            "Planning refactoring",
        ],
        "tools": [
            {
                "name": "kg_v2_get_module_deps",
                "latency": "<50ms",
                "type": "dependencies",
            },
            {"name": "kg_v2_dependency_impact", "latency": "<100ms", "type": "impact"},
            {
                "name": "kg_v2_find_circular_deps",
                "latency": "<100ms",
                "type": "circular",
            },
        ],
        "examples": [
            {
                "query": "kg_v2_get_module_deps('module_k1.l4_runtime.session_state', depth=2)",
                "use_case": "Get 2-level dependencies of session_state module",
            },
            {
                "query": "kg_v2_dependency_impact('module_k1.l2_orchestration.orchestrator')",
                "use_case": "See what breaks if orchestrator module changes",
            },
            {
                "query": "kg_v2_find_circular_deps()",
                "use_case": "Detect all circular import dependencies",
            },
        ],
    },
    "architecture": {
        "description": "High-level architecture overview and pattern discovery",
        "best_for": [
            "Understanding K1 5-layer architecture",
            "Feature context discovery",
            "Implementation planning",
            "Architecture health checks",
        ],
        "tools": [
            {"name": "kg_v2_graph_summary", "latency": "<10ms", "type": "overview"},
            {
                "name": "kg_v2_get_feature_context",
                "latency": "<100ms",
                "type": "feature",
            },
            {
                "name": "kg_v2_implementation_chain",
                "latency": "<100ms",
                "type": "context",
            },
            {"name": "kg_v2_diagnostics", "latency": "<20ms", "type": "health"},
        ],
        "examples": [
            {
                "query": "kg_v2_graph_summary()",
                "use_case": "Get high-level architecture stats and metrics",
            },
            {
                "query": "kg_v2_get_feature_context('agent lifecycle')",
                "use_case": "Find all ADRs, modules, contracts related to agent lifecycle",
            },
            {
                "query": "kg_v2_implementation_chain('adr_0086')",
                "use_case": "Get complete implementation context for ADR-0086",
            },
            {
                "query": "kg_v2_diagnostics('orphaned_nodes')",
                "use_case": "Find documentation gaps in architecture",
            },
        ],
    },
    "paths": {
        "description": "Find and analyze paths between nodes in the graph",
        "best_for": [
            "Understanding node relationships",
            "Tracing how features connect components",
            "Analyzing connection paths",
            "Impact analysis",
        ],
        "tools": [
            {"name": "kg_v2_paths", "latency": "<20ms", "type": "pathfinding"},
            {"name": "kg_v2_neighbors", "latency": "<5ms", "type": "navigation"},
        ],
        "examples": [
            {
                "query": "kg_v2_paths('adr_0005', 'adr_0086')",
                "use_case": "Find relationship path from agent lifecycle to dynamic creation ADRs",
            },
            {
                "query": "kg_v2_paths('module_k1.l1_input.parser', 'module_k1.l3_execution.agents', max_hops=5)",
                "use_case": "Find connection path between parser and agents",
            },
        ],
    },
    "graph_operations": {
        "description": "Add, modify, or remove nodes and edges in the knowledge graph",
        "best_for": [
            "Creating new ADRs",
            "Adding custom nodes",
            "Establishing relationships",
            "Removing obsolete entries",
        ],
        "tools": [
            {"name": "kg_v2_add_node", "latency": "<10ms", "type": "mutation"},
            {"name": "kg_v2_add_edge", "latency": "<10ms", "type": "mutation"},
            {"name": "kg_v2_remove_node", "latency": "<10ms", "type": "mutation"},
        ],
        "examples": [
            {
                "query": "kg_v2_add_node(node_id='adr_0100', node_type='adr', label='New Architecture Decision')",
                "use_case": "Create a new ADR node",
            },
            {
                "query": "kg_v2_add_edge(src='adr_0100', dst='adr_0086', relation='builds_on')",
                "use_case": "Link new ADR to existing decision",
            },
        ],
    },
    "ai_reasoning": {
        "description": "Specialized tools for AI agent reasoning and decision-making",
        "best_for": [
            "Understanding context for tasks",
            "Planning implementations",
            "Discovering edge cases",
            "Making informed decisions",
        ],
        "tools": [
            {"name": "kg_v2_ask", "latency": "<100ms", "type": "reasoning"},
            {
                "name": "kg_v2_implementation_chain",
                "latency": "<100ms",
                "type": "context",
            },
            {
                "name": "kg_v2_get_feature_context",
                "latency": "<100ms",
                "type": "context",
            },
        ],
        "examples": [
            {
                "query": "kg_v2_ask('How should I implement dynamic agent creation?')",
                "use_case": "Get AI-powered guidance on implementation approach",
            },
            {
                "query": "kg_v2_implementation_chain('adr_0086')",
                "use_case": "Get everything needed to implement a decision",
            },
        ],
    },
}

# Tool categories for quick navigation
TOOL_CATEGORIES = {
    "performance_critical": [
        "kg_v2_search",
        "kg_v2_find_by_type",
        "kg_v2_neighbors",
    ],
    "complex_queries": [
        "kg_v2_hybrid_search",
        "kg_v2_get_module_deps",
        "kg_v2_dependency_impact",
        "kg_v2_implementation_chain",
    ],
    "diagnostic": [
        "kg_v2_diagnostics",
        "kg_v2_find_circular_deps",
        "kg_v2_graph_summary",
    ],
    "mutation": [
        "kg_v2_add_node",
        "kg_v2_add_edge",
        "kg_v2_remove_node",
    ],
}


# ============================================================================
# K1 ARCHITECTURE PATTERNS (For Phase 3: Layer-Aware ask() Routing)
# ============================================================================

K1_LAYER_PATTERNS = {
    "layer_communication": {
        "patterns": [
            r"layer\s+(\d+|one|two|three|four|five).{0,30}layer\s+(\d+|one|two|three|four|five)",
            r"communication.{0,30}between",
            r"(?:layer|l)(\d).*(?:to|→|->).*(?:layer|l)(\d)",
            r"how.*layer.{0,20}communicate",
            r"interaction.*between.*layer",
        ],
        "response_template": "search for ADRs with 'communication' or 'layer' tags",
        "example_query": "What's the communication between Layer 1 and Layer 2?",
        "search_tags": ["communication", "layer", "integration"],
    },
    "component_discovery": {
        "patterns": [
            r"find all.{0,20}([\w\s]+)\s+components",
            r"list.{0,20}(thermal|memory|scheduler|agent|orchestrator|router|monitor|planner|researcher|safety).{0,20}component",
            r"what.*components.*layer",
            r"which.{0,20}modules.*layer",
        ],
        "response_template": "search for modules by component type and layer",
        "example_query": "Find all thermal components in Layer 5",
        "search_tags": ["component", "module", "architecture"],
    },
    "error_handling": {
        "patterns": [
            r"what\s+errors?",
            r"error.{0,20}(?:returns?|codes?|handling)",
            r"exception.{0,20}(?:raised|thrown)",
            r"(?:k0|k1).{0,20}(?:error|exception)",
            r"how.*handle.*error",
        ],
        "response_template": "search for error definitions and contracts",
        "example_query": "What errors does K0 return?",
        "search_tags": ["error", "exception", "contract"],
    },
    "agent_creation": {
        "patterns": [
            r"how.*(?:create|create|spawn|instantiate).{0,20}agent",
            r"agent.{0,20}(?:creation|lifecycle|initialization)",
            r"dynamic.{0,20}agent",
            r"agent.*factory",
        ],
        "response_template": "search for ADRs about agent creation and lifecycle",
        "example_query": "How do agents get created dynamically?",
        "search_tags": ["agent", "creation", "lifecycle", "dynamic"],
    },
    "performance": {
        "patterns": [
            r"(?:performance|latency|throughput|optimization)",
            r"(?:ttft|p95|p99|benchmark)",
            r"how.*fast",
            r"bottleneck",
        ],
        "response_template": "search for performance ADRs and benchmarks",
        "example_query": "What's the TTFT performance budget?",
        "search_tags": ["performance", "latency", "optimization"],
    },
    "routing_orchestration": {
        "patterns": [
            r"(?:routing|orchestration|coordination|scheduling)",
            r"how.*route",
            r"orchestrat",
            r"schedule.*task",
        ],
        "response_template": "search for routing and orchestration patterns",
        "example_query": "How does the orchestrator coordinate agents?",
        "search_tags": ["routing", "orchestration", "coordination"],
    },
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
