"""
K1 Port Scanner - Extract port interfaces and adapter implementations.

Scans K1 modules for hexagonal architecture compliance:
- Port interface definitions (ABC/Protocol-based I*Port, I*Provider classes)
- Nominal (inheritance) and structural (Protocol duck-typing) adapter linkage
- Null/mock adapter classification

K1-specific: K0 does not use the hexagonal port/adapter pattern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AdapterInfo:
    """Information about a single adapter implementation."""

    class_name: str
    file_path: str
    line_number: int
    is_null: bool = False  # Null/noop adapter
    is_mock: bool = False  # Mock/test adapter


@dataclass
class K1PortInfo:
    """Extracted K1 port interface information."""

    port_name: str
    module: str
    file_path: str
    line_number: int
    base_class: str  # ABC or Protocol
    method_count: int
    methods: list[str] = field(default_factory=list)
    adapters: list[AdapterInfo] = field(default_factory=list)
    status: str = "Active"


def _scan_port_definitions(k1_path: Path) -> list[K1PortInfo]:
    """
    Scan K1 Python files for port interface definitions.

    Detects:
    - class I*Port(ABC): or class I*Port(ABC, ...):
    - class I*Provider(ABC):
    - class I*Port(Protocol):
    - class I*Provider(Protocol):
    """
    ports: list[K1PortInfo] = []

    for py_file in k1_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            lines = content.split("\n")
            rel_path = str(py_file.relative_to(k1_path.parent))

            # Infer module from path
            module = _infer_module(py_file, k1_path)

            for i, line in enumerate(lines):
                # Match port interface class definitions
                match = re.match(
                    r"^class\s+(I[A-Z]\w*(?:Port|Provider))\s*\(\s*(\w+)",
                    line,
                )
                if match:
                    port_name = match.group(1)
                    base_class = match.group(2)

                    # Only count ABC and Protocol based interfaces
                    if base_class not in ("ABC", "Protocol"):
                        continue

                    # Count abstract methods (Protocol-aware)
                    methods = _extract_abstract_methods(lines, i, base_class)

                    ports.append(
                        K1PortInfo(
                            port_name=port_name,
                            module=module,
                            file_path=rel_path,
                            line_number=i + 1,
                            base_class=base_class,
                            method_count=len(methods),
                            methods=methods,
                        )
                    )

        except Exception:
            continue

    return ports


def _iter_class_body_def_indices(lines: list[str], class_start: int) -> list[int]:
    """Yield indices of `def`/`async def` lines at the class body indent."""
    class_indent = len(lines[class_start]) - len(lines[class_start].lstrip())
    body_indent: int | None = None
    out: list[int] = []
    for i in range(class_start + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        curr_indent = len(line) - len(line.lstrip())
        if curr_indent <= class_indent:
            break
        if body_indent is None:
            body_indent = curr_indent
        if curr_indent != body_indent:
            continue
        if stripped.startswith("def ") or stripped.startswith("async def "):
            out.append(i)
    return out


def _method_body_is_trivial(lines: list[str], def_idx: int) -> bool:
    """True if method body contains only docstring(s), `...`, and/or `pass`."""
    sig_end = def_idx
    while sig_end < len(lines) and not lines[sig_end].rstrip().endswith(":"):
        sig_end += 1
        if sig_end - def_idx > 20:
            return False
    def_line = lines[def_idx]
    def_indent = len(def_line) - len(def_line.lstrip())
    i = sig_end + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return False
    first_body = lines[i]
    body_indent = len(first_body) - len(first_body.lstrip())
    if body_indent <= def_indent:
        return False
    in_docstring = False
    docstring_quote = ""
    for j in range(i, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if not stripped:
            continue
        curr_indent = len(line) - len(line.lstrip())
        if in_docstring:
            if docstring_quote in line:
                in_docstring = False
            continue
        if curr_indent < body_indent:
            return True
        if stripped.startswith("#"):
            continue
        code_part = stripped.split("#", 1)[0].rstrip() if "#" in stripped else stripped
        if code_part in ("...", "pass", ""):
            continue
        if code_part.startswith('"""') or code_part.startswith("'''"):
            quote = code_part[:3]
            rest = code_part[3:]
            if quote in rest:
                continue
            in_docstring = True
            docstring_quote = quote
            continue
        if code_part[:1] in ('"', "'"):
            q = code_part[0]
            if code_part.endswith(q) and len(code_part) >= 2:
                continue
        return False
    return True


