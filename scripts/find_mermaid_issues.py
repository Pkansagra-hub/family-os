"""Find Mermaid-breaking syntax issues."""

with open(
    r"D:\familyos\architecture_diagrams\k1\back_tool_contract_architecture.mmd",
    "r",
    encoding="utf-8",
) as f:
    lines = f.readlines()

issues = []
for i, l in enumerate(lines):
    # Check for backslash-escaped quotes
    bs_idx = l.find('\\"')
    if bs_idx >= 0:
        issues.append((i + 1, "backslash-quote", bs_idx, l.strip()[:120]))
    # Check for \n inside node text (should be literal newline or #10;)
    # Check for unescaped " inside "..." that might break parsing

for num, kind, idx, text in issues:
    print(f"  LINE {num:>4} [{kind} at col {idx}]: {text}")
if not issues:
    print("No issues found")
else:
    print(f"\nTotal: {len(issues)} issues")
