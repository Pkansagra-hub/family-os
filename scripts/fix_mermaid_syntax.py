"""Fix Mermaid-breaking syntax in the architecture diagram."""

import re

with open(
    r"D:\familyos\architecture_diagrams\k1\back_tool_contract_architecture.mmd",
    "r",
    encoding="utf-8",
) as f:
    content = f.read()

# Fix 1: Replace \" with ' inside node text (Mermaid doesn't support escaped quotes in "..." strings)
content = content.replace('\\"', "'")

# Fix 2: Find multi-line subgraph titles (where the [" text spans multiple lines)
# Convert them to single-line with \n
# Pattern: subgraph XYZ["line1\n        line2\n        line3"]

# We need to find [" ... "] that spans multiple lines
result = []
i = 0
in_subgraph = False
in_title = False
title_start = 0
while i < len(content):
    if not in_subgraph:
        # Look for subgraph keyword followed by [
        m = re.search(r'subgraph\s+\w+\["', content[i:])
        if m:
            in_subgraph = True
            in_title = True
            title_start = i + m.start()
            # Find the opening [
            bracket_m = re.search(r'\["', content[i:])
            depth = 1
            j = i + bracket_m.start() + 2  # past ["
            # Find the matching "]
            while j < len(content) and depth > 0:
                if content[j] == "[":
                    depth += 1
                elif content[j] == "]":
                    depth -= 1
                elif content[j] == "\n" and depth == 1:
                    # We're inside the title and hit a newline - replace with \n
                    content = content[:j] + "\\n" + content[j + 1 :]
                    j += 2  # skip the \\n we just inserted
                    continue
                j += 1
            in_subgraph = False
            in_title = False
            i = j
            continue
    i += 1

with open(
    r"D:\familyos\architecture_diagrams\k1\back_tool_contract_architecture.mmd",
    "w",
    encoding="utf-8",
) as f:
    f.write(content)

# Verify by checking for any remaining issues
print("Fixed. Checking for remaining issues...")
with open(
    r"D:\familyos\architecture_diagrams\k1\back_tool_contract_architecture.mmd",
    "r",
    encoding="utf-8",
) as f:
    lines = f.readlines()

issues = []
for i, l in enumerate(lines):
    if '\\"' in l:
        issues.append((i + 1, l.strip()[:100]))

for num, text in issues:
    print(f"  REMAINING LINE {num}: {text}")
if not issues:
    print("  None found - clean!")
