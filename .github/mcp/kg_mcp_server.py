from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from collections import deque
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Tuple

from mcp.server.fastmcp import FastMCP

from mmd_parser import parse_mermaid, resolve_includes

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

MMD_ROOT_DEFAULT = Path(os.environ.get("MMD_ROOT", Path.cwd()))

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


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return slug or "diagram"


class KnowledgeGraphStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = RLock()
        self._data: Dict[str, Any] = {
            "version": 1,
            "created_at": time.time(),
            "updated_at": time.time(),
            "diagrams": {},
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
        except Exception as exc:  # pragma: no cover - I/O edge case
            log.warning("Failed to load KG store %s: %s", self.db_path, exc)
            return
        if not isinstance(payload, dict) or "diagrams" not in payload:
            log.warning("Invalid KG store format at %s, starting fresh", self.db_path)
            return
        self._data = {
            "version": payload.get("version", 1),
            "created_at": payload.get("created_at", time.time()),
            "updated_at": payload.get("updated_at", time.time()),
            "diagrams": payload.get("diagrams", {}),
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
        with self._lock:
            diagram_id = self._resolve_diagram_id(ref)
            if not diagram_id:
                raise KeyError(f"diagram_not_found: {ref}")
            record = self._data["diagrams"][diagram_id]
            return diagram_id, record

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

    def list_diagrams(self) -> List[Dict[str, Any]]:
        with self._lock:
            diagrams = []
            for diagram_id, record in self._data.get("diagrams", {}).items():
                diagrams.append(
                    {
                        "diagram_id": diagram_id,
                        "aliases": record.get("aliases", []),
                        "title": record.get("title"),
                        "description": record.get("description"),
                        "source_path": record.get("source_path"),
                        "counts": record.get("counts", {}),
                        "ingested_at": record.get("ingested_at"),
                        "updated_at": record.get("updated_at"),
                    }
                )
            diagrams.sort(key=lambda item: item.get("updated_at", 0.0), reverse=True)
            return diagrams

    def create_diagram(
        self, alias: str, title: Optional[str] = None, description: Optional[str] = None
    ) -> Dict[str, Any]:
        slug = alias.strip()
        if not slug:
            raise ValueError("alias_required")
        with self._lock:
            if slug in self._alias_index:
                raise ValueError(f"alias_already_exists: {slug}")
            diagram_id = str(uuid.uuid4())
            now = time.time()
            record = {
                "diagram_id": diagram_id,
                "aliases": [slug],
                "title": title or slug,
                "description": description,
                "nodes": {},
                "edges": [],
                "subgraphs": [],
                "ingested_at": None,
                "updated_at": now,
                "created_at": now,
            }
            self._data["diagrams"][diagram_id] = record
            self._reindex_unlocked()
            self._data["updated_at"] = now
            self._persist_unlocked()
            return record

    def ingest_from_path(
        self,
        path: Path,
        alias: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized = path.resolve()
        raw = normalized.read_text(encoding="utf-8")
        merged, includes = resolve_includes(raw, normalized.parent)
        nodes, edges, subs, styles = parse_mermaid(merged)
        now = time.time()
        with self._lock:
            existing_id = self._path_index.get(str(normalized))
            if existing_id:
                record = self._data["diagrams"][existing_id]
            else:
                existing_id = str(uuid.uuid4())
                record = {
                    "diagram_id": existing_id,
                    "aliases": [],
                    "created_at": now,
                    "nodes": {},
                    "edges": [],
                    "subgraphs": [],
                }
            existing_nodes = record.get("nodes", {})
            existing_edges = record.get("edges", [])

            node_map: Dict[str, Dict[str, Any]] = {}
            for node in nodes:
                previous = existing_nodes.get(node.id, {})
                node_map[node.id] = {
                    "id": node.id,
                    "label": node.label,
                    "shape": node.shape,
                    "classes": list(node.classes),
                    "subgraph_path": node.subgraph_path,
                    "props": dict(node.props),
                    "annotations": dict(previous.get("annotations", {})),
                    "memories": list(previous.get("memories", [])),
                    "origin": previous.get("origin", "diagram"),
                }
            # retain manual nodes not present in current diagram
            for node_id, payload in existing_nodes.items():
                if payload.get("origin") == "manual" and node_id not in node_map:
                    node_map[node_id] = payload

            diagram_edges = [
                {
                    "src": edge.src,
                    "dst": edge.dst,
                    "kind": edge.kind,
                    "label": edge.label,
                    "props": dict(edge.props),
                    "origin": "diagram",
                }
                for edge in edges
            ]
            manual_edges = [
                edge for edge in existing_edges if edge.get("origin") == "manual"
            ]

            record.update(
                {
                    "aliases": sorted(set(record.get("aliases", []))),
                    "title": title
                    or (
                        subs[0].title
                        if subs
                        else record.get("title") or normalized.stem
                    ),
                    "description": (
                        description
                        if description is not None
                        else record.get("description")
                    ),
                    "source_path": str(normalized),
                    "includes": includes,
                    "merged_content": merged,
                    "styles": styles,
                    "nodes": node_map,
                    "edges": self._merge_edges(diagram_edges + manual_edges),
                    "subgraphs": [
                        {"path": sg.path, "title": sg.title, "depth": sg.depth}
                        for sg in subs
                    ],
                    "ingested_at": now,
                }
            )
            if alias:
                aliases = set(record.get("aliases", []))
                aliases.add(alias)
                record["aliases"] = sorted(aliases)
            self._update_counts(record)
            self._touch(record)
            self._data["diagrams"][existing_id] = record
            self._reindex_unlocked()
            self._persist_unlocked()
            return record

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
    ) -> Dict[str, Any]:
        diagram_id, record = self._require_diagram(ref)
        with self._lock:
            node = record.get("nodes", {}).get(node_id, {})
            node.setdefault("id", node_id)
            node.setdefault("label", node_id)
            node.setdefault("shape", "auto")
            node.setdefault("classes", [])
            node.setdefault("subgraph_path", "")
            node.setdefault("props", {})
            node.setdefault("annotations", {})
            node.setdefault("memories", [])
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
            node["origin"] = origin
            record.setdefault("nodes", {})[node_id] = node
            self._update_counts(record)
            self._touch(record)
            self._data["diagrams"][diagram_id] = record
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
    ) -> Dict[str, Any]:
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
            merged = self._merge_edges(record.get("edges", []) + [edge_payload])
            record["edges"] = merged
            self._update_counts(record)
            self._touch(record)
            self._data["diagrams"][diagram_id] = record
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


def _infer_role(classes: Iterable[str]) -> Optional[str]:
    for cls in classes:
        key = cls.lower()
        if key in ROLE_MAP:
            return ROLE_MAP[key]
    return None


STORE = KnowledgeGraphStore(KG_STORE_PATH)


# --- MCP tools ------------------------------------------------------------


@mcp.tool()
def kg_list_diagrams() -> List[Dict[str, Any]]:
    """Return the diagrams tracked by the knowledge graph store."""
    return STORE.list_diagrams()


@mcp.tool()
def kg_create_diagram(
    alias: str, title: Optional[str] = None, description: Optional[str] = None
) -> Dict[str, Any]:
    """Create an empty diagram entry for manual knowledge capture."""
    return STORE.create_diagram(alias=alias, title=title, description=description)


@mcp.tool()
def kg_ingest(
    path: str,
    alias: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Ingest a Mermaid diagram into the knowledge graph store."""
    return STORE.ingest_from_path(
        Path(path), alias=alias, title=title, description=description
    )


@mcp.tool()
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
) -> Dict[str, Any]:
    """Add or update a node attached to a diagram."""
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
    )


@mcp.tool()
def kg_remove_node(diagram: str, node_id: str) -> Dict[str, Any]:
    """Remove a node and its incident edges from the diagram."""
    return STORE.remove_node(diagram, node_id)


@mcp.tool()
def kg_add_edge(
    diagram: str,
    src: str,
    dst: str,
    *,
    kind: str = "arrow",
    label: Optional[str] = None,
    props: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add or update an edge between two nodes."""
    return STORE.add_or_update_edge(
        diagram,
        src,
        dst,
        kind=kind,
        label=label,
        props=props,
        origin="manual",
    )


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
def kg_update_annotations(
    diagram: str, node_id: str, annotations: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge annotations into the node metadata."""
    return STORE.update_annotations(diagram, node_id, annotations)


@mcp.tool()
def kg_search(
    term: str, diagram: Optional[str] = None, limit: int = 20
) -> List[Dict[str, Any]]:
    """Search nodes and edges across the knowledge graph store."""
    return STORE.search(term, ref=diagram, limit=limit)


@mcp.tool()
def kg_neighbors(diagram: str, node_id: str, direction: str = "both") -> Dict[str, Any]:
    """Return adjacency information for the node in the diagram."""
    return STORE.neighbors(diagram, node_id, direction=direction)


@mcp.tool()
def kg_graph(diagram: str) -> Dict[str, Any]:
    """Return the full graph payload for a diagram."""
    return STORE.graph(diagram)


@mcp.tool()
def kg_summary(diagram: str) -> Dict[str, Any]:
    """Return a structural summary for a diagram."""
    return STORE.summary(diagram)


@mcp.tool()
def kg_paths(
    diagram: str, src: str, dst: str, max_hops: int = 6, max_paths: int = 5
) -> Dict[str, Any]:
    """Enumerate simple paths between two nodes."""
    return STORE.paths(diagram, src, dst, max_hops=max_hops, max_paths=max_paths)


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
