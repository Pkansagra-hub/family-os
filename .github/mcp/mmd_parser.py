"""Utilities for parsing Mermaid (MMD) diagrams used across MCP servers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

__all__ = [
    "ParsedNode",
    "ParsedEdge",
    "ParsedSubgraph",
    "resolve_includes",
    "parse_mermaid",
]

# --- Regex patterns ---

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
    """Resolve custom include lines like: %% include: ./_shared.mmd.inc.

    Returns combined text and a list of included file paths (absolute strings).
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
                except Exception as exc:  # pragma: no cover - surfaced in issues list
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

    Returns nodes, edges, subgraphs, and per-node styles.
    """

    nodes: Dict[str, ParsedNode] = {}
    edges: List[ParsedEdge] = []
    subgraphs: List[ParsedSubgraph] = []
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

        match = SUBGRAPH_START_PAT.match(line)
        if match:
            title = match.group("title").strip()
            sgid = _slug(title)
            sub_stack.append(sgid)
            subgraphs.append(
                ParsedSubgraph(
                    path=current_subpath(), title=title, depth=len(sub_stack)
                )
            )
            continue
        if SUBGRAPH_END_PAT.match(line):
            if sub_stack:
                sub_stack.pop()
            continue

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

    return list(nodes.values()), edges, subgraphs, styles
