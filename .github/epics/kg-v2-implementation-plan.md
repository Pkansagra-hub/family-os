# Knowledge Graph v2 - Complete Implementation Plan

**Epic ID:** KG-V2-001
**Status:** IN PROGRESS
**Start Date:** 2025-10-23
**Target:** 2025-10-29 (6 days)
**ADR:** `.github/architecture/0088-knowledge-graph-v2-architecture.md`

---

## Executive Summary

Build a **self-updating semantic repository graph** that:

- Indexes ADRs, code, contracts automatically
- Updates on git commits or scheduled intervals
- Provides 15 AI-focused MCP tools
- < 100ms query performance

**Key Innovation:** Zero-maintenance indexing via git hooks + cron scheduler.

---

## Architecture Overview

### File Structure

```
.github/
├── mcp/
│   ├── kg_v2_server.py          # FastMCP server (15 MCP tools)
│   ├── kg_store.py              # SQLite graph store
│   ├── kg_indexers.py           # ADR/Module/Contract indexers
│   ├── kg_scheduler.py          # Auto-indexing scheduler (NEW)
│   └── kg_queries.py            # Graph algorithms
├── copilot-memories/
│   └── kg_v2.db                 # SQLite database
├── contracts/kg/
│   ├── node.schema.json         # Node schema
│   ├── edge.schema.json         # Edge schema
│   └── kg_tools.openapi.yaml   # 15 tool specs
└── hooks/
    └── post-commit               # Git hook for auto-indexing (NEW)
```

### Data Model (Simplified)

**Node Schema:**

```json
{
  "node_id": "adr_0051",
  "node_type": "adr|module|contract|file",
  "label": "Agent Scheduling",
  "file_path": "docs/architecture/decisions/0051-agent-scheduling.md",
  "tags": ["scheduling", "agents"],
  "content_preview": "First 200 chars...",
  "code_snippet": "class AgentScheduler...",
  "created_at": 1729700000,
  "indexed_at": 1729700000
}
```

**Edge Schema:**

```json
{
  "src": "k1.l2_orchestration.agent_scheduler",
  "dst": "adr_0051",
  "relation": "implements|depends_on|references|tests",
  "evidence": "agent_scheduler.py:line 1 (docstring)"
}
```

---

## Auto-Indexing System (NEW)

### 1. Git Hook (Immediate Indexing)

**File:** `.github/hooks/post-commit`

```bash
#!/bin/bash
# Post-commit hook for auto-indexing

CHANGED_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD)

# Index ADRs
if echo "$CHANGED_FILES" | grep -q "docs/architecture/decisions/"; then
    python .github/mcp/kg_indexers.py index-adrs --incremental
fi

# Index K0/K1 code
if echo "$CHANGED_FILES" | grep -qE "^(k0|k1)/.*\.py$"; then
    python .github/mcp/kg_indexers.py index-modules --incremental
fi

# Index contracts
if echo "$CHANGED_FILES" | grep -q "contracts/"; then
    python .github/mcp/kg_indexers.py index-contracts --incremental
fi

echo "KG v2 indexed changed files"
```

**Installation:**

```bash
# One-time setup
cp .github/hooks/post-commit .git/hooks/post-commit
chmod +x .git/hooks/post-commit
```

---

### 2. Cron Scheduler (Full Re-Index)

**File:** `.github/mcp/kg_scheduler.py`

```python
"""
KG Auto-Indexing Scheduler

Usage:
    # Full re-index every 6 hours
    python kg_scheduler.py --mode cron --interval 6h

    # Full re-index once
    python kg_scheduler.py --mode once

    # Watch mode (for dev)
    python kg_scheduler.py --mode watch
"""

import schedule
import time
import subprocess
from pathlib import Path

class KGScheduler:
    def __init__(self, interval="6h"):
        self.interval = interval
        self.repo_root = Path(__file__).parent.parent.parent

    def full_reindex(self):
        """Run full repository re-index"""
        print(f"[{time.ctime()}] Starting full KG re-index...")

        # Index ADRs
        subprocess.run([
            "python", ".github/mcp/kg_indexers.py",
            "index-adrs", "--full"
        ], cwd=self.repo_root)

        # Index K0
        subprocess.run([
            "python", ".github/mcp/kg_indexers.py",
            "index-modules", "k0/", "--full"
        ], cwd=self.repo_root)

        # Index K1 (if exists)
        if (self.repo_root / "k1").exists():
            subprocess.run([
                "python", ".github/mcp/kg_indexers.py",
                "index-modules", "k1/", "--full"
            ], cwd=self.repo_root)

        # Index contracts
        subprocess.run([
            "python", ".github/mcp/kg_indexers.py",
            "index-contracts", "--full"
        ], cwd=self.repo_root)

        print(f"[{time.ctime()}] Full re-index complete")

    def run_cron(self):
        """Run as cron job"""
        hours = int(self.interval.rstrip("h"))
        schedule.every(hours).hours.do(self.full_reindex)

        # Initial run
        self.full_reindex()

        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(60)

    def run_watch(self):
        """Watch mode for development"""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class RepoWatcher(FileSystemEventHandler):
            def on_modified(self, event):
                if event.src_path.endswith(('.md', '.py', '.yaml')):
                    print(f"Detected change: {event.src_path}")
                    # Trigger incremental index
                    subprocess.run([
                        "python", ".github/mcp/kg_indexers.py",
                        "index-file", event.src_path
                    ])

        observer = Observer()
        observer.schedule(RepoWatcher(), str(self.repo_root), recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["cron", "once", "watch"], default="once")
    parser.add_argument("--interval", default="6h")
    args = parser.parse_args()

    scheduler = KGScheduler(interval=args.interval)

    if args.mode == "cron":
        scheduler.run_cron()
    elif args.mode == "watch":
        scheduler.run_watch()
    else:
        scheduler.full_reindex()
```

