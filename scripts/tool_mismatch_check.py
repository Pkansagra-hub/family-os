"""Check real tool-instruction vs allowlist mismatches."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poc.k1_poc.llm.types import ToolSchema
from poc.k1_poc.prompt.affect import AffectBand
from poc.k1_poc.prompt.builder import DynamicPromptBuilder
from poc.k1_poc.prompt.mode import TOOL_ALLOWLIST, PromptMode

builder = DynamicPromptBuilder()

all_tools = [
    ToolSchema(name=n, description=n + " tool", parameters={})
    for n in [
        "acknowledge",
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "recall_memory",
        "summarize_context",
        "dispatch_task",
        "refine_affect",
        "promote_belief",
    ]
]

tool_patterns = {
    "dispatch_task": ["call dispatch_task", "dispatch_task("],
    "acknowledge": ["call acknowledge()", "acknowledge()"],
    "recall_memory": ["call recall_memory", "recall_memory("],
    "update_beliefs": ["call update_beliefs", "update_beliefs("],
    "update_scoreboard": ["call update_scoreboard", "update_scoreboard("],
    "update_clarifications": ["call update_clarifications", "update_clarifications("],
    "update_narrative": ["call update_narrative", "update_narrative("],
    "refine_affect": ["call refine_affect", "refine_affect("],
    "promote_belief": ["call promote_belief", "promote_belief("],
}

print("=== Tool-instruction vs Allowlist REAL mismatches ===")
print("(prompt instructs tool X but mode allowlist excludes it)\n")

found = 0
for mode in PromptMode:
    ctx = builder.build(
        mode=mode, affect_band=AffectBand(band="neutral"), all_tool_schemas=all_tools
    )
    allowlist = set(TOOL_ALLOWLIST[mode])

    for tool_name, patterns in tool_patterns.items():
        for line in ctx.system_prompt.split("\n"):
            for p in patterns:
                if p in line:
                    negated = "NOT" in line or "never" in line.lower() or "Do not" in line
                    if not negated and tool_name not in allowlist:
                        print(f"  {mode.name}: tool={tool_name}")
                        print(f"    line: {line.strip()[:100]}")
                        found += 1
                        break
            else:
                continue
            break

if found == 0:
    print("  No genuine mismatches found.")

print(f"\nTotal mismatches: {found}")
print(f"\nTotal mismatches: {found}")
print(f"\nTotal mismatches: {found}")
