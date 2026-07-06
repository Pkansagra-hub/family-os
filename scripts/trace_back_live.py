"""Live Back LLM trace watcher.

Watches data/prompt_dumps/no_session/back/ for new prompt dump files
and prints a real-time trace of Back's behavior: system prompt key
sections, tool calls, tool results.

Usage:
  $env:PYTHONPATH="D:\familyos"
  python scripts\trace_back_live.py              # watch existing dumps + new ones
  python scripts\trace_back_live.py --follow     # tail mode: keep watching for new dumps
  python scripts\trace_back_live.py --latest     # just show the latest dump in detail
  python scripts\trace_back_live.py --session <hash>  # trace a specific session across all iters
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

DUMP_ROOT = Path("data/prompt_dumps")


def _find_back_dumps() -> list[Path]:
    """Find all Back prompt dumps across all session directories."""
    if not DUMP_ROOT.exists():
        return []
    dumps = []
    for session_dir in DUMP_ROOT.iterdir():
        if session_dir.is_dir():
            back_dir = session_dir / "back"
            if back_dir.is_dir():
                dumps.extend(back_dir.glob("back_llm_request_*.json"))
    return dumps


def _find_latest_dump() -> Path | None:
    """Find the most recent Back prompt dump."""
    dumps = _find_back_dumps()
    if not dumps:
        return None
    return max(dumps, key=os.path.getmtime)


# ── ANSI ──────────────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
RESET = "\033[0m"


def _label(k: str) -> str:
    return f"{BOLD}{CYAN}{k}{RESET}"


def _extract_payload(d: dict) -> dict | None:
    """Handle both old-style {messages} and new-style {payload: {messages}}."""
    p = d.get("payload", {})
    msgs = p.get("messages", []) or d.get("messages", [])
    tools = p.get("tools", []) or d.get("tools", [])
    sp = p.get("system_prompt", "") or d.get("system_prompt", "")
    if not msgs:
        return None
    return {"messages": msgs, "tools": tools, "system_prompt": sp, "raw": d}


def _quick_sections(system_prompt: str) -> list[str]:
    """Return which == SECTION == headers are present."""
    sections = []
    for line in system_prompt.split("\n"):
        stripped = line.strip()
        if stripped.startswith("== ") and stripped.endswith(" =="):
            sections.append(stripped)
    return sections


def _tool_call_names(messages: list) -> list[list[str]]:
    """Extract tool call names from each assistant message."""
    all_calls = []
    for m in messages:
        if m.get("role") == "assistant":
            tcs = m.get("tool_calls", [])
            names = [
                tc.get("name")  # Vertex / Google format
                or tc.get("function", {}).get("name", "?")  # OpenAI format
                for tc in tcs
            ]
            if names:
                all_calls.append(names)
    return all_calls


def _tool_results(messages: list) -> list[str]:
    """Get tool result summaries."""
    results = []
    for m in messages:
        if m.get("role") == "tool":
            c = m.get("content", "")
            try:
                obj = json.loads(c) if isinstance(c, str) else c
                if isinstance(obj, dict):
                    # Pattern A: ToolResult wrapper {status, data: {...}}
                    status = obj.get("status", "")
                    data = obj.get("data", {})
                    if isinstance(data, dict) and data:
                        verdict = data.get("verdict", "")
                        names = data.get("allowed_capability_names", [])
                        count = data.get("count", "")
                        plan = len(data.get("execution_plan", []))
                        if verdict:
                            results.append(f"verdict={verdict} allowed={len(names)} plan={plan}")
                        elif count is not None:
                            results.append(f"count={count}")
                        else:
                            results.append(f"keys={list(data.keys())[:5]}")
                    elif status:
                        results.append(f"status={status}")
                    # Pattern B: Flat resolution envelope {verdict, allowed_capability_names, ...}
                    elif "verdict" in obj:
                        verdict = obj.get("verdict", "?")
                        names = obj.get("allowed_capability_names", [])
                        plan = len(obj.get("execution_plan", []))
                        sub = obj.get("sub_reason", "")
                        diag = obj.get("diagnostics", []) or obj.get("binding_diagnostics", [])
                        parts = [f"verdict={verdict}"]
                        if sub:
                            parts.append(f"sub={sub}")
                        if names:
                            parts.append(f"allowed={names[:3]}")
                        if plan:
                            parts.append(f"plan={plan}")
                        if diag:
                            parts.append(
                                f"diag={[d.get('type','') if isinstance(d,dict) else str(d)[:60] for d in diag[:2]]}"
                            )
                        results.append(" ".join(parts))
                    else:
                        results.append(f"keys={list(obj.keys())[:5]}")
                else:
                    results.append(str(obj)[:200])
            except (json.JSONDecodeError, TypeError):
                results.append(str(c)[:200])
    return results


def trace_file(filepath: Path, *, verbose: bool = False) -> None:
    """Print a detailed trace of a single dump file."""
    with open(filepath, encoding="utf-8") as f:
        d = json.load(f)

    extracted = _extract_payload(d)
    if extracted is None:
        print(f"{DIM}  (no messages){RESET}")
        return

    msgs = extracted["messages"]
    tools = extracted["tools"]
    sp = extracted["system_prompt"]

    # ── Header ──
    iteration = d.get("iteration", "?")
    actor = d.get("actor", "?")
    session_id = d.get("session_id", "") or ""
    session_short = session_id[:12] if session_id else "?"

    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"  {_label('file')}     {filepath.name}")
    print(
        f"  {_label('actor')}    {actor}  {_label('iter')} {iteration}  {_label('session')} {session_short}"
    )
    print(f"  {_label('tools')}    {[t.get('name','?') for t in tools]}")

    # ── System prompt sections ──
    if sp:
        sections = _quick_sections(sp)
        print(f"  {_label('sections')} {sections}")
        if verbose:
            # Print key excerpts
            for keyword in [
                "FRAMING INTENTS",
                "THE EXECUTION PLAN IS SELF-CONTAINED",
                "resolve_situation is ALWAYS",
                "TYPICAL TASK COST",
                "NEVER DO THESE",
                "LAST RESORT",
            ]:
                idx = sp.find(keyword)
                if idx >= 0:
                    snippet = sp[idx : idx + 200].replace("\n", " ")
                    print(f"  {DIM}{keyword}:{RESET} {snippet}...")

    # ── Messages ──
    for i, m in enumerate(msgs):
        role = m.get("role", "?")
        content = m.get("content", "")
        tcs = m.get("tool_calls", [])

        if role == "system":
            continue  # already summarized

        elif role == "user":
            cstr = str(content)
            if len(cstr) > 300:
                cstr = cstr[:300] + "..."
            print(f"\n  {YELLOW}[{i}] USER:{RESET}")
            # Try to parse as JSON for cleaner display
            try:
                obj = json.loads(cstr) if isinstance(cstr, str) else cstr
                if isinstance(obj, dict):
                    intents = obj.get("intents", [])
                    for intent in intents[:3]:
                        print(
                            f"    intent: {intent.get('action','?')}  domain={intent.get('domain','?')}"
                        )
                    tier = obj.get("tier", "?")
                    safety = obj.get("safety_band", "?")
                    print(f"    tier={tier}  safety={safety}  task_id={obj.get('task_id','?')}")
                else:
                    print(f"    {cstr}")
            except (json.JSONDecodeError, TypeError):
                print(f"    {cstr}")

        elif role == "assistant":
            if tcs:
                names = [tc.get("name") or tc.get("function", {}).get("name", "?") for tc in tcs]
                call_label = ", ".join(names)
                print(f"\n  {GREEN}[{i}] ASSISTANT → {BOLD}{call_label}{RESET}")
                for tc in tcs:
                    # Vertex format: name + arguments at top level
                    # OpenAI format: name + arguments under "function" key
                    fn = tc if "name" in tc else tc.get("function", {})
                    fn_name = fn.get("name", "?")
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    args_str = json.dumps(args) if isinstance(args, dict) else str(args)
                    if len(args_str) > 250:
                        args_str = args_str[:250] + "..."
                    print(f"    {DIM}{fn_name}({args_str}){RESET}")
            else:
                cstr = str(content)[:200]
                print(f"\n  {GREEN}[{i}] ASSISTANT (text):{RESET} {cstr}")

        elif role == "tool":
            print(f"\n  {BLUE}[{i}] TOOL RESULT:{RESET}")
            cstr = str(content)
            try:
                obj = json.loads(cstr) if isinstance(cstr, str) else cstr
                if isinstance(obj, dict):
                    # Determine which pattern we have
                    status = obj.get("status", "")
                    data = obj.get("data", {}) if isinstance(obj.get("data"), dict) else {}

                    # Pattern A: ToolResult wrapper {status, data: {...}}
                    if status and data:
                        verdict = data.get("verdict", "")
                        names = data.get("allowed_capability_names", [])
                        plan_steps = len(data.get("execution_plan", []))
                        count = data.get("count", "")
                        results_list = data.get("results", [])
                        if verdict:
                            color = GREEN if "can" in str(verdict) else RED
                            print(f"    status={status}  verdict={color}{verdict}{RESET}")
                            if names:
                                print(f"    allowed_capability_names ({len(names)}):")
                                for n in names[:5]:
                                    print(f"      - {n}")
                            if plan_steps:
                                print(f"    execution_plan: {plan_steps} steps")
                        elif count is not None:
                            print(f"    status={status}  count={count}")
                        elif results_list:
                            print(f"    status={status}  results={len(results_list)} items")
                            for r in results_list[:3]:
                                if isinstance(r, dict):
                                    print(f"      {json.dumps(r)[:200]}")
                        else:
                            print(f"    status={status}")
                            for k in (
                                "verdict",
                                "allowed_capability_names",
                                "execution_plan",
                                "sub_reason",
                                "hil_request",
                            ):
                                if k in data:
                                    v = data[k]
                                    if isinstance(v, list):
                                        print(f"    {k}: [{len(v)} items]")
                                    elif isinstance(v, dict):
                                        print(f"    {k}: {json.dumps(v)[:150]}")
                                    else:
                                        print(f"    {k}: {v}")

                    # Pattern B: Flat resolution envelope {verdict, ...}
                    elif "verdict" in obj:
                        verdict = obj.get("verdict", "?")
                        names = obj.get("allowed_capability_names", [])
                        plan = obj.get("execution_plan", [])
                        sub = obj.get("sub_reason", "")
                        diag = obj.get("diagnostics", []) or obj.get("binding_diagnostics", [])
                        color = GREEN if "can" in str(verdict) else RED
                        print(f"    verdict={color}{verdict}{RESET}  sub={sub}")
                        if names:
                            print(f"    allowed_capability_names ({len(names)}):")
                            for n in names[:5]:
                                print(f"      - {n}")
                        if plan:
                            print(f"    execution_plan: {len(plan)} steps")
                            for step in plan[:3]:
                                if isinstance(step, dict):
                                    cn = step.get("capability_name", "?")
                                    ri = step.get("required_inputs", [])
                                    ri_names = [
                                        r.get("name", "?") if isinstance(r, dict) else str(r)
                                        for r in ri[:5]
                                    ]
                                    print(
                                        f"      step {step.get('step','?')}: {cn} inputs={ri_names}"
                                    )
                        if diag:
                            print("    diagnostics:")
                            for d in diag[:4]:
                                if isinstance(d, dict):
                                    t = d.get("type", "")
                                    reason = d.get("reason", "")
                                    msg = d.get("message", "") or d.get("verdict", "")
                                    print(f"      [{t}] {reason} {msg}"[:120])
                                else:
                                    print(f"      {str(d)[:120]}")

                    # Pattern C: Simple object
                    else:
                        print(f"    keys={list(obj.keys())[:8]}")
                        # Show first few values
                        for k, v in list(obj.items())[:5]:
                            if isinstance(v, str) and len(v) < 100:
                                print(f"    {k}: {v}")
                            elif isinstance(v, list):
                                print(f"    {k}: [{len(v)} items]")
                else:
                    print(f"    {cstr[:300]}")
            except (json.JSONDecodeError, TypeError):
                print(f"    {cstr[:300]}")

    # ── Summary ──
    calls = _tool_call_names(msgs)
    results = _tool_results(msgs)
    all_calls_flat = [c for group in calls for c in group]
    print(f"\n  {BOLD}SUMMARY:{RESET} {len(all_calls_flat)} tool calls: {all_calls_flat}")
    if results:
        print(f"  {BOLD}RESULTS:{RESET}")
        for r in results:
            print(f"    {r}")
    print(f"{BOLD}{'='*70}{RESET}\n")


def trace_latest(verbose: bool = False) -> None:
    """Trace the most recent dump file."""
    fp = _find_latest_dump()
    if fp is None:
        print("No prompt dumps found. Boot the kernel and interact with it first.")
        return
    trace_file(fp, verbose=verbose)


def trace_session(session_hash: str) -> None:
    """Trace all dumps for a specific session."""
    dumps = _find_back_dumps()
    matching = [p for p in dumps if session_hash in p.name or session_hash in str(p.parent.parent)]
    if not matching:
        print(f"No dumps found for session '{session_hash}'")
        return
    matching.sort(key=lambda p: p.name)
    print(f"\n{BOLD}Session '{session_hash}': {len(matching)} dumps{RESET}")
    for fp in matching:
        trace_file(fp)


def follow(interval: float = 0.5) -> None:
    """Watch for new dump files and trace them as they appear."""
    print(f"{BOLD}Watching for new Back dumps... (Ctrl+C to stop){RESET}")
    print(f"{DIM}Boot the kernel and interact via the web UI.{RESET}\n")
    seen = set(_find_back_dumps())
    try:
        while True:
            current = set(_find_back_dumps())
            new_files = current - seen
            for fp in sorted(new_files, key=lambda p: p.name):
                trace_file(fp)
            seen = current
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n{BOLD}Stopped.{RESET}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live Back LLM trace watcher")
    parser.add_argument(
        "--follow", "-f", action="store_true", help="Tail mode: keep watching for new dumps"
    )
    parser.add_argument("--latest", "-l", action="store_true", help="Show latest dump in detail")
    parser.add_argument("--session", "-s", type=str, help="Trace a specific session hash")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show prompt excerpts")
    parser.add_argument("--all", "-a", action="store_true", help="Trace ALL existing dumps")
    args = parser.parse_args()

    os.environ.setdefault("PYTHONPATH", str(Path(__file__).resolve().parent.parent))

    if args.session:
        trace_session(args.session)
    elif args.latest:
        trace_latest(verbose=args.verbose)
    elif args.all:
        dumps = sorted(_find_back_dumps(), key=lambda p: p.name)
        if not dumps:
            print("No prompt dumps found. Boot the kernel first.")
            return
        print(f"{BOLD}{len(dumps)} dumps total{RESET}")
        for fp in dumps:
            trace_file(fp, verbose=args.verbose)
    elif args.follow:
        follow()
    else:
        # Default: show latest, then follow
        trace_latest(verbose=args.verbose)
        print(f"{DIM}── Starting follow mode... ──{RESET}")
        follow()


if __name__ == "__main__":
    main()