**Deployment Options:**

1. **Systemd Service (Linux):**

```ini
# /etc/systemd/system/kg-indexer.service
[Unit]
Description=KG v2 Auto-Indexer
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/familyos
ExecStart=/usr/bin/python3 .github/mcp/kg_scheduler.py --mode cron --interval 6h
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

2. **Windows Task Scheduler:**

```powershell
# Create scheduled task
$action = New-ScheduledTaskAction -Execute "python" -Argument ".github\mcp\kg_scheduler.py --mode once" -WorkingDirectory "D:\familyos"
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "KG-Indexer" -Description "KG v2 Auto-Indexing"
```

3. **Docker Container:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", ".github/mcp/kg_scheduler.py", "--mode", "cron", "--interval", "6h"]
```

---

## Implementation Issues

### Issue #1: Design & Validate Contracts (4 hours)

**Files to Create:**

- `.github/contracts/kg/node.schema.json`
- `.github/contracts/kg/edge.schema.json`
- `.github/contracts/kg/kg_tools.openapi.yaml`

**Node Schema:**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["node_id", "node_type", "label"],
  "properties": {
    "node_id": {"type": "string"},
    "node_type": {"enum": ["adr", "module", "contract", "file"]},
    "label": {"type": "string"},
    "file_path": {"type": "string"},
    "tags": {"type": "array", "items": {"type": "string"}},
    "content_preview": {"type": "string", "maxLength": 500},
    "code_snippet": {"type": "string", "maxLength": 1000},
    "created_at": {"type": "number"},
    "indexed_at": {"type": "number"}
  }
}
```

**Edge Schema:**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["src", "dst", "relation"],
  "properties": {
    "src": {"type": "string"},
    "dst": {"type": "string"},
    "relation": {"enum": ["implements", "depends_on", "references", "tests"]},
    "evidence": {"type": "string"}
  }
}
```

**Validation:**

```bash
python k0/automation/lint_schemas.py --validate .github/contracts/kg/
```

---

### Issue #2: Implement SQLite Store (8 hours)

**File:** `.github/mcp/kg_store.py`

**SQLite Schema:**

```sql
-- Nodes table
CREATE TABLE nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    label TEXT NOT NULL,
    file_path TEXT,
    tags_json TEXT,
    content_preview TEXT,
    code_snippet TEXT,
    created_at REAL NOT NULL,
    indexed_at REAL NOT NULL
);

-- FTS5 for full-text search
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    node_id,
    label,
    content_preview,
    tags_json,
    content='nodes'
);

-- Edges table
CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    relation TEXT NOT NULL,
    evidence TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (src) REFERENCES nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (dst) REFERENCES nodes(node_id) ON DELETE CASCADE,
    UNIQUE(src, dst, relation)
);

-- Indexes
CREATE INDEX idx_nodes_type ON nodes(node_type);
CREATE INDEX idx_edges_src ON edges(src);
CREATE INDEX idx_edges_dst ON edges(dst);
CREATE INDEX idx_edges_relation ON edges(relation);
```

**KGStore Class:**

