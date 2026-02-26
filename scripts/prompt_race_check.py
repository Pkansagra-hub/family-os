"""One-shot race condition analysis for the dynamic prompt system."""

from poc.k1_poc.prompt.affect import AffectBand
from poc.k1_poc.prompt.builder import DynamicPromptBuilder
from poc.k1_poc.prompt.domain_rules import is_domain_applicable
from poc.k1_poc.prompt.mode import PromptMode

builder = DynamicPromptBuilder()

print("=" * 70)
print("ISSUE 1: {open_gaps_list} placeholder in CLARIFY_ASK")
print("=" * 70)
ctx = builder.build(
    mode=PromptMode.CLARIFY_ASK,
    affect_band=AffectBand(band="neutral"),
    all_tool_schemas=[],
)
if "{open_gaps_list}" in ctx.system_prompt:
    print("FOUND: Raw {open_gaps_list} placeholder leaks into assembled prompt!")
else:
    print("OK: placeholder not present")
print()

print("=" * 70)
print("ISSUE 2: WEAVE + crisis -- contradictory instructions")
print("=" * 70)
ctx = builder.build(
    mode=PromptMode.WEAVE,
    affect_band=AffectBand(band="crisis"),
    all_tool_schemas=[],
)
has_topic_first = "CURRENT topic first" in ctx.system_prompt
has_skip = "Skip" in ctx.system_prompt and "bridge" in ctx.system_prompt
if has_topic_first and has_skip:
    print("CONFLICT: Prompt contains both instructions:")
    for line in ctx.system_prompt.split("\n"):
        if "CURRENT topic" in line or ("Skip" in line and "bridge" in line.lower()):
            print(f"  -> {line.strip()}")
else:
    print("OK")
print()

print("=" * 70)
print("ISSUE 3: Trigger warnings in non-trigger modes (REACT_RHYTHM)")
print("=" * 70)
for mode in [PromptMode.STANDARD, PromptMode.CLARIFY_RESOLVE, PromptMode.INTERRUPT]:
    ctx = builder.build(mode=mode, affect_band=AffectBand(band="neutral"), all_tool_schemas=[])
    if "Do NOT call acknowledge()" in ctx.system_prompt and "task_complete" in ctx.system_prompt:
        print(
            f"  {mode.name}: trigger warning present (redundant -- this mode is never triggered by task_complete/weave/hitl)"
        )

print()
print("=" * 70)
print("ISSUE 4: Trigger warnings in REACT_RHYTHM_REDUCED modes")
print("=" * 70)
for mode in [PromptMode.CLARIFY_ASK, PromptMode.HITL_RESOLVE, PromptMode.CANCEL]:
    ctx = builder.build(mode=mode, affect_band=AffectBand(band="neutral"), all_tool_schemas=[])
    if "Do NOT call acknowledge()" in ctx.system_prompt and "task_complete" in ctx.system_prompt:
        print(f"  {mode.name}: trigger warning present (redundant)")

print()
print("=" * 70)
print("ISSUE 5: Crisis effective_iter=1 vs tool/acknowledge instructions")
print("=" * 70)
for mode in PromptMode:
    ctx = builder.build(mode=mode, affect_band=AffectBand(band="crisis"), all_tool_schemas=[])
    if ctx.max_iterations == 1:
        tools_listed = [t.name for t in ctx.tools] if ctx.tools else []
        has_ack_instruction = "acknowledge()" in ctx.system_prompt
        ack_in_tools = "acknowledge" in tools_listed
        print(f"  {mode.name}: max_iter=1, tools={tools_listed}")
        if has_ack_instruction and ack_in_tools:
            print(
                "    WARNING: Prompt instructs acknowledge() AND tool is available, but only 1 iteration means text-only forced"
            )
        elif has_ack_instruction and not ack_in_tools:
            print("    NOTE: Prompt mentions acknowledge() but tool not in allowlist (OK)")