def _extract_abstract_methods(
    lines: list[str], class_start: int, base_class: str = ""
) -> list[str]:
    """
    Extract abstract / Protocol-required method names from a class definition.

    For ABC: counts methods decorated with @abstractmethod.
    For Protocol: counts public methods whose body is only docstring/.../pass.
    For everything else: also applies the Protocol rule (best effort).
    """
    methods: list[str] = []
    def_indices = _iter_class_body_def_indices(lines, class_start)

    # Pre-compute decorator presence by walking back from each def.
    for di in def_indices:
        line = lines[di].strip()
        match = re.match(r"(?:async\s+)?def\s+(\w+)", line)
        if not match:
            continue
        name = match.group(1)

        # Walk back across decorators / blank lines to detect @abstractmethod
        has_abstract = False
        k = di - 1
        while k >= 0:
            s = lines[k].strip()
            if not s:
                k -= 1
                continue
            if s.startswith("@"):
                if "abstractmethod" in s:
                    has_abstract = True
                k -= 1
                continue
            break

        if base_class == "ABC":
            if has_abstract and name not in methods:
                methods.append(name)
            continue

        # Protocol (or unknown): public methods with trivial body
        if name.startswith("_") and not name.startswith("__"):
            continue
        if has_abstract or _method_body_is_trivial(lines, di):
            if name not in methods:
                methods.append(name)

    return methods


def _extract_class_public_methods(lines: list[str], class_start: int) -> list[str]:
    """
    Return the set of public method names defined at the body-indent of the class.

    Used by the structural adapter scan to check whether a class duck-types a Protocol.
    """
    out: list[str] = []
    for di in _iter_class_body_def_indices(lines, class_start):
        match = re.match(r"(?:async\s+)?def\s+(\w+)", lines[di].strip())
        if not match:
            continue
        name = match.group(1)
        if name.startswith("_"):
            continue
        if name not in out:
            out.append(name)
    return out


def _scan_adapter_implementations(k1_path: Path, ports: list[K1PortInfo]) -> None:
    """
    Nominal (inheritance-based) adapter scan.

    Detects classes that inherit from a known port interface, e.g.
    ``class FileStorageAdapter(IStoragePort):``. Required for ABC-based ports
    and still catches inheritance-based Protocol adapters.

    Structural (duck-typed) Protocol satisfaction is handled by
    :func:`_scan_structural_adapters`, which runs afterwards.
    """
    port_names = {p.port_name for p in ports}
    # Multi-map: same port_name may exist in different modules (e.g.
    # kernel.ILifecyclePort and sessionstate.ILifecyclePort, kernel.IFabricPort
    # and concierge.IFabricPort). Credit the adapter to the port whose module
    # matches the adapter file's module; otherwise credit all candidates.
    ports_by_name: dict[str, list[K1PortInfo]] = {}
    for p in ports:
        ports_by_name.setdefault(p.port_name, []).append(p)

    def _file_module(rel: str) -> str:
        parts = rel.replace("\\", "/").split("/")
        # rel_path is "k1/<module>/..." or "tests/k1/<module>/..."
        if parts[:1] == ["k1"] and len(parts) > 1:
            return parts[1]
        if parts[:2] == ["tests", "k1"] and len(parts) > 2:
            return parts[2]
        return ""

    for py_file in k1_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            lines = content.split("\n")
            rel_path = str(py_file.relative_to(k1_path.parent))

            for i, line in enumerate(lines):
                # Match class definitions that reference a known port
                match = re.match(
                    r"^class\s+(\w+)\s*\(([^)]+)\)",
                    line,
                )
                if not match:
                    continue

                class_name = match.group(1)
                bases = match.group(2)

                # Check if any base class is a known port
                for port_name in port_names:
                    if port_name in bases:
                        # Determine if this is a null/mock adapter
                        name_lower = class_name.lower()
                        is_null = "null" in name_lower or "noop" in name_lower
                        is_mock = (
                            "mock" in name_lower or "fake" in name_lower or "stub" in name_lower
                        )

                        adapter = AdapterInfo(
                            class_name=class_name,
                            file_path=rel_path,
                            line_number=i + 1,
                            is_null=is_null,
                            is_mock=is_mock,
                        )

                        # Resolve which port(s) this adapter satisfies. If the
                        # name is unique → trivially that one. If multiple
                        # ports share the name (e.g. ILifecyclePort exists in
                        # both kernel/ and sessionstate/), prefer the one
                        # whose module matches the adapter's file module.
                        candidates = ports_by_name.get(port_name, [])
                        adapter_module = _file_module(rel_path)
                        matched = [c for c in candidates if c.module == adapter_module]
                        if not matched:
                            matched = candidates
                        for port in matched:
                            port.adapters.append(adapter)
                        break

        except Exception:
            continue

    # Also scan tests/ directory for mock adapters
    tests_path = k1_path.parent / "tests" / "k1"
    if tests_path.exists():
        for py_file in tests_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                lines = content.split("\n")
                rel_path = str(py_file.relative_to(k1_path.parent))

                for i, line in enumerate(lines):
                    match = re.match(r"^class\s+(\w+)\s*\(([^)]+)\)", line)
                    if not match:
                        continue

                    class_name = match.group(1)
                    bases = match.group(2)

                    for port_name in port_names:
                        if port_name in bases:
                            adapter = AdapterInfo(
                                class_name=class_name,
                                file_path=rel_path,
                                line_number=i + 1,
                                is_null=False,
                                is_mock=True,
                            )
                            candidates = ports_by_name.get(port_name, [])
                            adapter_module = _file_module(rel_path)
                            matched = [c for c in candidates if c.module == adapter_module]
                            if not matched:
                                matched = candidates
                            for port in matched:
                                port.adapters.append(adapter)
                            break

            except Exception:
                continue