```python
import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from threading import RLock
import jsonschema

class KGStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = RLock()
        self._init_schema()
        self._load_contracts()

    def _init_schema(self):
        """Create tables if not exist"""
        with self.lock:
            self.conn.executescript("""
                -- See schema above
            """)
            self.conn.commit()

    def _load_contracts(self):
        """Load JSON schemas for validation"""
        contract_dir = Path(__file__).parent.parent / "contracts" / "kg"
        with open(contract_dir / "node.schema.json") as f:
            self.node_schema = json.load(f)
        with open(contract_dir / "edge.schema.json") as f:
            self.edge_schema = json.load(f)

    def add_node(self, node: Dict) -> Dict:
        """Add or update node with contract validation"""
        # Validate
        jsonschema.validate(node, self.node_schema)

        # Add timestamps
        if "created_at" not in node:
            node["created_at"] = time.time()
        node["indexed_at"] = time.time()

        # Insert/update
        with self.lock:
            self.conn.execute("""
                INSERT INTO nodes (node_id, node_type, label, file_path, tags_json, content_preview, code_snippet, created_at, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    label=excluded.label,
                    file_path=excluded.file_path,
                    tags_json=excluded.tags_json,
                    content_preview=excluded.content_preview,
                    code_snippet=excluded.code_snippet,
                    indexed_at=excluded.indexed_at
            """, (
                node["node_id"],
                node["node_type"],
                node["label"],
                node.get("file_path"),
                json.dumps(node.get("tags", [])),
                node.get("content_preview"),
                node.get("code_snippet"),
                node["created_at"],
                node["indexed_at"]
            ))

            # Update FTS
            self.conn.execute("""
                INSERT INTO nodes_fts(node_id, label, content_preview, tags_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    label=excluded.label,
                    content_preview=excluded.content_preview,
                    tags_json=excluded.tags_json
            """, (
                node["node_id"],
                node["label"],
                node.get("content_preview", ""),
                json.dumps(node.get("tags", []))
            ))

            self.conn.commit()

        return node

    def add_edge(self, edge: Dict) -> Dict:
        """Add edge with contract validation"""
        jsonschema.validate(edge, self.edge_schema)

        with self.lock:
            self.conn.execute("""
                INSERT INTO edges (src, dst, relation, evidence, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(src, dst, relation) DO UPDATE SET
                    evidence=excluded.evidence
            """, (
                edge["src"],
                edge["dst"],
                edge["relation"],
                edge.get("evidence", ""),
                time.time()
            ))
            self.conn.commit()

        return edge

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """Full-text search"""
        with self.lock:
            cursor = self.conn.execute("""
                SELECT n.* FROM nodes n
                JOIN nodes_fts ON nodes_fts.node_id = n.node_id
                WHERE nodes_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_neighbors(self, node_id: str, direction: str = "both", relation: Optional[str] = None) -> List[Dict]:
        """Get adjacent nodes"""
        with self.lock:
            if direction == "outgoing":
                where = "e.src = ?"
            elif direction == "incoming":
                where = "e.dst = ?"
            else:
                where = "(e.src = ? OR e.dst = ?)"

            if relation:
                where += f" AND e.relation = '{relation}'"

            params = [node_id] if direction != "both" else [node_id, node_id]

            cursor = self.conn.execute(f"""
                SELECT n.*, e.relation, e.evidence
                FROM edges e
                JOIN nodes n ON (
                    CASE
                        WHEN e.src = ? THEN n.node_id = e.dst
                        ELSE n.node_id = e.src
                    END
                )
                WHERE {where}
            """, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_module_deps(self, module_id: str, depth: Optional[int] = None) -> List[str]:
        """Get transitive dependencies (BFS)"""
        visited = set()
        queue = [(module_id, 0)]

        while queue:
            current, level = queue.pop(0)
            if current in visited:
                continue
            if depth is not None and level > depth:
                continue

            visited.add(current)

            # Find dependencies
            with self.lock:
                cursor = self.conn.execute("""
                    SELECT dst FROM edges
                    WHERE src = ? AND relation = 'depends_on'
                """, (current,))
                deps = [row["dst"] for row in cursor.fetchall()]

            for dep in deps:
                if dep not in visited:
                    queue.append((dep, level + 1))

        visited.discard(module_id)
        return list(visited)

    def find_circular_deps(self) -> List[List[str]]:
        """Detect circular dependencies (Tarjan's algorithm)"""
        # Simplified cycle detection
        with self.lock:
            cursor = self.conn.execute("""
                SELECT DISTINCT src FROM edges WHERE relation = 'depends_on'
            """)
            all_nodes = [row["src"] for row in cursor.fetchall()]

        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node, path):
            if node in rec_stack:
                # Found cycle
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:])
                return
            if node in visited:
                return

            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            with self.lock:
                cursor = self.conn.execute("""
                    SELECT dst FROM edges WHERE src = ? AND relation = 'depends_on'
                """, (node,))
                neighbors = [row["dst"] for row in cursor.fetchall()]

            for neighbor in neighbors:
                dfs(neighbor, path[:])

            rec_stack.discard(node)

        for node in all_nodes:
            dfs(node, [])

        return cycles
```

---

### Issue #3: Implement Indexers with Auto-Scheduler (12 hours)

**File:** `.github/mcp/kg_indexers.py`