print()
print("=" * 70)
print("ISSUE 6: Domain rules injected in non-applicable modes")
print("=" * 70)
leak_found = False
for domain in ["health", "finance", "legal", "children", "iot", "communication"]:
    for mode in PromptMode:
        ctx = builder.build(
            mode=mode,
            affect_band=AffectBand(band="neutral"),
            all_tool_schemas=[],
            domain=domain,
        )
        applicable = is_domain_applicable(domain, mode.value)
        injected = (
            f"DOMAIN: {domain.upper()}" in ctx.system_prompt
            or f"DOMAIN: {domain.replace('_', ' ').upper()}" in ctx.system_prompt
        )
        # Check both formats
        if not injected:
            # Check raw text match
            domain_text_start = "== DOMAIN:"
            injected = (
                domain_text_start in ctx.system_prompt and domain in ctx.system_prompt.lower()
            )
        if injected and not applicable:
            leak_found = True
            print(f"  LEAK: {domain} injected in {mode.name} (not in DOMAIN_APPLICABLE_MODES)")
if not leak_found:
    print("  Checking...")

print()
print("=" * 70)
print("ISSUE 7: Tool instructions vs tool availability mismatches")
print("=" * 70)
tool_mentions = {
    "dispatch_task": ["dispatch_task", "dispatch a task"],
    "acknowledge": ["acknowledge()"],
    "recall_memory": ["recall_memory"],
    "update_beliefs": ["update_beliefs"],
    "update_scoreboard": ["update_scoreboard"],
    "update_clarifications": ["update_clarifications"],
    "update_narrative": ["update_narrative"],
    "refine_affect": ["refine_affect"],
    "promote_belief": ["promote_belief"],
    "summarize_context": ["summarize_context"],
}

for mode in PromptMode:
    ctx = builder.build(mode=mode, affect_band=AffectBand(band="neutral"), all_tool_schemas=[])
    available = set(t.name for t in ctx.tools)

    for tool_name, patterns in tool_mentions.items():
        # Check if the tool is instructed/mentioned in prompt sections (not examples)
        # but NOT available in the tool list
        mentioned = any(p in ctx.system_prompt for p in patterns)
        in_tools = tool_name in available

        if mentioned and not in_tools:
            # Distinguish: mentioned in anti-pattern (negative) vs instruction (positive)
            # Anti-patterns say "do NOT" -- mentioning a tool to NOT use is fine
            anti_pattern_context = False
            for line in ctx.system_prompt.split("\n"):
                for p in patterns:
                    if p in line and (
                        "NOT" in line
                        or "never" in line.lower()
                        or "NEVER" in line
                        or "Do not" in line
                    ):
                        anti_pattern_context = True

            if not anti_pattern_context:
                print(f"  {mode.name}: prompt instructs '{tool_name}' but tool NOT in allowlist")

print()
print("=" * 70)
print("ISSUE 8: SAFETY_HITL wasted tokens in non-HITL modes")
print("=" * 70)
for mode in PromptMode:
    ctx = builder.build(mode=mode, affect_band=AffectBand(band="neutral"), all_tool_schemas=[])
    if "HITL relay rules" in ctx.system_prompt and mode not in (
        PromptMode.HITL_RELAY,
        PromptMode.HITL_RESOLVE,
    ):
        print(
            f"  {mode.name}: Contains HITL relay rules (wasted tokens -- mode never handles HITL)"
        )

print()
print("=" * 70)
print("ISSUE 9: ANTI_PATTERNS_FULL acknowledge warning vs trigger modes")
print("=" * 70)
for mode in PromptMode:
    ctx = builder.build(mode=mode, affect_band=AffectBand(band="neutral"), all_tool_schemas=[])
    if "ANTI-PATTERNS (NEVER DO THESE)" in ctx.system_prompt:
        if "acknowledge() on task_complete" in ctx.system_prompt:
            print(
                f"  {mode.name}: ANTI_PATTERNS_FULL warns about acknowledge on triggers (mode never receives triggers)"
            )

print()
print("=" * 70)
print("DONE - Race Condition Scan Complete")
print("=" * 70)