def _scan_structural_adapters(k1_path: Path, ports: list[K1PortInfo]) -> None:
    """
    Structural (duck-typed) adapter scan for ``@runtime_checkable`` Protocol ports.

    For each Protocol port, look in ``k1/<module>/adapters/**/*.py`` for top-level
    classes whose public method set is a superset of the port's required methods.
    Classes that already inherit a known port (caught by the nominal pass) and
    pytest test classes are skipped.
    """
    protocol_ports: dict[str, list[K1PortInfo]] = {}
    for p in ports:
        if p.base_class == "Protocol" and p.methods:
            protocol_ports.setdefault(p.module, []).append(p)
    if not protocol_ports:
        return

    all_port_names = {p.port_name for p in ports}

    for module, mod_ports in protocol_ports.items():
        # Pass A: scan <module>/adapters/ (canonical adapter location)
        # Pass B: scan <module>/**/*.py (excluding ports/, adapters/ already done,
        #   tests, __pycache__) — catches structural impls co-located with
        #   their consumers (e.g. KernelService in service.py satisfies
        #   ISessionManagerPort; ModelHub satisfies IModelHubPort).
        # Pass C: scan ALL of k1/ for cross-module structural impls — required
        #   because some ports are intentional cross-module DI seams (e.g.
        #   kernel.IModelHubPort is satisfied by k1/model_hub/.../ModelHub;
        #   kernel.IPlannerPort by k1/planner/.../Agent). To keep false
        #   positives low, Pass C requires a stricter method-set match.
        scan_dirs: list[Path] = []
        adapters_dir = k1_path / module / "adapters"
        if adapters_dir.exists():
            scan_dirs.append(adapters_dir)
        module_dir = k1_path / module
        if module_dir.exists():
            scan_dirs.append(module_dir)
        # Pass C: cross-module sweep
        scan_dirs.append(k1_path)

        seen_files: set[Path] = set()
        for scan_dir in scan_dirs:
            for py_file in scan_dir.rglob("*.py"):
                if py_file in seen_files:
                    continue
                seen_files.add(py_file)
                if "__pycache__" in str(py_file):
                    continue
                # Skip the originating module's ports/ subtree (Protocol decls).
                try:
                    rel_to_module = py_file.relative_to(module_dir) if module_dir.exists() else None
                except ValueError:
                    rel_to_module = None
                if (
                    rel_to_module is not None
                    and rel_to_module.parts
                    and rel_to_module.parts[0] == "ports"
                ):
                    continue
                # Skip any */ports/* path globally — those are Protocol decls
                if "/ports/" in str(py_file).replace("\\", "/"):
                    continue
                try:
                    lines = py_file.read_text(encoding="utf-8").split("\n")
                except Exception:
                    continue
                rel_path = str(py_file.relative_to(k1_path.parent))
                path_str = str(py_file).replace("\\", "/")
                in_test_path = "/test_" in path_str or "/tests/" in path_str
                fname_lower = py_file.name.lower()

                for i, line in enumerate(lines):
                    m = re.match(r"^class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:", line)
                    if not m:
                        continue
                    class_name = m.group(1)
                    bases = (m.group(2) or "").strip()
                    if class_name.startswith("Test") or class_name.endswith("TestCase"):
                        continue
                    # Skip Protocol declarations themselves
                    if "Protocol" in bases:
                        continue
                    if bases and any(pn in bases for pn in all_port_names):
                        continue  # nominal pass owns it
                    public_methods = set(_extract_class_public_methods(lines, i))
                    if not public_methods:
                        continue
                    name_lower = class_name.lower()
                    is_null = name_lower.startswith("null") or "noop" in name_lower
                    is_mock = (
                        "mock" in name_lower
                        or "fake" in name_lower
                        or "stub" in name_lower
                        or fname_lower.startswith("test_")
                        or in_test_path
                    )
                    for port in mod_ports:
                        required = set(port.methods)
                        if not required or not required.issubset(public_methods):
                            continue
                        if any(
                            a.class_name == class_name and a.file_path == rel_path
                            for a in port.adapters
                        ):
                            continue
                        port.adapters.append(
                            AdapterInfo(
                                class_name=class_name,
                                file_path=rel_path,
                                line_number=i + 1,
                                is_null=is_null,
                                is_mock=is_mock,
                            )
                        )