```python
"""
KG Repository Indexers

Usage:
    # Index everything
    python kg_indexers.py index-all

    # Index specific components
    python kg_indexers.py index-adrs [--full|--incremental]
    python kg_indexers.py index-modules k0/ [--full|--incremental]
    python kg_indexers.py index-contracts [--full]

    # Index single file
    python kg_indexers.py index-file path/to/file.py
"""

import ast
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from kg_store import KGStore

class ADRIndexer:
    """Index ADRs from docs/architecture/decisions/"""

    def __init__(self, store: KGStore):
        self.store = store
        self.repo_root = Path(__file__).parent.parent.parent
        self.adr_dir = self.repo_root / "docs" / "architecture" / "decisions"

    def index_all(self):
        """Index all ADR files"""
        adr_files = list(self.adr_dir.glob("*.md"))
        print(f"Indexing {len(adr_files)} ADRs...")

        for adr_file in adr_files:
            if adr_file.name in ["readme.md", "0000-template.md"]:
                continue
            self.index_file(adr_file)

        print(f"Indexed {len(adr_files)} ADRs")

    def index_file(self, file_path: Path):
        """Index single ADR file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract ADR number and title
        # Format: "# ADR-0051: Title" or "# ADR 0051: Title"
        title_match = re.search(r'^#\s+ADR[- ]?(\d+):\s*(.+)$', content, re.MULTILINE)
        if not title_match:
            print(f"Skipping {file_path.name} - no ADR header")
            return

        adr_num = title_match.group(1).zfill(4)
        title = title_match.group(2).strip()

        # Extract tags from content
        tags = []
        if "agent" in content.lower() or "scheduling" in content.lower():
            tags.append("agents")
        if "protocol" in content.lower():
            tags.append("protocol")
        if "performance" in content.lower():
            tags.append("performance")
        # Add more tag extraction logic

        # Create node
        node = {
            "node_id": f"adr_{adr_num}",
            "node_type": "adr",
            "label": title,
            "file_path": str(file_path.relative_to(self.repo_root)),
            "tags": tags,
            "content_preview": content[:500].replace('\n', ' ')
        }

        self.store.add_node(node)

        # Extract cross-references to other ADRs
        # Format: "ADR-0050" or "ADR 0050"
        related_adrs = re.findall(r'ADR[- ]?(\d+)', content)
        for related_num in related_adrs:
            related_num = related_num.zfill(4)
            if related_num != adr_num:
                self.store.add_edge({
                    "src": f"adr_{adr_num}",
                    "dst": f"adr_{related_num}",
                    "relation": "references",
                    "evidence": f"Mentioned in {file_path.name}"
                })

        print(f"Indexed ADR-{adr_num}: {title}")


class ModuleIndexer:
    """Index Python modules and extract dependencies"""

    def __init__(self, store: KGStore):
        self.store = store
        self.repo_root = Path(__file__).parent.parent.parent

    def index_directory(self, dir_path: Path):
        """Index all Python files in directory"""
        py_files = list(dir_path.rglob("*.py"))
        print(f"Indexing {len(py_files)} Python files in {dir_path}...")

        for py_file in py_files:
            if "__pycache__" in str(py_file):
                continue
            self.index_file(py_file)

        print(f"Indexed {len(py_files)} Python files")

    def index_file(self, file_path: Path):
        """Index single Python file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
        except:
            print(f"Skipping {file_path} - read error")
            return

        # Convert file path to module ID
        # e.g., k0/kernel/core.py → k0.kernel.core
        rel_path = file_path.relative_to(self.repo_root)
        module_id = str(rel_path.with_suffix('')).replace('/', '.').replace('\\', '.')

        # Extract docstring
        try:
            tree = ast.parse(code, filename=str(file_path))
            docstring = ast.get_docstring(tree) or ""
        except:
            docstring = ""

        # Extract imports
        imports = []
        try:
            tree = ast.parse(code, filename=str(file_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except:
            pass

        # Create node
        self.store.add_node({
            "node_id": module_id,
            "node_type": "module",
            "label": file_path.stem,
            "file_path": str(rel_path),
            "tags": [file_path.parts[0]],  # k0 or k1
            "content_preview": docstring[:500],
            "code_snippet": code[:1000]
        })

        # Create dependency edges
        for imp in imports:
            # Only track internal imports (k0.*, k1.*)
            if imp.startswith(('k0.', 'k1.')):
                self.store.add_edge({
                    "src": module_id,
                    "dst": imp,
                    "relation": "depends_on",
                    "evidence": f"Import in {file_path.name}"
                })

        # Check for ADR implementation
        # Look for "ADR-XXXX" or "Implements ADR XXXX" in docstring or comments
        adr_refs = re.findall(r'(?:ADR[- ]?|implements?\s+ADR[- ]?)(\d+)', code, re.IGNORECASE)
        for adr_num in adr_refs:
            adr_num = adr_num.zfill(4)
            self.store.add_edge({
                "src": module_id,
                "dst": f"adr_{adr_num}",
                "relation": "implements",
                "evidence": f"Docstring/comment in {file_path.name}"
            })

        print(f"Indexed module: {module_id}")


class ContractIndexer:
    """Index OpenAPI/AsyncAPI/JSON Schema contracts"""

    def __init__(self, store: KGStore):
        self.store = store
        self.repo_root = Path(__file__).parent.parent.parent

    def index_all(self):
        """Index all contract files"""
        contract_dirs = [
            self.repo_root / "k0" / "contracts",
            self.repo_root / "k1" / "contracts"
        ]

        for contract_dir in contract_dirs:
            if not contract_dir.exists():
                continue

            # OpenAPI/AsyncAPI
            for yaml_file in contract_dir.rglob("*.yaml"):
                self.index_contract(yaml_file)

            # JSON Schema
            for json_file in contract_dir.rglob("*.json"):
                self.index_contract(json_file)

    def index_contract(self, file_path: Path):
        """Index single contract file"""
        rel_path = file_path.relative_to(self.repo_root)

        # Extract contract name
        contract_name = file_path.stem

        # Determine contract type
        if "openapi" in file_path.name:
            contract_type = "openapi"
        elif "asyncapi" in file_path.name:
            contract_type = "asyncapi"
        elif ".schema.json" in file_path.name:
            contract_type = "json_schema"
        else:
            contract_type = "unknown"

        self.store.add_node({
            "node_id": contract_name,
            "node_type": "contract",
            "label": contract_name,
            "file_path": str(rel_path),
            "tags": [contract_type, file_path.parts[0]],  # k0 or k1
            "content_preview": f"{contract_type} contract"
        })

        print(f"Indexed contract: {contract_name}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["index-all", "index-adrs", "index-modules", "index-contracts", "index-file"])
    parser.add_argument("path", nargs="?", help="Path for index-modules or index-file")
    parser.add_argument("--full", action="store_true", help="Full re-index")
    parser.add_argument("--incremental", action="store_true", help="Incremental index")
    args = parser.parse_args()

    # Initialize store
    db_path = Path.home() / ".github" / "copilot-memories" / "kg_v2.db"
    store = KGStore(str(db_path))

    if args.command == "index-all":
        ADRIndexer(store).index_all()
        ModuleIndexer(store).index_directory(Path("k0"))
        if Path("k1").exists():
            ModuleIndexer(store).index_directory(Path("k1"))
        ContractIndexer(store).index_all()

    elif args.command == "index-adrs":
        ADRIndexer(store).index_all()

    elif args.command == "index-modules":
        if not args.path:
            print("Error: --path required for index-modules")
            return
        ModuleIndexer(store).index_directory(Path(args.path))

    elif args.command == "index-contracts":
        ContractIndexer(store).index_all()

    elif args.command == "index-file":
        if not args.path:
            print("Error: --path required for index-file")
            return
        file_path = Path(args.path)
        if file_path.suffix == ".md":
            ADRIndexer(store).index_file(file_path)
        elif file_path.suffix == ".py":
            ModuleIndexer(store).index_file(file_path)
        else:
            print(f"Unsupported file type: {file_path.suffix}")

if __name__ == "__main__":
    main()
```

