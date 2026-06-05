"""Verify the fixed diagram."""

with open(
    r"D:\familyos\architecture_diagrams\k1\back_tool_contract_architecture.mmd",
    "r",
    encoding="utf-8",
) as f:
    content = f.read()
    lines = content.split("\n")

print(f"Lines: {len(lines)}")
ob = content.count("{")
cb = content.count("}")
print(f"Braces: {ob}/{cb} Match: {ob==cb}")

# Check for key sections
sections = [
    "RULES",
    "L0_ROUTING",
    "L1_INTAKE",
    "OVERVIEW",
    "Q1_WHO",
    "Q2_ALLOWED",
    "Q3_TOOL",
    "OUTPUT",
    "TAXONOMY",
    "L3_VERDICT",
    "L4_LOOP",
    "L5_SERVICE",
    "L6_WRAPUP",
    "HAPPY",
    "GUIDE",
    "STORES",
]
for s in sections:
    found = [i + 1 for i, l in enumerate(lines) if f"subgraph {s}" in l]
    print(f'  {"OK" if found else "MISS"} {s}: line {found[0] if found else "-"}')

# Check for any remaining SyntaxErrors
if ob != cb:
    print("\nWARNING: Brace mismatch!")

# Check for multi-line subgraph titles that didn't get fixed
print("\nMulti-line subgraph titles (potential issue):")
for i, l in enumerate(lines):
    stripped = l.strip()
    if stripped.startswith("subgraph ") and "[" in stripped:
        # Check if this spans multiple lines
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if (
                next_line
                and not next_line.startswith("direction")
                and not next_line.startswith("%%")
            ):
                # This subgraph title might continue on next line
                if "]" not in stripped:
                    print(f"  Line {i+1}: title continues to next line")
