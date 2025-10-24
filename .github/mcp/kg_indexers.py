"""
KG Indexers for extracting semantic information from repository artifacts.

This module provides indexers that scan repository directories and create
semantic knowledge graph nodes and relations.

Components:
- ADRIndexer: Scans docs/architecture/decisions/ and indexes ADRs
- Module structure detection and dependency extraction (Phase 2)
- Contract indexing (Phase 2)

Performance Targets:
- ADR indexing: <500ms for full directory
- Cross-reference detection: <100ms
- Metadata extraction: <5ms per file
"""

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class ADRMetadata:
    """Metadata extracted from an ADR file."""

    adr_id: str  # e.g., "0051", "0087"
    title: str  # From markdown header
    status: str  # PROPOSED, ACCEPTED, IMPLEMENTED, REJECTED, etc.
    related_adr_ids: List[str]  # Cross-referenced ADR IDs
    file_path: str  # Absolute path to .md file
    extracted_at: float  # Timestamp


class ADRIndexer:
    """
    Indexes Architecture Decision Records from docs/architecture/decisions/.

    Extracts:
    - ADR metadata (status, date, author, category)
    - Cross-references between ADRs
    - YAML front-matter fields
    - Markdown headers and structure

    Performance Target: <500ms for full directory with 87+ ADRs
    """

    # ADR filename pattern: 0001-some-title.md or 0001a-some-title.md
    ADR_PATTERN = re.compile(r"^(\d{4}[a-z]?)-(.+)\.md$")

    # Cross-reference patterns in markdown links and text
    ADR_REFERENCE_PATTERNS = [
        r"\[ADR-?(\d{4}[a-z]?)\b",  # [ADR-0051 or [ADR0051
        r"\(0(\d{3}[a-z]?)-",  # (0051- or (0051a-
        r"ADR.{0,2}(\d{4}[a-z]?)\b",  # ADR 0051 or ADR-0051
    ]

    def __init__(self) -> None:
        """Initialize ADR indexer."""
        self.indexed_adrs: Dict[str, ADRMetadata] = {}
        self.reference_graph: Dict[str, Set[str]] = (
            {}
        )  # adr_id -> set of referenced adr_ids

    def ingest_directory(
        self, directory: Path, store: Any = None, diagram_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Scan ADR directory and create semantic KG nodes.

        Args:
            directory: Path to ADR directory (e.g., docs/architecture/decisions/)
            store: Optional KnowledgeGraphStore to add nodes to
            diagram_id: Optional diagram ID to add nodes to

        Returns:
            Dict with indexing results:
            - adr_count: Number of ADRs indexed
            - created_nodes: Number of nodes created in KG
            - extracted_relations: Number of relations detected
            - errors: List of indexing errors
            - metadata: Dict of adr_id -> ADRMetadata

        Performance: <500ms for typical repository
        """
        start_time = time.time()
        results = {
            "adr_count": 0,
            "created_nodes": 0,
            "extracted_relations": 0,
            "errors": [],
            "metadata": {},
        }

        if not directory.exists():
            results["errors"].append(f"Directory not found: {directory}")
            return results

        adr_files = sorted(
            f for f in directory.glob("*.md") if self.ADR_PATTERN.match(f.name)
        )

        # First pass: Extract metadata
        for adr_file in adr_files:
            try:
                metadata = self.extract_metadata(adr_file)
                if metadata:
                    self.indexed_adrs[metadata.adr_id] = metadata
                    results["metadata"][metadata.adr_id] = {
                        "title": metadata.title,
                        "status": metadata.status,
                        "file_path": metadata.file_path,
                    }
                    results["adr_count"] += 1
            except Exception as e:  # pragma: no cover - I/O edge case
                results["errors"].append(f"Failed to extract {adr_file.name}: {str(e)}")

        # Second pass: Extract cross-references
        for adr_id, metadata in self.indexed_adrs.items():
            self.reference_graph[adr_id] = self._extract_adr_references(metadata)
            results["extracted_relations"] += len(self.reference_graph[adr_id])

        # Third pass: Create KG nodes if store provided
        if store:
            for adr_id, metadata in self.indexed_adrs.items():
                try:
                    store.add_or_update_node(
                        diagram_id or "",
                        f"adr_{adr_id}",
                        label=metadata.title,
                        node_type="adr",
                        semantic_tags=self._extract_tags(metadata),
                        metadata={
                            "status": metadata.status,
                        },
                        file_path=str(metadata.file_path),
                        created_by="adr_indexer",
                    )
                    results["created_nodes"] += 1

                    # Create relations to referenced ADRs
                    for ref_adr_id in self.reference_graph.get(adr_id, set()):
                        try:
                            store.add_or_update_edge(
                                diagram_id or "",
                                f"adr_{adr_id}",
                                f"adr_{ref_adr_id}",
                                relation_type="references",
                                strength=0.8,
                                evidence=f"Extracted from {metadata.file_path}",
                            )
                        except Exception:
                            pass  # Skip if target ADR not indexed

                except Exception as e:  # pragma: no cover - store edge case
                    results["errors"].append(
                        f"Failed to create KG node for ADR-{adr_id}: {str(e)}"
                    )

        elapsed_ms = (time.time() - start_time) * 1000
        results["elapsed_ms"] = elapsed_ms
        results["performance_ok"] = elapsed_ms < 500

        return results

    def extract_metadata(self, adr_file: Path) -> Optional[ADRMetadata]:
        """
        Extract metadata from a single ADR file.

        Extracts:
        - ADR ID from filename (0051 from 0051-agent-scheduling.md)
        - Title from markdown header (# ADR-XXXX: ...)
        - Status from YAML front-matter or Status: field
        - Date, author, category from markdown fields
        - Related ADR IDs from cross-references

        Args:
            adr_file: Path to .md file

        Returns:
            ADRMetadata or None if parsing fails

        Performance: <5ms per file
        """
        # Extract ID from filename
        match = self.ADR_PATTERN.match(adr_file.name)
        if not match:
            return None

        adr_id = match.group(1)

        # Read file
        content = adr_file.read_text(encoding="utf-8")

        # Extract title from markdown header
        title = self._extract_title(content) or f"ADR {adr_id}"

        # Extract status
        status = self._extract_status(content) or "PROPOSED"

        return ADRMetadata(
            adr_id=adr_id,
            title=title,
            status=status,
            related_adr_ids=[],  # Populated in second pass
            file_path=str(adr_file),
            extracted_at=time.time(),
        )

    def _extract_title(self, content: str) -> Optional[str]:
        """Extract title from markdown headers."""
        # Look for # ADR-XXXX: Title or # ADR XXXX: Title or # Title
        patterns = [
            r"^#\s+(?:ADR[- ]?\d+:\s+)?(.+?)(?:\s*-\s*|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_status(self, content: str) -> Optional[str]:
        """Extract status field from markdown."""
        # Look for Status: PROPOSED, ACCEPTED, etc.
        patterns = [
            r"\*\*Status:\*?\*?\s*([A-Z]+)",  # **Status:** PROPOSED
            r"Status:\s*([A-Z]+)",  # Status: PROPOSED
            r"\*?\*?Status\*?\*?:\s*([A-Z]+)",  # Status: PROPOSED
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                status = match.group(1).upper()
                if status in (
                    "PROPOSED",
                    "ACCEPTED",
                    "IMPLEMENTED",
                    "REJECTED",
                    "SUPERSEDED",
                    "AMENDED",
                ):
                    return status
        return None

    def _extract_field(
        self, content: str, field_names: str, value_pattern: str
    ) -> Optional[str]:
        """Extract a named field from markdown."""
        # field_names: comma-separated list of field names to search for
        # value_pattern: regex to extract value after field name
        for field in field_names.split("|"):
            # Try: **field:** value or field: value
            patterns = [
                rf"\*\*{field}\*\*:\s*{value_pattern}",  # **Field:** value
                rf"{field}:\s*{value_pattern}",  # Field: value
            ]
            for pattern in patterns:
                match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        return None

    def _extract_adr_references(self, metadata: ADRMetadata) -> Set[str]:
        """Extract ADR references from a file."""
        content = Path(metadata.file_path).read_text(encoding="utf-8")
        references: Set[str] = set()

        for pattern in self.ADR_REFERENCE_PATTERNS:
            matches = re.finditer(pattern, content, re.MULTILINE)
            for match in matches:
                adr_id = match.group(1)
                # Normalize: 0051, 0051a -> 0051, 0051a
                if adr_id.startswith("0"):
                    references.add(adr_id)
                else:
                    references.add(f"0{adr_id}")

        # Remove self-references and non-indexed ADRs
        return {
            ref
            for ref in references
            if ref != metadata.adr_id and ref in self.indexed_adrs
        }

    def _extract_tags(self, metadata: ADRMetadata) -> List[str]:
        """Generate semantic tags from ADR metadata."""
        tags: List[str] = []

        # Add status as tag
        if metadata.status:
            tags.append(metadata.status.lower())

        # Add architectural area based on title keywords
        for keyword in [
            "agent",
            "actor",
            "orchestration",
            "protocol",
            "planning",
            "tool",
            "memory",
            "storage",
        ]:
            if keyword in metadata.title.lower():
                tags.append(keyword)

        return list(set(tags))  # Deduplicate

    def get_adr_status_distribution(self) -> Dict[str, int]:
        """Get count of ADRs by status."""
        distribution: Dict[str, int] = {}
        for metadata in self.indexed_adrs.values():
            distribution[metadata.status] = distribution.get(metadata.status, 0) + 1
        return distribution

    def get_adr_by_status(self, status: str) -> List[ADRMetadata]:
        """Get all ADRs with a specific status."""
        return [
            metadata
            for metadata in self.indexed_adrs.values()
            if metadata.status.upper() == status.upper()
        ]

    def get_adr_dependencies(self, adr_id: str) -> Dict[str, Any]:
        """Get dependency information for an ADR."""
        if adr_id not in self.indexed_adrs:
            return {}

        metadata = self.indexed_adrs[adr_id]
        outgoing = self.reference_graph.get(adr_id, set())

        # Find incoming references
        incoming = {
            ref_adr for ref_adr, refs in self.reference_graph.items() if adr_id in refs
        }

        return {
            "adr_id": adr_id,
            "title": metadata.title,
            "status": metadata.status,
            "references": list(outgoing),
            "referenced_by": list(incoming),
            "total_relations": len(outgoing) + len(incoming),
        }

    def find_by_tag(self, tag: str) -> List[ADRMetadata]:
        """Find ADRs by semantic tag."""
        results = []
        for metadata in self.indexed_adrs.values():
            tags = self._extract_tags(metadata)
            if tag.lower() in tags:
                results.append(metadata)
        return results


@dataclass
class ModuleMetadata:
    """Metadata extracted from a Python module."""

    module_id: str  # e.g., "k0.kernel", "k1.l2_orchestration.agent_scheduler"
    module_name: str  # Human-readable name
    module_type: str  # "package" or "file"
    file_path: str  # Absolute path to .py file (only for modules of type "file")
    docstring: Optional[str]  # Module docstring for context
    imports: List[str]  # List of imported modules
    extracted_at: float  # Timestamp
    package_path: Optional[str] = None  # For packages: path to __init__.py


class ModuleIndexer:
    """
    Indexes Python modules from k0/ and k1/ directories.

    Extracts:
    - Module structure (packages and files)
    - Python imports to build dependency graph
    - Docstrings for context
    - Module-level metadata

    Performance Target: <2 seconds for k0/ + k1/ (500+ modules)
    Accuracy Target: 90%+ on dependency detection
    """

    def __init__(self) -> None:
        """Initialize module indexer."""
        self.indexed_modules: Dict[str, ModuleMetadata] = {}
        self.import_graph: Dict[str, Set[str]] = (
            {}
        )  # module_id -> set of imported module_ids
        self.reverse_import_graph: Dict[str, Set[str]] = (
            {}
        )  # module_id -> set of modules that import it

    def ingest_directory(
        self,
        directory: Path,
        store: Any = None,
        diagram_id: Optional[str] = None,
        prefix: str = "",
    ) -> Dict[str, Any]:
        """
        Scan module directory recursively and create semantic KG nodes.

        Args:
            directory: Path to module directory (e.g., k0/, k1/)
            store: Optional KnowledgeGraphStore to add nodes to
            diagram_id: Optional diagram ID to add nodes to
            prefix: Module name prefix (e.g., "k0", "k1")

        Returns:
            Dict with indexing results:
            - module_count: Number of modules indexed
            - file_count: Number of Python files indexed
            - created_nodes: Number of nodes created in KG
            - extracted_imports: Number of imports detected
            - errors: List of indexing errors

        Performance: <2 seconds for k0/ + k1/
        """
        start_time = time.time()
        results = {
            "module_count": 0,
            "file_count": 0,
            "created_nodes": 0,
            "extracted_imports": 0,
            "errors": [],
        }

        if not directory.exists():
            results["errors"].append(f"Directory not found: {directory}")
            return results

        # First pass: Walk directory and extract module structure
        for py_file in directory.rglob("*.py"):
            # Skip __pycache__ and test files for initial pass
            if "__pycache__" in py_file.parts:
                continue

            try:
                relative_path = py_file.relative_to(directory)
                module_id = self._path_to_module_id(relative_path, prefix)

                # Extract metadata
                metadata = self.extract_module_metadata(py_file, module_id)
                if metadata:
                    self.indexed_modules[module_id] = metadata
                    results["file_count"] += 1

            except Exception as e:  # pragma: no cover - I/O edge case
                results["errors"].append(
                    f"Failed to extract module {py_file.name}: {str(e)}"
                )

        # Second pass: Extract imports and build dependency graph
        for module_id, metadata in self.indexed_modules.items():
            self.import_graph[module_id] = self._extract_imports(metadata)
            results["extracted_imports"] += len(self.import_graph[module_id])

        # Build reverse graph
        for module_id, imports in self.import_graph.items():
            for imported in imports:
                if imported not in self.reverse_import_graph:
                    self.reverse_import_graph[imported] = set()
                self.reverse_import_graph[imported].add(module_id)

        results["module_count"] = len(self.indexed_modules)

        # Third pass: Create KG nodes if store provided
        if store:
            for module_id, metadata in self.indexed_modules.items():
                try:
                    store.add_or_update_node(
                        diagram_id or "",
                        module_id,
                        label=metadata.module_name,
                        node_type=(
                            "module" if metadata.module_type == "file" else "package"
                        ),
                        semantic_tags=self._extract_module_tags(metadata),
                        metadata={
                            "module_type": metadata.module_type,
                            "import_count": len(self.import_graph.get(module_id, [])),
                        },
                        file_path=metadata.file_path,
                        created_by="module_indexer",
                    )
                    results["created_nodes"] += 1

                    # Create edges for imports
                    for imported_module in self.import_graph.get(module_id, []):
                        try:
                            store.add_or_update_edge(
                                diagram_id or "",
                                module_id,
                                imported_module,
                                relation_type="depends_on",
                                strength=0.9,
                                evidence=f"Extracted from {metadata.file_path}",
                            )
                        except Exception:
                            pass  # Skip if target module not indexed

                except Exception as e:  # pragma: no cover - store edge case
                    results["errors"].append(
                        f"Failed to create KG node for module {module_id}: {str(e)}"
                    )

        elapsed_ms = (time.time() - start_time) * 1000
        results["elapsed_ms"] = elapsed_ms
        results["performance_ok"] = elapsed_ms < 2000  # 2 second target

        return results

    def extract_module_metadata(
        self, py_file: Path, module_id: str
    ) -> Optional[ModuleMetadata]:
        """
        Extract metadata from a single Python module.

        Extracts:
        - Module ID from file path
        - Docstring for context
        - Import statements
        - Module-level metadata

        Args:
            py_file: Path to .py file
            module_id: Computed module ID

        Returns:
            ModuleMetadata or None if parsing fails

        Performance: <5ms per file
        """
        try:
            content = py_file.read_text(encoding="utf-8")

            # Extract docstring
            docstring = self._extract_docstring(content)

            # Compute module name from ID
            module_name = module_id.split(".")[-1].replace("_", " ").title()

            return ModuleMetadata(
                module_id=module_id,
                module_name=module_name,
                module_type="file" if py_file.name.endswith(".py") else "package",
                file_path=str(py_file),
                docstring=docstring,
                imports=[],  # Populated in second pass
                extracted_at=time.time(),
            )
        except Exception:
            return None

    def _path_to_module_id(self, relative_path: Path, prefix: str) -> str:
        """Convert file path to module ID."""
        # k0/kernel/core.py -> k0.kernel.core
        # k1/l2_orchestration/agent_scheduler.py -> k1.l2_orchestration.agent_scheduler
        # k0/kernel/__init__.py -> k0.kernel (remove __init__)
        parts = list(relative_path.parts[:-1]) + [relative_path.stem]
        parts = [p for p in parts if p != "__init__"]  # Remove __init__ parts
        module_path = ".".join([prefix] + parts) if prefix else ".".join(parts)
        return module_path.rstrip(".")  # Remove trailing dots

    def _extract_docstring(self, content: str) -> Optional[str]:
        """Extract module-level docstring."""
        # Look for triple-quoted string at start of file
        patterns = [
            r'^"""(.+?)"""',  # """..."""
            r"^'''(.+?)'''",  # '''...'''
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
            if match:
                docstring = match.group(1).strip()
                # Return first 200 chars
                return docstring[:200] if len(docstring) > 200 else docstring
        return None

    def _extract_imports(self, metadata: ModuleMetadata) -> Set[str]:
        """Extract imports from a module."""
        content = Path(metadata.file_path).read_text(encoding="utf-8")
        imports: Set[str] = set()

        # Find all import statements
        patterns = [
            r"^from\s+([\w.]+)\s+import",  # from x.y import
            r"^import\s+([\w.]+)",  # import x.y
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, content, re.MULTILINE)
            for match in matches:
                module_name = match.group(1)
                # Only track imports from k0 or k1
                if module_name.startswith("k0") or module_name.startswith("k1"):
                    # Normalize to module ID (remove trailing .)
                    normalized = module_name.rstrip(".")
                    imports.add(normalized)

        return imports

    def _extract_module_tags(self, metadata: ModuleMetadata) -> List[str]:
        """Generate semantic tags from module metadata."""
        tags: List[str] = []

        # Add module layer tag if k1
        if metadata.module_id.startswith("k1"):
            for layer in [
                "l1_input",
                "l2_orchestration",
                "l3_execution",
                "l4_ingress",
                "l4_runtime",
                "l5_infrastructure",
            ]:
                if layer in metadata.module_id:
                    tags.append(layer)

        # Add keywords from module name
        for keyword in [
            "scheduler",
            "agent",
            "orchestrator",
            "kernel",
            "bus",
            "storage",
            "contract",
            "telemetry",
            "security",
        ]:
            if keyword in metadata.module_id.lower():
                tags.append(keyword)

        # Add docstring keywords if present
        if metadata.docstring:
            for keyword in ["async", "thread", "distributed", "actor", "protocol"]:
                if keyword in metadata.docstring.lower():
                    tags.append(keyword)

        return list(set(tags))  # Deduplicate

    def get_module_dependencies(self, module_id: str) -> Dict[str, Any]:
        """Get dependency information for a module."""
        if module_id not in self.indexed_modules:
            return {}

        metadata = self.indexed_modules[module_id]
        outgoing = self.import_graph.get(module_id, set())
        incoming = self.reverse_import_graph.get(module_id, set())

        return {
            "module_id": module_id,
            "module_name": metadata.module_name,
            "imports": list(outgoing),
            "imported_by": list(incoming),
            "total_relations": len(outgoing) + len(incoming),
            "file_path": metadata.file_path,
        }

    def find_circular_dependencies(self) -> List[List[str]]:
        """Detect circular dependencies in import graph."""
        cycles = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def visit(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self.import_graph.get(node, []):
                if neighbor not in visited:
                    visit(neighbor, path[:])
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor) if neighbor in path else -1
                    if cycle_start >= 0:
                        cycle = path[cycle_start:] + [neighbor]
                        if cycle not in cycles:
                            cycles.append(cycle)

            rec_stack.discard(node)

        for module_id in self.indexed_modules:
            if module_id not in visited:
                visit(module_id, [])

        return cycles


@dataclass
class ContractMetadata:
    """Metadata extracted from a contract file."""

    contract_id: str  # e.g., "k0.kernel_api", "k1.agent_lifecycle"
    contract_name: str  # Human-readable name
    contract_type: str  # "openapi", "asyncapi", "jsonschema", "protobuf"
    file_path: str  # Absolute path to contract file
    version: Optional[str]  # Contract version (from spec)
    endpoints: List[str]  # API endpoints (for OpenAPI)
    schemas: List[str]  # Referenced schemas
    description: Optional[str]  # Contract description
    extracted_at: float  # Timestamp


class ContractIndexer:
    """
    Indexes contract specifications from k0/contracts and k1/contracts.

    Supports:
    - OpenAPI 3.0+ (YAML and JSON)
    - AsyncAPI 2.0+ (for event schemas)
    - JSON Schema Draft 7+

    Extracts:
    - Contract metadata (name, type, version)
    - API endpoints (from OpenAPI)
    - Schema definitions (from JSON Schema refs)
    - Contract relationships (what modules implement this)

    Performance Target: <1 second for full contracts scan (200+ contracts)
    """

    def __init__(self) -> None:
        """Initialize contract indexer."""
        self.indexed_contracts: Dict[str, ContractMetadata] = {}
        self.schema_refs: Dict[str, Set[str]] = (
            {}
        )  # contract_id -> set of referenced schema files
        self.impl_modules: Dict[str, Set[str]] = (
            {}
        )  # contract_id -> set of implementing modules

    def ingest_directory(
        self,
        directory: Path,
        store: Any = None,
        diagram_id: Optional[str] = None,
        prefix: str = "",
    ) -> Dict[str, Any]:
        """
        Scan contract directory recursively and create semantic KG nodes.

        Args:
            directory: Path to contract directory (e.g., k0/contracts/, k1/contracts/)
            store: Optional KnowledgeGraphStore to add nodes to
            diagram_id: Optional diagram ID to add nodes to
            prefix: Module name prefix (e.g., "k0", "k1")

        Returns:
            Dict with indexing results:
            - contract_count: Number of contracts indexed
            - openapi_count: Number of OpenAPI specs
            - asyncapi_count: Number of AsyncAPI specs
            - jsonschema_count: Number of JSON Schema files
            - flatbuffers_count: Number of FlatBuffers schema files
            - created_nodes: Number of nodes created in KG
            - extracted_schemas: Number of schema references
            - errors: List of indexing errors

        Performance: <1 second for k0/contracts + k1/contracts
        """
        start_time = time.time()
        results = {
            "contract_count": 0,
            "openapi_count": 0,
            "asyncapi_count": 0,
            "jsonschema_count": 0,
            "flatbuffers_count": 0,
            "created_nodes": 0,
            "extracted_schemas": 0,
            "errors": [],
        }

        if not directory.exists():
            results["errors"].append(f"Directory not found: {directory}")
            return results

        # Find all contract files
        contract_files: Dict[str, Path] = {}

        # DEBUG: count total files found
        total_files_checked = 0
        files_with_valid_ext = 0
        files_detected = 0

        for file_path in directory.rglob("*"):
            total_files_checked += 1
            if file_path.is_dir() or file_path.name.startswith("."):
                continue

            # Recognize contract types by extension and content
            if file_path.suffix.lower() in [".yaml", ".yml", ".json", ".fbs"]:
                files_with_valid_ext += 1
                try:
                    content = file_path.read_text(encoding="utf-8")

                    # FlatBuffers schema files
                    if file_path.suffix.lower() == ".fbs":
                        contract_type = "flatbuffers"
                    else:
                        contract_type = self._detect_contract_type(file_path, content)

                    if contract_type:
                        contract_files[str(file_path)] = (file_path, contract_type)
                        files_detected += 1
                except Exception as e:
                    results["errors"].append(
                        f"Failed to read {file_path.name}: {str(e)}"
                    )

        # Add debug info to results
        results["_debug_total_files"] = total_files_checked
        results["_debug_valid_ext"] = files_with_valid_ext
        results["_debug_files_detected"] = files_detected

        # First pass: Extract metadata
        for file_path, contract_type in contract_files.values():
            try:
                relative_path = file_path.relative_to(directory)
                contract_id = self._path_to_contract_id(relative_path, prefix)

                metadata = self.extract_contract_metadata(
                    file_path, contract_id, contract_type
                )
                if metadata:
                    self.indexed_contracts[contract_id] = metadata
                    results["contract_count"] += 1

                    # Count by type
                    if contract_type == "openapi":
                        results["openapi_count"] += 1
                    elif contract_type == "asyncapi":
                        results["asyncapi_count"] += 1
                    elif contract_type == "jsonschema":
                        results["jsonschema_count"] += 1
                    elif contract_type == "flatbuffers":
                        results["flatbuffers_count"] += 1

            except Exception as e:  # pragma: no cover - I/O edge case
                results["errors"].append(
                    f"Failed to extract contract {file_path.name}: {str(e)}"
                )

        # Second pass: Extract schema references
        for contract_id, metadata in self.indexed_contracts.items():
            self.schema_refs[contract_id] = set(metadata.schemas)
            results["extracted_schemas"] += len(metadata.schemas)

        # Third pass: Create KG nodes if store provided
        if store:
            for contract_id, metadata in self.indexed_contracts.items():
                try:
                    store.add_or_update_node(
                        diagram_id or "",
                        contract_id,
                        label=metadata.contract_name,
                        node_type="contract",
                        semantic_tags=self._extract_contract_tags(metadata),
                        metadata={
                            "contract_type": metadata.contract_type,
                            "version": metadata.version,
                            "endpoint_count": len(metadata.endpoints),
                            "schema_count": len(metadata.schemas),
                        },
                        file_path=metadata.file_path,
                        created_by="contract_indexer",
                    )
                    results["created_nodes"] += 1

                    # Create edges to schemas
                    for schema_name in metadata.schemas:
                        try:
                            schema_id = (
                                f"{prefix}.schema.{schema_name}"
                                if prefix
                                else f"schema.{schema_name}"
                            )
                            store.add_or_update_edge(
                                diagram_id or "",
                                contract_id,
                                schema_id,
                                relation_type="uses",
                                strength=0.8,
                                evidence=f"Referenced in {metadata.file_path}",
                            )
                        except Exception:
                            pass  # Skip if schema node not created yet

                except Exception as e:  # pragma: no cover - store edge case
                    results["errors"].append(
                        f"Failed to create KG node for contract {contract_id}: {str(e)}"
                    )

        elapsed_ms = (time.time() - start_time) * 1000
        results["elapsed_ms"] = elapsed_ms
        results["performance_ok"] = elapsed_ms < 1000  # 1 second target

        return results

    def extract_contract_metadata(
        self, file_path: Path, contract_id: str, contract_type: str
    ) -> Optional[ContractMetadata]:
        """
        Extract metadata from a single contract file.

        Args:
            file_path: Path to contract file
            contract_id: Computed contract ID
            contract_type: Type of contract (openapi, asyncapi, jsonschema)

        Returns:
            ContractMetadata or None if parsing fails

        Performance: <10ms per file
        """
        try:
            content = file_path.read_text(encoding="utf-8")

            if contract_type == "openapi":
                return self._extract_openapi_metadata(content, contract_id, file_path)
            elif contract_type == "asyncapi":
                return self._extract_asyncapi_metadata(content, contract_id, file_path)
            elif contract_type == "jsonschema":
                return self._extract_jsonschema_metadata(
                    content, contract_id, file_path
                )
            elif contract_type == "flatbuffers":
                return self._extract_flatbuffers_metadata(
                    content, contract_id, file_path
                )

        except Exception:
            return None

        return None

    def _detect_contract_type(self, file_path: Path, content: str) -> Optional[str]:
        """Detect contract type from file and content."""
        # Try to parse as YAML/JSON
        try:
            import json

            import yaml

            # Try JSON first
            try:
                data = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                # Try YAML
                data = yaml.safe_load(content)

            if isinstance(data, dict):
                # Detect by openapi version
                if "openapi" in data:
                    return "openapi"
                # Detect by asyncapi version
                elif "asyncapi" in data:
                    return "asyncapi"
                # Detect by JSON Schema indicators
                elif "$schema" in data or "properties" in data or "type" in data:
                    return "jsonschema"
                # Default: treat all other YAML/JSON in contracts as jsonschema
                else:
                    return "jsonschema"

        except Exception:
            pass

        # Fallback: check file name patterns
        name_lower = file_path.name.lower()
        if "openapi" in name_lower or "api" in name_lower:
            return "openapi"
        elif "asyncapi" in name_lower or "event" in name_lower:
            return "asyncapi"
        elif "schema" in name_lower or "contract" in name_lower:
            return "jsonschema"

        # Default: all YAML/JSON files in contracts are treated as jsonschema
        if file_path.suffix.lower() in [".yaml", ".yml", ".json"]:
            return "jsonschema"

        return None

    def _extract_openapi_metadata(
        self, content: str, contract_id: str, file_path: Path
    ) -> Optional[ContractMetadata]:
        """Extract metadata from OpenAPI specification."""
        try:
            import json

            import yaml

            try:
                data = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                import yaml

                data = yaml.safe_load(content)

            if not isinstance(data, dict):
                return None

            # Extract info
            info = data.get("info", {})
            title = info.get("title", "OpenAPI Contract")
            version = info.get("version", "1.0")
            description = info.get("description")

            # Extract endpoints from paths
            endpoints = []
            paths = data.get("paths", {})
            for path, methods in paths.items():
                if isinstance(methods, dict):
                    for method in methods.keys():
                        if method.lower() in ["get", "post", "put", "delete", "patch"]:
                            endpoints.append(f"{method.upper()} {path}")

            # Extract schemas
            schemas = []
            components = data.get("components", {})
            if components:
                schemas_section = components.get("schemas", {})
                schemas = (
                    list(schemas_section.keys())
                    if isinstance(schemas_section, dict)
                    else []
                )

            return ContractMetadata(
                contract_id=contract_id,
                contract_name=title,
                contract_type="openapi",
                file_path=str(file_path),
                version=version,
                endpoints=endpoints,
                schemas=schemas,
                description=description,
                extracted_at=time.time(),
            )

        except Exception:
            return None

    def _extract_asyncapi_metadata(
        self, content: str, contract_id: str, file_path: Path
    ) -> Optional[ContractMetadata]:
        """Extract metadata from AsyncAPI specification."""
        try:
            import json

            import yaml

            try:
                data = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                import yaml

                data = yaml.safe_load(content)

            if not isinstance(data, dict):
                return None

            # Extract info
            info = data.get("info", {})
            title = info.get("title", "AsyncAPI Contract")
            version = info.get("version", "1.0")
            description = info.get("description")

            # Extract channels/topics as "endpoints"
            endpoints = []
            channels = data.get("channels", {})
            if isinstance(channels, dict):
                endpoints = list(channels.keys())

            # Extract schemas
            schemas = []
            components = data.get("components", {})
            if components:
                schemas_section = components.get("schemas", {})
                schemas = (
                    list(schemas_section.keys())
                    if isinstance(schemas_section, dict)
                    else []
                )

            return ContractMetadata(
                contract_id=contract_id,
                contract_name=title,
                contract_type="asyncapi",
                file_path=str(file_path),
                version=version,
                endpoints=endpoints,
                schemas=schemas,
                description=description,
                extracted_at=time.time(),
            )

        except Exception:
            return None

    def _extract_jsonschema_metadata(
        self, content: str, contract_id: str, file_path: Path
    ) -> Optional[ContractMetadata]:
        """Extract metadata from JSON Schema."""
        try:
            import json

            import yaml

            # Try JSON first
            try:
                data = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                # Try YAML
                data = yaml.safe_load(content)

            if not isinstance(data, dict):
                return None

            # Extract title/description
            title = data.get(
                "title", file_path.stem.replace(".", " ").replace("_", " ").title()
            )
            description = data.get("description")
            schema_version = data.get("$schema", "draft-07")

            # Extract required properties as "endpoints"
            endpoints = []
            if "required" in data and isinstance(data["required"], list):
                endpoints = data["required"][:5]  # First 5 required fields

            # Extract nested schemas
            schemas = []
            if "definitions" in data:
                schemas = list(data["definitions"].keys())
            elif "$defs" in data:
                schemas = list(data["$defs"].keys())

            return ContractMetadata(
                contract_id=contract_id,
                contract_name=title,
                contract_type="jsonschema",
                file_path=str(file_path),
                version=schema_version,
                endpoints=endpoints,  # Required fields
                schemas=schemas,  # Nested definitions
                description=description,
                extracted_at=time.time(),
            )

        except Exception:
            return None

    def _extract_flatbuffers_metadata(
        self, content: str, contract_id: str, file_path: Path
    ) -> Optional[ContractMetadata]:
        """Extract metadata from FlatBuffers schema (.fbs) file."""
        try:
            # Parse FlatBuffers schema
            # FlatBuffers schemas define tables, structs, and enums
            import re

            # Extract table/struct definitions
            table_pattern = re.compile(
                r"^(?:table|struct|enum)\s+(\w+)\s*{", re.MULTILINE
            )
            tables = table_pattern.findall(content)

            # Extract namespace
            namespace_pattern = re.compile(r"namespace\s+([\w.]+)\s*;")
            namespaces = namespace_pattern.findall(content)
            namespace = namespaces[0] if namespaces else ""

            # Extract file root (if present)
            root_pattern = re.compile(r"root_type\s+(\w+)\s*;")
            root_matches = root_pattern.findall(content)
            root_type = (
                root_matches[0] if root_matches else (tables[0] if tables else "")
            )

            # Title: namespace + root type or filename
            title = (
                f"{namespace}.{root_type}"
                if namespace and root_type
                else file_path.stem.replace("_", " ").title()
            )

            # Extract comment (first comment block as description)
            comment_pattern = re.compile(r"//\s*(.+?)$", re.MULTILINE)
            comments = comment_pattern.findall(content[:500])  # First 500 chars
            description = (
                comments[0]
                if comments
                else f"FlatBuffers schema in {namespace}" if namespace else None
            )

            return ContractMetadata(
                contract_id=contract_id,
                contract_name=title,
                contract_type="flatbuffers",
                file_path=str(file_path),
                version="1.0",
                endpoints=tables[:10],  # Schema tables/structs as "endpoints"
                schemas=tables,  # All defined types
                description=description,
                extracted_at=time.time(),
            )

        except Exception:
            return None

    def _path_to_contract_id(self, relative_path: Path, prefix: str) -> str:
        """Convert file path to contract ID."""
        # k0/contracts/openapi.k0.yaml -> k0.contracts.openapi_k0
        # k1/contracts/api/agent_lifecycle.yaml -> k1.contracts.api.agent_lifecycle
        parts = list(relative_path.parts[:-1]) + [relative_path.stem]
        contract_path = ".".join([prefix] + parts) if prefix else ".".join(parts)
        return contract_path.replace("__init__", "").rstrip(".")

    def _extract_contract_tags(self, metadata: ContractMetadata) -> List[str]:
        """Generate semantic tags from contract metadata."""
        tags: List[str] = []

        # Add contract type
        tags.append(metadata.contract_type)

        # Add keywords from title
        for keyword in [
            "kernel",
            "agent",
            "orchestration",
            "event",
            "query",
            "storage",
            "api",
        ]:
            if keyword in metadata.contract_name.lower():
                tags.append(keyword)

        # Add keywords from description
        if metadata.description:
            for keyword in ["request", "response", "command", "event", "schema"]:
                if keyword in metadata.description.lower():
                    tags.append(keyword)

        return list(set(tags))  # Deduplicate

    def get_contract_info(self, contract_id: str) -> Dict[str, Any]:
        """Get detailed information about a contract."""
        if contract_id not in self.indexed_contracts:
            return {}

        metadata = self.indexed_contracts[contract_id]
        return {
            "contract_id": contract_id,
            "contract_name": metadata.contract_name,
            "contract_type": metadata.contract_type,
            "version": metadata.version,
            "endpoints": metadata.endpoints,
            "schemas": metadata.schemas,
            "file_path": metadata.file_path,
            "description": metadata.description,
        }

    def find_contracts_by_type(self, contract_type: str) -> List[ContractMetadata]:
        """Find contracts by type (openapi, asyncapi, jsonschema)."""
        return [
            metadata
            for metadata in self.indexed_contracts.values()
            if metadata.contract_type.lower() == contract_type.lower()
        ]

    def find_contracts_by_keyword(self, keyword: str) -> List[ContractMetadata]:
        """Find contracts matching keyword in name or description."""
        results = []
        keyword_lower = keyword.lower()
        for metadata in self.indexed_contracts.values():
            if keyword_lower in metadata.contract_name.lower():
                results.append(metadata)
            elif metadata.description and keyword_lower in metadata.description.lower():
                results.append(metadata)
        return results

    def get_contract_statistics(self) -> Dict[str, Any]:
        """Get statistics about indexed contracts."""
        type_counts: Dict[str, int] = {}
        total_endpoints = 0
        total_schemas = 0

        for metadata in self.indexed_contracts.values():
            type_counts[metadata.contract_type] = (
                type_counts.get(metadata.contract_type, 0) + 1
            )
            total_endpoints += len(metadata.endpoints)
            total_schemas += len(metadata.schemas)

        return {
            "total_contracts": len(self.indexed_contracts),
            "type_distribution": type_counts,
            "total_endpoints": total_endpoints,
            "total_schemas": total_schemas,
            "avg_endpoints_per_contract": (
                total_endpoints / len(self.indexed_contracts)
                if self.indexed_contracts
                else 0
            ),
            "avg_schemas_per_contract": (
                total_schemas / len(self.indexed_contracts)
                if self.indexed_contracts
                else 0
            ),
        }


@dataclass
class DependencyPath:
    """Represents a path in the dependency graph."""

    source: str  # Starting module ID
    target: str  # Ending module ID
    path: List[str]  # Full path from source to target
    length: int  # Number of hops (len(path) - 1)
    is_circular: bool = False  # True if path closes back to source


@dataclass
class CircularDependency:
    """Represents a circular dependency (cycle) in the graph."""

    modules: List[str]  # Modules involved in cycle
    cycle_length: int  # Number of modules in cycle
    edges: List[tuple]  # (src, dst) pairs forming the cycle
    detected_at: float  # Timestamp


class DependencyGraphEngine:
    """
    Analyzes dependency graphs from ModuleIndexer to answer complex questions:
    - What are all transitive dependencies of module X?
    - What would break if I modify module X?
    - Are there circular dependencies?
    - What is the dependency depth/breadth?

    Operates on ModuleIndexer's import_graph:
    {
        'module_id': {
            'imports': ['dep1', 'dep2', ...],
            'imported_by': ['dependent1', 'dependent2', ...]
        }
    }

    Performance Target: <100ms per query, <5ms for caching operations
    """

    def __init__(self, module_indexer: Optional["ModuleIndexer"] = None) -> None:
        """
        Initialize dependency graph engine.

        Args:
            module_indexer: Optional ModuleIndexer instance to use as data source
        """
        self.module_indexer = module_indexer
        self._transitive_cache: Dict[str, Set[str]] = {}
        self._dependents_cache: Dict[str, Set[str]] = {}
        self._circular_cache: Optional[List[CircularDependency]] = None
        self._cache_valid = False

    def set_module_indexer(self, module_indexer: "ModuleIndexer") -> None:
        """Set module indexer and invalidate caches."""
        self.module_indexer = module_indexer
        self._invalidate_caches()

    def _invalidate_caches(self) -> None:
        """Invalidate all caches."""
        self._transitive_cache = {}
        self._dependents_cache = {}
        self._circular_cache = None
        self._cache_valid = False

    def get_direct_dependencies(self, module_id: str) -> List[str]:
        """
        Get direct dependencies of a module (immediate imports only).

        Args:
            module_id: Module ID to query

        Returns:
            List of directly imported modules
        """
        if not self.module_indexer:
            return []

        import_graph = self.module_indexer.import_graph
        if module_id not in import_graph:
            return []

        return list(import_graph[module_id].get("imports", []))

    def get_direct_dependents(self, module_id: str) -> List[str]:
        """
        Get modules that directly depend on this module.

        Args:
            module_id: Module ID to query

        Returns:
            List of modules that directly import this module
        """
        if not self.module_indexer:
            return []

        import_graph = self.module_indexer.import_graph
        if module_id not in import_graph:
            return []

        return list(import_graph[module_id].get("imported_by", []))

    def get_transitive_dependencies(
        self, module_id: str, max_depth: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get all transitive dependencies of a module (BFS).

        Args:
            module_id: Starting module
            max_depth: Optional maximum depth to traverse (None = unlimited)

        Returns:
            Dict with:
            - dependencies: Set of all modules this module depends on
            - depth: Maximum depth reached
            - by_depth: Dict mapping depth to set of modules at that depth
        """
        if not self.module_indexer:
            return {"dependencies": set(), "depth": 0, "by_depth": {}}

        # Check cache first
        if module_id in self._transitive_cache and max_depth is None:
            return {
                "dependencies": self._transitive_cache[module_id].copy(),
                "depth": len(self._transitive_cache[module_id]),
                "by_depth": self._build_by_depth(module_id),
            }

        import_graph = self.module_indexer.import_graph

        visited = set()
        by_depth = {0: {module_id}}
        current_depth = 0

        queue = [(module_id, 0)]

        while queue:
            current, depth = queue.pop(0)

            if depth > 0:
                visited.add(current)

            if max_depth is not None and depth >= max_depth:
                continue

            if current not in import_graph:
                continue

            for dep in import_graph[current].get("imports", []):
                if dep not in visited:
                    if dep not in by_depth:
                        by_depth[depth + 1] = set()
                    by_depth[depth + 1].add(dep)
                    queue.append((dep, depth + 1))
                    current_depth = max(current_depth, depth + 1)

        # Cache result if no depth limit
        if max_depth is None:
            self._transitive_cache[module_id] = visited.copy()

        return {
            "dependencies": visited,
            "depth": current_depth,
            "by_depth": by_depth,
        }

    def get_transitive_dependents(
        self, module_id: str, max_depth: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get all modules that transitively depend on this module (reverse BFS).

        Args:
            module_id: Module to analyze
            max_depth: Optional maximum depth

        Returns:
            Dict with:
            - dependents: Set of all modules that depend on this
            - depth: Maximum depth reached
            - by_depth: Dict mapping depth to modules at that depth
        """
        if not self.module_indexer:
            return {"dependents": set(), "depth": 0, "by_depth": {}}

        # Check cache
        if module_id in self._dependents_cache and max_depth is None:
            return {
                "dependents": self._dependents_cache[module_id].copy(),
                "depth": len(self._dependents_cache[module_id]),
                "by_depth": self._build_dependents_by_depth(module_id),
            }

        import_graph = self.module_indexer.import_graph

        visited = set()
        by_depth = {0: {module_id}}
        current_depth = 0

        queue = [(module_id, 0)]

        while queue:
            current, depth = queue.pop(0)

            if depth > 0:
                visited.add(current)

            if max_depth is not None and depth >= max_depth:
                continue

            if current not in import_graph:
                continue

            for dependent in import_graph[current].get("imported_by", []):
                if dependent not in visited:
                    if dependent not in by_depth:
                        by_depth[depth + 1] = set()
                    by_depth[depth + 1].add(dependent)
                    queue.append((dependent, depth + 1))
                    current_depth = max(current_depth, depth + 1)

        # Cache result
        if max_depth is None:
            self._dependents_cache[module_id] = visited.copy()

        return {
            "dependents": visited,
            "depth": current_depth,
            "by_depth": by_depth,
        }

    def _build_by_depth(self, module_id: str) -> Dict[int, Set[str]]:
        """Rebuild by_depth dict from transitive deps (for caching)."""
        if not self.module_indexer:
            return {}

        import_graph = self.module_indexer.import_graph
        by_depth = {0: {module_id}}
        visited = set()
        queue = [(module_id, 0)]

        while queue:
            current, depth = queue.pop(0)
            if depth > 0:
                visited.add(current)
            if current not in import_graph:
                continue

            for dep in import_graph[current].get("imports", []):
                if dep not in visited:
                    if depth + 1 not in by_depth:
                        by_depth[depth + 1] = set()
                    by_depth[depth + 1].add(dep)
                    queue.append((dep, depth + 1))

        return by_depth

    def _build_dependents_by_depth(self, module_id: str) -> Dict[int, Set[str]]:
        """Rebuild by_depth dict from transitive dependents."""
        if not self.module_indexer:
            return {}

        import_graph = self.module_indexer.import_graph
        by_depth = {0: {module_id}}
        visited = set()
        queue = [(module_id, 0)]

        while queue:
            current, depth = queue.pop(0)
            if depth > 0:
                visited.add(current)
            if current not in import_graph:
                continue

            for dependent in import_graph[current].get("imported_by", []):
                if dependent not in visited:
                    if depth + 1 not in by_depth:
                        by_depth[depth + 1] = set()
                    by_depth[depth + 1].add(dependent)
                    queue.append((dependent, depth + 1))

        return by_depth

    def find_circular_dependencies(self) -> List[CircularDependency]:
        """
        Find all circular dependencies in the module graph.

        Uses DFS to detect cycles. A cycle is detected when we encounter
        a node that is already in the current DFS path.

        Returns:
            List of CircularDependency instances
        """
        if not self.module_indexer:
            return []

        # Return cached result if valid
        if self._circular_cache is not None:
            return self._circular_cache

        import_graph = self.module_indexer.import_graph
        cycles = []
        visited = set()
        rec_stack = set()
        path_stack = []

        def dfs(node: str, path: List[str]) -> None:
            """DFS to find cycles."""
            visited.add(node)
            rec_stack.add(node)
            path_stack.append(node)

            if node not in import_graph:
                rec_stack.remove(node)
                path_stack.pop()
                return

            for neighbor in import_graph[node].get("imports", []):
                if neighbor not in visited:
                    dfs(neighbor, path + [neighbor])
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start_idx = path_stack.index(neighbor)
                    cycle = path_stack[cycle_start_idx:] + [neighbor]
                    edges = [(cycle[i], cycle[i + 1]) for i in range(len(cycle) - 1)]

                    cycles.append(
                        CircularDependency(
                            modules=cycle,
                            cycle_length=len(cycle) - 1,
                            edges=edges,
                            detected_at=time.time(),
                        )
                    )

            rec_stack.remove(node)
            path_stack.pop()

        for node in import_graph:
            if node not in visited:
                dfs(node, [node])

        self._circular_cache = cycles
        return cycles

    def get_dependency_stats(self, module_id: str) -> Dict[str, Any]:
        """
        Get comprehensive dependency statistics for a module.

        Args:
            module_id: Module to analyze

        Returns:
            Dict with:
            - direct_dependencies: Count of direct imports
            - transitive_dependencies: Count of all transitive imports
            - dependency_depth: Maximum depth in dependency tree
            - direct_dependents: Count of direct dependents
            - transitive_dependents: Count of all transitive dependents
            - dependent_depth: Maximum depth in dependent tree
            - is_leaf: True if module has no direct dependencies
            - is_root: True if no other modules depend on it
            - impact_radius: Number of modules transitively affected by changes
        """
        direct_deps = self.get_direct_dependencies(module_id)
        trans_deps = self.get_transitive_dependencies(module_id)
        direct_dependents = self.get_direct_dependents(module_id)
        trans_dependents = self.get_transitive_dependents(module_id)

        return {
            "direct_dependencies": len(direct_deps),
            "transitive_dependencies": len(trans_deps["dependencies"]),
            "dependency_depth": trans_deps["depth"],
            "direct_dependents": len(direct_dependents),
            "transitive_dependents": len(trans_dependents["dependents"]),
            "dependent_depth": trans_dependents["depth"],
            "is_leaf": len(direct_deps) == 0,
            "is_root": len(direct_dependents) == 0,
            "impact_radius": len(trans_dependents["dependents"]),
        }

    def find_paths(
        self, source: str, target: str, max_paths: int = 10, max_depth: int = 10
    ) -> List[DependencyPath]:
        """
        Find all dependency paths from source to target.

        Args:
            source: Starting module
            target: Target module
            max_paths: Maximum number of paths to find
            max_depth: Maximum path depth to search

        Returns:
            List of DependencyPath instances
        """
        if not self.module_indexer:
            return []

        import_graph = self.module_indexer.import_graph
        paths = []

        def dfs(current: str, target: str, path: List[str], visited: Set[str]) -> None:
            """DFS to find paths."""
            if len(paths) >= max_paths:
                return

            if len(path) > max_depth:
                return

            if current == target:
                paths.append(
                    DependencyPath(
                        source=source,
                        target=target,
                        path=path,
                        length=len(path) - 1,
                    )
                )
                return

            if current not in import_graph:
                return

            for dep in import_graph[current].get("imports", []):
                if dep not in visited:
                    visited_copy = visited.copy()
                    visited_copy.add(dep)
                    dfs(dep, target, path + [dep], visited_copy)

        dfs(source, target, [source], {source})
        return paths

    def get_impact_analysis(self, module_id: str) -> Dict[str, Any]:
        """
        Analyze the impact of changes to a module.

        Args:
            module_id: Module being modified

        Returns:
            Dict with:
            - directly_affected: Direct dependents
            - transitively_affected: All transitive dependents
            - affected_layers: K1 layers affected (if applicable)
            - risk_level: "low" (<5 affected), "medium" (5-20), "high" (>20)
            - circular_risk: True if module is part of a cycle
        """
        direct_dependents = self.get_direct_dependents(module_id)
        trans_dependents = self.get_transitive_dependents(module_id)

        # Check if in circular dependency
        cycles = self.find_circular_dependencies()
        in_cycle = any(module_id in c.modules for c in cycles)

        # Determine risk level
        affected_count = len(trans_dependents["dependents"])
        if affected_count < 5:
            risk = "low"
        elif affected_count < 20:
            risk = "medium"
        else:
            risk = "high"

        return {
            "directly_affected": direct_dependents,
            "transitively_affected": list(trans_dependents["dependents"]),
            "affected_count": affected_count,
            "risk_level": risk,
            "circular_risk": in_cycle,
        }