---

### Issue #4: Implement 15 MCP Tools (12 hours)

**File:** `.github/mcp/kg_v2_server.py`

```python
"""
Knowledge Graph v2 MCP Server

15 AI-focused tools for repository context
"""

import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from kg_store import KGStore
from kg_queries import DependencyAnalyzer, ContextBuilder

# Initialize
mcp = FastMCP("kg_v2")
DB_PATH = os.environ.get("KG_DB", str(Path.home() / ".github" / "copilot-memories" / "kg_v2.db"))
store = KGStore(DB_PATH)
dep_analyzer = DependencyAnalyzer(store)
context_builder = ContextBuilder(store)

# ==================== Core Graph Operations ====================

@mcp.tool()
def kg_search(query: str, limit: int = 20):
    """Full-text search across all nodes (ADRs, modules, contracts, files)"""
    return store.search(query, limit)


@mcp.tool()
def kg_neighbors(node_id: str, direction: str = "both", relation: str = None):
    """
    Get adjacent nodes

    Args:
        node_id: Node to query
        direction: "outgoing", "incoming", or "both"
        relation: Filter by relation type (implements, depends_on, references, tests)
    """
    return store.get_neighbors(node_id, direction, relation)


@mcp.tool()
def kg_add_node(node_id: str, node_type: str, label: str, file_path: str = None, tags: list = None):
    """Create or update a node"""
    return store.add_node({
        "node_id": node_id,
        "node_type": node_type,
        "label": label,
        "file_path": file_path,
        "tags": tags or []
    })


@mcp.tool()
def kg_add_edge(src: str, dst: str, relation: str, evidence: str = None):
    """Create an edge between two nodes"""
    return store.add_edge({
        "src": src,
        "dst": dst,
        "relation": relation,
        "evidence": evidence
    })


# ==================== Queries ====================

@mcp.tool()
def kg_find_by_type(node_type: str, limit: int = 50):
    """Find all nodes of a type (adr, module, contract, file)"""
    with store.lock:
        cursor = store.conn.execute("""
            SELECT * FROM nodes WHERE node_type = ? LIMIT ?
        """, (node_type, limit))
        return [dict(row) for row in cursor.fetchall()]


@mcp.tool()
def kg_graph_summary():
    """High-level statistics about the graph"""
    with store.lock:
        stats = {}

        # Node counts by type
        cursor = store.conn.execute("""
            SELECT node_type, COUNT(*) as count
            FROM nodes
            GROUP BY node_type
        """)
        stats["nodes_by_type"] = {row["node_type"]: row["count"] for row in cursor.fetchall()}

        # Edge counts by relation
        cursor = store.conn.execute("""
            SELECT relation, COUNT(*) as count
            FROM edges
            GROUP BY relation
        """)
        stats["edges_by_relation"] = {row["relation"]: row["count"] for row in cursor.fetchall()}

        # Total counts
        stats["total_nodes"] = sum(stats["nodes_by_type"].values())
        stats["total_edges"] = sum(stats["edges_by_relation"].values())

        return stats


@mcp.tool()
def kg_paths(src: str, dst: str, max_hops: int = 6):
    """Find all paths between two nodes (BFS)"""
    paths = []
    queue = [(src, [src])]
    visited = set()

    while queue and len(paths) < 5:  # Max 5 paths
        current, path = queue.pop(0)

        if len(path) > max_hops:
            continue

        if current == dst:
            paths.append(path)
            continue

        if current in visited:
            continue
        visited.add(current)

        neighbors = store.get_neighbors(current, direction="outgoing")
        for neighbor in neighbors:
            neighbor_id = neighbor["node_id"]
            if neighbor_id not in path:
                queue.append((neighbor_id, path + [neighbor_id]))

    return paths


# ==================== Dependency Analysis ====================

@mcp.tool()
def kg_get_module_deps(module_id: str, depth: int = None):
    """Get all dependencies of a module (transitive)"""
    return dep_analyzer.get_module_deps(module_id, depth)


@mcp.tool()
def kg_dependency_impact(module_id: str):
    """What breaks if I change this module?"""
    return dep_analyzer.dependency_impact(module_id)


@mcp.tool()
def kg_find_circular_deps():
    """Detect circular dependencies"""
    return store.find_circular_deps()


# ==================== AI Context Builders ====================

@mcp.tool()
def kg_implementation_chain(adr_id: str):
    """
    Get complete implementation context for an ADR
    Returns: contracts, code, tests, related ADRs
    """
    return context_builder.implementation_chain(adr_id)


@mcp.tool()
def kg_get_feature_context(feature_name: str):
    """
    Get context for implementing a new feature
    Returns: related ADRs, similar code, contracts, patterns
    """
    return context_builder.feature_context(feature_name)


@mcp.tool()
def kg_ask(query: str):
    """
    Natural language query router

    Examples:
        "What implements ADR-0051?"
        "What breaks if I change agent_scheduler?"
        "Show me circular dependencies"
        "Give me context for health monitoring"
    """
    query_lower = query.lower()

    if "implements" in query_lower and "adr" in query_lower:
        # Extract ADR number
        import re
        match = re.search(r'adr[- ]?(\d+)', query_lower)
        if match:
            adr_num = match.group(1).zfill(4)
            return kg_implementation_chain(f"adr_{adr_num}")

    elif "breaks" in query_lower or "impact" in query_lower:
        # Extract module name
        import re
        match = re.search(r'(?:change|modify)\s+(\w+)', query_lower)
        if match:
            module_name = match.group(1)
            # Find module ID
            results = kg_search(module_name, limit=1)
            if results:
                return kg_dependency_impact(results[0]["node_id"])

    elif "circular" in query_lower:
        return kg_find_circular_deps()

    elif "context" in query_lower or "implement" in query_lower:
        # Extract feature name
        import re
        match = re.search(r'(?:context for|implement)\s+(.+)', query_lower)
        if match:
            feature = match.group(1).strip('?')
            return kg_get_feature_context(feature)

    else:
        # Fallback to search
        return kg_search(query)


# ==================== Diagnostics ====================

@mcp.tool()
def kg_diagnostics(diagnostic_type: str):
    """
    Architecture diagnostics

    Types:
        - orphaned_code: Code with no edges
        - missing_tests: Code without test coverage
        - circular_deps: Circular dependencies
    """
    if diagnostic_type == "orphaned_code":
        with store.lock:
            cursor = store.conn.execute("""
                SELECT n.* FROM nodes n
                WHERE n.node_type = 'module'
                  AND NOT EXISTS (SELECT 1 FROM edges WHERE src = n.node_id OR dst = n.node_id)
            """)
            return [dict(row) for row in cursor.fetchall()]

    elif diagnostic_type == "missing_tests":
        with store.lock:
            cursor = store.conn.execute("""
                SELECT n.* FROM nodes n
                WHERE n.node_type = 'module'
                  AND NOT EXISTS (
                      SELECT 1 FROM edges e
                      WHERE e.dst = n.node_id AND e.relation = 'tests'
                  )
            """)
            return [dict(row) for row in cursor.fetchall()]

    elif diagnostic_type == "circular_deps":
        return kg_find_circular_deps()

    else:
        return {"error": f"Unknown diagnostic type: {diagnostic_type}"}


if __name__ == "__main__":
    mcp.run()
```

