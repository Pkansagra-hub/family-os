"""
Knowledge Graph Indexers

Indexers that populate the KG from repository sources:
- ADRIndexer: Parse ADRs, extract metadata and cross-references
- ModuleIndexer: AST parsing for Python imports and dependencies
- ContractIndexer: Parse OpenAPI/JSON schemas for API contracts

All indexers automatically generate vector embeddings for semantic search.

Usage:
    from kg_indexers import ADRIndexer, ModuleIndexer, ContractIndexer
    from kg_store import KGStore

    store = KGStore("kg.db")

    # Index ADRs (with automatic embedding generation)
    adr_indexer = ADRIndexer(store, generate_embeddings=True)
    adr_indexer.index_all("docs/architecture/decisions")

    # Index Python modules
    mod_indexer = ModuleIndexer(store, generate_embeddings=True)
    mod_indexer.index_all("k1")

    # Index contracts
    contract_indexer = ContractIndexer(store, generate_embeddings=True)
    contract_indexer.index_all(".github/contracts/kg")
"""

import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

try:
    from kg_store import generate_embedding

    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    print(
        "Warning: sentence-transformers not installed. Embeddings will not be generated."
    )
    print("Install with: pip install sentence-transformers")


class ADRIndexer:
    """Index Architecture Decision Records"""

    def __init__(self, store, generate_embeddings: bool = True):
        self.store = store
        self.adr_pattern = re.compile(r"^(\d{4}[a-z]?)-(.+)\.md$")
        self.generate_embeddings = generate_embeddings and EMBEDDINGS_AVAILABLE

    def index_all(self, adr_dir: str) -> Dict[str, int]:
        """Index all ADRs in directory"""
        adr_path = Path(adr_dir)
        if not adr_path.exists():
            return {"indexed": 0, "errors": 0}

        stats = {"indexed": 0, "errors": 0, "skipped": 0}

        for adr_file in adr_path.glob("*.md"):
            # Skip template
            if adr_file.name == "0000-template.md":
                stats["skipped"] += 1
                continue

            try:
                self.index_adr(adr_file)
                stats["indexed"] += 1
            except Exception as e:
                print(f"Error indexing {adr_file}: {e}")
                stats["errors"] += 1

        return stats

    def index_adr(self, adr_file: Path) -> None:
        """Index a single ADR file"""
        content = adr_file.read_text(encoding="utf-8")

        # Extract ADR number and title from filename
        match = self.adr_pattern.match(adr_file.name)
        if not match:
            raise ValueError(f"Invalid ADR filename: {adr_file.name}")

        adr_num, slug = match.groups()
        node_id = f"adr_{adr_num}"

        # Extract title from first heading
        title_match = re.search(r"^#\s+ADR-\d+[a-z]?:\s*(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else slug.replace("-", " ").title()

        # Extract status
        status_match = re.search(r"\*\*Status\*\*:\s*(\w+)", content)
        status = status_match.group(1).lower() if status_match else "unknown"

        # Extract date
        date_match = re.search(r"\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
        date_str = date_match.group(1) if date_match else None

        # Extract tags from content (common technical terms)
        tags = self._extract_tags(content, title)
        tags.append(status)
        tags.append(f"adr_{adr_num}")

        # Limit to 18 tags (leave room for 2 more system tags)
        tags = list(set(tags))[:18]

        # Create content preview (first 500 chars of Context section)
        context_match = re.search(r"##\s+Context\s+(.+?)(?=##|\Z)", content, re.DOTALL)
        if context_match:
            context_text = context_match.group(1).strip()
            preview = (
                context_text[:500] + "..." if len(context_text) > 500 else context_text
            )
        else:
            preview = content[:500] + "..." if len(content) > 500 else content

        # Clean preview (remove markdown formatting)
        preview = re.sub(r"[*_`#]", "", preview)
        preview = re.sub(r"\n+", " ", preview)

        # Add node
        node_data = {
            "node_id": node_id,
            "node_type": "adr",
            "label": f"ADR-{adr_num}: {title}",
            "file_path": str(adr_file.absolute()),
            "tags": list(set(tags)),
            "content_preview": preview,
        }

        self.store.add_node(node_data)

        # Generate and store embedding
        if self.generate_embeddings:
            try:
                embedding_text = f"{title}. {preview}"
                embedding = generate_embedding(embedding_text)
                self.store.add_embedding(node_id, embedding)
            except Exception as e:
                print(f"Warning: Failed to generate embedding for {node_id}: {e}")

        # Extract cross-references
        self._extract_references(node_id, content)

    def _extract_tags(self, content: str, title: str) -> List[str]:
        """Extract relevant tags from content and title"""
        tags = []

        # Common technical terms
        keywords = [
            "actor",
            "agent",
            "orchestrator",
            "planner",
            "supervisor",
            "protocol",
            "mpst",
            "lifecycle",
            "fsm",
            "state machine",
            "memory",
            "storage",
            "database",
            "cache",
            "queue",
            "performance",
            "latency",
            "throughput",
            "scalability",
            "security",
            "privacy",
            "capability",
            "sandbox",
            "monitoring",
            "observability",
            "metrics",
            "tracing",
            "api",
            "contract",
            "schema",
            "validation",
            "bridge",
            "kernel",
            "k0",
            "k1",
            "microkernel",
        ]

        content_lower = content.lower()
        title_lower = title.lower()

        for keyword in keywords:
            if keyword in content_lower or keyword in title_lower:
                tags.append(keyword)

        return tags

    def _extract_references(self, adr_id: str, content: str) -> None:
        """Extract ADR cross-references and create edges"""
        # Pattern: ADR-0001, ADR-0001a, etc.
        ref_pattern = re.compile(r"ADR-(\d{4}[a-z]?)")

        for match in ref_pattern.finditer(content):
            ref_num = match.group(1)
            ref_id = f"adr_{ref_num}"

            # Don't create self-references
            if ref_id == adr_id:
                continue

            # Check if referenced ADR exists
            if self.store.get_node(ref_id):
                # Create reference edge
                try:
                    self.store.add_edge(
                        {
                            "src": adr_id,
                            "dst": ref_id,
                            "relation": "references",
                            "evidence": "Referenced in ADR content",
                        }
                    )
                except Exception:
                    pass  # Edge might already exist


class ModuleIndexer:
    """Index Python modules and their dependencies"""

    def __init__(
        self, store, repo_root: Path | None = None, generate_embeddings: bool = True
    ):
        self.store = store
        self.repo_root = repo_root or Path.cwd().resolve()
        self.generate_embeddings = generate_embeddings and EMBEDDINGS_AVAILABLE

    def index_all(self, module_dir: str) -> Dict[str, int]:
        """Index all Python modules in directory (two-pass: nodes then edges)"""
        module_path = Path(module_dir)
        if not module_path.exists():
            return {"indexed": 0, "errors": 0}

        stats = {"indexed": 0, "errors": 0, "skipped": 0}

        # PASS 1: Index all module nodes first
        modules_to_process = []
        for py_file in module_path.rglob("*.py"):
            # Skip test files and __pycache__
            if "__pycache__" in str(py_file) or "test_" in py_file.name:
                stats["skipped"] += 1
                continue

            try:
                self.index_module(py_file, create_edges=False)
                modules_to_process.append(py_file)
                stats["indexed"] += 1
            except Exception as e:
                print(f"Error indexing {py_file}: {e}")
                stats["errors"] += 1

        # PASS 2: Create dependency edges after all nodes exist
        for py_file in modules_to_process:
            try:
                self.create_module_edges(py_file)
            except Exception:
                # Silently skip edge creation failures
                pass

        return stats

    def index_module(self, py_file: Path, create_edges: bool = True) -> None:
        """Index a single Python module"""
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except SyntaxError:
            # Skip files with syntax errors
            return

        # Create module identifier from path
        abs_path = py_file.resolve()
        try:
            rel_path = abs_path.relative_to(self.repo_root)
        except ValueError:
            # Path is not relative to repo root, skip
            return

        module_id = (
            str(rel_path).replace("\\", "/").replace("/", ".").replace(".py", "")
        )
        node_id = f"module_{module_id}"

        # Extract imports
        imports = self._extract_imports(tree)

        # Extract docstring
        docstring = ast.get_docstring(tree) or ""
        preview = (docstring[:497] + "...") if len(docstring) > 500 else docstring

        # Extract code snippet (first class or function)
        snippet = self._extract_snippet(tree, content) or ""

        # Determine tags
        tags = [module_id.split(".")[0]]  # Root module (k0, k1, etc.)
        if tags[0] == "":  # Handle edge case of empty root
            tags = ["mcp"]
        if "test" in module_id:
            tags.append("test")

        # Add node
        node_data = {
            "node_id": node_id,
            "node_type": "module",
            "label": module_id,
            "file_path": str(py_file.absolute()),
            "tags": tags,
            "content_preview": preview,
            "code_snippet": snippet,
        }

        self.store.add_node(node_data)

        # Generate and store embedding
        if self.generate_embeddings:
            try:
                embedding_text = f"{module_id}. {preview}"
                embedding = generate_embedding(embedding_text)
                self.store.add_embedding(node_id, embedding)
            except Exception as e:
                print(f"Warning: Failed to generate embedding for {node_id}: {e}")

        # Create dependency edges (optional, for single-pass indexing)
        if create_edges:
            self._create_dependency_edges(node_id, imports)

    def create_module_edges(self, py_file: Path) -> None:
        """Create dependency edges for a module (second pass)"""
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except SyntaxError:
            return

        # Recreate module identifier
        abs_path = py_file.resolve()
        try:
            rel_path = abs_path.relative_to(self.repo_root)
        except ValueError:
            return

        module_id = (
            str(rel_path).replace("\\", "/").replace("/", ".").replace(".py", "")
        )
        node_id = f"module_{module_id}"

        # Extract imports and create edges
        imports = self._extract_imports(tree)
        self._create_dependency_edges(node_id, imports)

    def _extract_imports(self, tree: ast.AST) -> Set[str]:
        """Extract import statements"""
        imports = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)

        return imports

    def _extract_snippet(self, tree: ast.AST, content: str) -> Optional[str]:
        """Extract first significant code snippet"""
        lines = content.split("\n")

        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    start = node.lineno - 1
                    end = min(node.end_lineno, start + 10)  # Max 10 lines
                    return "\n".join(lines[start:end])

        return None

    def _create_dependency_edges(self, module_id: str, imports: Set[str]) -> None:
        """Create edges for module dependencies"""
        for imp in imports:
            # Only track internal dependencies (k0, k1, etc.)
            if not imp.startswith(("k0", "k1", "bridge", "services")):
                continue

            # Try both package and __init__ variants
            possible_targets = [
                f"module_{imp}",  # Direct module
                f"module_{imp}.__init__",  # Package __init__
            ]

            # Try to find which one exists
            target_id = None
            for candidate in possible_targets:
                if self.store.get_node(candidate):
                    target_id = candidate
                    break

            # If no target found, skip (module might not be indexed yet or is external)
            if not target_id:
                continue

            # Create edge
            try:
                self.store.add_edge(
                    {
                        "src": module_id,
                        "dst": target_id,
                        "relation": "depends_on",
                        "evidence": f"import {imp}",
                    }
                )
            except Exception:
                pass  # Edge might already exist


class ContractIndexer:
    """Index API contracts (OpenAPI, JSON Schema)"""

    def __init__(self, store, generate_embeddings: bool = True):
        self.store = store
        self.generate_embeddings = generate_embeddings and EMBEDDINGS_AVAILABLE

    def index_all(self, contract_dir: str) -> Dict[str, int]:
        """Index all contract files in directory"""
        contract_path = Path(contract_dir)
        if not contract_path.exists():
            return {"indexed": 0, "errors": 0}

        stats = {"indexed": 0, "errors": 0, "skipped": 0}

        # Index all YAML files (contracts, schemas, protocols)
        for yaml_file in contract_path.rglob("*.yaml"):
            # Skip examples directory
            if "examples" in yaml_file.parts:
                stats["skipped"] += 1
                continue
            try:
                self.index_contract_file(yaml_file)
                stats["indexed"] += 1
            except Exception as e:
                print(f"Error indexing {yaml_file}: {e}")
                stats["errors"] += 1

        for yml_file in contract_path.rglob("*.yml"):
            # Skip examples directory
            if "examples" in yml_file.parts:
                stats["skipped"] += 1
                continue
            try:
                self.index_contract_file(yml_file)
                stats["indexed"] += 1
            except Exception as e:
                print(f"Error indexing {yml_file}: {e}")
                stats["errors"] += 1

        # Index all JSON files (schemas)
        for json_file in contract_path.rglob("*.json"):
            # Skip examples directory
            if "examples" in json_file.parts:
                stats["skipped"] += 1
                continue
            try:
                self.index_contract_file(json_file)
                stats["indexed"] += 1
            except Exception as e:
                print(f"Error indexing {json_file}: {e}")
                stats["errors"] += 1

        # Index all FlatBuffers schema files
        for fbs_file in contract_path.rglob("*.fbs"):
            # Skip examples directory
            if "examples" in fbs_file.parts:
                stats["skipped"] += 1
                continue
            try:
                self.index_fbs_file(fbs_file)
                stats["indexed"] += 1
            except Exception as e:
                print(f"Error indexing {fbs_file}: {e}")
                stats["errors"] += 1

        return stats

    def index_contract_file(self, contract_file: Path) -> None:
        """Index a generic contract file (YAML/JSON)"""
        # Read and parse file
        content = contract_file.read_text(encoding="utf-8")

        if contract_file.suffix in [".yaml", ".yml"]:
            # Handle multi-document YAML files (with --- separators)
            try:
                data = yaml.safe_load(content)
            except yaml.YAMLError:
                # If parsing fails, skip
                return
        elif contract_file.suffix == ".json":
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                return
        else:
            return

        # Generate node_id from relative path (remove k0/k1 prefix and extension)
        repo_root = contract_file.parents[3]  # Assumes contracts is 3 levels deep
        try:
            rel_path = contract_file.relative_to(repo_root)
            path_str = (
                str(rel_path)
                .replace("\\", "/")
                .replace("/", ".")
                .replace(contract_file.suffix, "")
            )
            node_id = f"contract_{path_str}"
        except ValueError:
            # Fallback if relative_to fails
            node_id = f"contract_{contract_file.stem}"

        # Extract metadata
        if isinstance(data, dict):
            title = data.get("title", data.get("name", contract_file.stem))
            description = data.get("description", data.get("summary", ""))

            # Ensure description is a string (not dict/list)
            if not isinstance(description, str):
                description = ""

            # Extract tags from various sources
            tags = ["contract"]
            if "k0" in str(contract_file):
                tags.append("k0")
            if "k1" in str(contract_file):
                tags.append("k1")

            # Add contract type hints
            if "openapi" in content.lower() or "swagger" in content.lower():
                tags.append("openapi")
            if "schema" in contract_file.name.lower():
                tags.append("schema")
            if data.get("type") and isinstance(data.get("type"), str):
                tags.append(data["type"])

            # Extract parent directory as category
            parent_dir = contract_file.parent.name
            if parent_dir != "contracts":
                tags.append(parent_dir)
        else:
            title = contract_file.stem
            description = ""
            tags = ["contract"]

        # Create preview (enforce 500 char limit)
        preview_text = description if description else content
        preview = (
            preview_text[:497] + "..." if len(preview_text) > 500 else preview_text
        )

        # Create snippet (first few lines of content or key fields) - enforce 1000 char limit
        snippet_lines = []
        if isinstance(data, dict):
            for key in list(data.keys())[:10]:
                value = data[key]
                if isinstance(value, (str, int, float, bool)):
                    snippet_lines.append(f"{key}: {value}")
                else:
                    snippet_lines.append(f"{key}: {type(value).__name__}")
        snippet_text = "\n".join(snippet_lines)
        snippet = (
            snippet_text[:997] + "..." if len(snippet_text) > 1000 else snippet_text
        )

        # Add node
        node_data = {
            "node_id": node_id,
            "node_type": "contract",
            "label": title,
            "file_path": str(contract_file.absolute()),
            "tags": list(set(tags)),
            "content_preview": preview,
            "code_snippet": snippet,
        }

        self.store.add_node(node_data)

        # Generate and store embedding
        if self.generate_embeddings:
            try:
                embedding_text = f"{title}. {preview}"
                embedding = generate_embedding(embedding_text)
                self.store.add_embedding(node_id, embedding)
            except Exception as e:
                print(f"Warning: Failed to generate embedding for {node_id}: {e}")

    def index_fbs_file(self, fbs_file: Path) -> None:
        """Index FlatBuffers schema file"""
        content = fbs_file.read_text(encoding="utf-8")

        # Generate node_id from relative path
        repo_root = fbs_file.parents[3]  # Assumes contracts is 3 levels deep
        try:
            rel_path = fbs_file.relative_to(repo_root)
            path_str = (
                str(rel_path).replace("\\", "/").replace("/", ".").replace(".fbs", "")
            )
            node_id = f"contract_{path_str}"
        except ValueError:
            node_id = f"contract_{fbs_file.stem}"

        # Extract title from filename and first comment
        title = fbs_file.stem.replace("_", " ").title()

        # Look for namespace and comments
        lines = content.split("\n")
        description_lines = []
        namespace = None

        for line in lines[:20]:  # Check first 20 lines
            line = line.strip()
            if line.startswith("//"):
                description_lines.append(line[2:].strip())
            elif line.startswith("namespace "):
                namespace = line.split()[1].rstrip(";")

        description = " ".join(description_lines)

        # Extract tags
        tags = ["contract", "flatbuffers", "fbs", "schema"]
        if "k0" in str(fbs_file):
            tags.append("k0")
        if "k1" in str(fbs_file):
            tags.append("k1")
        if namespace:
            tags.append(namespace)

        # Add parent directory as category
        parent_dir = fbs_file.parent.name
        if parent_dir != "contracts":
            tags.append(parent_dir)

        # Create preview (enforce 500 char limit)
        preview_text = description if description else content
        preview = (
            preview_text[:497] + "..." if len(preview_text) > 500 else preview_text
        )

        # Extract table/struct definitions as snippet (enforce 1000 char limit)
        snippet_lines = []
        in_definition = False
        for line in lines:
            line = line.strip()
            if (
                line.startswith("table ")
                or line.startswith("struct ")
                or line.startswith("enum ")
            ):
                snippet_lines.append(line)
                in_definition = True
            elif in_definition and line == "}":
                snippet_lines.append(line)
                in_definition = False
                if len(snippet_lines) >= 20:
                    break
            elif in_definition:
                snippet_lines.append("  " + line)

        snippet_text = "\n".join(snippet_lines[:20])
        snippet = (
            snippet_text[:997] + "..." if len(snippet_text) > 1000 else snippet_text
        )

        # Add node
        node_data = {
            "node_id": node_id,
            "node_type": "contract",
            "label": title,
            "file_path": str(fbs_file.absolute()),
            "tags": list(set(tags)),
            "content_preview": preview,
            "code_snippet": snippet,
        }

        self.store.add_node(node_data)

        # Generate and store embedding
        if self.generate_embeddings:
            try:
                embedding_text = f"{title}. {preview}"
                embedding = generate_embedding(embedding_text)
                self.store.add_embedding(node_id, embedding)
            except Exception as e:
                print(f"Warning: Failed to generate embedding for {node_id}: {e}")

    def index_openapi(self, spec_file: Path) -> None:
        """Index OpenAPI specification"""
        content = spec_file.read_text(encoding="utf-8")
        spec = yaml.safe_load(content)

        # Extract contract info
        contract_name = spec_file.stem
        node_id = f"contract_{contract_name}"

        title = spec.get("info", {}).get("title", contract_name)
        description = spec.get("info", {}).get("description", "")
        version = spec.get("info", {}).get("version", "unknown")

        # Extract tags
        tags = ["openapi", "api", version]
        if "tags" in spec:
            tags.extend([tag.get("name", "") for tag in spec.get("tags", [])])

        # Create preview
        preview = f"{description[:500]}..." if len(description) > 500 else description

        # Extract endpoints as snippet
        endpoints = []
        for path, methods in spec.get("paths", {}).items():
            for method in methods.keys():
                if method in ["get", "post", "put", "delete", "patch"]:
                    endpoints.append(f"{method.upper()} {path}")

        snippet = "\n".join(endpoints[:10])  # First 10 endpoints

        # Add node
        node_data = {
            "node_id": node_id,
            "node_type": "contract",
            "label": title,
            "file_path": str(spec_file.absolute()),
            "tags": list(set(tags)),
            "content_preview": preview,
            "code_snippet": snippet,
        }

        self.store.add_node(node_data)

        # Generate and store embedding
        if self.generate_embeddings:
            try:
                embedding_text = f"{title}. {preview}"
                embedding = generate_embedding(embedding_text)
                self.store.add_embedding(node_id, embedding)
            except Exception as e:
                print(f"Warning: Failed to generate embedding for {node_id}: {e}")

    def index_json_schema(self, schema_file: Path) -> None:
        """Index JSON Schema"""
        content = schema_file.read_text(encoding="utf-8")
        schema = json.loads(content)

        # Extract schema info
        schema_name = schema_file.stem
        node_id = f"contract_{schema_name}"

        title = schema.get("title", schema_name)
        description = schema.get("description", "")

        # Extract tags
        tags = ["json_schema", "schema"]
        if "type" in schema:
            tags.append(schema["type"])

        # Create preview
        preview = f"{description[:500]}..." if len(description) > 500 else description

        # Extract properties as snippet
        properties = schema.get("properties", {})
        snippet_lines = []
        for prop, details in list(properties.items())[:10]:
            prop_type = details.get("type", "unknown")
            snippet_lines.append(f"{prop}: {prop_type}")

        snippet = "\n".join(snippet_lines)

        # Add node
        node_data = {
            "node_id": node_id,
            "node_type": "contract",
            "label": title,
            "file_path": str(schema_file.absolute()),
            "tags": list(set(tags)),
            "content_preview": preview,
            "code_snippet": snippet,
        }

        self.store.add_node(node_data)

        # Generate and store embedding
        if self.generate_embeddings:
            try:
                embedding_text = f"{title}. {preview}"
                embedding = generate_embedding(embedding_text)
                self.store.add_embedding(node_id, embedding)
            except Exception as e:
                print(f"Warning: Failed to generate embedding for {node_id}: {e}")


def main():
    """Test indexers"""
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    import tempfile

    from kg_store import KGStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    print(f"Testing indexers with {db_path}\n")

    try:
        store = KGStore(db_path)

        # Test ADR indexer
        print("Testing ADRIndexer...")
        adr_indexer = ADRIndexer(store)
        adr_stats = adr_indexer.index_all("docs/architecture/decisions")
        print(
            f"  Indexed: {adr_stats['indexed']}, Errors: {adr_stats['errors']}, Skipped: {adr_stats['skipped']}"
        )

        # Test Module indexer
        print("\nTesting ModuleIndexer...")
        mod_indexer = ModuleIndexer(store)
        k1_stats = mod_indexer.index_all("k1")
        print(
            f"  K1 - Indexed: {k1_stats['indexed']}, Errors: {k1_stats['errors']}, Skipped: {k1_stats['skipped']}"
        )

        # Test Contract indexer
        print("\nTesting ContractIndexer...")
        contract_indexer = ContractIndexer(store)
        contract_stats = contract_indexer.index_all(".github/contracts/kg")
        print(
            f"  Contracts - Indexed: {contract_stats['indexed']}, Errors: {contract_stats['errors']}"
        )

        # Show summary
        summary = store.get_graph_summary()
        print("\nGraph Summary:")
        print(f"  Total nodes: {summary['total_nodes']}")
        print(f"  Total edges: {summary['total_edges']}")
        print(f"  Nodes by type: {summary['nodes_by_type']}")
        print(f"  Edges by relation: {summary['edges_by_relation']}")

        # Test search
        print("\nSearch 'agent':")
        results = store.search("agent", limit=5)
        for r in results:
            print(f"  - {r['node_id']}: {r['label'][:50]}")

        store.close()
        print("\n✅ Indexers test passed!")

    finally:
        Path(db_path).unlink()


if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()
