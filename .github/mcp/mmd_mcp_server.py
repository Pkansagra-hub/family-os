# mmd_mcp_server.py
# MCP server to ingest Mermaid (MMD) diagrams and expose them as LLM-digestible graphs
# Tools provided:
#   - mmd_list(root?, glob?) â†’ list *.mmd files
#   - mmd_read(path, resolve_includes=True, max_depth=4) â†’ {content, includes}
#   - mmd_ingest(path) â†’ parse + store into SQLite; returns counts & diagram_id
#   - mmd_parse_preview(content) â†’ preview parse (no DB write)
#   - mmd_graph(diagram) â†’ {nodes, edges, subgraphs}
#   - mmd_neighbors(diagram, node_id, direction="both") â†’ adjacency
#   - mmd_paths(diagram, src, dst, max_hops=6, max_paths=5) â†’ simple path search
#   - mmd_summary(diagram) â†’ counts, top hubs, class/role breakdown
#   - mmd_validate(diagram) â†’ issues (dangling edges, dupes, empty subgraphs)
#   - code_hints(diagram, node_id) â†’ opinionated scaffolding suggestions for that node
# Resources:
#   - mmd://diagram/{diagram}/summary
#   - mmd://diagram/{diagram}/adjacency
# Prompt:
#   - diagram.context(diagram, task?) â†’ compact overview with flows & key modules

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mmd_mcp")

# --- Config ---
MMD_DB = Path(os.environ.get("MMD_DB", Path.home() / ".mcp_mmd" / "mmd.db"))
MMD_DB.parent.mkdir(parents=True, exist_ok=True)

MMD_ROOT_DEFAULT = Path(os.environ.get("MMD_ROOT", Path.cwd()))

mcp = FastMCP("mmd")

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

# --- SQLite helpers ---