**File:** `.github/mcp/kg_queries.py` (Helper classes)

```python
"""Graph algorithms and context builders"""

from typing import Dict, List, Optional

class DependencyAnalyzer:
    def __init__(self, store):
        self.store = store

    def get_module_deps(self, module_id: str, depth: Optional[int] = None) -> List[str]:
        """Already implemented in KGStore"""
        return self.store.get_module_deps(module_id, depth)

    def dependency_impact(self, module_id: str) -> Dict:
        """Reverse dependency analysis"""
        # Find direct dependents
        direct_dependents = []
        with self.store.lock:
            cursor = self.store.conn.execute("""
                SELECT src, evidence FROM edges
                WHERE dst = ? AND relation = 'depends_on'
            """, (module_id,))
            direct_dependents = [dict(row) for row in cursor.fetchall()]

        # Find transitive dependents (BFS upward)
        transitive = set()
        queue = [d["src"] for d in direct_dependents]
        while queue:
            current = queue.pop(0)
            if current in transitive:
                continue
            transitive.add(current)

            with self.store.lock:
                cursor = self.store.conn.execute("""
                    SELECT src FROM edges WHERE dst = ? AND relation = 'depends_on'
                """, (current,))
                next_level = [row["src"] for row in cursor.fetchall()]
            queue.extend(next_level)

        # Find affected tests
        with self.store.lock:
            cursor = self.store.conn.execute("""
                SELECT src FROM edges WHERE dst = ? AND relation = 'tests'
            """, (module_id,))
            tests = [row["src"] for row in cursor.fetchall()]

        return {
            "module": module_id,
            "direct_dependents": direct_dependents,
            "transitive_dependents": list(transitive),
            "affected_tests": tests,
            "total_impact": len(transitive) + len(direct_dependents)
        }


class ContextBuilder:
    def __init__(self, store):
        self.store = store

    def implementation_chain(self, adr_id: str) -> Dict:
        """Complete ADR implementation context"""
        # Get ADR node
        with self.store.lock:
            cursor = self.store.conn.execute("""
                SELECT * FROM nodes WHERE node_id = ?
            """, (adr_id,))
            adr = dict(cursor.fetchone()) if cursor.fetchone() else None

        if not adr:
            return {"error": f"ADR {adr_id} not found"}

        # Find implementations
        implementations = self.store.get_neighbors(adr_id, direction="incoming", relation="implements")

        # Find required contracts
        contracts = self.store.get_neighbors(adr_id, direction="outgoing", relation="references")
        contracts = [c for c in contracts if c["node_type"] == "contract"]

        # Find tests
        tests = []
        for impl in implementations:
            impl_tests = self.store.get_neighbors(impl["node_id"], direction="incoming", relation="tests")
            tests.extend(impl_tests)

        # Find related ADRs
        related_adrs = self.store.get_neighbors(adr_id, direction="both", relation="references")
        related_adrs = [a for a in related_adrs if a["node_type"] == "adr"]

        return {
            "adr": adr,
            "implementations": implementations,
            "contracts": contracts,
            "tests": tests,
            "related_adrs": related_adrs
        }

    def feature_context(self, feature_name: str) -> Dict:
        """Context for implementing a new feature"""
        # Search for related ADRs
        related_adrs = self.store.search(feature_name, limit=5)
        related_adrs = [a for a in related_adrs if a["node_type"] == "adr"]

        # Search for similar code
        similar_code = self.store.search(feature_name, limit=10)
        similar_code = [c for c in similar_code if c["node_type"] == "module"]

        # Find contracts
        contracts = self.store.search(feature_name, limit=5)
        contracts = [c for c in contracts if c["node_type"] == "contract"]

        return {
            "query": feature_name,
            "related_adrs": related_adrs,
            "similar_code": similar_code,
            "contracts": contracts,
            "suggestion": "Start by reading the related ADRs and reviewing similar implementations"
        }
```

