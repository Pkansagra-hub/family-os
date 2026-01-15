"""
ADR Scanner - Extract ADR definitions from docs/architecture/decisions-K0/*.md.

Parses ADR markdown files and extracts:
- ADR ID (K001, K002, etc.)
- Title
- Status (Accepted, Proposed, Deprecated)
- Category (Core, Pipeline, Module)
- Related modules/pipelines

Usage:
    from governance.k0.scripts.adr_scanner import scan_adrs
    adrs = scan_adrs()
    for a in adrs:
        print(f"{a['adr_id']}: {a['title']} [{a['status']}]")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ADRInfo:
    """Extracted ADR information."""

    adr_id: str  # K001, K002, etc.
    title: str
    status: str  # Accepted, Proposed, Deprecated, Superseded
    category: str  # Core, Pipeline, Module
    date: str | None
    related_modules: list[str] = field(default_factory=list)
    related_pipelines: list[str] = field(default_factory=list)
    file_path: str = ""
    superseded_by: str | None = None


def _extract_adr_id(filename: str, content: str) -> str:
    """Extract ADR ID from filename or content."""
    # Try filename first (k001-xxx.md -> K001, k003.1-xxx.md -> K003.1)
    match = re.search(r"k(\d{3}(?:\.\d+)?)", filename.lower())
    if match:
        return f"K{match.group(1)}"

    # Try content header
    match = re.search(r"#\s*(?:ADR[- ]?)?(K\d{3}(?:\.\d+)?)", content, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    return "Kxxx"


def _extract_title(content: str) -> str:
    """Extract title from first heading."""
    match = re.search(r"^#\s+(?:ADR[- ]?K?\d+[:\s-]*)?(.*?)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()[:100]
    return "Untitled"


def _extract_status(content: str) -> str:
    """Extract status from content."""
    # Look for Status: line
    match = re.search(r"\*\*Status\*\*:\s*(\w+)", content, re.IGNORECASE)
    if match:
        status = match.group(1).lower()
        if "accepted" in status or "active" in status:
            return "Accepted"
        if "proposed" in status or "draft" in status:
            return "Proposed"
        if "deprecated" in status:
            return "Deprecated"
        if "superseded" in status:
            return "Superseded"

    # Check for status in table
    match = re.search(r"\|\s*Status\s*\|\s*(\w+)", content, re.IGNORECASE)
    if match:
        return match.group(1).capitalize()

    return "Unknown"


def _extract_date(content: str) -> str | None:
    """Extract date from content."""
    match = re.search(r"\*\*Date\*\*:\s*([\d\-/]+)", content)
    if match:
        return match.group(1)

    match = re.search(r"Date:\s*([\d\-/]+)", content)
    if match:
        return match.group(1)

    return None


def _extract_related_modules(content: str) -> list[str]:
    """Extract related module IDs."""
    modules = set()
    for match in re.finditer(r"\b(M\d{2})\b", content):
        modules.add(match.group(1))
    return sorted(modules)


def _extract_related_pipelines(content: str) -> list[str]:
    """Extract related pipeline IDs."""
    pipelines = set()
    for match in re.finditer(r"\b(P\d{2})\b", content):
        pipelines.add(match.group(1))
    return sorted(pipelines)


def _extract_superseded_by(content: str) -> str | None:
    """Check if ADR is superseded."""
    match = re.search(r"[Ss]uperseded\s+by\s+(K\d{3})", content)
    if match:
        return match.group(1)
    return None


def _determine_category(filepath: Path, content: str) -> str:
    """Determine ADR category from path or content."""
    path_str = str(filepath).lower()

    if "/modules/" in path_str:
        return "Module"
    if "/pipelines/" in path_str:
        return "Pipeline"
    if "/core/" in path_str:
        return "Core"

    # Check content for hints
    content_lower = content.lower()
    if "module" in content_lower[:500]:
        return "Module"
    if "pipeline" in content_lower[:500]:
        return "Pipeline"

    return "Core"


def scan_adrs(decisions_path: Path | None = None) -> list[ADRInfo]:
    """
    Scan docs/architecture/decisions-K0/ and extract all ADRs.

    Args:
        decisions_path: Path to decisions directory (defaults to repo root)

    Returns:
        List of ADRInfo with ADR details
    """
    if decisions_path is None:
        repo_root = Path(__file__).parent.parent.parent.parent
        decisions_path = repo_root / "docs" / "architecture" / "decisions-K0"

    if not decisions_path.exists():
        raise FileNotFoundError(f"Decisions directory not found at {decisions_path}")

    adrs: list[ADRInfo] = []

    # Scan main directory and subdirectories
    for md_file in sorted(decisions_path.rglob("*.md")):
        if md_file.name.startswith("_") or md_file.name == "README.md":
            continue

        try:
            content = md_file.read_text(encoding="utf-8")

            adr_id = _extract_adr_id(md_file.name, content)
            if adr_id == "Kxxx":
                continue  # Skip non-ADR files

            # Skip K000 template file
            if adr_id == "K000":
                continue

            adrs.append(
                ADRInfo(
                    adr_id=adr_id,
                    title=_extract_title(content),
                    status=_extract_status(content),
                    category=_determine_category(md_file, content),
                    date=_extract_date(content),
                    related_modules=_extract_related_modules(content),
                    related_pipelines=_extract_related_pipelines(content),
                    file_path=str(md_file.relative_to(decisions_path.parent.parent.parent)),
                    superseded_by=_extract_superseded_by(content),
                )
            )
        except Exception as e:
            print(f"Warning: Failed to parse {md_file}: {e}")
            continue

    # Sort by ADR ID
    adrs.sort(key=lambda a: a.adr_id)

    return adrs


def generate_markdown_table(adrs: list[ADRInfo]) -> str:
    """Generate markdown table for Part 11.1 ADR Registry."""
    lines = [
        "| ID | Title | Status | Category | Modules | Pipelines | Date |",
        "|----|-------|--------|----------|---------|-----------|------|",
    ]

    for a in adrs:
        modules = ", ".join(a.related_modules[:3]) or "-"
        if len(a.related_modules) > 3:
            modules += "..."
        pipelines = ", ".join(a.related_pipelines[:2]) or "-"
        if len(a.related_pipelines) > 2:
            pipelines += "..."
        date = a.date or "-"

        title = a.title[:40]
        if len(a.title) > 40:
            title += "..."

        lines.append(
            f"| `{a.adr_id}` | {title} | {a.status} | {a.category} | {modules} | {pipelines} | {date} |"
        )

    return "\n".join(lines)


def diff_with_master(adrs: list[ADRInfo], master_path: Path) -> dict[str, Any]:
    """
    Compare scanned ADRs with what's in k0_architecture_master.md.

    Uses MarkdownRegistry for reliable AST-based table parsing.
    """
    from governance.k0.scripts.markdown_parser import MarkdownRegistry

    registry = MarkdownRegistry(master_path)

    # Get ADR tables from Part 11.1 (there may be multiple subtables)
    registered = set()

    # Try to get the Core ADRs table
    core_table = registry.get_table("11.1", "Core ADRs")
    pipeline_table = registry.get_table("11.1", "Pipeline ADRs")
    module_table = registry.get_table("11.1", "Module ADRs")

    for table in [core_table, pipeline_table, module_table]:
        if table:
            for row in table.rows:
                # ADR ID typically in first column - match case-insensitively
                first_cell = row.cells[0] if row.cells else ""
                # Match K001 or k001 format (with optional sub-version .1)
                match = re.search(r"[kK](\d{3}(?:\.\d+)?)", first_cell)
                if match:
                    # Normalize to uppercase
                    registered.add(f"K{match.group(1)}")

    scanned_ids = {a.adr_id for a in adrs}

    return {
        "missing_in_master": sorted(scanned_ids - registered),
        "missing_in_code": sorted(registered - scanned_ids),
        "scanned_count": len(adrs),
        "registered_count": len(registered),
    }


if __name__ == "__main__":
    adrs = scan_adrs()
    print(f"Found {len(adrs)} ADRs:\n")

    by_category = {}
    for a in adrs:
        by_category.setdefault(a.category, []).append(a)

    for cat, cat_adrs in sorted(by_category.items()):
        print(f"\n{cat} ({len(cat_adrs)}):")
        for a in cat_adrs[:5]:
            print(f"  {a.adr_id}: {a.title[:50]} [{a.status}]")
        if len(cat_adrs) > 5:
            print(f"  ... and {len(cat_adrs) - 5} more")

    print("\n" + "=" * 60)
    print("Markdown Table (first 10):")
    print(generate_markdown_table(adrs[:10]))
