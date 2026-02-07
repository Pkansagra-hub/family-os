"""
K1 ADR Scanner - Extract ADR definitions from k1/docs/adrs/*.md.

Parses ADR markdown files with YAML frontmatter and extracts:
- ADR ID (FAB-001, SS-001, K1-001, etc.)
- Title
- Status (Proposed, Accepted, Deprecated, Superseded)
- Module (fabric, sessionstate, orchestrator, etc.)
- Layer (L0-L6)
- Related events, contracts, ports
- Implementation issue references

Usage:
    from governance.k1.scripts.adr_scanner import scan_adrs
    adrs = scan_adrs()
    for a in adrs:
        print(f"{a.adr_id}: {a.title} [{a.status}]")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Module prefix to full module name mapping
MODULE_PREFIXES: dict[str, str] = {
    "FAB": "fabric",
    "SS": "sessionstate",
    "ORCH": "orchestrator",
    "PLAN": "planner",
    "CON": "concierge",
    "MH": "model_hub",
    "BUS": "bus",
    "MEM": "memory_writer",
    "AGT": "agent",
    "SUP": "supervision",
    "RET": "retention",
    "HITL": "hitl",
    "TOOL": "tools",
    "COORD": "coordination",
    "SCHED": "scheduler",
    "LEARN": "learning",
    "TRACE": "tracing",
    "CACHE": "cache",
    "CONN": "connectors",
    "SSE": "sse",
    "BR": "bridge",
    "K1": "cross-cutting",
}

# Reverse mapping: module name -> prefix
MODULE_TO_PREFIX: dict[str, str] = {v: k for k, v in MODULE_PREFIXES.items()}


@dataclass
class K1ADRInfo:
    """Extracted K1 ADR information."""

    adr_id: str  # FAB-001, SS-001, K1-001
    title: str
    status: str  # Proposed, Accepted, Deprecated, Superseded
    date: str | None
    module: str  # fabric, sessionstate, cross-cutting
    layer: str | None  # L0, L1, L2, L2.5, L3, L4, L5, L6
    authors: list[str] = field(default_factory=list)
    related_adrs: list[str] = field(default_factory=list)
    related_events: list[str] = field(default_factory=list)
    related_contracts: list[str] = field(default_factory=list)
    related_ports: list[str] = field(default_factory=list)
    implements_issue: str | None = None
    superseded_by: str | None = None
    tags: list[str] = field(default_factory=list)
    file_path: str = ""


def _parse_frontmatter(content: str) -> dict[str, Any] | None:
    """
    Parse YAML frontmatter from markdown content.

    Expects content starting with '---' and ending with '---'.
    Returns parsed YAML dict or None if no frontmatter found.
    """
    # Match frontmatter block
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return None

    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None


def _extract_adr_id_from_filename(filename: str) -> str | None:
    """
    Extract ADR ID from filename.

    Expects: FAB-001-some-title.md, SS-002-another.md, K1-001-cross-cutting.md
    """
    match = re.match(r"^([A-Z]+)-(\d{3})", filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None


def _extract_adr_id_from_content(content: str) -> str | None:
    """Fallback: extract ADR ID from heading or content."""
    match = re.search(r"#\s*([A-Z]+-\d{3})", content)
    if match:
        return match.group(1)
    return None


def _get_module_from_prefix(adr_id: str) -> str:
    """Derive module name from ADR ID prefix."""
    prefix = adr_id.split("-")[0] if "-" in adr_id else adr_id
    return MODULE_PREFIXES.get(prefix, "unknown")


def _ensure_list(val: Any) -> list[str]:
    """Ensure value is a list of strings."""
    if val is None:
        return []
    if isinstance(val, str):
        return [val] if val else []
    if isinstance(val, list):
        return [str(v) for v in val if v]
    return []


def _parse_adr_from_frontmatter(fm: dict[str, Any], filename: str, file_path: str) -> K1ADRInfo:
    """Build K1ADRInfo from parsed YAML frontmatter."""
    adr_id = fm.get("adr_id") or _extract_adr_id_from_filename(filename) or "UNKNOWN"

    return K1ADRInfo(
        adr_id=adr_id,
        title=fm.get("title", "Untitled"),
        status=fm.get("status", "Unknown"),
        date=fm.get("date"),
        module=fm.get("module") or _get_module_from_prefix(adr_id),
        layer=fm.get("layer"),
        authors=_ensure_list(fm.get("authors")),
        related_adrs=_ensure_list(fm.get("related_adrs")),
        related_events=_ensure_list(fm.get("related_events")),
        related_contracts=_ensure_list(fm.get("related_contracts")),
        related_ports=_ensure_list(fm.get("related_ports")),
        implements_issue=fm.get("implements_issue"),
        superseded_by=fm.get("superseded_by"),
        tags=_ensure_list(fm.get("tags")),
        file_path=file_path,
    )


def _parse_adr_fallback(content: str, filename: str, file_path: str) -> K1ADRInfo | None:
    """
    Fallback parser for ADRs without YAML frontmatter.

    Attempts regex extraction from markdown inline fields:
    **Status**: Accepted, **Date**: 2025-01-01, etc.
    """
    adr_id = _extract_adr_id_from_filename(filename) or _extract_adr_id_from_content(content)
    if not adr_id:
        return None

    # Extract title from first heading
    title_match = re.search(r"^#\s+(?:[A-Z]+-\d{3}[:\s-]*)?(.*?)$", content, re.MULTILINE)
    title = title_match.group(1).strip()[:100] if title_match else "Untitled"

    # Extract status
    status = "Unknown"
    status_match = re.search(r"\*\*Status\*\*:\s*(\w+)", content, re.IGNORECASE)
    if status_match:
        status = status_match.group(1).capitalize()

    # Extract date
    date = None
    date_match = re.search(r"\*\*Date\*\*:\s*([\d\-/]+)", content)
    if date_match:
        date = date_match.group(1)

    return K1ADRInfo(
        adr_id=adr_id,
        title=title,
        status=status,
        date=date,
        module=_get_module_from_prefix(adr_id),
        layer=None,
        file_path=file_path,
    )


def scan_adrs(adrs_path: Path | None = None) -> list[K1ADRInfo]:
    """
    Scan k1/docs/adrs/ and extract all ADRs.

    Supports two source formats:
    1. YAML frontmatter (preferred, sync-ready)
    2. Inline markdown fields (legacy fallback)

    Args:
        adrs_path: Path to ADR directory (defaults to k1/docs/adrs/)

    Returns:
        Sorted list of K1ADRInfo with ADR details
    """
    if adrs_path is None:
        repo_root = Path(__file__).parent.parent.parent.parent
        adrs_path = repo_root / "k1" / "docs" / "adrs"

    if not adrs_path.exists():
        return []

    adrs: list[K1ADRInfo] = []

    for md_file in sorted(adrs_path.rglob("*.md")):
        # Skip template and README
        if md_file.name.startswith("_") or md_file.name == "README.md":
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            rel_path = str(md_file.relative_to(adrs_path.parent.parent.parent))

            # Try YAML frontmatter first (preferred)
            fm = _parse_frontmatter(content)
            if fm:
                adr = _parse_adr_from_frontmatter(fm, md_file.name, rel_path)
                adrs.append(adr)
                continue

            # Fallback to regex extraction
            adr = _parse_adr_fallback(content, md_file.name, rel_path)
            if adr:
                adrs.append(adr)

        except Exception as e:
            print(f"Warning: Failed to parse {md_file}: {e}")
            continue

    # Sort by ADR ID
    adrs.sort(key=lambda a: a.adr_id)

    return adrs


def scan_legacy_adrs(legacy_path: Path | None = None) -> list[K1ADRInfo]:
    """
    Scan docs/architecture/decisions-K1/ for legacy ADRs.

    These are historical ADRs that may not have YAML frontmatter.
    This function supports the index.yml format used in the legacy structure.

    Args:
        legacy_path: Path to legacy decisions directory

    Returns:
        List of K1ADRInfo from legacy location
    """
    if legacy_path is None:
        repo_root = Path(__file__).parent.parent.parent.parent
        legacy_path = repo_root / "docs" / "architecture" / "decisions-K1"

    if not legacy_path.exists():
        return []

    adrs: list[K1ADRInfo] = []

    # Scan index.yml files in layer subdirectories
    for index_file in sorted(legacy_path.rglob("index.yml")):
        try:
            content = index_file.read_text(encoding="utf-8")
            index_data = yaml.safe_load(content)

            if not isinstance(index_data, dict):
                continue

            # Extract layer from directory name (e.g., "03-layer2-orchestration" -> "L2")
            layer_dir = index_file.parent.name
            layer = _extract_layer_from_dirname(layer_dir)

            # Process ADR entries - each key below "adrs" is an ADR
            adr_entries = index_data.get("adrs", index_data)
            if isinstance(adr_entries, dict):
                for key, entry in adr_entries.items():
                    if not isinstance(entry, dict):
                        continue
                    adr_number = entry.get("adr_number", key)
                    adrs.append(
                        K1ADRInfo(
                            adr_id=f"LEGACY-{adr_number}",
                            title=entry.get("title", "Untitled"),
                            status=entry.get("status", "Unknown"),
                            date=None,
                            module=_infer_module_from_layers(entry.get("affected_modules", [])),
                            layer=layer,
                            tags=entry.get("concerns", []),
                            file_path=str(index_file.parent / entry.get("file_path", f"{key}/")),
                        )
                    )
            elif isinstance(adr_entries, list):
                for entry in adr_entries:
                    if not isinstance(entry, dict):
                        continue
                    adr_number = entry.get("adr_number", "000")
                    adrs.append(
                        K1ADRInfo(
                            adr_id=f"LEGACY-{adr_number}",
                            title=entry.get("title", "Untitled"),
                            status=entry.get("status", "Unknown"),
                            date=None,
                            module=_infer_module_from_layers(entry.get("affected_modules", [])),
                            layer=layer,
                            tags=entry.get("concerns", []),
                            file_path=str(
                                index_file.parent / entry.get("file_path", f"adr-{adr_number}/")
                            ),
                        )
                    )
        except Exception as e:
            print(f"Warning: Failed to parse {index_file}: {e}")
            continue

    adrs.sort(key=lambda a: a.adr_id)
    return adrs


def _extract_layer_from_dirname(dirname: str) -> str | None:
    """Extract layer designation from directory name."""
    match = re.search(r"layer(\d+(?:\.\d+)?)", dirname, re.IGNORECASE)
    if match:
        return f"L{match.group(1)}"
    if "cross" in dirname.lower() or "foundation" in dirname.lower():
        return "L0"
    return None


def _infer_module_from_layers(affected_modules: list[str] | None) -> str:
    """Infer primary module from affected_modules list."""
    if not affected_modules:
        return "cross-cutting"
    # Return first module
    return affected_modules[0] if affected_modules else "cross-cutting"


def generate_markdown_table(adrs: list[K1ADRInfo]) -> str:
    """Generate markdown table for ADR registry."""
    lines = [
        "| ID | Title | Status | Module | Layer | Events | Contracts | Ports | Tags |",
        "|----|-------|--------|--------|-------|--------|-----------|-------|------|",
    ]

    for a in adrs:
        title = a.title[:35]
        if len(a.title) > 35:
            title += "..."

        events = str(len(a.related_events)) if a.related_events else "-"
        contracts = str(len(a.related_contracts)) if a.related_contracts else "-"
        ports = str(len(a.related_ports)) if a.related_ports else "-"
        tags_display = ", ".join(a.tags[:2]) if a.tags else "-"
        if len(a.tags) > 2:
            tags_display += "..."

        lines.append(
            f"| `{a.adr_id}` | {title} | {a.status} | {a.module} | "
            f"{a.layer or '-'} | {events} | {contracts} | {ports} | {tags_display} |"
        )

    return "\n".join(lines)


def generate_summary(adrs: list[K1ADRInfo]) -> dict[str, Any]:
    """Generate summary statistics for ADRs."""
    by_status: dict[str, int] = {}
    by_module: dict[str, int] = {}
    by_layer: dict[str, int] = {}

    for a in adrs:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        by_module[a.module] = by_module.get(a.module, 0) + 1
        if a.layer:
            by_layer[a.layer] = by_layer.get(a.layer, 0) + 1

    return {
        "total": len(adrs),
        "by_status": by_status,
        "by_module": by_module,
        "by_layer": by_layer,
    }


def diff_with_registry(adrs: list[K1ADRInfo], registry_path: Path | None = None) -> dict[str, Any]:
    """
    Compare scanned ADRs against a registry file or future master doc.

    Currently compares against k1/docs/adrs/README.md prefix table
    and validates internal consistency.

    Args:
        adrs: Scanned ADRs
        registry_path: Path to registry file (future k1_architecture_master.md)

    Returns:
        Dict with drift information
    """
    issues: list[str] = []

    # Check for duplicate IDs
    seen_ids: dict[str, str] = {}
    for a in adrs:
        if a.adr_id in seen_ids:
            issues.append(f"Duplicate ID {a.adr_id}: {a.file_path} and {seen_ids[a.adr_id]}")
        seen_ids[a.adr_id] = a.file_path

    # Validate ID prefix matches module
    for a in adrs:
        expected_module = _get_module_from_prefix(a.adr_id)
        if expected_module != "unknown" and a.module != expected_module:
            issues.append(
                f"{a.adr_id}: prefix suggests module '{expected_module}' "
                f"but frontmatter says '{a.module}'"
            )

    # Check for missing required fields
    for a in adrs:
        if a.status == "Unknown":
            issues.append(f"{a.adr_id}: missing status")
        if not a.date:
            issues.append(f"{a.adr_id}: missing date")
        if a.module == "unknown":
            issues.append(f"{a.adr_id}: unrecognized module prefix")

    # Check for broken ADR cross-references
    all_ids = {a.adr_id for a in adrs}
    for a in adrs:
        for ref in a.related_adrs:
            if ref not in all_ids:
                issues.append(f"{a.adr_id}: references unknown ADR '{ref}'")
        if a.superseded_by and a.superseded_by not in all_ids:
            issues.append(f"{a.adr_id}: superseded_by references unknown ADR '{a.superseded_by}'")

    return {
        "scanned_count": len(adrs),
        "issues": issues,
        "issue_count": len(issues),
    }


if __name__ == "__main__":
    print("K1 ADR Scanner")
    print("=" * 60)

    # Scan primary location
    adrs = scan_adrs()
    print(f"\nFound {len(adrs)} ADRs in k1/docs/adrs/:\n")

    by_module: dict[str, list[K1ADRInfo]] = {}
    for a in adrs:
        by_module.setdefault(a.module, []).append(a)

    for mod, mod_adrs in sorted(by_module.items()):
        print(f"\n  {mod} ({len(mod_adrs)}):")
        for a in mod_adrs[:5]:
            print(f"    {a.adr_id}: {a.title[:50]} [{a.status}]")
        if len(mod_adrs) > 5:
            print(f"    ... and {len(mod_adrs) - 5} more")

    # Check legacy location
    legacy = scan_legacy_adrs()
    if legacy:
        print(f"\nFound {len(legacy)} legacy ADRs in docs/architecture/decisions-K1/")

    # Validate
    diff = diff_with_registry(adrs)
    if diff["issues"]:
        print(f"\nValidation issues ({diff['issue_count']}):")
        for issue in diff["issues"][:10]:
            print(f"  ! {issue}")
    else:
        print("\nNo validation issues found.")

    print("\n" + "=" * 60)
    print("Markdown Table:")
    print(generate_markdown_table(adrs[:10]))