def _infer_module(py_file: Path, k1_path: Path) -> str:
    """Infer module name from file path."""
    try:
        rel = py_file.relative_to(k1_path)
        parts = rel.parts
        if parts:
            return parts[0]
    except ValueError:
        pass
    return "unknown"


def scan_ports(k1_path: Path | None = None) -> list[K1PortInfo]:
    """
    Scan K1 codebase for port interfaces and their adapter implementations.

    Steps:
    1. Find all port interface definitions (I*Port, I*Provider)
    2. Find all adapter implementations that inherit from ports (nominal pass)
    3. Find duck-typed adapters that satisfy Protocol ports structurally
    4. Link adapters to their port interfaces

    Args:
        k1_path: Path to k1/ directory

    Returns:
        Sorted list of K1PortInfo with linked adapters
    """
    if k1_path is None:
        repo_root = Path(__file__).parent.parent.parent.parent
        k1_path = repo_root / "k1"

    if not k1_path.exists():
        return []

    # 1. Scan for port definitions
    ports = _scan_port_definitions(k1_path)

    # 2. Nominal (inheritance) adapter pass
    _scan_adapter_implementations(k1_path, ports)

    # 3. Structural (duck-typed) adapter pass for Protocol ports
    _scan_structural_adapters(k1_path, ports)

    # Sort by module then port name
    ports.sort(key=lambda p: (p.module, p.port_name))

    return ports


def generate_markdown_table(ports: list[K1PortInfo]) -> str:
    """Generate markdown table for port registry."""
    lines = [
        "| Port | Module | Base | Methods | Adapters | Null | Mock | File |",
        "|------|--------|------|---------|----------|------|------|------|",
    ]

    for p in ports:
        real_adapters = [a for a in p.adapters if not a.is_null and not a.is_mock]
        null_adapters = [a for a in p.adapters if a.is_null]
        mock_adapters = [a for a in p.adapters if a.is_mock]

        adapter_names = ", ".join(a.class_name for a in real_adapters[:2])
        if len(real_adapters) > 2:
            adapter_names += "..."

        lines.append(
            f"| `{p.port_name}` | {p.module} | {p.base_class} | "
            f"{p.method_count} | {adapter_names or '-'} | "
            f"{len(null_adapters)} | {len(mock_adapters)} | "
            f"`{p.file_path.split('/')[-1]}` |"
        )

    return "\n".join(lines)


def generate_summary(ports: list[K1PortInfo]) -> dict[str, Any]:
    """Generate port/adapter summary."""
    by_module: dict[str, int] = {}
    total_adapters = 0
    total_null = 0
    total_mock = 0
    unimplemented: list[str] = []

    for p in ports:
        by_module[p.module] = by_module.get(p.module, 0) + 1
        real = [a for a in p.adapters if not a.is_null and not a.is_mock]
        total_adapters += len(real)
        total_null += sum(1 for a in p.adapters if a.is_null)
        total_mock += sum(1 for a in p.adapters if a.is_mock)
        if not real:
            unimplemented.append(f"{p.module}.{p.port_name}")

    return {
        "total_ports": len(ports),
        "total_adapters": total_adapters,
        "total_null": total_null,
        "total_mock": total_mock,
        "by_module": by_module,
        "unimplemented": unimplemented,
    }


