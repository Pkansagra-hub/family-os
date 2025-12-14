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
    """Index API contracts (OpenAPI, JSON Schema, FlatBuffers)

    Automatically:
    - Detects contract type (openapi/jsonschema/flatbuffers/asyncapi)
    - Assigns layer tags (k0/k1/bridge - mutually exclusive)
    - Standardizes tag format: ['contract', '<type>', '<layer>', ...custom]
    - Extracts critical context: methods, errors, auth, fields
    - Generates 2000+ char previews with context
    """

    def __init__(self, store, generate_embeddings: bool = True):
        self.store = store
        self.generate_embeddings = generate_embeddings and EMBEDDINGS_AVAILABLE

    # ========================================================================
    # HELPER METHODS: Metadata Detection & Extraction
    # ========================================================================

    def _detect_contract_type(self, file_path: str, content: str) -> str:
        """Detect contract type from file extension and content"""
        file_path_lower = file_path.lower()

        # FlatBuffers (always by extension)
        if file_path_lower.endswith(".fbs"):
            return "flatbuffers"

        # JSON (assume schema)
        if file_path_lower.endswith(".json"):
            return "jsonschema"

        # YAML files can be OpenAPI or AsyncAPI
        if file_path_lower.endswith((".yml", ".yaml")):
            content_lower = content.lower()
            if "asyncapi" in content_lower:
                return "asyncapi"
            if "openapi" in content_lower or "swagger" in content_lower:
                return "openapi"
            # Default YAML to openapi
            return "openapi"

        return "unknown"

    def _get_layer_tag(self, file_path: str) -> str:
        """Determine layer tag (k0/k1/bridge) - mutually exclusive"""
        file_path_lower = file_path.lower()
        file_path_normalized = file_path.replace("\\\\", "/")

        # Bridge contracts (K1 contracts that reference K0)
        if (
            "k1/contracts/k0_bridge" in file_path_lower
            or "k1\\contracts\\k0_bridge" in file_path
        ):
            return "bridge"

        # K0 contracts
        if "k0/contracts" in file_path_lower or "k0\\contracts" in file_path:
            return "k0"

        # K1 contracts
        if "k1/contracts" in file_path_lower or "k1\\contracts" in file_path:
            return "k1"

        # Default: try to infer from path
        if "/k0" in file_path_normalized or "\\k0" in file_path:
            return "k0"
        if "/k1" in file_path_normalized or "\\k1" in file_path:
            return "k1"

        return "unknown"

    def _extract_critical_context(self, content: str, contract_type: str) -> str:
        """Extract critical context for AI: errors, methods, auth, etc."""
        context_items = []

        if contract_type == "openapi":
            # Extract HTTP methods
            methods = set(
                re.findall(
                    r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b", content.upper()
                )
            )
            if methods:
                context_items.append(f"Methods: {', '.join(sorted(methods))}")

            # Extract status codes
            status_codes = sorted(set(re.findall(r"([2345]\d{2})", content)))
            if status_codes:
                context_items.append(f"Status Codes: {', '.join(status_codes[:10])}")

            # Check for authentication
            if re.search(r"(securitySchemes|bearer|auth|oauth)", content.lower()):
                context_items.append("[AUTH REQUIRED]")

            # Check for rate limiting
            if re.search(r"(rate.?limit|x.?rate)", content.lower()):
                context_items.append("[RATE LIMITING]")

        elif contract_type == "jsonschema":
            # Extract required fields
            required_match = re.search(r'"required"\\s*:\\s*\\[(.*?)\\]', content)
            if required_match:
                fields = re.findall(r'"(\w+)"', required_match.group(1))
                if fields:
                    context_items.append(f"Required: {', '.join(fields[:5])}")

            # Check for constraints
            if "enum" in content.lower():
                context_items.append("[ENUM CONSTRAINTS]")
            if "pattern" in content.lower():
                context_items.append("[PATTERN VALIDATION]")
            if "minLength" in content or "maxLength" in content:
                context_items.append("[LENGTH CONSTRAINTS]")

        elif contract_type == "flatbuffers":
            # Extract definitions
            definitions = re.findall(r"(?:table|struct|enum)\s+(\w+)", content)
            if definitions:
                context_items.append(f"Definitions: {', '.join(definitions[:8])}")

            # Extract namespace
            namespace_match = re.search(r"namespace\s+([.\w]+)", content)
            if namespace_match:
                context_items.append(f"NS: {namespace_match.group(1)}")

        return " | ".join(context_items) if context_items else ""

    def _enhance_preview(
        self, content: str, description: str, contract_type: str, file_path: str
    ) -> str:
        """Create enhanced preview with critical context (2000 char limit)"""
        # Extract critical context
        context = self._extract_critical_context(content, contract_type)

        # Build preview
        preview_parts = []

        if context:
            preview_parts.append(f"[{context}]")

        if description:
            preview_parts.append(description)
        else:
            # Use beginning of actual content
            preview_parts.append(content[:500])

        preview = "\n".join(preview_parts)

        # Enforce 2000 char limit
        if len(preview) > 2000:
            preview = preview[:1997] + "..."

        return preview

    def _standardize_tags(
        self, base_tags: List[str], contract_type: str, layer: str
    ) -> List[str]:
        """Standardize tags to format: ['contract', '<type>', '<layer>', ...custom]"""
        tags = ["contract"]

        # Add type
        if contract_type != "unknown":
            tags.append(contract_type)

        # Add layer (mutually exclusive)
        if layer != "unknown":
            tags.append(layer)

        # Add custom tags (category, namespace, etc)
        custom = [
            t
            for t in base_tags
            if t not in ["contract", contract_type, layer, "schema", "fbs", "object"]
            and t
            not in [
                "openapi",
                "jsonschema",
                "flatbuffers",
                "asyncapi",
                "k0",
                "k1",
                "bridge",
            ]
        ]
        tags.extend(sorted(set(custom)))

        # Remove duplicates while preserving order
        return list(dict.fromkeys(tags))

    # ========================================================================
    # MAIN INDEXING METHODS
    # ========================================================================

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
        """Index a generic contract file (YAML/JSON) with enhanced metadata"""
        # Read and parse file
        content = contract_file.read_text(encoding="utf-8")

        if contract_file.suffix in [".yaml", ".yml"]:
            try:
                data = yaml.safe_load(content)
            except yaml.YAMLError:
                return
        elif contract_file.suffix == ".json":
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                return
        else:
            return

        # Generate node_id from relative path
        repo_root = contract_file.parents[3]
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
            node_id = f"contract_{contract_file.stem}"

        # Extract metadata with new logic
        if isinstance(data, dict):
            title = data.get("title", data.get("name", contract_file.stem))
            description = data.get("description", data.get("summary", ""))
            if not isinstance(description, str):
                description = ""
        else:
            title = contract_file.stem
            description = ""
            data = {}

        # AUTOMATICALLY DETECT CONTRACT TYPE
        contract_type = self._detect_contract_type(str(contract_file), content)

        # AUTOMATICALLY DETERMINE LAYER (mutually exclusive)
        layer = self._get_layer_tag(str(contract_file))

        # Extract base tags from directory structure
        base_tags = []
        parent_dir = contract_file.parent.name
        if parent_dir != "contracts":
            base_tags.append(parent_dir)

        # STANDARDIZE TAGS
        tags = self._standardize_tags(base_tags, contract_type, layer)

        # ENHANCE PREVIEW WITH CRITICAL CONTEXT (up to 2000 chars)
        preview = self._enhance_preview(
            content, description, contract_type, str(contract_file)
        )

        # Create snippet from key fields
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

        # Add node with enhanced metadata
        node_data = {
            "node_id": node_id,
            "node_type": "contract",
            "label": title,
            "file_path": str(contract_file.absolute()),
            "tags": tags,
            "content_preview": preview,
            "code_snippet": snippet,
        }

        self.store.add_node(node_data)

        # Generate embedding
        if self.generate_embeddings:
            try:
                embedding_text = f"{title}. {preview}"
                embedding = generate_embedding(embedding_text)
                self.store.add_embedding(node_id, embedding)
            except Exception as e:
                print(f"Warning: Failed to generate embedding for {node_id}: {e}")

        # NEW: Extract relationships for OpenAPI specs (Phase 4)
        if contract_type == "openapi" and isinstance(data, dict):
            relationships = self._extract_openapi_relationships(data, node_id)
            self._integrate_relationships(node_id, relationships)
            if relationships:
                print(
                    f"  Extracted {len(relationships)} relationships from OpenAPI spec"
                )

    def index_fbs_file(self, fbs_file: Path) -> None:
        """Index FlatBuffers schema file with enhanced metadata"""
        content = fbs_file.read_text(encoding="utf-8")

        # Generate node_id from relative path
        repo_root = fbs_file.parents[3]
        try:
            rel_path = fbs_file.relative_to(repo_root)
            path_str = (
                str(rel_path).replace("\\", "/").replace("/", ".").replace(".fbs", "")
            )
            node_id = f"contract_{path_str}"
        except ValueError:
            node_id = f"contract_{fbs_file.stem}"

        # Extract title from filename
        title = fbs_file.stem.replace("_", " ").title()

        # Extract comments and namespace
        lines = content.split("\n")
        description_lines = []
        namespace = None

        for line in lines[:20]:
            line = line.strip()
            if line.startswith("//"):
                description_lines.append(line[2:].strip())
            elif line.startswith("namespace "):
                namespace = line.split()[1].rstrip(";")

        description = " ".join(description_lines)

        # DETECT TYPE (will be flatbuffers)
        contract_type = self._detect_contract_type(str(fbs_file), content)

        # DETERMINE LAYER (mutually exclusive)
        layer = self._get_layer_tag(str(fbs_file))

        # Extract base tags
        base_tags = []
        if namespace:
            base_tags.append(namespace)
        parent_dir = fbs_file.parent.name
        if parent_dir != "contracts":
            base_tags.append(parent_dir)

        # STANDARDIZE TAGS
        tags = self._standardize_tags(base_tags, contract_type, layer)

        # ENHANCE PREVIEW (up to 2000 chars)
        preview = self._enhance_preview(
            content, description, contract_type, str(fbs_file)
        )

        # Extract definitions as snippet
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
            "tags": tags,
            "content_preview": preview,
            "code_snippet": snippet,
        }

        self.store.add_node(node_data)

        # Generate embedding
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

    # ========================================================================
    # RELATIONSHIP EXTRACTION METHODS (Phase 4)
    # ========================================================================

    def _resolve_schema_id(self, schema_ref: str, base_path: str | None = None) -> str:
        """Convert schema reference to KG node ID.

        Handles:
        1. External refs: './jsonschema/envelope.schema.json'
           → 'contract_k0.contracts.jsonschema.envelope.schema'
        2. Internal refs: '#/components/schemas/Envelope'
           → 'contract_k0_openapi_Envelope'
        3. Relative paths: Resolve against base contract path

        Args:
            schema_ref: Schema reference string
            base_path: Optional base path for resolving relative refs

        Returns:
            Normalized node ID string
        """
        # Handle internal refs: #/components/schemas/EnvelopeName
        if schema_ref.startswith("#/"):
            # Extract schema name from internal ref
            parts = schema_ref.split("/")
            if len(parts) >= 4 and parts[1] == "components" and parts[2] == "schemas":
                schema_name = parts[3]
                # Return as component reference (e.g., "contract_k0_openapi_Envelope")
                return f"contract_openapi_{schema_name}"
            return f"contract_{schema_ref.replace('/', '_').replace('#', '')}"

        # Handle external refs: ./jsonschema/envelope.schema.json
        if schema_ref.startswith("./") or schema_ref.startswith("../"):
            # Normalize path separators and remove extension
            normalized_path = schema_ref.replace("\\", "/").replace("./", "")
            normalized_path = normalized_path.replace("../", "")
            normalized_path = (
                normalized_path.replace(".json", "")
                .replace(".yaml", "")
                .replace(".yml", "")
            )

            # Convert path to node ID: jsonschema/envelope.schema -> contract_jsonschema.envelope.schema
            normalized_path = normalized_path.replace("/", ".")
            return f"contract_k0.contracts.{normalized_path}"

        # Handle absolute paths or already normalized refs
        if "/" in schema_ref or "\\" in schema_ref:
            normalized_path = (
                schema_ref.replace("\\", "/")
                .replace(".json", "")
                .replace(".yaml", "")
                .replace(".yml", "")
            )
            normalized_path = normalized_path.replace("/", ".")
            return f"contract_{normalized_path}"

        # Fallback: treat as simple schema name
        return f"contract_{schema_ref.replace('.json', '').replace('.yaml', '').replace('.yml', '')}"

    def _extract_openapi_relationships(
        self, spec: Dict, contract_id: str
    ) -> List[Dict]:
        """Extract relationships from OpenAPI spec.

        All relationships use 'references' type (schema-compliant).
        Evidence field captures relationship details:
        - Component refs: 'OpenAPI component: <name>'
        - Endpoint request: 'Endpoint request: <method> <path>'
        - Endpoint response: 'Endpoint response [status]: <method> <path>'
        - Parameter: 'Parameter [in] name: <method> <path>'

        Args:
            spec: Parsed OpenAPI specification dict
            contract_id: Source contract node ID

        Returns:
            List of relationship dicts with src, dst, relation, evidence
        """
        relationships = []

        if not isinstance(spec, dict):
            return relationships

        # 1. Extract component schema references
        for schema_name, schema_def in (
            spec.get("components", {}).get("schemas", {}).items()
        ):
            if isinstance(schema_def, dict) and "$ref" in schema_def:
                schema_ref = schema_def["$ref"]
                dst_id = self._resolve_schema_id(schema_ref)
                relationships.append(
                    {
                        "src": contract_id,
                        "dst": dst_id,
                        "relation": "references",
                        "evidence": f"OpenAPI component: {schema_name}",
                    }
                )

        # 2. Extract endpoint schema usage (paths)
        for path, path_item in spec.get("paths", {}).items():
            if not isinstance(path_item, dict):
                continue

            for method, operation in path_item.items():
                if method.lower() not in [
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                ]:
                    continue
                if not isinstance(operation, dict):
                    continue

                # a) Request body schemas (what the endpoint consumes)
                if "requestBody" in operation:
                    request_body = operation["requestBody"]
                    if isinstance(request_body, dict):
                        for content_type, content in request_body.get(
                            "content", {}
                        ).items():
                            if isinstance(content, dict) and "schema" in content:
                                schema_obj = content["schema"]
                                if (
                                    isinstance(schema_obj, dict)
                                    and "$ref" in schema_obj
                                ):
                                    schema_ref = schema_obj["$ref"]
                                    dst_id = self._resolve_schema_id(schema_ref)
                                    relationships.append(
                                        {
                                            "src": contract_id,
                                            "dst": dst_id,
                                            "relation": "references",
                                            "evidence": f"Endpoint request: {method.upper()} {path}",
                                        }
                                    )

                # b) Response schemas (what the endpoint produces)
                for status, response in operation.get("responses", {}).items():
                    if not isinstance(response, dict):
                        continue

                    for content_type, content in response.get("content", {}).items():
                        if isinstance(content, dict) and "schema" in content:
                            schema_obj = content["schema"]
                            if isinstance(schema_obj, dict) and "$ref" in schema_obj:
                                schema_ref = schema_obj["$ref"]
                                dst_id = self._resolve_schema_id(schema_ref)
                                relationships.append(
                                    {
                                        "src": contract_id,
                                        "dst": dst_id,
                                        "relation": "references",
                                        "evidence": f"Endpoint response [{status}]: {method.upper()} {path}",
                                    }
                                )

                # c) Parameter schemas (for query/path parameters with schema refs)
                for param in operation.get("parameters", []):
                    if isinstance(param, dict) and "schema" in param:
                        schema_obj = param["schema"]
                        if isinstance(schema_obj, dict) and "$ref" in schema_obj:
                            schema_ref = schema_obj["$ref"]
                            dst_id = self._resolve_schema_id(schema_ref)
                            param_name = param.get("name", "unknown")
                            param_in = param.get("in", "query")
                            relationships.append(
                                {
                                    "src": contract_id,
                                    "dst": dst_id,
                                    "relation": "references",
                                    "evidence": f"Parameter [{param_in}] {param_name}: {method.upper()} {path}",
                                }
                            )

        return relationships

    def _integrate_relationships(
        self, contract_id: str, relationships: List[Dict]
    ) -> None:
        """Store relationship edges in the knowledge graph.

        Args:
            contract_id: Source contract node ID
            relationships: List of relationship dicts to store
        """
        added_count = 0
        skipped_count = 0

        for rel in relationships:
            try:
                # Use safe_add_edge to skip relationships where dst doesn't exist yet
                result = self.store.safe_add_edge(rel)
                if result is not None:
                    added_count += 1
                else:
                    # Destination node doesn't exist yet (may be created later or external)
                    skipped_count += 1
            except Exception as e:
                print(
                    f"Warning: Failed to add relationship {rel.get('dst', 'unknown')}: {e}"
                )


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