---

### Issue #5: Testing & Deployment (6 hours)

**File:** `.github/mcp/tests/test_kg_v2.py`

```python
"""WARD tests for KG v2"""

from ward import test, fixture
from pathlib import Path
import tempfile
from kg_store import KGStore
from kg_indexers import ADRIndexer, ModuleIndexer

@fixture
def temp_store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store = KGStore(f.name)
        yield store
        Path(f.name).unlink()

@test("Can add and retrieve node")
def test_node_operations(store=temp_store):
    node = {
        "node_id": "test_node",
        "node_type": "adr",
        "label": "Test ADR"
    }
    store.add_node(node)

    results = store.search("Test")
    assert len(results) > 0
    assert results[0]["node_id"] == "test_node"

@test("Can add edge and query neighbors")
def test_edge_operations(store=temp_store):
    store.add_node({"node_id": "a", "node_type": "module", "label": "A"})
    store.add_node({"node_id": "b", "node_type": "module", "label": "B"})
    store.add_edge({"src": "a", "dst": "b", "relation": "depends_on"})

    neighbors = store.get_neighbors("a", direction="outgoing")
    assert len(neighbors) == 1
    assert neighbors[0]["node_id"] == "b"

@test("Can detect circular dependencies")
def test_circular_deps(store=temp_store):
    # Create cycle: a → b → c → a
    store.add_node({"node_id": "a", "node_type": "module", "label": "A"})
    store.add_node({"node_id": "b", "node_type": "module", "label": "B"})
    store.add_node({"node_id": "c", "node_type": "module", "label": "C"})
    store.add_edge({"src": "a", "dst": "b", "relation": "depends_on"})
    store.add_edge({"src": "b", "dst": "c", "relation": "depends_on"})
    store.add_edge({"src": "c", "dst": "a", "relation": "depends_on"})

    cycles = store.find_circular_deps()
    assert len(cycles) > 0

@test("ADR indexer works")
def test_adr_indexer(store=temp_store):
    indexer = ADRIndexer(store)
    # Test with real ADR file
    adr_file = Path("docs/architecture/decisions/0001-k0-k1-kernel-split.md")
    if adr_file.exists():
        indexer.index_file(adr_file)

        results = store.search("kernel")
        assert len(results) > 0

@test("Performance: search < 100ms")
def test_performance(store=temp_store):
    import time

    # Add 100 nodes
    for i in range(100):
        store.add_node({
            "node_id": f"node_{i}",
            "node_type": "module",
            "label": f"Module {i}"
        })

    # Time search
    start = time.time()
    store.search("Module", limit=20)
    duration = (time.time() - start) * 1000

    assert duration < 100, f"Search took {duration}ms (should be < 100ms)"
```