def diff_with_registry(ports: list[K1PortInfo]) -> dict[str, Any]:
    """
    Validate port/adapter consistency.

    Checks:
    - Ports without any real adapters (only null/mock)
    - Ports without null adapters (missing testability)
    - Adapters in test code but no real adapters
    - Protocol ports without ... method bodies
    """
    # Planned-but-not-yet-wired ports + ports satisfied by stub-only impls or
    # cross-module classes the structural scanner can't easily classify.
    # All have docstrings explicitly documenting deferred wiring.
    PLANNED_PORTS: frozenset[str] = frozenset(
        {
            # Planned per 09_wiring_plan S1/S3/S6 — kernel runtime container ports
            "kernel.IBusPort",
            "kernel.IFabricPort",
            "kernel.IOrchestratorPort",
            "kernel.IModelHubPort",
            "kernel.IPlannerPort",
            # Production impl injected at runtime via create_with_ports();
            # only stub provided in-tree (k1/fabric/factory.py:_StubEmbeddingPort)
            "fabric.IEmbeddingPort",
            # File-local section-data providers — satisfied by SessionStateManager
            # via duck typing in production; fakes only in tests
            "sessionstate.IEvictionSectionProvider",
            "sessionstate.IMigrationSectionProvider",
        }
    )

    # Marker Protocols (zero abstract methods) — accepted by design.
    MARKER_PORTS: frozenset[str] = frozenset(
        {
            "fabric.ICapabilityProvider",
        }
    )

    issues: list[str] = []
    warnings: list[str] = []

    for p in ports:
        real = [a for a in p.adapters if not a.is_null and not a.is_mock]
        null = [a for a in p.adapters if a.is_null]
        fq = f"{p.module}.{p.port_name}"

        if not real and not null:
            msg = f"{fq}: no adapters found"
            if fq in PLANNED_PORTS or fq in MARKER_PORTS:
                tag = (
                    "marker Protocol by design"
                    if fq in MARKER_PORTS
                    else "planned per 09_wiring_plan"
                )
                warnings.append(f"{msg} ({tag})")
            else:
                issues.append(msg)
        elif not real:
            msg = f"{fq}: only null/mock adapters, no production adapter"
            if fq in PLANNED_PORTS:
                warnings.append(f"{msg} (planned per 09_wiring_plan)")
            else:
                issues.append(msg)
        if not null and real:
            issues.append(f"{fq}: missing null adapter for testing")
        if p.method_count == 0:
            msg = f"{fq}: port has no abstract methods"
            if fq in MARKER_PORTS:
                warnings.append(f"{msg} (marker Protocol by design)")
            else:
                issues.append(msg)

    return {
        "scanned_count": len(ports),
        "issues": issues,
        "issue_count": len(issues),
        "warnings": warnings,
        "warning_count": len(warnings),
    }


if __name__ == "__main__":
    ports = scan_ports()
    print("K1 Port Scanner")
    print("=" * 60)
    print(f"Found {len(ports)} port interfaces:\n")

    by_module: dict[str, list[K1PortInfo]] = {}
    for p in ports:
        by_module.setdefault(p.module, []).append(p)

    for mod, mod_ports in sorted(by_module.items()):
        print(f"\n  {mod} ({len(mod_ports)} ports):")
        for p in mod_ports:
            real = [a for a in p.adapters if not a.is_null and not a.is_mock]
            null = [a for a in p.adapters if a.is_null]
            mock = [a for a in p.adapters if a.is_mock]
            print(f"    {p.port_name} ({p.base_class}, {p.method_count} methods)")
            for a in real:
                print(f"      -> {a.class_name} ({a.file_path})")
            if null:
                print(f"      -> {len(null)} null adapter(s)")
            if mock:
                print(f"      -> {len(mock)} mock adapter(s)")

    summary = generate_summary(ports)
    print(
        f"\nSummary: {summary['total_ports']} ports, "
        f"{summary['total_adapters']} adapters, "
        f"{summary['total_null']} null, {summary['total_mock']} mock"
    )

    if summary["unimplemented"]:
        print(f"\nUnimplemented ports ({len(summary['unimplemented'])}):")
        for name in summary["unimplemented"]:
            print(f"  ! {name}")

    print("\n" + "=" * 60)
    print("Markdown Table:")
    print(generate_markdown_table(ports))