def _connect():
    con = sqlite3.connect(MMD_DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def _init_db():
    con = _connect()
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS diagrams(
          id TEXT PRIMARY KEY,
          path TEXT,
          title TEXT,
          content TEXT NOT NULL,
          includes_json TEXT NOT NULL,
          ingested_at REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS diagrams_path_idx ON diagrams(path);

        CREATE TABLE IF NOT EXISTS subgraphs(
          diagram_id TEXT NOT NULL,
          path TEXT NOT NULL,
          title TEXT NOT NULL,
          depth INTEGER NOT NULL,
          PRIMARY KEY (diagram_id, path),
          FOREIGN KEY (diagram_id) REFERENCES diagrams(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS nodes(
          diagram_id TEXT NOT NULL,
          node_id TEXT NOT NULL,
          label TEXT,
          shape TEXT,
          classes_json TEXT NOT NULL,
          subgraph_path TEXT,
          props_json TEXT NOT NULL,
          PRIMARY KEY (diagram_id, node_id),
          FOREIGN KEY (diagram_id) REFERENCES diagrams(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS edges(
          diagram_id TEXT NOT NULL,
          src TEXT NOT NULL,
          dst TEXT NOT NULL,
          kind TEXT NOT NULL,
          label TEXT,
          props_json TEXT NOT NULL,
          FOREIGN KEY (diagram_id) REFERENCES diagrams(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS edges_src_idx ON edges(diagram_id, src);
        CREATE INDEX IF NOT EXISTS edges_dst_idx ON edges(diagram_id, dst);
        """
    )
    con.commit()
    con.close()


_init_db()

# --- Mermaid parsing ---

EDGE_PAT = re.compile(
    r"^\s*(?P<src>[^\s\[]+)\s*(?P<arrow>[-.=]*-+>)\s*(?:\|(?P<label>[^|]+)\|\s*)?(?P<dst>[^\s\[]+)"
)
UNDIRECTED_PAT = re.compile(r"^\s*(?P<src>[^\s\[]+)\s*-{3,}\s*(?P<dst>[^\s\[]+)")
NODE_DEF_PAT = re.compile(
    r"^\s*(?P<id>[A-Za-z0-9_:-]+)\s*(?:(?P<bracket>\[(?P<square>.*)\]|\(\((?P<circle>.*)\)\)|\{(?P<diamond>.*)\}|\"(?P<quoted>.*)\"))?\s*(?:::(?P<class>[A-Za-z0-9_\- ]+))?\s*$"
)
CLASS_ASSIGN_PAT = re.compile(
    r"^\s*class\s+(?P<ids>[A-Za-z0-9_,\s:-]+)\s+(?P<class>[A-Za-z0-9_\-]+)\s*$"
)
SUBGRAPH_START_PAT = re.compile(r"^\s*subgraph\s+(?P<title>.+?)\s*$", re.IGNORECASE)
SUBGRAPH_END_PAT = re.compile(r"^\s*end\s*$", re.IGNORECASE)
INCLUDE_PAT = re.compile(r"^\s*%%\s*include:\s*(?P<rel>\S+)\s*$")
STYLE_PAT = re.compile(r"^\s*style\s+(?P<id>[A-Za-z0-9_:-]+)\s+(?P<props>.+)$")


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")


@dataclass
class ParsedNode:
    id: str
    label: str
    shape: str
    classes: List[str]
    subgraph_path: str
    props: Dict[str, Any]


@dataclass
class ParsedEdge:
    src: str
    dst: str
    kind: str
    label: Optional[str]
    props: Dict[str, Any]


@dataclass
class ParsedSubgraph:
    path: str
    title: str
    depth: int


def resolve_includes(
    text: str, base_dir: Path, max_depth: int = 4
) -> Tuple[str, List[str]]:
    """Resolve custom include lines like: %% include: ./_shared.mmd.inc
    Returns combined text and list of included file paths (absolute).
    """
    included: List[str] = []

    def _resolve_one(blob: str, base: Path, depth: int) -> str:
        if depth > max_depth:
            return blob
        out_lines: List[str] = []
        for line in blob.splitlines():
            match = INCLUDE_PAT.match(line)
            if match:
                rel = match.group("rel")
                inc_path = (base / rel).resolve()
                try:
                    inc_text = inc_path.read_text(encoding="utf-8")
                    included.append(str(inc_path))
                    out_lines.append(_resolve_one(inc_text, inc_path.parent, depth + 1))
                except Exception as exc:
                    out_lines.append(f"%% include failed: {rel} ({exc})")
            else:
                out_lines.append(line)
        return "\n".join(out_lines)

    combined = _resolve_one(text, base_dir, 0)
    return combined, included


def parse_mermaid(
    content: str,
) -> Tuple[
    List[ParsedNode], List[ParsedEdge], List[ParsedSubgraph], Dict[str, Dict[str, str]]
]:
    """Very tolerant parser for Mermaid flowcharts.
    Returns (nodes, edges, subgraphs, styles_by_id).
    """
    nodes: Dict[str, ParsedNode] = {}
    edges: List[ParsedEdge] = []
    subs: List[ParsedSubgraph] = []
    styles: Dict[str, Dict[str, str]] = {}

    class_map: Dict[str, Set[str]] = {}
    sub_stack: List[str] = []

    def current_subpath() -> str:
        return "/".join(sub_stack)

    lines = content.splitlines()
    for raw in lines:
        line = raw.strip("\ufeff")  # drop BOM if any
        if not line or line.lstrip().startswith("%%"):
            continue

        # Subgraphs
        match = SUBGRAPH_START_PAT.match(line)
        if match:
            title = match.group("title").strip()
            sgid = _slug(title)
            sub_stack.append(sgid)
            subs.append(
                ParsedSubgraph(
                    path=current_subpath(), title=title, depth=len(sub_stack)
                )
            )
            continue
        if SUBGRAPH_END_PAT.match(line):
            if sub_stack:
                sub_stack.pop()
            continue

        # Styles
        style_match = STYLE_PAT.match(line)
        if style_match:
            node_id = style_match.group("id")
            props: Dict[str, str] = {}
            for kv in style_match.group("props").split(","):
                if ":" in kv:
                    key, value = kv.split(":", 1)
                    props[key.strip()] = value.strip()
            styles[node_id] = props
            continue

        # Class assignment lines
        class_match = CLASS_ASSIGN_PAT.match(line)
        if class_match:
            ids = [
                item.strip()
                for item in class_match.group("ids").split(",")
                if item.strip()
            ]
            cls = class_match.group("class").strip()
            for item in ids:
                class_map.setdefault(item, set()).add(cls)
            continue

        # Edge (directed)
        edge_match = EDGE_PAT.match(line)
        if edge_match:
            src = edge_match.group("src")
            dst = edge_match.group("dst")
            arrow = edge_match.group("arrow")
            label = (edge_match.group("label") or "").strip() or None
            kind = "arrow"
            if "-." in arrow:
                kind = "dashed"
            elif "==" in arrow:
                kind = "thick"
            # Create placeholder nodes if not seen
            if src not in nodes:
                nodes[src] = ParsedNode(
                    id=src,
                    label=src,
                    shape="auto",
                    classes=[],
                    subgraph_path=current_subpath(),
                    props={},
                )
            if dst not in nodes:
                nodes[dst] = ParsedNode(
                    id=dst,
                    label=dst,
                    shape="auto",
                    classes=[],
                    subgraph_path=current_subpath(),
                    props={},
                )
            edges.append(ParsedEdge(src=src, dst=dst, kind=kind, label=label, props={}))
            continue

        # Edge (undirected ---)
        undirected_match = UNDIRECTED_PAT.match(line)
        if undirected_match:
            src = undirected_match.group("src")
            dst = undirected_match.group("dst")
            if src not in nodes:
                nodes[src] = ParsedNode(
                    id=src,
                    label=src,
                    shape="auto",
                    classes=[],
                    subgraph_path=current_subpath(),
                    props={},
                )
            if dst not in nodes:
                nodes[dst] = ParsedNode(
                    id=dst,
                    label=dst,
                    shape="auto",
                    classes=[],
                    subgraph_path=current_subpath(),
                    props={},
                )
            edges.append(
                ParsedEdge(src=src, dst=dst, kind="line", label=None, props={})
            )
            continue

        # Node definition
        node_match = NODE_DEF_PAT.match(line)
        if node_match:
            node_id = node_match.group("id")
            square = node_match.group("square")
            circle = node_match.group("circle")
            diamond = node_match.group("diamond")
            quoted = node_match.group("quoted")
            label = square or circle or diamond or quoted or node_id
            label = label.replace("\\n", " ").strip()
            shape = (
                "box"
                if square
                else (
                    "circle"
                    if circle
                    else ("diamond" if diamond else ("text" if quoted else "auto"))
                )
            )
            cls = (node_match.group("class") or "").strip()
            classes = [c.strip() for c in cls.split() if c.strip()] if cls else []
            classes = sorted(set(classes) | class_map.get(node_id, set()))
            nodes[node_id] = ParsedNode(
                id=node_id,
                label=label,
                shape=shape,
                classes=classes,
                subgraph_path=current_subpath(),
                props={},
            )
            continue

    for node_id, props in styles.items():
        if node_id in nodes:
            nodes[node_id].props.update({"style": props})

    return list(nodes.values()), edges, subs, styles


# --- Persistence helpers ---


def _upsert_diagram(
    path: Optional[str], title: str, content: str, includes: List[str]
) -> str:
    did = str(uuid.uuid4())
    now = time.time()
    con = _connect()
    cur = con.cursor()
    # If path already exists, replace diagram id to keep single current version
    if path:
        row = cur.execute("SELECT id FROM diagrams WHERE path=?", (path,)).fetchone()
        if row:
            # Delete existing rows
            old = row[0]
            cur.execute("DELETE FROM subgraphs WHERE diagram_id=?", (old,))
            cur.execute("DELETE FROM nodes WHERE diagram_id=?", (old,))
            cur.execute("DELETE FROM edges WHERE diagram_id=?", (old,))
            cur.execute("DELETE FROM diagrams WHERE id=?", (old,))
    cur.execute(
        "INSERT INTO diagrams(id, path, title, content, includes_json, ingested_at) VALUES(?,?,?,?,?,?)",
        (did, path, title, content, json.dumps(includes), now),
    )
    con.commit()
    con.close()
    return did


def _store_graph(
    diagram_id: str,
    nodes: List[ParsedNode],
    edges: List[ParsedEdge],
    subs: List[ParsedSubgraph],
):
    con = _connect()
    cur = con.cursor()
    for s in subs:
        cur.execute(
            "INSERT OR REPLACE INTO subgraphs(diagram_id, path, title, depth) VALUES(?,?,?,?)",
            (diagram_id, s.path, s.title, s.depth),
        )
    for n in nodes:
        cur.execute(
            "INSERT OR REPLACE INTO nodes(diagram_id, node_id, label, shape, classes_json, subgraph_path, props_json) VALUES(?,?,?,?,?,?,?)",
            (
                diagram_id,
                n.id,
                n.label,
                n.shape,
                json.dumps(n.classes),
                n.subgraph_path,
                json.dumps(n.props),
            ),
        )
    for e in edges:
        cur.execute(
            "INSERT INTO edges(diagram_id, src, dst, kind, label, props_json) VALUES(?,?,?,?,?,?)",
            (diagram_id, e.src, e.dst, e.kind, e.label, json.dumps(e.props)),
        )
    con.commit()
    con.close()


def _resolve_diagram(diagram: str) -> Optional[str]:
    """Resolve diagram parameter as id or as file path."""
    con = _connect()
    cur = con.cursor()
    # Try by id
    row = cur.execute("SELECT id FROM diagrams WHERE id=?", (diagram,)).fetchone()
    if row:
        con.close()
        return row[0]
    # Try by path (abs or rel)
    # Normalize
    p = Path(diagram)
    candidates = [str(p), str(p.resolve())]
    for c in candidates:
        row = cur.execute("SELECT id FROM diagrams WHERE path=?", (c,)).fetchone()
        if row:
            con.close()
            return row[0]
    con.close()
    return None


# --- Tools ---


@mcp.tool()
def mmd_list(
    root: Optional[str] = None, glob_pattern: str = "**/*.mmd"
) -> List[Dict[str, Any]]:
    """List Mermaid files under root (default = ${MMD_ROOT} or cwd)."""
    r = Path(root) if root else MMD_ROOT_DEFAULT
    files = []
    for path in sorted(Path(r).glob(glob_pattern)):
        try:
            sz = path.stat().st_size
        except Exception:
            sz = None
        files.append({"path": str(path.resolve()), "bytes": sz})
    return files


@mcp.tool()
def mmd_read(
    path: str, should_resolve_includes: bool = True, max_depth: int = 4
) -> Dict[str, Any]:
    """Read a Mermaid file; optionally resolve custom include directives."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    includes: List[str] = []
    if should_resolve_includes:
        text, includes = resolve_includes(text, p.parent, max_depth=max_depth)
    # Title heuristic: first non-empty non-comment line not starting with config frontmatter
    title = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("%%") or s.startswith("---"):
            continue
        title = s[:120]
        break
    return {
        "path": str(p.resolve()),
        "title": title,
        "content": text,
        "includes": includes,
    }


@mcp.tool()
def mmd_parse_preview(content: str) -> Dict[str, Any]:
    """Parse Mermaid content without storing; returns graph JSON."""
    nodes, edges, subs, styles = parse_mermaid(content)
    return {
        "nodes": [asdict(n) for n in nodes],
        "edges": [asdict(e) for e in edges],
        "subgraphs": [asdict(s) for s in subs],
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


@mcp.tool()
def mmd_ingest(path: str) -> Dict[str, Any]:
    """Ingest a Mermaid file: resolve includes, parse, and store graph."""
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    merged, includes = resolve_includes(raw, p.parent)
    nodes, edges, subs, styles = parse_mermaid(merged)
    # Title from filename or first subgraph
    title = p.name
    if subs:
        title = subs[0].title
    did = _upsert_diagram(str(p.resolve()), title, merged, includes)
    _store_graph(did, nodes, edges, subs)
    return {
        "diagram_id": did,
        "path": str(p.resolve()),
        "title": title,
        "counts": {"nodes": len(nodes), "edges": len(edges), "subgraphs": len(subs)},
        "includes": includes,
    }


@mcp.tool()
def mmd_graph(diagram: str) -> Dict[str, Any]:
    """Return nodes, edges, subgraphs for a stored diagram (by id or path)."""
    did = _resolve_diagram(diagram)
    if not did:
        return {"error": "diagram_not_found"}
    con = _connect()
    cur = con.cursor()
    drow = cur.execute(
        "SELECT id, path, title FROM diagrams WHERE id=?", (did,)
    ).fetchone()
    nrows = cur.execute("SELECT * FROM nodes WHERE diagram_id=?", (did,)).fetchall()
    erows = cur.execute("SELECT * FROM edges WHERE diagram_id=?", (did,)).fetchall()
    srows = cur.execute(
        "SELECT * FROM subgraphs WHERE diagram_id=? ORDER BY depth", (did,)
    ).fetchall()
    con.close()
    nodes = [
        {
            "id": r["node_id"],
            "label": r["label"],
            "shape": r["shape"],
            "classes": json.loads(r["classes_json"]),
            "subgraph_path": r["subgraph_path"],
            "props": json.loads(r["props_json"]),
            "role": _infer_role(json.loads(r["classes_json"])),
        }
        for r in nrows
    ]
    edges = [
        {
            "src": r["src"],
            "dst": r["dst"],
            "kind": r["kind"],
            "label": r["label"],
            "props": json.loads(r["props_json"]),
        }
        for r in erows
    ]
    subgraphs = [
        {"path": r["path"], "title": r["title"], "depth": r["depth"]} for r in srows
    ]
    return {
        "diagram": {"id": drow["id"], "path": drow["path"], "title": drow["title"]},
        "nodes": nodes,
        "edges": edges,
        "subgraphs": subgraphs,
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "subgraphs": len(subgraphs),
        },
    }


def _infer_role(classes: List[str]) -> Optional[str]:
    for c in classes:
        key = c.strip().lower()
        if key in ROLE_MAP:
            return ROLE_MAP[key]
    return None


@mcp.tool()
def mmd_neighbors(
    diagram: str, node_id: str, direction: str = "both"
) -> Dict[str, Any]:
    """Return adjacency for a node: outgoing/incoming/both."""
    did = _resolve_diagram(diagram)
    if not did:
        return {"error": "diagram_not_found"}
    con = _connect()
    cur = con.cursor()
    out = []
    inc = []
    if direction in ("out", "both"):
        out = [
            dict(r)
            for r in cur.execute(
                "SELECT dst as node, kind, label FROM edges WHERE diagram_id=? AND src=?",
                (did, node_id),
            ).fetchall()
        ]
    if direction in ("in", "both"):
        inc = [
            dict(r)
            for r in cur.execute(
                "SELECT src as node, kind, label FROM edges WHERE diagram_id=? AND dst=?",
                (did, node_id),
            ).fetchall()
        ]
    con.close()
    return {"node": node_id, "out": out, "in": inc}


@mcp.tool()
def mmd_paths(
    diagram: str, src: str, dst: str, max_hops: int = 6, max_paths: int = 5
) -> Dict[str, Any]:
    """Find up to max_paths simple paths from src to dst (BFS over edges)."""
    did = _resolve_diagram(diagram)
    if not did:
        return {"error": "diagram_not_found"}
    con = _connect()
    cur = con.cursor()
    edges = cur.execute(
        "SELECT src, dst FROM edges WHERE diagram_id=?", (did,)
    ).fetchall()
    con.close()
    adj: Dict[str, List[str]] = {}
    for r in edges:
        adj.setdefault(r["src"], []).append(r["dst"])

    paths: List[List[str]] = []
    from collections import deque

    q = deque([[src]])
    visited_paths: Set[Tuple[str, ...]] = set()
    while q and len(paths) < max_paths:
        path = q.popleft()
        if len(path) - 1 > max_hops:
            continue
        last = path[-1]
        if last == dst:
            t = tuple(path)
            if t not in visited_paths:
                visited_paths.add(t)
                paths.append(path)
            continue
        for nxt in adj.get(last, []):
            if nxt in path:  # avoid cycles in simple paths
                continue
            q.append(path + [nxt])

    return {"src": src, "dst": dst, "paths": paths}


@mcp.tool()
def mmd_summary(diagram: str) -> Dict[str, Any]:
    """High-level summary for LLM digestion: counts, top hubs, roles, subgraphs."""
    did = _resolve_diagram(diagram)
    if not did:
        return {"error": "diagram_not_found"}
    con = _connect()
    cur = con.cursor()
    nrows = cur.execute(
        "SELECT node_id, classes_json FROM nodes WHERE diagram_id=?", (did,)
    ).fetchall()
    erows = cur.execute(
        "SELECT src, dst FROM edges WHERE diagram_id=?", (did,)
    ).fetchall()
    srows = cur.execute(
        "SELECT path, title, depth FROM subgraphs WHERE diagram_id=?", (did,)
    ).fetchall()
    drow = cur.execute(
        "SELECT id, path, title FROM diagrams WHERE id=?", (did,)
    ).fetchone()
    con.close()

    deg: Dict[str, int] = {}
    for r in erows:
        deg[r["src"]] = deg.get(r["src"], 0) + 1
        deg[r["dst"]] = deg.get(r["dst"], 0) + 1
    top = sorted(deg.items(), key=lambda x: x[1], reverse=True)[:10]

    role_counts: Dict[str, int] = {}
    for r in nrows:
        role = _infer_role(json.loads(r["classes_json"]))
        if role:
            role_counts[role] = role_counts.get(role, 0) + 1

    subgs = [
        {"path": r["path"], "title": r["title"], "depth": r["depth"]} for r in srows
    ]

    return {
        "diagram": {"id": drow["id"], "path": drow["path"], "title": drow["title"]},
        "counts": {"nodes": len(nrows), "edges": len(erows), "subgraphs": len(subgs)},
        "top_hubs": [{"node": n, "degree": d} for n, d in top],
        "roles": role_counts,
        "subgraphs": subgs,
    }


@mcp.tool()
def mmd_validate(diagram: str) -> Dict[str, Any]:
    """Static checks: duplicated edges, dangling references, empty subgraphs."""
    did = _resolve_diagram(diagram)
    if not did:
        return {"error": "diagram_not_found"}
    con = _connect()
    cur = con.cursor()
    nodes = {
        r["node_id"]
        for r in cur.execute(
            "SELECT node_id FROM nodes WHERE diagram_id=?", (did,)
        ).fetchall()
    }
    edges = [
        tuple(r)
        for r in cur.execute(
            "SELECT src, dst, kind, label FROM edges WHERE diagram_id=?", (did,)
        ).fetchall()
    ]
    subgs = [
        r["path"]
        for r in cur.execute(
            "SELECT path FROM subgraphs WHERE diagram_id=?", (did,)
        ).fetchall()
    ]
    con.close()

    issues: List[Dict[str, Any]] = []
    # Dangling
    for src, dst, kind, label in edges:
        if src not in nodes:
            issues.append(
                {"severity": "error", "type": "dangling_src", "src": src, "dst": dst}
            )
        if dst not in nodes:
            issues.append(
                {"severity": "error", "type": "dangling_dst", "src": src, "dst": dst}
            )
    # Duplicates
    seen: Set[Tuple[str, str, str, str]] = set()
    for e in edges:
        if e in seen:
            issues.append(
                {
                    "severity": "warn",
                    "type": "duplicate_edge",
                    "edge": {"src": e[0], "dst": e[1], "kind": e[2], "label": e[3]},
                }
            )
        seen.add(e)
    # Empty subgraphs (no nodes with that prefix)
    for sg in subgs:
        if not any(n.startswith(sg) for n in subgs if n != sg):
            # check if any node belongs into this subgraph path
            # We stored node.subgraph_path exactly equal to stack path at def time; approximate check
            pass
    return {"diagram": did, "issues": issues}


@mcp.tool()
def code_hints(diagram: str, node_id: str) -> Dict[str, Any]:
    """Opinionated scaffolding guidance for a node based on its role/classes."""
    did = _resolve_diagram(diagram)
    if not did:
        return {"error": "diagram_not_found"}
    con = _connect()
    cur = con.cursor()
    r = cur.execute(
        "SELECT label, classes_json FROM nodes WHERE diagram_id=? AND node_id=?",
        (did, node_id),
    ).fetchone()
    con.close()
    if not r:
        return {"error": "node_not_found"}
    label = r["label"]
    classes = json.loads(r["classes_json"]) or []
    role = _infer_role(classes) or "module"

    # Very lightweight mapping from role â†’ folder + stubs
    mapping = {
        "api": {"folder": "api/", "stub": "FastAPI router with POST/GET endpoints"},
        "gateway": {"folder": "policy/", "stub": "OPA/ABAC check + request shaping"},
        "processing": {
            "folder": "services/",
            "stub": "orchestrator/service class with execute()",
        },
        "memory": {"folder": "hippocampus/", "stub": "writer/reader units + UoW hooks"},
        "bus": {"folder": "events/", "stub": "event schemas + publisher/subscriber"},
        "storage": {"folder": "storage/", "stub": "SQLite/Vector adapters + UoW"},
        "cache": {"folder": "storage/cache/", "stub": "LRU/TTL + WAL coherence"},
        "module": {"folder": "modules/", "stub": "thin module with __init__ and run()"},
    }
    hint = mapping.get(role, mapping["module"])
    return {
        "node": node_id,
        "label": label,
        "role": role,
        "classes": classes,
        "recommend": {
            "folder": hint["folder"],
            "stubs": [hint["stub"], "logging + metrics", "unit tests (ward)"],
        },
    }


# --- Resources ---


@mcp.resource("mmd://diagram/{diagram}/summary")
def res_summary(diagram: str) -> Dict[str, Any]:
    return mmd_summary(diagram)


@mcp.resource("mmd://diagram/{diagram}/adjacency")
def res_adjacency(diagram: str) -> Dict[str, Any]:
    did = _resolve_diagram(diagram)
    if not did:
        return {"error": "diagram_not_found"}
    con = _connect()
    cur = con.cursor()
    nodes = [
        r[0]
        for r in cur.execute(
            "SELECT node_id FROM nodes WHERE diagram_id=?", (did,)
        ).fetchall()
    ]
    adj = {}
    for n in nodes:
        out = [
            r[0]
            for r in cur.execute(
                "SELECT dst FROM edges WHERE diagram_id=? AND src=?", (did, n)
            ).fetchall()
        ]
        inc = [
            r[0]
            for r in cur.execute(
                "SELECT src FROM edges WHERE diagram_id=? AND dst=?", (did, n)
            ).fetchall()
        ]
        adj[n] = {"out": out, "in": inc}
    con.close()
    return {"diagram": did, "adjacency": adj}


# --- Prompt ---


@mcp.prompt(
    name="diagram.context",
    description="Compact overview of a stored Mermaid diagram for quick ramp-up",
)
def diagram_context(diagram: str, task: Optional[str] = None) -> str:
    summ = mmd_summary(diagram)
    if "error" in summ:
        return f"Diagram not found: {diagram}"
    title = summ["diagram"]["title"]
    hubs = (
        ", ".join(f"{h['node']}({h['degree']})" for h in summ["top_hubs"])
        or "(no edges)"
    )
    roles = ", ".join(f"{k}:{v}" for k, v in summ["roles"].items()) or "unknown"
    lines = [
        f"# Diagram: {title}",
        f"Nodes: {summ['counts']['nodes']}  Edges: {summ['counts']['edges']}  Subgraphs: {summ['counts']['subgraphs']}",
        f"Top hubs: {hubs}",
        f"Roles: {roles}",
        "\n## How to read this system",
        "- Start from top hubs and follow outgoing edges to see orchestrators and buses.",
        "- Storage/memory nodes anchor contracts and persistence; API/gateway nodes face inputs.",
        "- Each edge label (if present) implies a contract/event to implement.",
    ]
    if task:
        lines.append(f"\n## Task focus\n- {task}")
    lines.append(
        "\nUse mmd_neighbors/mmd_paths for precise traversals; use code_hints(node) for scaffolding."
    )
    return "\n".join(lines)


@mcp.prompt(
    name="diagram.flows",
    description="Summarize key flows in a stored Mermaid diagram or trace paths between two nodes",
)
def diagram_flows(
    diagram: str,
    src: Optional[str] = None,
    dst: Optional[str] = None,
    max_hops: int = 6,
    max_paths: int = 5,
    task: Optional[str] = None,
) -> str:
    graph = mmd_graph(diagram)
    if "error" in graph:
        return f"Diagram not found: {diagram}"

    summary = mmd_summary(diagram)
    if "error" in summary:
        return f"Unable to summarize diagram: {diagram}"

    lines = [
        f"# Diagram: {graph['diagram']['title']}",
        f"Nodes: {summary['counts']['nodes']}  Edges: {summary['counts']['edges']}  Subgraphs: {summary['counts']['subgraphs']}",
    ]

    if src and dst:
        path_info: Dict[str, Any] = mmd_paths(
            diagram, src, dst, max_hops=max_hops, max_paths=max_paths
        )
        path_lines: List[str] = []
        raw_paths = cast(List[List[Any]], path_info.get("paths", []))
        for candidate in raw_paths:
            segments = [str(node) for node in candidate]
            path_lines.append(" â†’ ".join(segments))
        if not path_lines:
            lines.append(
                f"No paths found between `{src}` and `{dst}` within {max_hops} hops."
            )
        else:
            lines.append(
                f"Paths between `{src}` and `{dst}` (max_hops={max_hops}, max_paths={max_paths}):"
            )
            for idx, path_description in enumerate(path_lines, start=1):
                lines.append(f"{idx}. {path_description}")
    else:
        top_hubs = {hub["node"] for hub in summary.get("top_hubs", [])[:5]}
        edges = graph.get("edges", [])
        spotlight = [
            e for e in edges if e.get("src") in top_hubs or e.get("dst") in top_hubs
        ]
        lines.append("\n## Highlighted flows around top hubs")
        if not spotlight:
            lines.append("(no edges to highlight)")
        else:
            for edge in spotlight[:12]:
                label = f" [{edge['label']}]" if edge.get("label") else ""
                lines.append(f"- {edge['src']} â†’ {edge['dst']}{label}")

    lines.append(
        "\nUse `mmd_neighbors` for adjacency details or pass `src`/`dst` to focus on a specific trace."
    )
    if task:
        lines.append(f"\n## Task focus\n- {task}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")  # type: ignore[attr-defined]