**Run tests:**

```bash
python -m ward test --path .github/mcp/tests/
```

---

## Deployment Checklist

### 1. Update MCP Config

**File:** `.vscode/mcp.json`

```jsonc
{
  "servers": {
    "kg_v2": {
      "type": "stdio",
      "command": "py",
      "args": ["-3", "-u", "D:\\familyos\\.github\\mcp\\kg_v2_server.py"],
      "cwd": "D:\\familyos",
      "env": {
        "KG_DB": "D:\\familyos\\.github\\copilot-memories\\kg_v2.db"
      }
    }
  }
}
```

### 2. Install Git Hook

```bash
cp .github/hooks/post-commit .git/hooks/post-commit
chmod +x .git/hooks/post-commit
```

### 3. Run Initial Index

```bash
python .github/mcp/kg_indexers.py index-all
```

### 4. Start Scheduler (Optional)

```bash
# Run once
python .github/mcp/kg_scheduler.py --mode once

# Run as daemon (Linux)
python .github/mcp/kg_scheduler.py --mode cron --interval 6h &

# Or set up systemd/Task Scheduler (see above)
```

### 5. Verify MCP Server

```bash
# Test MCP server
python .github/mcp/kg_v2_server.py
# Should start without errors
```

---

## Usage Examples

### In Copilot Chat

```
You: "What implements ADR-0051?"
Copilot: [calls kg_implementation_chain("adr_0051")]
→ Returns: agent_scheduler.py, related contracts, tests

You: "What breaks if I change k0.bus?"
Copilot: [calls kg_dependency_impact("k0.bus")]
→ Returns: 15 dependent modules

You: "Give me context for implementing health monitoring"
Copilot: [calls kg_get_feature_context("health monitoring")]
→ Returns: Related ADRs, similar code patterns, contracts

You: "Find circular dependencies"
Copilot: [calls kg_find_circular_deps()]
→ Returns: List of circular dependency chains
```

---

## Performance Targets

| Operation | Target | How Achieved |
|-----------|--------|--------------|
| Full index (87 ADRs + 200 modules) | < 5s | Parallel processing, bulk inserts |
| Incremental index (1 file) | < 100ms | Direct SQL updates |
| Search query | < 50ms | FTS5 + indexes |
| Dependency impact | < 100ms | Indexed edges, BFS |
| Graph summary | < 20ms | Cached aggregations |

---

## Maintenance

### Re-Index Triggers

1. **Git commit** → Auto (via post-commit hook)
2. **Scheduled** → Every 6 hours (via kg_scheduler.py)
3. **Manual** → `python kg_indexers.py index-all`

### Monitoring

```bash
# Check database size
du -h .github/copilot-memories/kg_v2.db

# Check index freshness
sqlite3 .github/copilot-memories/kg_v2.db "SELECT MAX(indexed_at) FROM nodes;"

# Check for errors
tail -f /var/log/kg-indexer.log  # If using systemd
```

---

## Success Metrics

- ✅ **87 ADRs indexed** in < 2 seconds
- ✅ **200+ K0 modules indexed** in < 3 seconds
- ✅ **15 MCP tools** working
- ✅ **< 100ms** query performance
- ✅ **Auto-indexing** on git commits
- ✅ **Zero manual maintenance** required

---

## Timeline

| Day | Tasks | Hours | Status |
|-----|-------|-------|--------|
| Oct 23 | Issue #1: Contracts | 4 | ⏳ |
| Oct 24 | Issue #2: Store | 8 | 🔜 |
| Oct 25 | Issue #3: Indexers + Scheduler | 12 | 🔜 |
| Oct 26-27 | Issue #4: MCP Tools | 12 | 🔜 |
| Oct 28-29 | Issue #5: Tests + Deploy | 6 | 🔜 |

**Total: 42 hours (6 days)**

---

## Next Steps

1. Create contracts (node.schema.json, edge.schema.json, kg_tools.openapi.yaml)
2. Implement SQLite store with FTS5
3. Build indexers with AST parsing
4. Create auto-scheduler with git hooks
5. Implement 15 MCP tools
6. Write WARD tests
7. Deploy and verify

**Ready to start with Issue #1 (Contracts)?**
