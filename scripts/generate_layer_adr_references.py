#!/usr/bin/env python3
"""
Generate layer-specific ADR reference files from the ADR family map.

This script:
1. Parses docs/architecture/tables/adr_family_map.md
2. Extracts all ADRs for each layer (L1-L5 + N/A)
3. Generates comprehensive ADR reference markdown files for each layer
4. Handles multi-layer entries (e.g., L1-L3 appears in L1, L2, and L3)
5. Includes N/A (cross-cutting) ADRs in all layer references

Output files:
- k1/l1_input/ADR_REFERENCE.md
- k1/l2_orchestration/ADR_REFERENCE.md
- k1/l3_execution/ADR_REFERENCE.md
- k1/l4_runtime/ADR_REFERENCE.md
- k1/l5_infrastructure/ADR_REFERENCE.md
- docs/architecture/ADR_REFERENCE_CROSS_CUTTING.md
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def parse_adr_family_map(map_file: Path) -> List[Dict[str, str]]:
    """
    Parse the ADR family map markdown table.

    Returns list of entries with keys:
    - family, subcomponent, sub_subcomponent, layer, file, examples, adr
    """
    entries = []

    with open(map_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the table between markers
    start_marker = "<!-- ADR-FAMILY-MAP:BEGIN -->"
    end_marker = "<!-- ADR-FAMILY-MAP:END -->"

    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print(f"⚠️  Warning: Could not find table markers in {map_file}")
        return entries

    table_content = content[start_idx + len(start_marker) : end_idx]
    lines = table_content.strip().split("\n")

    # Skip header and separator rows
    data_lines = [l for l in lines if l.strip() and not l.strip().startswith("|---")]
    if len(data_lines) > 0 and "|" in data_lines[0]:
        data_lines = data_lines[1:]  # Skip header row

    for line in data_lines:
        if not line.strip() or not line.strip().startswith("|"):
            continue

        # Split by | and clean up
        parts = [p.strip() for p in line.split("|")]
        parts = [p for p in parts if p]  # Remove empty strings

        if len(parts) < 7:
            continue

        entry = {
            "family": parts[0],
            "subcomponent": parts[1],
            "sub_subcomponent": parts[2],
            "layer": parts[3],
            "file": parts[4],
            "examples": parts[5],
            "adr": parts[6],
        }

        entries.append(entry)

    return entries


def extract_adr_numbers(adr_text: str) -> List[str]:
    """
    Extract ADR numbers from the ADR column text.

    Examples:
    - "ADR-0004" -> ["ADR-0004"]
    - "ADR-0015, ADR-0015a" -> ["ADR-0015", "ADR-0015a"]
    - "ADR-0084, ADR-0084a/b/c/d" -> ["ADR-0084", "ADR-0084a", "ADR-0084b", "ADR-0084c", "ADR-0084d"]
    """
    adrs = []

    # Remove markdown links and status markers
    adr_text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", adr_text)
    adr_text = re.sub(r"NEEDS_IMPLEMENTATION|PLANNED|DRAFT", "", adr_text)

    # Find all ADR-XXXX patterns
    adr_pattern = r"ADR-(\d{4}[a-z]?)"
    matches = re.findall(adr_pattern, adr_text, re.IGNORECASE)

    for match in matches:
        adrs.append(f"ADR-{match}")

    # Handle slash notation (e.g., ADR-0084a/b/c/d)
    slash_pattern = r"ADR-(\d{4})([a-z])/([a-z])"
    slash_matches = re.findall(slash_pattern, adr_text, re.IGNORECASE)

    for base, first, rest in slash_matches:
        # Remove the already-added first letter version if present
        base_adr = f"ADR-{base}{first}"
        if base_adr not in adrs:
            adrs.append(base_adr)
        # Add the rest
        for letter in rest:
            adrs.append(f"ADR-{base}{letter}")

    return sorted(set(adrs))


def get_layer_entries(
    entries: List[Dict[str, str]], layer: str
) -> List[Dict[str, str]]:
    """
    Get all entries for a specific layer.

    Handles multi-layer entries like "L1-L3" (should appear in L1, L2, and L3).
    """
    layer_entries = []

    for entry in entries:
        entry_layer = entry["layer"].strip()

        # Handle exact match
        if entry_layer == layer:
            layer_entries.append(entry)
            continue

        # Handle multi-layer entries (e.g., "L1-L3")
        if "-" in entry_layer:
            try:
                start, end = entry_layer.split("-")
                start_num = int(start[1:]) if start.startswith("L") else 0
                end_num = int(end[1:]) if end.startswith("L") else 0
                layer_num = int(layer[1:]) if layer.startswith("L") else 0

                if start_num <= layer_num <= end_num:
                    layer_entries.append(entry)
            except (ValueError, IndexError):
                pass

    return layer_entries


def get_unique_adrs(entries: List[Dict[str, str]]) -> List[str]:
    """
    Get sorted unique list of ADRs from entries.

    Sorts ADR-XXXX numerically, then by suffix letter.
    """
    all_adrs = set()

    for entry in entries:
        adrs = extract_adr_numbers(entry["adr"])
        all_adrs.update(adrs)

    # Sort: ADR-0004, ADR-0004a, ADR-0004b, ADR-0015, etc.
    def adr_sort_key(adr: str) -> Tuple[int, str]:
        match = re.match(r"ADR-(\d+)([a-z]?)", adr, re.IGNORECASE)
        if match:
            num, letter = match.groups()
            return (int(num), letter or "")
        return (9999, adr)

    return sorted(all_adrs, key=adr_sort_key)


def group_entries_by_family(
    entries: List[Dict[str, str]],
) -> Dict[str, List[Dict[str, str]]]:
    """Group entries by family name."""
    grouped = defaultdict(list)

    for entry in entries:
        family = entry["family"]
        grouped[family].append(entry)

    return dict(grouped)


def generate_layer_reference(
    layer: str,
    entries: List[Dict[str, str]],
    output_file: Path,
    na_entries: List[Dict[str, str]],
) -> None:
    """
    Generate ADR reference markdown file for a layer.

    Args:
        layer: Layer name (L1, L2, L3, L4, L5, or N/A)
        entries: Layer-specific entries
        output_file: Output file path
        na_entries: Cross-cutting N/A entries to include
    """
    # Combine layer-specific and N/A entries
    all_entries = entries + na_entries

    unique_adrs = get_unique_adrs(all_entries)
    grouped = group_entries_by_family(all_entries)

    layer_names = {
        "L1": "Layer 1 - Input",
        "L2": "Layer 2 - Orchestration",
        "L3": "Layer 3 - Execution",
        "L4": "Layer 4 - Runtime",
        "L5": "Layer 5 - Infrastructure",
        "N/A": "Cross-Cutting Concerns",
    }

    layer_descriptions = {
        "L1": "This layer handles all input streams (WebSocket, audio, multimodal) and initial processing.",
        "L2": "This layer orchestrates agent coordination, planning, and task management.",
        "L3": "This layer executes agent tasks, tool calls, and model inference.",
        "L4": "This layer manages session state, learning loops, and runtime coordination.",
        "L5": "This layer provides infrastructure services (event bus, metrics, storage).",
        "N/A": "These ADRs apply across all layers and affect system-wide architecture.",
    }

    # Generate markdown content
    lines = []
    lines.append(f"# ADR Reference Guide: {layer_names.get(layer, layer)}")
    lines.append("")
    lines.append("**Generated:** Auto-generated from ADR family map  ")
    lines.append(
        f"**Purpose:** Quick reference for ADRs relevant to {layer_names.get(layer, layer)} development"
    )
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(layer_descriptions.get(layer, ""))
    lines.append("")
    lines.append(f"**Total Relevant ADRs:** {len(unique_adrs)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## Quick Reference: All ADRs for {layer_names.get(layer, layer)}")
    lines.append("")
    lines.append("| ADR | Title | Family |")
    lines.append("|-----|-------|--------|")

    # Build ADR to title mapping
    adr_to_title = {}
    adr_to_family = {}
    for entry in all_entries:
        adrs = extract_adr_numbers(entry["adr"])
        for adr in adrs:
            if adr not in adr_to_title:
                # Try to extract title from ADR number
                adr_num = adr.replace("ADR-", "").replace("adr-", "")
                # Construct ADR filename
                adr_file = f"docs/architecture/decisions/{adr_num.lower()}-*.md"
                # Use subcomponent as title placeholder
                title = f"{adr_num.upper()} {entry['subcomponent']}"
                adr_to_title[adr] = title
                adr_to_family[adr] = entry["family"]

    # Generate quick reference table
    for adr in unique_adrs:
        title = adr_to_title.get(adr, "Unknown")
        family = adr_to_family.get(adr, "Unknown")
        adr_link = adr.lower().replace("adr-", "")
        lines.append(
            f"| [{adr}](../../docs/architecture/decisions/{adr_link}-*.md) | {title} | {family} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Detailed Breakdown by Family")
    lines.append("")

    # Generate detailed breakdown
    for family in sorted(grouped.keys()):
        family_entries = grouped[family]
        family_adrs = get_unique_adrs(family_entries)

        lines.append(f"### {family}")
        lines.append("")

        # Group by ADR within family
        adr_to_entries = defaultdict(list)
        for entry in family_entries:
            adrs = extract_adr_numbers(entry["adr"])
            for adr in adrs:
                adr_to_entries[adr].append(entry)

        for adr in sorted(
            family_adrs, key=lambda x: (int(re.search(r"\d+", x).group()), x)
        ):
            adr_entries = adr_to_entries[adr]
            title = adr_to_title.get(adr, "Unknown")
            adr_link = adr.lower().replace("adr-", "")

            lines.append(
                f"#### [{adr}](../../docs/architecture/decisions/{adr_link}-*.md): {title}"
            )
            lines.append("")
            lines.append("**Components:**")
            lines.append("")

            for entry in adr_entries:
                component_name = entry["sub_subcomponent"] or entry["subcomponent"]
                lines.append(f"- **{entry['subcomponent']}** → {component_name}")
                lines.append(f"  - File: `{entry['file']}`")

                # Truncate examples if too long
                examples = entry["examples"]
                if len(examples) > 200:
                    examples = examples[:197] + "..."

                lines.append(f"  - {examples}")
                lines.append("")

        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Usage Guidelines")
    lines.append("")
    lines.append(
        "1. **Before Development**: Review relevant ADRs to understand architectural decisions and constraints"
    )
    lines.append(
        "2. **During Development**: Reference specific ADR sections for implementation details and patterns"
    )
    lines.append(
        "3. **Code Reviews**: Verify implementations align with ADR specifications"
    )
    lines.append(
        "4. **Updates**: If you modify an ADR, regenerate this file using `python scripts/generate_layer_adr_references.py`"
    )
    lines.append("")
    lines.append("## Legend")
    lines.append("")
    lines.append(
        "- **Family**: High-level architectural area (e.g., Actor Fabric, Bridge, K0 Core)"
    )
    lines.append(
        "- **Components**: Specific implementation components covered by the ADR"
    )
    lines.append("- **File**: Python module path where component is implemented")
    lines.append("- **N/A ADRs**: Cross-cutting concerns that apply to all layers")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*This file is auto-generated. Do not edit manually. Regenerate using:*"
    )
    lines.append("```bash")
    lines.append("python scripts/generate_layer_adr_references.py")
    lines.append("```")

    # Write to file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(
        f"✅ Generated {output_file} ({len(unique_adrs)} ADRs, {len(all_entries)} total entries)"
    )


def main():
    """Main entry point."""
    # Paths
    repo_root = Path(__file__).parent.parent
    family_map_file = (
        repo_root / "docs" / "architecture" / "tables" / "adr_family_map.md"
    )

    if not family_map_file.exists():
        print(f"❌ Error: ADR family map not found at {family_map_file}")
        return 1

    print(f"📖 Parsing ADR family map from {family_map_file}...")
    entries = parse_adr_family_map(family_map_file)
    print(f"📊 Found {len(entries)} total entries in family map")

    # Get N/A (cross-cutting) entries
    na_entries = get_layer_entries(entries, "N/A")
    print(f"🔄 Found {len(na_entries)} cross-cutting (N/A) entries")

    # Layer configurations
    layers = {
        "L1": repo_root / "k1" / "l1_input" / "ADR_REFERENCE.md",
        "L2": repo_root / "k1" / "l2_orchestration" / "ADR_REFERENCE.md",
        "L3": repo_root / "k1" / "l3_execution" / "ADR_REFERENCE.md",
        "L4": repo_root / "k1" / "l4_runtime" / "ADR_REFERENCE.md",
        "L5": repo_root / "k1" / "l5_infrastructure" / "ADR_REFERENCE.md",
    }

    # Generate layer-specific references
    print("\n🚀 Generating layer-specific ADR references...")
    print("=" * 70)

    for layer, output_file in layers.items():
        layer_entries = get_layer_entries(entries, layer)
        layer_adrs = get_unique_adrs(layer_entries)

        print(
            f"\n{layer}: {len(layer_adrs)} unique ADRs ({len(layer_entries)} entries)"
        )
        print(f"   Output: {output_file.relative_to(repo_root)}")

        generate_layer_reference(layer, layer_entries, output_file, na_entries)

    # Generate N/A cross-cutting reference
    na_output = repo_root / "docs" / "architecture" / "ADR_REFERENCE_CROSS_CUTTING.md"
    na_adrs = get_unique_adrs(na_entries)

    print(f"\nN/A: {len(na_adrs)} unique ADRs ({len(na_entries)} entries)")
    print(f"   Output: {na_output.relative_to(repo_root)}")

    generate_layer_reference("N/A", na_entries, na_output, [])

    print("\n" + "=" * 70)
    print("✅ All ADR reference files generated successfully!")
    print("\n📝 Summary:")
    print(f"   Total entries processed: {len(entries)}")
    print(f"   Layer reference files: {len(layers)}")
    print("   Cross-cutting reference: 1")
    print(f"   Total files generated: {len(layers) + 1}")

    return 0


if __name__ == "__main__":
    exit(main())
