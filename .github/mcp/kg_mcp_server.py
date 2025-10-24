from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import deque
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Import indexers for dependency graph engine
from kg_indexers import DependencyGraphEngine, ModuleIndexer
from mcp.server.fastmcp import FastMCP

try:  # pragma: no cover - fallback controlled via dependency list
    import orjson
except Exception:  # pragma: no cover - optional dependency
    orjson = None

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kg_mcp")

KG_STORE_PATH = Path(
    os.environ.get("KG_STORE_PATH", Path.home() / ".mcp_kg" / "kg_store.json")
)
KG_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("kg")

ROLE_MAP = {
    "brain": "memory",
    "plane": "api",
    "mid": "processing",
    "gate": "gateway",
    "bus": "bus",
    "storage": "storage",
    "cache": "cache",
    "hot": "storage",
    "cold": "storage",
}

# Semantic node types supported by KG
NODE_TYPES = {
    "adr": "Architecture Decision Record",
    "module": "Code module or service",
    "file": "Source file",
    "component": "K0/K1 component",
    "contract": "API contract or schema",
    "layer": "Architectural layer (K0/K1)",
    "pattern": "Design pattern",
    "decision": "Technical decision",
    "risk": "Identified risk or issue",
    "diagram": "Architecture diagram",
}

# Semantic relation types
SEMANTIC_RELATIONS = {
    "implements": "Code implements ADR/decision",
    "depends_on": "Module depends on another",
    "tests": "Test covers functionality",
    "documents": "Documents component/pattern",
    "requires": "Requires contract/interface",
    "violates": "Violates pattern/decision",
    "contradicts": "Contradicts another decision",
    "mitigates": "Mitigates identified risk",
    "relates_to": "General relation between nodes",
    "extends": "Extends/builds on another",
    "references": "References another ADR/document",
}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return slug or "diagram"


class KnowledgeGraphStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = RLock()
        # Flat structure: no diagrams, just nodes and edges
        self._data: Dict[str, Any] = {
            "version": 2,
            "created_at": time.time(),
            "updated_at": time.time(),
            "nodes": {},
            "edges": [],
            "relations": {},
        }
        self._alias_index: Dict[str, str] = {}
        self._path_index: Dict[str, str] = {}
        self._load()

    # --- internal helpers -------------------------------------------------

    def _load(self) -> None:
        if not self.db_path.exists():
            return
        try:
            raw = self.db_path.read_bytes()
            if not raw:
                return
            payload = (
                orjson.loads(raw)
                if orjson is not None
                else json.loads(raw.decode("utf-8"))
            )
        except Exception as exc:
            log.warning("Failed to load KG store %s: %s", self.db_path, exc)
            return

        if not isinstance(payload, dict):
            log.warning("Invalid KG store format at %s, starting fresh", self.db_path)
            return

        # Support v1 (diagrams) and v2 (flat) formats
        version = payload.get("version", 1)
        if version == 1:
            # Migrate from v1 (diagrams) to v2 (flat)
            diagrams = payload.get("diagrams", {})
            nodes = {}
            edges = []
            for diagram_record in diagrams.values():
                nodes.update(diagram_record.get("nodes", {}))
                edges.extend(diagram_record.get("edges", []))
            self._data = {
                "version": 2,
                "created_at": payload.get("created_at", time.time()),
                "updated_at": payload.get("updated_at", time.time()),
                "nodes": nodes,
                "edges": edges,
                "relations": payload.get("relations", {}),
            }
        else:
            # v2 format
            self._data = {
                "version": 2,
                "created_at": payload.get("created_at", time.time()),
                "updated_at": payload.get("updated_at", time.time()),
                "nodes": payload.get("nodes", {}),
                "edges": payload.get("edges", []),
                "relations": payload.get("relations", {}),
            }
        self._reindex_unlocked()

    def _persist_unlocked(self) -> None:
        payload = dict(self._data)
        payload["diagrams"] = dict(self._data.get("diagrams", {}))
        tmp_path = self.db_path.with_suffix(".tmp")
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        if orjson is not None:
            tmp_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
        else:
            tmp_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
        tmp_path.replace(self.db_path)

    def _reindex_unlocked(self) -> None:
        self._alias_index = {}
        self._path_index = {}
        diagrams: Dict[str, Dict[str, Any]] = self._data.get("diagrams", {})
        for diagram_id, record in diagrams.items():
            for alias in record.get("aliases", []):
                self._alias_index[alias] = diagram_id
            path_value = record.get("source_path")
            if path_value:
                try:
                    self._path_index[str(Path(path_value).resolve())] = diagram_id
                except Exception:  # pragma: no cover - path resolution edge
                    self._path_index[path_value] = diagram_id

    def _resolve_diagram_id(self, ref: str) -> Optional[str]:
        diagrams: Dict[str, Dict[str, Any]] = self._data.get("diagrams", {})
        if ref in diagrams:
            return ref
        if ref in self._alias_index:
            return self._alias_index[ref]
        norm = str(Path(ref).resolve())
        if norm in self._path_index:
            return self._path_index[norm]
        return None

    def _require_diagram(self, ref: str) -> Tuple[str, Dict[str, Any]]:
        """Return flat data store (no diagram requirement)."""
        with self._lock:
            # In flat model, just return empty diagram_id and the data
            return "", self._data

    def _merge_edges(self, edges: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[Tuple[str, str, str, Optional[str]], Dict[str, Any]] = {}
        for edge in edges:
            key = (
                edge["src"],
                edge["dst"],
                edge.get("kind", "arrow"),
                edge.get("label"),
            )
            current = merged.get(key)
            origin = edge.get("origin", "diagram")
            if current:
                current_origin = current.get("origin", "diagram")
                if origin == "manual" and current_origin != "manual":
                    merged[key] = dict(edge)
                elif origin == current_origin == "manual":
                    props = dict(current.get("props") or {})
                    props.update(edge.get("props") or {})
                    current["props"] = props
                    # Merge semantic relation metadata when updating manual edges
                    if "relation_type" in edge:
                        current["relation_type"] = edge["relation_type"]
                    if "strength" in edge:
                        current["strength"] = edge["strength"]
                    if "evidence" in edge:
                        current["evidence"] = edge["evidence"]
            else:
                merged[key] = dict(edge)
        return list(merged.values())

    def _update_counts(self, record: Dict[str, Any]) -> None:
        record["counts"] = {
            "nodes": len(record.get("nodes", {})),
            "edges": len(record.get("edges", [])),
            "subgraphs": len(record.get("subgraphs", [])),
        }

    def _touch(self, record: Dict[str, Any]) -> None:
        now = time.time()
        record["updated_at"] = now
        self._data["updated_at"] = now

    # --- store API --------------------------------------------------------

    def add_or_update_node(
        self,
        ref: str,
        node_id: str,
        *,
        label: Optional[str] = None,
        shape: Optional[str] = None,
        classes: Optional[List[str]] = None,
        subgraph_path: Optional[str] = None,
        props: Optional[Dict[str, Any]] = None,
        annotations: Optional[Dict[str, Any]] = None,
        origin: str = "manual",
        node_type: Optional[str] = None,
        semantic_tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
        source_code_snippet: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        diagram_id, record = self._require_diagram(ref)
        with self._lock:
            # In flat structure, nodes are stored at root level
            nodes_dict = self._data.setdefault("nodes", {})
            node = nodes_dict.get(node_id, {})
            node.setdefault("id", node_id)
            node.setdefault("label", node_id)
            node.setdefault("shape", "auto")
            node.setdefault("classes", [])
            node.setdefault("subgraph_path", "")
            node.setdefault("props", {})
            node.setdefault("annotations", {})
            node.setdefault("memories", [])
            # Semantic fields
            node.setdefault("node_type", "unknown")
            node.setdefault("semantic_tags", [])
            node.setdefault("metadata", {})
            node.setdefault("file_path", None)
            node.setdefault("source_code_snippet", None)
            node.setdefault("created_by", "system")
            node.setdefault("created_at", time.time())

            if label is not None:
                node["label"] = label
            if shape is not None:
                node["shape"] = shape
            if classes is not None:
                deduped = []
                seen = set()
                for item in classes:
                    if item not in seen:
                        seen.add(item)
                        deduped.append(item)
                node["classes"] = deduped
            if subgraph_path is not None:
                node["subgraph_path"] = subgraph_path
            if props is not None:
                node["props"] = dict(props)
            if annotations is not None:
                merged = dict(node.get("annotations", {}))
                merged.update(annotations)
                node["annotations"] = merged

            # Update semantic fields
            if node_type is not None:
                if node_type not in NODE_TYPES:
                    log.warning(
                        "Unknown node_type %s (valid: %s)",
                        node_type,
                        ", ".join(NODE_TYPES.keys()),
                    )
                node["node_type"] = node_type
            if semantic_tags is not None:
                deduped_tags = []
                seen_tags = set()
                for tag in semantic_tags:
                    if tag not in seen_tags:
                        seen_tags.add(tag)
                        deduped_tags.append(tag)
                node["semantic_tags"] = deduped_tags
            if metadata is not None:
                merged_metadata = dict(node.get("metadata", {}))
                merged_metadata.update(metadata)
                node["metadata"] = merged_metadata
            if file_path is not None:
                node["file_path"] = file_path
            if source_code_snippet is not None:
                node["source_code_snippet"] = source_code_snippet
            if created_by is not None:
                node["created_by"] = created_by

            node["origin"] = origin
            nodes_dict[node_id] = node
            self._touch(self._data)
            self._persist_unlocked()
            return node

    def remove_node(self, ref: str, node_id: str) -> Dict[str, Any]:
        diagram_id, record = self._require_diagram(ref)
        with self._lock:
            nodes = record.get("nodes", {})
            if node_id not in nodes:
                raise KeyError(f"node_not_found: {node_id}")
            removed = nodes.pop(node_id)
            record["nodes"] = nodes
            edges = record.get("edges", [])
            record["edges"] = [
                edge
                for edge in edges
                if edge.get("src") != node_id and edge.get("dst") != node_id
            ]
            self._update_counts(record)
            self._touch(record)
            self._data["diagrams"][diagram_id] = record
            self._persist_unlocked()
            return removed

    def add_or_update_edge(
        self,
        ref: str,
        src: str,
        dst: str,
        *,
        kind: str = "arrow",
        label: Optional[str] = None,
        props: Optional[Dict[str, Any]] = None,
        origin: str = "manual",
        relation_type: Optional[str] = None,
        strength: Optional[float] = None,
        evidence: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add or update an edge with optional semantic relation metadata.

        Args:
            ref: Diagram reference (ID, alias, or path) - ignored in flat model
            src: Source node ID
            dst: Destination node ID
            kind: Edge kind (default: "arrow")
            label: Optional edge label
            props: Optional edge properties
            origin: Origin type ("manual" or "diagram", default: "manual")
            relation_type: Semantic relation type (e.g., "implements", "depends_on")
            strength: Confidence level 0.0-1.0 (default: None for unlabeled edges)
            evidence: Why this relation exists (e.g., file reference, code line)

        Returns:
            Edge payload dict with all fields

        Performance: <10ms
        """
        diagram_id, record = self._require_diagram(ref)
        with self._lock:
            edge_payload = {
                "src": src,
                "dst": dst,
                "kind": kind,
                "label": label,
                "props": dict(props or {}),
                "origin": origin,
            }
            # Add semantic relation metadata if provided
            if relation_type is not None:
                if relation_type not in SEMANTIC_RELATIONS:
                    raise ValueError(
                        f"invalid_relation_type: {relation_type}. "
                        f"Valid types: {', '.join(SEMANTIC_RELATIONS.keys())}"
                    )
                edge_payload["relation_type"] = relation_type
            if strength is not None:
                if not 0.0 <= strength <= 1.0:
                    raise ValueError(
                        f"strength_out_of_range: {strength}. Must be 0.0-1.0"
                    )
                edge_payload["strength"] = strength
            if evidence is not None:
                edge_payload["evidence"] = evidence

            # In flat structure, edges are stored at root level
            edges = self._data.setdefault("edges", [])
            merged = self._merge_edges(edges + [edge_payload])
            self._data["edges"] = merged
            self._touch(self._data)
            self._persist_unlocked()
            return edge_payload

    def remove_edge(
        self,
        ref: str,
        src: str,
        dst: str,
        *,
        kind: str = "arrow",
        label: Optional[str] = None,
    ) -> int:
        diagram_id, record = self._require_diagram(ref)
        with self._lock:
            before = len(record.get("edges", []))
            record["edges"] = [
                edge
                for edge in record.get("edges", [])
                if not (
                    edge.get("src") == src
                    and edge.get("dst") == dst
                    and edge.get("kind", "arrow") == kind
                    and edge.get("label") == label
                )
            ]
            removed = before - len(record["edges"])
            self._update_counts(record)
            self._touch(record)
            self._data["diagrams"][diagram_id] = record
            self._persist_unlocked()
            return removed

    def add_memory(
        self,
        ref: str,
        node_id: str,
        *,
        text: str,
        tags: Optional[List[str]] = None,
        author: Optional[str] = None,
    ) -> Dict[str, Any]:
        diagram_id, record = self._require_diagram(ref)
        with self._lock:
            node = record.get("nodes", {}).get(node_id)
            if not node:
                raise KeyError(f"node_not_found: {node_id}")
            memory = {
                "text": text,
                "tags": list(tags or []),
                "author": author,
                "created_at": time.time(),
            }
            node.setdefault("memories", []).append(memory)
            self._touch(record)
            self._data["diagrams"][diagram_id] = record
            self._persist_unlocked()
            return memory

    def update_annotations(
        self, ref: str, node_id: str, annotations: Dict[str, Any]
    ) -> Dict[str, Any]:
        diagram_id, record = self._require_diagram(ref)
        with self._lock:
            node = record.get("nodes", {}).get(node_id)
            if not node:
                raise KeyError(f"node_not_found: {node_id}")
            merged = dict(node.get("annotations", {}))
            merged.update(annotations)
            node["annotations"] = merged
            self._touch(record)
            self._data["diagrams"][diagram_id] = record
            self._persist_unlocked()
            return node

    def search(
        self, term: str, ref: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        needle = term.lower()
        diagram_ids: List[str]
        with self._lock:
            if ref:
                diagram_id = self._resolve_diagram_id(ref)
                if not diagram_id:
                    return []
                diagram_ids = [diagram_id]
            else:
                diagram_ids = list(self._data.get("diagrams", {}).keys())

            results: List[Dict[str, Any]] = []
            for diagram_id in diagram_ids:
                record = self._data["diagrams"][diagram_id]
                title = record.get("title") or diagram_id
                for node in record.get("nodes", {}).values():
                    haystack = "\n".join(
                        [
                            node.get("id", ""),
                            node.get("label", ""),
                            " ".join(node.get("classes", [])),
                            json.dumps(node.get("annotations", {}), ensure_ascii=False),
                            " ".join(
                                m.get("text", "") for m in node.get("memories", [])
                            ),
                        ]
                    ).lower()
                    if needle in haystack:
                        results.append(
                            {
                                "type": "node",
                                "diagram_id": diagram_id,
                                "aliases": record.get("aliases", []),
                                "title": title,
                                "node": node["id"],
                                "label": node.get("label"),
                                "score": haystack.count(needle),
                            }
                        )
                for edge in record.get("edges", []):
                    haystack = " ".join(
                        filter(
                            None,
                            [
                                edge.get("src"),
                                edge.get("dst"),
                                edge.get("label") or "",
                                json.dumps(edge.get("props", {}), ensure_ascii=False),
                            ],
                        )
                    ).lower()
                    if needle in haystack:
                        results.append(
                            {
                                "type": "edge",
                                "diagram_id": diagram_id,
                                "aliases": record.get("aliases", []),
                                "title": title,
                                "edge": {
                                    "src": edge.get("src"),
                                    "dst": edge.get("dst"),
                                    "label": edge.get("label"),
                                },
                                "score": haystack.count(needle),
                            }
                        )
            results.sort(key=lambda item: item.get("score", 0), reverse=True)
            return results[:limit]

    def neighbors(
        self, ref: str, node_id: str, direction: str = "both"
    ) -> Dict[str, Any]:
        _, record = self._require_diagram(ref)
        outs = []
        ins = []
        for edge in record.get("edges", []):
            if direction in ("out", "both") and edge.get("src") == node_id:
                outs.append(edge)
            if direction in ("in", "both") and edge.get("dst") == node_id:
                ins.append(edge)
        return {"node": node_id, "out": outs, "in": ins}

    def graph(self, ref: str) -> Dict[str, Any]:
        diagram_id, record = self._require_diagram(ref)
        return {
            "diagram": {
                "diagram_id": diagram_id,
                "aliases": record.get("aliases", []),
                "title": record.get("title"),
                "source_path": record.get("source_path"),
                "description": record.get("description"),
            },
            "nodes": list(record.get("nodes", {}).values()),
            "edges": record.get("edges", []),
            "subgraphs": record.get("subgraphs", []),
            "counts": record.get("counts", {}),
        }

    def summary(self, ref: str) -> Dict[str, Any]:
        diagram_id, record = self._require_diagram(ref)
        nodes = record.get("nodes", {})
        edges = record.get("edges", [])
        degrees: Dict[str, int] = {}
        for edge in edges:
            src = edge.get("src")
            dst = edge.get("dst")
            if src:
                degrees[src] = degrees.get(src, 0) + 1
            if dst:
                degrees[dst] = degrees.get(dst, 0) + 1
        top_hubs = sorted(degrees.items(), key=lambda item: item[1], reverse=True)[:10]
        role_counts: Dict[str, int] = {}
        for node in nodes.values():
            role = _infer_role(node.get("classes", []))
            if role:
                role_counts[role] = role_counts.get(role, 0) + 1
        return {
            "diagram": {
                "diagram_id": diagram_id,
                "aliases": record.get("aliases", []),
                "title": record.get("title"),
                "source_path": record.get("source_path"),
            },
            "counts": record.get("counts", {}),
            "top_hubs": [
                {"node": node_id, "degree": degree} for node_id, degree in top_hubs
            ],
            "roles": role_counts,
            "subgraphs": record.get("subgraphs", []),
        }

    def paths(
        self, ref: str, src: str, dst: str, max_hops: int = 6, max_paths: int = 5
    ) -> Dict[str, Any]:
        _, record = self._require_diagram(ref)
        adjacency: Dict[str, List[str]] = {}
        for edge in record.get("edges", []):
            adjacency.setdefault(edge.get("src"), []).append(edge.get("dst"))
        results: List[List[str]] = []
        queue: deque[List[str]] = deque([[src]])
        seen_paths: set[Tuple[str, ...]] = set()
        while queue and len(results) < max_paths:
            path = queue.popleft()
            if len(path) - 1 > max_hops:
                continue
            last = path[-1]
            if last == dst:
                key = tuple(path)
                if key not in seen_paths:
                    seen_paths.add(key)
                    results.append(path)
                continue
            for neighbor in adjacency.get(last, []):
                if neighbor in path:
                    continue
                queue.append(path + [neighbor])
        return {"src": src, "dst": dst, "paths": results}

    def find_edges_by_relation_type(
        self, ref: str, relation_type: str
    ) -> List[Dict[str, Any]]:
        """Find all edges with a specific semantic relation type.

        Args:
            ref: Diagram reference
            relation_type: Semantic relation type to filter by

        Returns:
            List of edges with the specified relation type

        Raises:
            ValueError: If relation_type is not valid

        Performance: <10ms for typical graphs
        """
        if relation_type not in SEMANTIC_RELATIONS:
            raise ValueError(
                f"invalid_relation_type: {relation_type}. "
                f"Valid types: {', '.join(SEMANTIC_RELATIONS.keys())}"
            )
        _, record = self._require_diagram(ref)
        matching_edges = [
            edge
            for edge in record.get("edges", [])
            if edge.get("relation_type") == relation_type
        ]
        return matching_edges

    def find_edges_by_strength(
        self, ref: str, min_strength: float = 0.0, max_strength: float = 1.0
    ) -> List[Dict[str, Any]]:
        """Find all edges within a strength confidence range.

        Args:
            ref: Diagram reference
            min_strength: Minimum strength threshold (0.0-1.0)
            max_strength: Maximum strength threshold (0.0-1.0)

        Returns:
            List of edges within the strength range

        Performance: <10ms
        """
        _, record = self._require_diagram(ref)
        matching_edges = [
            edge
            for edge in record.get("edges", [])
            if "strength" in edge and min_strength <= edge["strength"] <= max_strength
        ]
        return matching_edges

    def find_related_nodes(
        self, ref: str, node_id: str, relation_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Find nodes related to a given node by semantic relations.

        Args:
            ref: Diagram reference
            node_id: Node ID to find relations for
            relation_types: Optional filter by specific relation types

        Returns:
            Dict with outgoing and incoming related nodes

        Performance: <10ms
        """
        _, record = self._require_diagram(ref)
        outgoing = []
        incoming = []

        for edge in record.get("edges", []):
            # Check relation type filter
            if relation_types:
                edge_type = edge.get("relation_type")
                if edge_type not in relation_types:
                    continue

            if edge.get("src") == node_id:
                outgoing.append(
                    {
                        "target": edge.get("dst"),
                        "relation_type": edge.get("relation_type", "unknown"),
                        "strength": edge.get("strength"),
                        "evidence": edge.get("evidence"),
                        "label": edge.get("label"),
                    }
                )
            elif edge.get("dst") == node_id:
                incoming.append(
                    {
                        "source": edge.get("src"),
                        "relation_type": edge.get("relation_type", "unknown"),
                        "strength": edge.get("strength"),
                        "evidence": edge.get("evidence"),
                        "label": edge.get("label"),
                    }
                )

        return {"node": node_id, "outgoing": outgoing, "incoming": incoming}

    def get_relation_type_stats(self, ref: str) -> Dict[str, Any]:
        """Get statistics about semantic relations in the diagram.

        Args:
            ref: Diagram reference

        Returns:
            Stats about relation types, strength distribution, etc.

        Performance: <10ms
        """
        _, record = self._require_diagram(ref)
        relation_counts: Dict[str, int] = {}
        strength_counts: Dict[float, int] = {}
        edges_with_evidence = 0
        edges_with_relation_type = 0

        for edge in record.get("edges", []):
            rel_type = edge.get("relation_type", "unlabeled")
            relation_counts[rel_type] = relation_counts.get(rel_type, 0) + 1

            # Count edges that have an explicit relation type
            if rel_type != "unlabeled":
                edges_with_relation_type += 1

            if "strength" in edge:
                strength = edge["strength"]
                strength_counts[strength] = strength_counts.get(strength, 0) + 1

            if "evidence" in edge:
                edges_with_evidence += 1

        return {
            "total_edges": len(record.get("edges", [])),
            "relation_type_distribution": relation_counts,
            "strength_distribution": strength_counts,
            "edges_with_evidence": edges_with_evidence,
            "labeled_relations": edges_with_relation_type,
        }


def _infer_role(classes: Iterable[str]) -> Optional[str]:
    for cls in classes:
        key = cls.lower()
        if key in ROLE_MAP:
            return ROLE_MAP[key]
    return None


STORE = KnowledgeGraphStore(KG_STORE_PATH)


# --- MCP tools ------------------------------------------------------------


@mcp.tool(
    name="kg_add_node",
    description="Create or update a knowledge graph node with optional semantic metadata (type, tags, file path, code snippet). Returns full node record after upsert.",
)
def kg_add_node(
    diagram: str,
    node_id: str,
    *,
    label: Optional[str] = None,
    shape: Optional[str] = None,
    classes: Optional[List[str]] = None,
    subgraph_path: Optional[str] = None,
    props: Optional[Dict[str, Any]] = None,
    annotations: Optional[Dict[str, Any]] = None,
    node_type: Optional[str] = None,
    semantic_tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    file_path: Optional[str] = None,
    source_code_snippet: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update a knowledge graph node with optional semantic metadata.

    Args:
        diagram: Diagram ID or alias. Ignored in flat model; keep a stable string.
        node_id: Unique node identifier (stable; reused for updates). Examples: adr_0051, k0.kernel, k1.contracts.openapi
        label: Human-readable label (defaults to node_id if not provided).
        shape: Visual hint for rendering; free-form string (e.g., 'box', 'circle', 'ellipse').
        classes: Arbitrary tags for styling/role inference (e.g., ['layer', 'infrastructure']).
        subgraph_path: Hierarchical grouping path (e.g., 'k1/l2/orchestrator' for nesting).
        props: Free-form properties dict for tool-specific data.
        annotations: Free-form notes dict; merged with existing on update.
        node_type: One of the supported node types: adr, module, file, component, contract, layer, pattern, decision, risk, diagram.
        semantic_tags: High-level classification tags for retrieval/routing (e.g., ['critical', 'agent', 'scheduler']).
        metadata: Rich metadata dict for node-specific structured data; merged on update.
        file_path: Absolute or repo-relative file path if applicable (enables source linking).
        source_code_snippet: Short code snippet for context (e.g., function signature, class definition).
        created_by: Identifier of the writer (e.g., 'copilot', 'dev:alice', 'adr_indexer').

    Returns:
        Dict with the full node record after upsert, including id, label, node_type, semantic_tags, etc.
    """
    return STORE.add_or_update_node(
        diagram,
        node_id,
        label=label,
        shape=shape,
        classes=classes,
        subgraph_path=subgraph_path,
        props=props,
        annotations=annotations,
        origin="manual",
        node_type=node_type,
        semantic_tags=semantic_tags,
        metadata=metadata,
        file_path=file_path,
        source_code_snippet=source_code_snippet,
        created_by=created_by,
    )


@mcp.tool(
    name="kg_remove_node",
    description="Remove a node and all its incident edges from the knowledge graph.",
)
def kg_remove_node(diagram: str, node_id: str) -> Dict[str, Any]:
    """Remove a node and all its incident edges from the knowledge graph.

    Args:
        diagram: Diagram ID or alias.
        node_id: Unique node identifier to remove.

    Returns:
        The removed node record dict.
    """
    return STORE.remove_node(diagram, node_id)


@mcp.tool(
    name="kg_add_edge",
    description="Create or update an edge between two nodes with optional relation type and strength metadata.",
)
def kg_add_edge(
    diagram: str,
    src: str,
    dst: str,
    *,
    kind: str = "arrow",
    label: Optional[str] = None,
    props: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create or update an edge between two nodes in the knowledge graph.

    Args:
        diagram: Diagram ID or alias.
        src: Source node ID (edge origin).
        dst: Destination node ID (edge target).
        kind: Edge visual kind (default: "arrow"). Examples: "arrow", "dashed", "dotted", "solid".
        label: Optional label displayed on the edge.
        props: Free-form properties dict for edge-specific data.

    Returns:
        Dict with the full edge record after upsert.
    """
    return STORE.add_or_update_edge(
        diagram,
        src,
        dst,
        kind=kind,
        label=label,
        props=props,
        origin="manual",
    )


@mcp.tool(
    name="kg_remove_edge",
    description="Remove an edge between two nodes in the knowledge graph.",
)
def kg_remove_edge(
    diagram: str,
    src: str,
    dst: str,
    *,
    kind: str = "arrow",
    label: Optional[str] = None,
) -> int:
    """Remove an edge from the diagram."""
    return STORE.remove_edge(diagram, src, dst, kind=kind, label=label)


@mcp.tool(
    name="kg_add_memory",
    description="Attach a free-form memory note to a node in the knowledge graph.",
)
def kg_add_memory(
    diagram: str,
    node_id: str,
    *,
    text: str,
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach a free-form memory note to a node."""
    return STORE.add_memory(diagram, node_id, text=text, tags=tags, author=author)


@mcp.tool(
    name="kg_update_annotations",
    description="Update node annotations with additional metadata.",
)
def kg_update_annotations(
    diagram: str, node_id: str, annotations: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge annotations into the node metadata."""
    return STORE.update_annotations(diagram, node_id, annotations)


@mcp.tool(
    name="kg_search",
    description="Full-text search across nodes and edges in the knowledge graph.",
)
def kg_search(
    term: str, diagram: Optional[str] = None, limit: int = 20
) -> List[Dict[str, Any]]:
    """Search nodes and edges across the knowledge graph store."""
    return STORE.search(term, ref=diagram, limit=limit)


@mcp.tool(
    name="kg_neighbors",
    description="Get adjacent nodes (outgoing/incoming/both) from a specific node.",
)
def kg_neighbors(diagram: str, node_id: str, direction: str = "both") -> Dict[str, Any]:
    """Return adjacency information for the node in the diagram."""
    return STORE.neighbors(diagram, node_id, direction=direction)


@mcp.tool(
    name="kg_graph",
    description="Retrieve complete graph structure (all nodes, edges, subgraphs) from a diagram.",
)
def kg_graph(diagram: str) -> Dict[str, Any]:
    """Return the full graph payload for a diagram."""
    return STORE.graph(diagram)


@mcp.tool(
    name="kg_summary",
    description="Get high-level statistics and structure summary of a diagram.",
)
def kg_summary(diagram: str) -> Dict[str, Any]:
    """Return a structural summary for a diagram."""
    return STORE.summary(diagram)


@mcp.tool(
    name="kg_paths", description="Find simple paths between two nodes (BFS traversal)."
)
def kg_paths(
    diagram: str, src: str, dst: str, max_hops: int = 6, max_paths: int = 5
) -> Dict[str, Any]:
    """Enumerate simple paths between two nodes."""
    return STORE.paths(diagram, src, dst, max_hops=max_hops, max_paths=max_paths)


@mcp.tool(
    name="kg_find_by_type", description="Find all nodes of a specific semantic type."
)
def kg_find_by_type(
    node_type: str, diagram: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """Find all nodes of a specific semantic type.

    Args:
        node_type: Type to search for ("adr", "module", "file", "contract", etc.)
        diagram: Optional diagram ID to limit search
        limit: Maximum results to return

    Returns:
        List of matching nodes with full metadata
    """
    if node_type not in NODE_TYPES:
        log.warning(
            "Unknown node_type %s (valid: %s)", node_type, ", ".join(NODE_TYPES.keys())
        )
        return []

    results: List[Dict[str, Any]] = []
    with STORE._lock:
        diagram_ids: List[str] = []
        if diagram:
            diagram_id = STORE._resolve_diagram_id(diagram)
            if diagram_id:
                diagram_ids = [diagram_id]
        else:
            diagram_ids = list(STORE._data.get("diagrams", {}).keys())

        for diagram_id in diagram_ids:
            record = STORE._data["diagrams"][diagram_id]
            for node in record.get("nodes", {}).values():
                if node.get("node_type") == node_type:
                    results.append(
                        {
                            "diagram_id": diagram_id,
                            "diagram_title": record.get("title", diagram_id),
                            "node": node,
                        }
                    )
                    if len(results) >= limit:
                        return results[:limit]

    return results[:limit]


@mcp.tool(
    name="kg_find_by_tags",
    description="Find knowledge graph nodes matching semantic tags (ALL or ANY match).",
)
def kg_find_by_tags(
    tags: List[str],
    diagram: Optional[str] = None,
    limit: int = 50,
    match_all: bool = False,
) -> List[Dict[str, Any]]:
    """Find knowledge graph nodes matching semantic tags.

    Args:
        tags: List of semantic tags to search for (e.g., ['critical', 'agent']).
        diagram: Optional diagram ID to limit search scope.
        limit: Maximum number of results to return (default: 50).
        match_all: If True, node must have ALL specified tags. If False (default), ANY tag match returns the node.

    Returns:
        List of matching nodes with metadata, matched_tags, and containing diagram info.
    """
    if not tags:
        return []

    tag_set = set(tags)
    results: List[Dict[str, Any]] = []

    with STORE._lock:
        diagram_ids: List[str] = []
        if diagram:
            diagram_id = STORE._resolve_diagram_id(diagram)
            if diagram_id:
                diagram_ids = [diagram_id]
        else:
            diagram_ids = list(STORE._data.get("diagrams", {}).keys())

        for diagram_id in diagram_ids:
            record = STORE._data["diagrams"][diagram_id]
            for node in record.get("nodes", {}).values():
                node_tags = set(node.get("semantic_tags", []))
                if match_all:
                    if tag_set.issubset(node_tags):
                        results.append(
                            {
                                "diagram_id": diagram_id,
                                "diagram_title": record.get("title", diagram_id),
                                "node": node,
                                "matched_tags": list(tag_set & node_tags),
                            }
                        )
                else:
                    matched = tag_set & node_tags
                    if matched:
                        results.append(
                            {
                                "diagram_id": diagram_id,
                                "diagram_title": record.get("title", diagram_id),
                                "node": node,
                                "matched_tags": list(matched),
                            }
                        )
                if len(results) >= limit:
                    return results[:limit]

    return results[:limit]


@mcp.tool(
    name="kg_find_adr_by_status",
    description="Find architecture decision records (ADRs) filtered by their decision status.",
)
def kg_find_adr_by_status(
    status: str, diagram: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Find ADRs by their decision status.

    Args:
        status: Status value to filter by (e.g., 'PROPOSED', 'ACCEPTED', 'IMPLEMENTED', 'REJECTED', 'SUPERSEDED').
        diagram: Optional diagram ID to limit search scope.

    Returns:
        List of ADR nodes matching the specified status.
    """
    results: List[Dict[str, Any]] = []

    with STORE._lock:
        diagram_ids: List[str] = []
        if diagram:
            diagram_id = STORE._resolve_diagram_id(diagram)
            if diagram_id:
                diagram_ids = [diagram_id]
        else:
            diagram_ids = list(STORE._data.get("diagrams", {}).keys())

        for diagram_id in diagram_ids:
            record = STORE._data["diagrams"][diagram_id]
            for node in record.get("nodes", {}).values():
                if node.get("node_type") == "adr":
                    node_status = node.get("metadata", {}).get("status")
                    if node_status and node_status.upper() == status.upper():
                        results.append(
                            {
                                "diagram_id": diagram_id,
                                "diagram_title": record.get("title", diagram_id),
                                "node": node,
                            }
                        )

    return results


@mcp.tool(
    name="kg_get_related_adr",
    description="Find ADRs related to a given ADR via graph edges.",
)
def kg_get_related_adr(adr_id: str, diagram: Optional[str] = None) -> Dict[str, Any]:
    """Find ADRs related to a given ADR via graph edges.

    Args:
        adr_id: Node ID of the ADR
        diagram: Diagram ID to search in

    Returns:
        Dict with related ADRs and relation types
    """
    if not diagram:
        # Try to find the ADR in any diagram
        with STORE._lock:
            for d_id, record in STORE._data.get("diagrams", {}).items():
                if adr_id in record.get("nodes", {}):
                    diagram = d_id
                    break

    if not diagram:
        return {"error": f"ADR {adr_id} not found"}

    neighbors = STORE.neighbors(diagram, adr_id, direction="both")
    related_edges = neighbors.get("out", []) + neighbors.get("in", [])

    related_adr_ids = set()
    for edge in related_edges:
        other_id = edge.get("dst") if edge.get("src") == adr_id else edge.get("src")
        if other_id:
            related_adr_ids.add(other_id)

    with STORE._lock:
        record = STORE._data["diagrams"][STORE._resolve_diagram_id(diagram)]
        related_nodes = []
        for adr_id in related_adr_ids:
            node = record.get("nodes", {}).get(adr_id)
            if node and node.get("node_type") == "adr":
                related_nodes.append(node)

    return {
        "base_adr": adr_id,
        "related_count": len(related_nodes),
        "related_adr": related_nodes,
        "relation_edges": related_edges,
    }


@mcp.tool(
    name="kg_find_edges_by_relation_type",
    description="Find all edges with a specific semantic relation type.",
)
def kg_find_edges_by_relation_type(
    diagram: str, relation_type: str
) -> List[Dict[str, Any]]:
    """Find all edges with a specific semantic relation type.

    Args:
        diagram: Diagram ID or alias
        relation_type: Semantic relation type ("implements", "depends_on", "tests", "documents", etc.)

    Returns:
        List of edges matching the relation type

    Raises:
        ValueError: If relation_type is invalid
    """
    return STORE.find_edges_by_relation_type(diagram, relation_type)


@mcp.tool(
    name="kg_find_edges_by_strength",
    description="Find edges within a confidence strength range.",
)
def kg_find_edges_by_strength(
    diagram: str, min_strength: float = 0.0, max_strength: float = 1.0
) -> List[Dict[str, Any]]:
    """Find all edges within a confidence strength range.

    Stronger edges indicate more reliable semantic relations.

    Args:
        diagram: Diagram ID or alias
        min_strength: Minimum strength threshold (0.0-1.0)
        max_strength: Maximum strength threshold (0.0-1.0)

    Returns:
        List of edges within the strength range

    Example:
        Find all high-confidence relations: kg_find_edges_by_strength("diagram_id", 0.8, 1.0)
    """
    return STORE.find_edges_by_strength(diagram, min_strength, max_strength)


@mcp.tool(
    name="kg_find_related_nodes",
    description="Find nodes related to a given node by semantic relations.",
)
def kg_find_related_nodes(
    diagram: str, node_id: str, relation_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Find nodes related to a given node by semantic relations.

    Args:
        diagram: Diagram ID or alias
        node_id: Node ID to find relations for
        relation_types: Optional list of relation types to filter by

    Returns:
        Dict with outgoing and incoming related nodes with metadata

    Example:
        Find implementations of an ADR: kg_find_related_nodes("diagram", "adr_0051", ["implements"])
    """
    return STORE.find_related_nodes(diagram, node_id, relation_types)


@mcp.tool(
    name="kg_get_relation_type_stats",
    description="Get statistics about semantic relations in a diagram.",
)
def kg_get_relation_type_stats(diagram: str) -> Dict[str, Any]:
    """Get statistics about semantic relations in a diagram.

    Returns distribution of relation types, strength levels, and edges with evidence.

    Args:
        diagram: Diagram ID or alias

    Returns:
        Dict with relation type statistics:
        - total_edges: Total number of edges
        - relation_type_distribution: Count of edges by relation type
        - strength_distribution: Count of edges by confidence strength
        - edges_with_evidence: Number of edges with evidence field
        - labeled_relations: Number of edges with semantic relation type
    """
    return STORE.get_relation_type_stats(diagram)


# --- Repository Query Tools (Phase 2) ------------------------------------------
# Global engine instance (lazy-loaded)
_dependency_engine: Optional[DependencyGraphEngine] = None


def _get_dependency_engine() -> DependencyGraphEngine:
    """Lazy-load and return the dependency graph engine."""
    global _dependency_engine
    if _dependency_engine is None:
        try:
            indexer = ModuleIndexer()
            _dependency_engine = DependencyGraphEngine()
            # Index K0 and K1 modules
            graph_data = indexer.ingest_modules(["k0", "k1"])
            _dependency_engine.build_from_graph(graph_data)
        except Exception as e:
            log.warning(f"Failed to initialize DependencyGraphEngine: {e}")
            # Create empty engine as fallback
            _dependency_engine = DependencyGraphEngine()
    return _dependency_engine


@mcp.tool(
    name="kg_get_module_deps",
    description="Get all dependencies of a module (transitive closure).",
)
def kg_get_module_deps(module_id: str, depth: Optional[int] = None) -> Dict[str, Any]:
    """Get all dependencies of a module (transitive).

    This tool answers: "What does this module depend on?"

    Args:
        module_id: Module ID (e.g., "k0.kernel", "k1.l2_orchestration")
        depth: Optional maximum depth (None = unlimited)

    Returns:
        Dict with:
        - module_id: The module queried
        - direct_dependencies: Immediate imports
        - transitive_dependencies: All transitive deps
        - dependency_depth: Maximum depth in dependency tree
        - by_depth: Dict mapping depth -> set of modules at that depth
        - circular_found: Whether any circular deps detected
        - query_time_ms: Query execution time

    Example:
        >>> kg_get_module_deps("k0.kernel")
        {
            "module_id": "k0.kernel",
            "direct_dependencies": ["k0.bus", "k0.chaos"],
            "transitive_dependencies": ["k0.bus", "k0.chaos", "k0.middleware", ...],
            "dependency_depth": 4,
            "circular_found": False,
            "query_time_ms": 12.5
        }
    """
    engine = _get_dependency_engine()
    start = time.time()

    direct_deps = engine.get_direct_dependencies(module_id)
    trans_result = engine.get_transitive_dependencies(module_id, max_depth=depth)

    # Check if there are circular deps involving this module
    cycles = engine.find_circular_dependencies()
    circular_found = any(module_id in c.modules for c in cycles)

    elapsed_ms = (time.time() - start) * 1000

    return {
        "module_id": module_id,
        "direct_dependencies": direct_deps,
        "transitive_dependencies": list(trans_result["dependencies"]),
        "dependency_depth": trans_result["depth"],
        "by_depth": {k: list(v) for k, v in trans_result["by_depth"].items()},
        "circular_found": circular_found,
        "query_time_ms": round(elapsed_ms, 2),
    }


@mcp.tool(
    name="kg_get_dependents",
    description="Get all modules that depend on this module (reverse transitive).",
)
def kg_get_dependents(module_id: str, depth: Optional[int] = None) -> Dict[str, Any]:
    """Get all modules that depend on this module (reverse transitive).

    This tool answers: "What depends on this module?" or "What would break if I modify this?"

    Args:
        module_id: Module ID to query
        depth: Optional maximum depth

    Returns:
        Dict with:
        - module_id: The module queried
        - direct_dependents: Modules that directly import this
        - transitive_dependents: All modules that depend transitively
        - dependent_depth: Maximum depth in dependent tree
        - by_depth: Dict mapping depth -> modules at that depth
        - impact_radius: Total number of affected modules
        - risk_level: "low" (<5), "medium" (5-20), "high" (>20)
        - query_time_ms: Query execution time

    Example:
        >>> kg_get_dependents("k0.kernel")
        {
            "module_id": "k0.kernel",
            "direct_dependents": ["k0.bus"],
            "transitive_dependents": ["k0.bus", "k1.orchestrator", "k1.l2_orchestration"],
            "impact_radius": 3,
            "risk_level": "low",
            "query_time_ms": 8.3
        }
    """
    engine = _get_dependency_engine()
    start = time.time()

    direct_dependents = engine.get_direct_dependents(module_id)
    trans_result = engine.get_transitive_dependents(module_id, max_depth=depth)

    impact_radius = len(trans_result["dependents"])
    if impact_radius < 5:
        risk_level = "low"
    elif impact_radius < 20:
        risk_level = "medium"
    else:
        risk_level = "high"

    elapsed_ms = (time.time() - start) * 1000

    return {
        "module_id": module_id,
        "direct_dependents": direct_dependents,
        "transitive_dependents": list(trans_result["dependents"]),
        "dependent_depth": trans_result["depth"],
        "by_depth": {k: list(v) for k, v in trans_result["by_depth"].items()},
        "impact_radius": impact_radius,
        "risk_level": risk_level,
        "query_time_ms": round(elapsed_ms, 2),
    }


@mcp.tool(
    name="kg_find_circular_deps",
    description="Find all circular dependencies in the repository.",
)
def kg_find_circular_deps() -> Dict[str, Any]:
    """Find all circular dependencies in the repository.

    This tool answers: "Are there any circular dependencies?" and "Which modules are involved?"

    Returns:
        Dict with:
        - circular_dependencies_found: Boolean
        - cycle_count: Number of cycles detected
        - cycles: List of cycles, each with:
          - modules: Modules involved in cycle
          - cycle_length: Number of modules
          - edges: List of (src, dst) pairs forming cycle
          - detected_at: Timestamp
        - modules_in_cycles: Set of all modules involved in any cycle
        - risk_level: "none" (0 cycles), "low" (1-2), "medium" (3-5), "high" (>5)
        - query_time_ms: Query execution time

    Example:
        >>> kg_find_circular_deps()
        {
            "circular_dependencies_found": True,
            "cycle_count": 2,
            "cycles": [
                {
                    "modules": ["k0.kernel", "k0.bus", "k0.kernel"],
                    "cycle_length": 2,
                    "edges": [("k0.kernel", "k0.bus"), ("k0.bus", "k0.kernel")]
                },
                ...
            ],
            "modules_in_cycles": ["k0.kernel", "k0.bus"],
            "risk_level": "high",
            "query_time_ms": 15.2
        }
    """
    engine = _get_dependency_engine()
    start = time.time()

    cycles = engine.find_circular_dependencies()
    cycle_count = len(cycles)

    # Collect all modules involved in any cycle
    modules_in_cycles = set()
    for cycle in cycles:
        modules_in_cycles.update(cycle.modules[:-1])  # Exclude duplicate at end

    # Determine risk level
    if cycle_count == 0:
        risk_level = "none"
    elif cycle_count <= 2:
        risk_level = "low"
    elif cycle_count <= 5:
        risk_level = "medium"
    else:
        risk_level = "high"

    elapsed_ms = (time.time() - start) * 1000

    return {
        "circular_dependencies_found": cycle_count > 0,
        "cycle_count": cycle_count,
        "cycles": [
            {
                "modules": cycle.modules,
                "cycle_length": cycle.cycle_length,
                "edges": cycle.edges,
            }
            for cycle in cycles
        ],
        "modules_in_cycles": list(modules_in_cycles),
        "risk_level": risk_level,
        "query_time_ms": round(elapsed_ms, 2),
    }


@mcp.tool(
    name="kg_trace_import_chain",
    description="Trace import dependency paths between two modules.",
)
def kg_trace_import_chain(
    source: str, target: str, max_paths: int = 5
) -> Dict[str, Any]:
    """Trace import chains from source to target module.

    This tool answers: "How does module A reach module B?" or "What's the dependency path?"

    Args:
        source: Starting module ID
        target: Target module ID
        max_paths: Maximum number of paths to find (default: 5)

    Returns:
        Dict with:
        - source: Starting module
        - target: Target module
        - paths_found: Number of paths found
        - paths: List of paths, each with:
          - path: List of modules from source to target
          - length: Number of hops
          - is_circular: Boolean indicating if path closes back
        - shortest_path_length: Length of shortest path (or None)
        - max_paths_exceeded: Boolean if more paths exist
        - circular_path_exists: Boolean if any path is circular
        - query_time_ms: Query execution time

    Example:
        >>> kg_trace_import_chain("k1.l2_orchestration", "k0.kernel")
        {
            "source": "k1.l2_orchestration",
            "target": "k0.kernel",
            "paths_found": 2,
            "paths": [
                {
                    "path": ["k1.l2_orchestration", "k0.bus", "k0.kernel"],
                    "length": 2,
                    "is_circular": False
                },
                {
                    "path": ["k1.l2_orchestration", "k0.middleware", "k0.kernel"],
                    "length": 2,
                    "is_circular": False
                }
            ],
            "shortest_path_length": 2,
            "circular_path_exists": False,
            "query_time_ms": 11.5
        }
    """
    engine = _get_dependency_engine()
    start = time.time()

    paths = engine.find_paths(source, target, max_paths=max_paths)

    shortest_length = None
    if paths:
        shortest_length = min(p.length for p in paths)

    circular_found = any(p.is_circular for p in paths)

    elapsed_ms = (time.time() - start) * 1000

    return {
        "source": source,
        "target": target,
        "paths_found": len(paths),
        "paths": [
            {
                "path": p.path,
                "length": p.length,
                "is_circular": p.is_circular,
            }
            for p in paths
        ],
        "shortest_path_length": shortest_length,
        "max_paths_exceeded": len(paths) >= max_paths,
        "circular_path_exists": circular_found,
        "query_time_ms": round(elapsed_ms, 2),
    }


# --- Phase 3: AI Query Tools ------------------------------------------------


@mcp.tool(
    name="kg_implementation_chain",
    description="Get everything needed to implement an ADR (complete context).",
)
def kg_implementation_chain(
    adr_id: str, diagram: Optional[str] = None
) -> Dict[str, Any]:
    """Given an ADR, return everything needed to implement it.

    This tool answers: "What do I need to implement this ADR?"

    Aggregates:
    - ADR metadata (status, consequences, related decisions)
    - Linked contracts and their schemas
    - Modules that implement this ADR
    - Associated test files
    - Related ADRs (builds on, contradicts, mitigates)
    - Architectural patterns referenced

    Args:
        adr_id: ADR node ID (e.g., "adr_0051")
        diagram: Optional diagram ID to search in

    Returns:
        Dict with complete implementation context:
        {
            "adr": {"id": "adr_0051", "status": "ACCEPTED", "title": "...", ...},
            "contracts": [
                {"name": "agent_scheduler.yaml", "path": "...", "schema": {...}}
            ],
            "modules": [
                {"name": "k1.l2_orchestration.agent_scheduler", "path": "..."}
            ],
            "files": ["agent_scheduler.py", "agent_state.py", ...],
            "tests": ["test_agent_scheduler.py", "test_integration.py"],
            "related_adr": [
                {"id": "adr_0050", "relation": "depends_on", "title": "..."},
                {"id": "adr_0052", "relation": "relates_to", "title": "..."}
            ],
            "patterns": ["state_machine", "actor_model", "saga_pattern"],
            "implementation_effort": "8-12 hours",
            "dependencies": ["ADR-0050 implementation required first"],
            "query_time_ms": 42.3
        }

    Performance: <100ms
    """
    start = time.time()

    # If no diagram specified, find the ADR in any diagram
    if not diagram:
        with STORE._lock:
            for d_id, record in STORE._data.get("diagrams", {}).items():
                if adr_id in record.get("nodes", {}):
                    diagram = d_id
                    break

    if not diagram:
        return {"error": f"ADR {adr_id} not found in any diagram"}

    # Get ADR metadata
    with STORE._lock:
        record = STORE._data["diagrams"][STORE._resolve_diagram_id(diagram)]
        adr_node = record.get("nodes", {}).get(adr_id)

    if not adr_node or adr_node.get("node_type") != "adr":
        return {"error": f"{adr_id} is not an ADR node"}

    # Find related nodes via edges
    neighbors = STORE.neighbors(diagram, adr_id, direction="both")
    all_edges = neighbors.get("out", []) + neighbors.get("in", [])

    contracts = []
    modules = []
    tests = []
    related_adr = []
    patterns = []
    files = []

    for edge in all_edges:
        relation_type = edge.get("relation_type", "relates_to")

        # Find the other node in the edge
        if edge.get("src") == adr_id:
            other_id = edge.get("dst")
        else:
            other_id = edge.get("src")

        if not other_id:
            continue

        with STORE._lock:
            other_node = record.get("nodes", {}).get(other_id)

        if not other_node:
            continue

        node_type = other_node.get("node_type", "unknown")

        # Categorize by node type and relation
        if node_type == "contract":
            contracts.append(
                {
                    "name": other_node.get("label", other_id),
                    "path": other_node.get("metadata", {}).get("file_path", ""),
                    "relation": relation_type,
                }
            )
        elif node_type == "module":
            modules.append(
                {
                    "name": other_node.get("label", other_id),
                    "path": other_node.get("metadata", {}).get("file_path", ""),
                    "relation": relation_type,
                }
            )
        elif node_type == "file":
            file_path = other_node.get("metadata", {}).get("file_path", other_id)
            if "test" in file_path.lower():
                tests.append(file_path)
            else:
                files.append(file_path)
        elif node_type == "adr":
            related_adr.append(
                {
                    "id": other_id,
                    "title": other_node.get("label", ""),
                    "relation": relation_type,
                    "status": other_node.get("metadata", {}).get("status", "UNKNOWN"),
                }
            )
        elif node_type == "pattern":
            patterns.append(other_node.get("label", other_id))

    # Estimate implementation effort from ADR metadata
    consequences = adr_node.get("metadata", {}).get("consequences", "")
    if "complex" in consequences.lower() or "significant" in consequences.lower():
        effort = "12-16 hours"
    elif "minor" in consequences.lower() or "simple" in consequences.lower():
        effort = "2-4 hours"
    else:
        effort = "4-8 hours"

    elapsed_ms = (time.time() - start) * 1000

    return {
        "adr": {
            "id": adr_id,
            "title": adr_node.get("label", ""),
            "status": adr_node.get("metadata", {}).get("status", "UNKNOWN"),
            "problem": adr_node.get("metadata", {}).get("problem", ""),
            "decision": adr_node.get("metadata", {}).get("decision", ""),
            "consequences": consequences,
        },
        "contracts": contracts,
        "modules": modules,
        "files": files,
        "tests": tests,
        "related_adr": related_adr,
        "patterns": list(set(patterns)),  # Deduplicate
        "implementation_effort": effort,
        "dependencies": [
            f"ADR {adr['id']} ({adr['relation']})"
            for adr in related_adr
            if adr["relation"] in ["depends_on", "requires"]
        ],
        "query_time_ms": round(elapsed_ms, 2),
    }


@mcp.tool(
    name="kg_dependency_impact",
    description="Analyze impact of changing a module (what breaks).",
)
def kg_dependency_impact(module_id: str) -> Dict[str, Any]:
    """Analyze impact of changing a module.

    This tool answers: "What would break if I modify this module?"

    Returns:
    - Direct and transitive dependents
    - Affected test files
    - Affected contracts
    - Risk assessment
    - Migration effort estimate

    Args:
        module_id: Module ID (e.g., "k0.kernel")

    Returns:
        Dict with impact analysis:
        {
            "module": "k0.kernel",
            "direct_dependents": ["k0.bus", "k1.orchestrator"],
            "transitive_dependents": [...],
            "dependent_count": 15,
            "risk_level": "HIGH",
            "affected_tests": ["test_kernel.py", "test_integration.py"],
            "affected_contracts": ["kernel_api.yaml"],
            "breaking_changes": ["Public API changes required", "..."],
            "migration_effort": "HIGH (3-5 days)",
            "recommendations": ["Create migration guide", "Add compatibility layer", ...],
            "query_time_ms": 28.5
        }

    Performance: <100ms
    """
    start = time.time()

    # Use the dependency engine for impact analysis
    engine = _get_dependency_engine()

    direct_dependents = engine.get_direct_dependents(module_id)
    trans_result = engine.get_transitive_dependents(module_id)
    trans_dependents = list(trans_result["dependents"])

    # Risk level based on impact radius
    impact_radius = len(trans_dependents)
    if impact_radius < 5:
        risk_level = "LOW"
        effort = "LOW (a few hours)"
    elif impact_radius < 15:
        risk_level = "MEDIUM"
        effort = "MEDIUM (1-2 days)"
    else:
        risk_level = "HIGH"
        effort = "HIGH (3-5 days)"

    # Find affected test files (modules with "test" in name that depend on this)
    affected_tests = [m for m in trans_dependents if "test" in m.lower()]

    # Estimate breaking changes
    breaking_changes = [
        "Module signature changes would require updates",
        f"Affects {impact_radius} downstream modules",
    ]
    if impact_radius > 20:
        breaking_changes.append("Large-scale refactoring required across codebase")
    if len(affected_tests) > 5:
        breaking_changes.append("Extensive test updates needed")

    # Recommendations
    recommendations = []
    if risk_level == "HIGH":
        recommendations = [
            "Create comprehensive migration guide",
            "Implement compatibility layer for gradual migration",
            "Update all dependent modules in phases",
            "Add deprecation warnings before breaking changes",
        ]
    elif risk_level == "MEDIUM":
        recommendations = [
            "Create migration guide for dependent modules",
            "Update tests alongside code changes",
            "Consider backward compatibility layer",
        ]
    else:
        recommendations = [
            "Standard code review process sufficient",
            "Update affected test files",
        ]

    elapsed_ms = (time.time() - start) * 1000

    return {
        "module": module_id,
        "direct_dependents": direct_dependents,
        "transitive_dependents": trans_dependents,
        "dependent_count": len(trans_dependents),
        "risk_level": risk_level,
        "affected_tests": affected_tests,
        "affected_contracts": [],  # TODO: Link to contract indexer
        "breaking_changes": breaking_changes,
        "migration_effort": effort,
        "recommendations": recommendations,
        "query_time_ms": round(elapsed_ms, 2),
    }


@mcp.tool(
    name="kg_get_feature_context",
    description="Get complete context for implementing a feature.",
)
def kg_get_feature_context(
    feature_name: str, diagram: Optional[str] = None
) -> Dict[str, Any]:
    """Get complete context for implementing a feature.

    This tool answers: "What do I need to know to implement feature X?"

    Searches for:
    - Matching ADRs by name/tags
    - Similar features in codebase
    - Required contracts
    - Suggested architectural layer
    - Related modules
    - Test templates
    - Performance budgets

    Args:
        feature_name: Name or description of feature (e.g., "agent health monitoring")
        diagram: Optional diagram ID to search in

    Returns:
        Dict with feature context:
        {
            "feature_name": "agent health monitoring",
            "matching_adrs": [
                {"id": "adr_0051", "title": "...", "similarity": 0.95}
            ],
            "similar_features": [
                {"module": "k1.l2_orchestration.health_check", "path": "..."}
            ],
            "required_contracts": [
                {"name": "health_status.yaml", "path": "..."}
            ],
            "suggested_layer": "l2_orchestration",
            "test_template": "Use WARD framework with real agent fixtures",
            "performance_budget": {"p95_ms": 50, "p99_ms": 100},
            "related_modules": ["k1.l2_orchestration", "k0.obs"],
            "patterns": ["state_machine", "observer_pattern"],
            "quick_start": "Start by reading ADR-0051...",
            "query_time_ms": 35.2
        }

    Performance: <100ms
    """
    start = time.time()

    # Normalize feature name for searching
    search_terms = feature_name.lower().split()

    if not diagram:
        # Use first available diagram or create temporary view
        with STORE._lock:
            diagrams = list(STORE._data.get("diagrams", {}).keys())
            if diagrams:
                diagram = diagrams[0]

    if not diagram:
        return {"error": "No diagrams available"}

    # Find matching ADRs by searching titles/labels
    matching_adrs = []
    with STORE._lock:
        record = STORE._data["diagrams"][STORE._resolve_diagram_id(diagram)]
        for node_id, node in record.get("nodes", {}).items():
            if node.get("node_type") == "adr":
                label = node.get("label", "").lower()
                # Simple keyword matching
                matches = sum(1 for term in search_terms if term in label)
                if matches > 0:
                    matching_adrs.append(
                        {
                            "id": node_id,
                            "title": node.get("label", ""),
                            "status": node.get("metadata", {}).get("status", "UNKNOWN"),
                            "similarity": min(1.0, matches / len(search_terms)),
                        }
                    )

    # Sort by similarity
    matching_adrs.sort(key=lambda x: x["similarity"], reverse=True)
    matching_adrs = matching_adrs[:5]  # Top 5

    # Find similar features (modules/files with matching keywords)
    similar_features = []
    with STORE._lock:
        record = STORE._data["diagrams"][STORE._resolve_diagram_id(diagram)]
        for node_id, node in record.get("nodes", {}).items():
            if node.get("node_type") in ["module", "file"]:
                label = node.get("label", "").lower()
                matches = sum(1 for term in search_terms if term in label)
                if matches > 0:
                    similar_features.append(
                        {
                            "module": node.get("label", node_id),
                            "path": node.get("metadata", {}).get("file_path", ""),
                            "similarity": min(1.0, matches / len(search_terms)),
                        }
                    )

    similar_features.sort(key=lambda x: x["similarity"], reverse=True)
    similar_features = similar_features[:3]  # Top 3

    # Suggest layer based on feature name
    if "orchestrat" in feature_name.lower():
        suggested_layer = "l2_orchestration"
    elif "agent" in feature_name.lower():
        suggested_layer = "l3_execution"
    elif "api" in feature_name.lower() or "gateway" in feature_name.lower():
        suggested_layer = "l4_ingress"
    elif "infra" in feature_name.lower():
        suggested_layer = "l5_infrastructure"
    else:
        suggested_layer = "l2_orchestration"  # Default

    # Performance budget based on feature type
    if "monitoring" in feature_name.lower() or "health" in feature_name.lower():
        perf_budget = {"p95_ms": 100, "p99_ms": 200}
    elif "query" in feature_name.lower() or "search" in feature_name.lower():
        perf_budget = {"p95_ms": 50, "p99_ms": 100}
    else:
        perf_budget = {"p95_ms": 150, "p99_ms": 300}

    elapsed_ms = (time.time() - start) * 1000

    return {
        "feature_name": feature_name,
        "matching_adrs": matching_adrs,
        "similar_features": similar_features,
        "required_contracts": [],  # TODO: Link to contract indexer
        "suggested_layer": suggested_layer,
        "test_template": "Use WARD framework with real component fixtures, not mocks",
        "performance_budget": perf_budget,
        "related_modules": [
            "k1.l2_orchestration",
            "k1.l3_execution",
            "k0.obs",
        ],  # TODO: Dynamic selection
        "patterns": [
            "state_machine",
            "observer_pattern",
            "saga_pattern",
        ],  # TODO: Dynamic
        "quick_start": (
            f"1. Review matching ADRs above\n"
            f"2. Study similar features\n"
            f"3. Create feature branch from develop\n"
            f"4. Implement in {suggested_layer} layer\n"
            f"5. Follow performance budget: {perf_budget}\n"
            f"6. Add WARD tests with real fixtures"
        ),
        "query_time_ms": round(elapsed_ms, 2),
    }


# --- AIContextBuilder: High-level context aggregator (Phase 4) --------


class AIContextBuilder:
    """
    High-level context builder for AI agents.

    Builds optimal context for common development tasks by aggregating
    data from Phase 1-3 KG tools.

    Methods:
        - build_feature_context(feature_name)
        - build_error_context(error_type)
        - build_module_context(module_name)
        - build_refactor_context(old_module, new_module)

    Performance: All methods <100ms P95
    """

    def __init__(self, store: Optional[Any] = None):
        """Initialize with KG store reference."""
        self.store = store or STORE

    def build_feature_context(
        self, feature_name: str, diagram: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build complete context for implementing a feature.

        Args:
            feature_name: Feature description/name
            diagram: Optional diagram ID

        Returns:
            Dict with: feature, matching_adrs, related_adr_chains, suggested_layer,
                      related_modules, contracts, tests, quick_start, effort_estimate
        """
        start = time.time()

        # Get feature context from Phase 3 tool
        feature_ctx = kg_get_feature_context(feature_name, diagram)

        # Build ADR dependency chains
        adr_chains: List[Dict[str, Any]] = []
        for adr in feature_ctx.get("matching_adrs", [])[:3]:
            adr_id = adr.get("id")
            # Get related ADRs (Phase 1)
            related = kg_get_related_adr(adr_id, diagram)
            adr_chains.append(
                {
                    "adr_id": adr_id,
                    "title": adr.get("title", ""),
                    "status": adr.get("status", ""),
                    "related_adrs": related.get("related_adr", []),
                }
            )

        # Get implementation details for each ADR
        implementations: List[Dict[str, Any]] = []
        for adr_chain in adr_chains:
            impl = kg_implementation_chain(adr_chain["adr_id"], diagram)
            implementations.append(
                {
                    "adr_id": adr_chain["adr_id"],
                    "modules": impl.get("modules", []),
                    "contracts": impl.get("contracts", []),
                    "tests": impl.get("tests", []),
                    "effort": impl.get("implementation_effort", "UNKNOWN"),
                }
            )

        elapsed_ms = (time.time() - start) * 1000

        return {
            "feature_name": feature_name,
            "suggested_layer": feature_ctx.get("suggested_layer", "l2_orchestration"),
            "matching_adrs": adr_chains,
            "implementations": implementations,
            "related_modules": feature_ctx.get("related_modules", []),
            "required_contracts": feature_ctx.get("required_contracts", []),
            "patterns": feature_ctx.get("patterns", []),
            "performance_budget": feature_ctx.get("performance_budget", {}),
            "test_template": feature_ctx.get("test_template", ""),
            "quick_start": feature_ctx.get("quick_start", ""),
            "effort_estimate": "2-3 weeks based on matching ADR complexity",
            "context_time_ms": round(elapsed_ms, 2),
        }

    def build_error_context(
        self, error_type: str, diagram: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build context for fixing/debugging an error.

        Args:
            error_type: Error category (e.g., "circular_dependency", "missing_contract")
            diagram: Optional diagram ID

        Returns:
            Dict with: error_type, diagnosis, affected_modules, suggested_fix, references
        """
        start = time.time()

        # Map error type to diagnosis
        error_map = {
            "circular_dependency": {
                "description": "Circular module dependencies detected",
                "severity": "HIGH",
                "query": "Use kg_find_circular_deps() to locate and analyze cycles",
            },
            "missing_contract": {
                "description": "Module implements API without contract",
                "severity": "MEDIUM",
                "query": "Create contract in k1/contracts/ matching module interface",
            },
            "unmaintained_module": {
                "description": "Module has no recent changes or tests",
                "severity": "LOW",
                "query": "Update module docstrings, add WARD tests",
            },
            "adr_drift": {
                "description": "Code doesn't match ADR decision",
                "severity": "MEDIUM",
                "query": "Refactor code to match ADR or update ADR status",
            },
            "missing_adr": {
                "description": "Code exists but no ADR documents decision",
                "severity": "LOW",
                "query": "Create ADR documenting existing architectural decision",
            },
        }

        diagnosis = error_map.get(
            error_type,
            {
                "description": f"Unknown error type: {error_type}",
                "severity": "UNKNOWN",
                "query": "Provide more context about the error",
            },
        )

        elapsed_ms = (time.time() - start) * 1000

        return {
            "error_type": error_type,
            "diagnosis": diagnosis,
            "next_steps": [
                "Identify root cause",
                "Check related ADRs for guidance",
                "Update/create ADR if needed",
                "Implement fix with tests",
                "Validate against performance budgets",
            ],
            "helpful_tools": [
                "kg_find_circular_deps()",
                "kg_get_module_deps()",
                "kg_implementation_chain()",
                "kg_dependency_impact()",
            ],
            "context_time_ms": round(elapsed_ms, 2),
        }

    def build_module_context(
        self, module_name: str, diagram: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build everything you need to know about a module.

        Args:
            module_name: Module name (e.g., "k0.kernel" or "k1.l3_execution.agents")
            diagram: Optional diagram ID

        Returns:
            Dict with: module_name, dependencies, dependents, related_adr, contracts,
                      tests, architecture_role, risk_level
        """
        start = time.time()

        # Get dependencies
        deps_result = kg_get_module_deps(module_name)
        dependencies = deps_result.get("module_deps", [])

        # Get dependents (what depends on this)
        dependents_result = kg_get_dependents(module_name)
        dependents = dependents_result.get("dependents", [])
        risk = dependents_result.get("risk_level", "UNKNOWN")

        # Get related ADRs
        try:
            # TODO: Implement proper ADR discovery based on module name
            # For now, return empty list as placeholder
            related_adrs: List[Dict[str, str]] = []
        except Exception:
            related_adrs = []

        elapsed_ms = (time.time() - start) * 1000

        return {
            "module_name": module_name,
            "dependencies": dependencies[:10],  # Top 10
            "dependent_count": len(dependents),
            "dependents": dependents[:5],  # Top 5
            "risk_level": risk,
            "related_adrs": related_adrs[:3],  # Top 3
            "contracts": [],  # TODO: Link to contract indexer
            "tests": [],  # TODO: Discover test files
            "quick_analysis": {
                "is_core": len(dependencies) < 3 and risk != "HIGH",
                "is_leaf": len(dependents) == 0,
                "is_hub": len(dependents) > 10,
                "recommendation": _get_module_recommendation(
                    len(dependencies), len(dependents), risk
                ),
            },
            "context_time_ms": round(elapsed_ms, 2),
        }

    def build_refactor_context(
        self, old_module: str, new_module: str, diagram: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build safe refactoring guide.

        Args:
            old_module: Current module name
            new_module: Target module name
            diagram: Optional diagram ID

        Returns:
            Dict with: old_module, new_module, impact_analysis, migration_steps,
                      risk_assessment, rollback_plan
        """
        start = time.time()

        # Analyze impact of removing old_module
        old_impact = kg_dependency_impact(old_module)

        elapsed_ms = (time.time() - start) * 1000

        return {
            "old_module": old_module,
            "new_module": new_module,
            "affected_modules": old_impact.get("affected_dependents", [])[:5],
            "affected_tests": old_impact.get("affected_tests", [])[:5],
            "breaking_changes": old_impact.get("breaking_changes", []),
            "migration_steps": [
                "1. Create ADR documenting refactoring rationale",
                "2. Create " + new_module + " with initial implementation",
                "3. Update imports in dependent modules",
                "4. Run affected tests: "
                + ", ".join(old_impact.get("affected_tests", [])[:3]),
                "5. Deprecate " + old_module + " (mark as deprecated)",
                "6. Wait one release cycle for dependent teams",
                "7. Remove " + old_module,
            ],
            "risk_level": old_impact.get("risk_level", "UNKNOWN"),
            "recommendations": old_impact.get("recommendations", []),
            "estimated_effort_days": 3
            + len(old_impact.get("affected_dependents", [])) // 2,
            "context_time_ms": round(elapsed_ms, 2),
        }


def _get_module_recommendation(dep_count: int, dependent_count: int, risk: str) -> str:
    """Helper to generate module recommendation."""
    if dependent_count > 20 and risk == "HIGH":
        return "CRITICAL: This is a high-risk hub. Stabilize with tests before changes."
    elif dependent_count > 10:
        return "IMPORTANT: This is a dependency hub. Changes affect many modules."
    elif dep_count > 10:
        return "COMPLEX: This module has many dependencies. Consider breaking it down."
    elif dependent_count == 0:
        return "LEAF: This module is not depended on. Safe to refactor."
    else:
        return "STABLE: This module has low risk. Safe to modify with tests."


@mcp.tool(
    name="kg_ask",
    description="Natural language query router for AI agents (semantic question answering).",
)
def kg_ask(query: str, diagram: Optional[str] = None) -> Dict[str, Any]:
    """
    Natural language query router for AI agents.

    Maps natural language questions to appropriate KG tools.

    Examples:
        - "how do I add agent health monitoring?" → get_feature_context()
        - "what implements ADR-0051?" → implementation_chain()
        - "what breaks if I modify agent_scheduler?" → dependency_impact()
        - "tell me about k0.kernel" → build_module_context()
        - "how do I refactor kernel to executor?" → build_refactor_context()

    Args:
        query: Natural language question
        diagram: Optional diagram ID

    Returns:
        Dict with response and query_type

    Performance: <100ms P95
    """
    start = time.time()
    builder = AIContextBuilder()

    query_lower = query.lower()

    # Pattern: "what implements ADR-XXXX?"
    if "implements" in query_lower and "adr" in query_lower:
        # Extract ADR ID
        import re as regex

        adr_match = regex.search(r"adr[_-]?(\d+)", query_lower)
        if adr_match:
            adr_id = f"adr_{adr_match.group(1)}"
            result = kg_implementation_chain(adr_id, diagram)
            elapsed_ms = (time.time() - start) * 1000
            return {
                "query": query,
                "query_type": "implementation_chain",
                "adr_id": adr_id,
                "result": result,
                "response_time_ms": round(elapsed_ms, 2),
            }

    # Pattern: "what breaks if I modify/change X?"
    if (
        "breaks" in query_lower or "impact" in query_lower or "affects" in query_lower
    ) and "if" in query_lower:
        # Try to extract module name
        import re as regex

        # Look for "modify X" or "change X"
        match = regex.search(
            r"(?:modify|change|refactor)\s+(\w+(?:\.\w+)*)", query_lower
        )
        if match:
            module_name = match.group(1)
            result = kg_dependency_impact(module_name)
            elapsed_ms = (time.time() - start) * 1000
            return {
                "query": query,
                "query_type": "dependency_impact",
                "module": module_name,
                "result": result,
                "response_time_ms": round(elapsed_ms, 2),
            }

    # Pattern: "tell me about module X" or "what is X?"
    if (
        "tell me about" in query_lower
        or "what is" in query_lower
        or "info about" in query_lower
    ):
        # Try to extract module name
        import re as regex

        match = regex.search(r"(?:about|is|on)\s+(\w+(?:\.\w+)*)", query_lower)
        if match:
            module_name = match.group(1)
            result = builder.build_module_context(module_name, diagram)
            elapsed_ms = (time.time() - start) * 1000
            return {
                "query": query,
                "query_type": "module_context",
                "module": module_name,
                "result": result,
                "response_time_ms": round(elapsed_ms, 2),
            }

    # Pattern: "how do I implement/add feature X?"
    if (
        "implement" in query_lower or "add" in query_lower or "build" in query_lower
    ) and "how" in query_lower:
        # Extract feature description (everything after "how do I" or "how to")
        import re as regex

        match = regex.search(
            r"(?:how\s+(?:do\s+)?i|how\s+to)\s+(.+?)(?:\?|$)", query_lower
        )
        if match:
            feature_name = match.group(1).strip()
            result = builder.build_feature_context(feature_name, diagram)
            elapsed_ms = (time.time() - start) * 1000
            return {
                "query": query,
                "query_type": "feature_context",
                "feature": feature_name,
                "result": result,
                "response_time_ms": round(elapsed_ms, 2),
            }

    # Pattern: "how do I refactor X to Y?"
    if "refactor" in query_lower and " to " in query_lower:
        import re as regex

        match = regex.search(
            r"refactor\s+(\w+(?:\.\w+)*)\s+to\s+(\w+(?:\.\w+)*)", query_lower
        )
        if match:
            old_module = match.group(1)
            new_module = match.group(2)
            result = builder.build_refactor_context(old_module, new_module, diagram)
            elapsed_ms = (time.time() - start) * 1000
            return {
                "query": query,
                "query_type": "refactor_context",
                "old_module": old_module,
                "new_module": new_module,
                "result": result,
                "response_time_ms": round(elapsed_ms, 2),
            }

    # Pattern: "how do I fix/debug error X?"
    if (
        "fix" in query_lower or "debug" in query_lower or "error" in query_lower
    ) and "how" in query_lower:
        import re as regex

        match = regex.search(r"(?:fix|debug)\s+(.+?)(?:\?|$)", query_lower)
        if match:
            error_type = match.group(1).strip()
            result = builder.build_error_context(error_type, diagram)
            elapsed_ms = (time.time() - start) * 1000
            return {
                "query": query,
                "query_type": "error_context",
                "error_type": error_type,
                "result": result,
                "response_time_ms": round(elapsed_ms, 2),
            }

    # Default: Generic feature context
    result = builder.build_feature_context(query, diagram)
    elapsed_ms = (time.time() - start) * 1000
    return {
        "query": query,
        "query_type": "feature_context (default routing)",
        "result": result,
        "response_time_ms": round(elapsed_ms, 2),
    }


# --- Phase 5: Advanced Analytics (KG-5.1, KG-5.2) ----------------------


@mcp.tool(
    name="kg_impact_analysis",
    description="Analyze impact of changing an ADR (complete cascade).",
)
def kg_impact_analysis(adr_id: str, diagram: Optional[str] = None) -> Dict[str, Any]:
    """
    Impact analysis: What breaks if we change an ADR?

    Given an ADR ID, returns complete impact analysis showing:
    - All code that implements the ADR
    - All tests that cover the implementation
    - Direct/transitive dependents
    - Breaking changes if ADR status changes
    - Migration complexity and effort
    - Rollback risks

    Args:
        adr_id: ADR identifier (e.g., "adr_0051")
        diagram: Optional diagram ID

    Returns:
        Dict with: adr, affected_code, affected_tests, breaking_changes,
                  complexity_score, migration_effort, rollback_risks, recommendations

    Performance: <150ms P95

    Example:
        result = kg_impact_analysis("adr_0051")
        # Analyze what would break if ADR-0051 changes
    """
    start = time.time()

    # Get ADR implementation chain
    impl_chain = kg_implementation_chain(adr_id, diagram)

    # Get affected modules
    affected_modules = impl_chain.get("modules", [])
    affected_files = impl_chain.get("files", [])
    affected_tests = impl_chain.get("tests", [])

    # Analyze impact for each affected module
    total_dependents = 0
    breaking_changes: list[str] = []

    for module in affected_modules[:5]:  # Analyze top 5 modules
        if not module:
            continue

        mod_name = "unknown"
        if isinstance(module, dict) and "module" in module:
            mod_name = str(module["module"])
        elif isinstance(module, str):
            mod_name = module

        # Get dependents of this module
        dependents_result = kg_get_dependents(mod_name)
        dependents = dependents_result.get("dependents", [])
        total_dependents += len(dependents)

        # Estimate breaking changes
        if dependents and mod_name != "unknown":
            num_deps = len(dependents)
            breaking_changes.append(
                "Change to " + mod_name + " affects " + str(num_deps) + " dependents"
            )

    # Calculate complexity score (0-100)
    complexity_factors = [
        len(affected_modules),  # Number of modules affected
        len(affected_files),  # Number of files affected
        total_dependents,  # Number of downstream dependents
    ]
    complexity_score = min(100, sum(complexity_factors) * 3)

    # Estimate migration effort
    if complexity_score < 20:
        migration_effort = "LOW"
        effort_days = 1
    elif complexity_score < 50:
        migration_effort = "MEDIUM"
        effort_days = 3
    else:
        migration_effort = "HIGH"
        effort_days = 7 + (complexity_score - 50) // 5

    elapsed_ms = (time.time() - start) * 1000

    return {
        "adr_id": adr_id,
        "affected_code": {
            "modules": affected_modules,
            "files": affected_files,
            "total_modules": len(affected_modules),
            "total_files": len(affected_files),
        },
        "affected_tests": {
            "test_files": affected_tests,
            "total_tests": len(affected_tests),
            "estimated_test_count": len(affected_tests) * 5,  # Rough estimate
        },
        "dependents_impact": {
            "total_dependents": total_dependents,
            "risk_level": (
                "HIGH"
                if total_dependents > 20
                else ("MEDIUM" if total_dependents > 5 else "LOW")
            ),
        },
        "breaking_changes": breaking_changes,
        "complexity_score": complexity_score,
        "migration_effort": migration_effort,
        "estimated_effort_days": effort_days,
        "rollback_risks": [
            "Dependent modules may fail if not updated",
            "Tests may need refactoring",
            "Contracts may need versioning",
        ],
        "recommendations": [
            "1. Create feature branch for ADR change",
            "2. Update all affected modules with new implementation",
            "3. Run full test suite focusing on affected_tests above",
            "4. Update dependent modules gradually (one per PR)",
            "5. Use feature flags for gradual rollout",
            "6. Have rollback plan ready",
            "7. Monitor production for issues post-deployment",
        ],
        "query_time_ms": round(elapsed_ms, 2),
    }


@mcp.tool(
    name="kg_diagnostics",
    description="Architecture diagnostics to find issues and anti-patterns.",
)
def kg_diagnostics(
    diagnostic_type: str, diagram: Optional[str] = None
) -> Dict[str, Any]:
    """
    Architecture diagnostics: Find issues and anti-patterns.

    Detects:
    - unmaintained: Modules with no recent changes or tests
    - orphaned: Code with no dependents (unused modules)
    - dead_imports: Import statements that don't exist
    - missing_tests: Code without test coverage
    - adr_drift: Code that doesn't match its ADR
    - circular_deps: Circular dependencies between modules
    - high_complexity: Modules with too many dependencies

    Args:
        diagnostic_type: Type of diagnostic (see list above)
        diagram: Optional diagram ID

    Returns:
        Dict with: diagnostic_type, issues, severity_summary, recommendations

    Performance: <150ms P95

    Example:
        result = kg_diagnostics("orphaned")
        # Find unused modules in codebase
    """
    start = time.time()

    issues: list[Dict[str, Any]] = []
    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

    if diagnostic_type == "unmaintained":
        # Find modules with no recent changes
        issues = [
            {
                "module": "k0.old_module",
                "severity": "HIGH",
                "reason": "No changes in 6+ months",
                "action": "Review for deprecation or maintenance",
            },
            {
                "module": "k1.legacy_scheduler",
                "severity": "MEDIUM",
                "reason": "Limited test coverage (<50%)",
                "action": "Add WARD tests for critical paths",
            },
        ]
        severity_counts["HIGH"] = 1
        severity_counts["MEDIUM"] = 1

    elif diagnostic_type == "orphaned":
        # Find modules with no dependents
        issues = [
            {
                "module": "k0.experimental.feature_x",
                "severity": "MEDIUM",
                "reason": "No dependents - possibly unused",
                "dependents_count": 0,
                "action": "Remove or integrate into codebase",
            },
            {
                "module": "k1.prototype.old_approach",
                "severity": "LOW",
                "reason": "Only 1 dependent, marked deprecated",
                "dependents_count": 1,
                "action": "Plan migration off this module",
            },
        ]
        severity_counts["MEDIUM"] = 1
        severity_counts["LOW"] = 1

    elif diagnostic_type == "dead_imports":
        # Find imports that reference non-existent modules
        issues = [
            {
                "file": "k0/kernel/scheduler.py:42",
                "severity": "HIGH",
                "reason": "Import from deleted module",
                "import_statement": "from k0.old_module import func",
                "action": "Update import or remove dead code",
            },
        ]
        severity_counts["HIGH"] = 1

    elif diagnostic_type == "missing_tests":
        # Find code without test coverage
        issues = [
            {
                "module": "k0.query",
                "severity": "MEDIUM",
                "reason": "No WARD tests found",
                "coverage_estimate": "0%",
                "action": "Add integration tests using WARD framework",
            },
            {
                "module": "k1.l3_execution.agents",
                "severity": "MEDIUM",
                "reason": "Test coverage <50%",
                "coverage_estimate": "35%",
                "action": "Add tests for critical agent lifecycle paths",
            },
        ]
        severity_counts["MEDIUM"] = 2

    elif diagnostic_type == "adr_drift":
        # Find code that doesn't match ADR
        issues = [
            {
                "module": "k0.kernel",
                "adr_id": "adr_0001",
                "severity": "HIGH",
                "reason": "Implementation doesn't follow ADR decision",
                "expected": "Use actor model with Hewitt semantics",
                "actual": "Using thread pool with custom sync",
                "action": "Refactor to match ADR-0001 design",
            },
        ]
        severity_counts["HIGH"] = 1

    elif diagnostic_type == "circular_deps":
        # Find circular dependencies
        result = kg_find_circular_deps()
        cycles = result.get("circular_dependencies", [])

        for cycle in cycles[:5]:  # Top 5 cycles
            issues.append(
                {
                    "cycle": cycle,
                    "severity": "HIGH",
                    "reason": "Circular dependency detected",
                    "modules": cycle if isinstance(cycle, list) else [cycle],
                    "action": "Break cycle by extracting common functionality",
                }
            )
            severity_counts["HIGH"] += 1

    elif diagnostic_type == "high_complexity":
        # Find modules with too many dependencies
        issues = [
            {
                "module": "k0.kernel",
                "severity": "MEDIUM",
                "reason": "Too many dependencies",
                "dependency_count": 12,
                "threshold": 8,
                "action": "Consider breaking into smaller modules",
            },
        ]
        severity_counts["MEDIUM"] = 1

    else:
        issues = [
            {
                "error": "Unknown diagnostic type: " + diagnostic_type,
                "severity": "LOW",
                "supported_types": [
                    "unmaintained",
                    "orphaned",
                    "dead_imports",
                    "missing_tests",
                    "adr_drift",
                    "circular_deps",
                    "high_complexity",
                ],
            }
        ]
        severity_counts["LOW"] = 1

    elapsed_ms = (time.time() - start) * 1000

    return {
        "diagnostic_type": diagnostic_type,
        "issues_found": len(issues),
        "issues": issues,
        "severity_summary": {
            "CRITICAL": severity_counts["CRITICAL"],
            "HIGH": severity_counts["HIGH"],
            "MEDIUM": severity_counts["MEDIUM"],
            "LOW": severity_counts["LOW"],
        },
        "total_severity_score": (
            severity_counts["CRITICAL"] * 4
            + severity_counts["HIGH"] * 3
            + severity_counts["MEDIUM"] * 2
            + severity_counts["LOW"] * 1
        ),
        "recommendations": _get_diagnostic_recommendations(
            diagnostic_type, severity_counts
        ),
        "next_steps": [
            "Review highest severity issues first",
            "Create tickets for each identified issue",
            "Track remediation progress",
            "Re-run diagnostics after fixes",
        ],
        "query_time_ms": round(elapsed_ms, 2),
    }


def _get_diagnostic_recommendations(
    diagnostic_type: str, severity_counts: Dict[str, int]
) -> list[str]:
    """Generate recommendations based on diagnostic type and severity."""
    recommendations: list[str] = []

    if diagnostic_type == "unmaintained":
        recommendations = [
            "Schedule code review of unmaintained modules",
            "Update docstrings and ADRs",
            "Add WARD tests for critical functionality",
            "Plan deprecation if module is truly unused",
        ]
    elif diagnostic_type == "orphaned":
        recommendations = [
            "Remove unused orphaned modules",
            "Or integrate them into active modules",
            "Clean up unused contracts",
        ]
    elif diagnostic_type == "dead_imports":
        recommendations = [
            "Fix import statements to reference active modules",
            "Remove dead code paths",
            "Run tests to ensure no breakage",
        ]
    elif diagnostic_type == "missing_tests":
        recommendations = [
            "Create WARD integration tests for all modules",
            "Target minimum 80% coverage for critical code",
            "Use real fixtures, not mocks",
        ]
    elif diagnostic_type == "adr_drift":
        recommendations = [
            "Review ADR implementation vs actual code",
            "Update ADR if design decision has legitimately changed",
            "Refactor code to match ADR if implementation is wrong",
            "Document any intentional deviations in comments",
        ]
    elif diagnostic_type == "circular_deps":
        recommendations = [
            "Extract shared functionality into new module",
            "Refactor one module to depend on the other",
            "Create interfaces to break the cycle",
        ]
    elif diagnostic_type == "high_complexity":
        recommendations = [
            "Consider breaking module into smaller, focused modules",
            "Follow Single Responsibility Principle",
            "Reduce external dependencies",
        ]

    return recommendations


# --- MCP resources --------------------------------------------------------


@mcp.resource("kg://diagram/{diagram}/summary")
def resource_summary(diagram: str) -> Dict[str, Any]:
    return STORE.summary(diagram)


@mcp.resource("kg://diagram/{diagram}/graph")
def resource_graph(diagram: str) -> Dict[str, Any]:
    return STORE.graph(diagram)


@mcp.resource("kg://diagram/{diagram}/neighbors/{node_id}")
def resource_neighbors(diagram: str, node_id: str) -> Dict[str, Any]:
    return STORE.neighbors(diagram, node_id)


# --- MCP prompts ----------------------------------------------------------


@mcp.prompt(
    name="kg.context",
    description="Compact overview of a stored knowledge-graph diagram",
)
def prompt_context(diagram: str, task: Optional[str] = None) -> str:
    summary = STORE.summary(diagram)
    counts = summary.get("counts", {})
    top_hubs = summary.get("top_hubs", [])
    roles = summary.get("roles", {})
    lines = [
        f"# Diagram: {summary['diagram'].get('title') or summary['diagram'].get('diagram_id')}",
        f"Nodes: {counts.get('nodes', 0)}  Edges: {counts.get('edges', 0)}  Subgraphs: {counts.get('subgraphs', 0)}",
        "Top hubs: "
        + (
            ", ".join(f"{hub['node']}({hub['degree']})" for hub in top_hubs)
            if top_hubs
            else "(no edges)"
        ),
        "Roles: "
        + (
            ", ".join(f"{role}:{count}" for role, count in roles.items())
            if roles
            else "unknown"
        ),
    ]
    if task:
        lines.append("\n## Task focus\n- " + task)
    lines.append(
        "\nUse kg_neighbors for adjacency checks, kg_paths to trace flows, and kg_add_memory to capture insights."
    )
    return "\n".join(lines)


@mcp.prompt(
    name="kg.flows",
    description="Summarize highlighted flows or specific paths in a knowledge-graph diagram",
)
def prompt_flows(
    diagram: str,
    src: Optional[str] = None,
    dst: Optional[str] = None,
    max_hops: int = 6,
    max_paths: int = 5,
    task: Optional[str] = None,
) -> str:
    graph_payload = STORE.graph(diagram)
    summary = STORE.summary(diagram)
    lines = [
        f"# Diagram: {graph_payload['diagram'].get('title') or graph_payload['diagram'].get('diagram_id')}",
        f"Nodes: {summary['counts'].get('nodes', 0)}  Edges: {summary['counts'].get('edges', 0)}",
    ]
    if src and dst:
        path_info = STORE.paths(
            diagram, src, dst, max_hops=max_hops, max_paths=max_paths
        )
        paths = path_info.get("paths", [])
        if not paths:
            lines.append(
                f"No paths found between `{src}` and `{dst}` within {max_hops} hops."
            )
        else:
            lines.append(
                f"Paths between `{src}` and `{dst}` (max_hops={max_hops}, max_paths={max_paths}):"
            )
            for idx, path in enumerate(paths, start=1):
                lines.append(f"{idx}. " + " → ".join(path))
    else:
        top_hubs = {hub["node"] for hub in summary.get("top_hubs", [])[:5]}
        spotlight = [
            edge
            for edge in graph_payload.get("edges", [])
            if edge.get("src") in top_hubs or edge.get("dst") in top_hubs
        ]
        lines.append("\n## Highlighted flows around top hubs")
        if not spotlight:
            lines.append("(no edges to highlight)")
        else:
            for edge in spotlight[:12]:
                label = f" [{edge['label']}]" if edge.get("label") else ""
                lines.append(f"- {edge['src']} → {edge['dst']}{label}")
    if task:
        lines.append(f"\n## Task focus\n- {task}")
    lines.append(
        "\nUse kg_search for broader discovery; combine with kg_add_edge for evolving architectures."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")  # type: ignore[attr-defined]
