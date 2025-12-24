"""
Script to find all sync wrapper patterns in k0 codebase.
Identifies run_in_executor, asyncio.to_thread and similar patterns.
"""

import re
from datetime import datetime
from pathlib import Path

K0_PATH = Path(__file__).parent.parent
OUTPUT_FILE = K0_PATH / "docs" / "sync_wrapper_audit.md"

# Patterns to search for
SYNC_WRAPPER_PATTERNS = [
    (r"run_in_executor\s*\(", "run_in_executor"),
    (r"asyncio\.to_thread\s*\(", "asyncio.to_thread"),
    (r"loop\.run_in_executor", "loop.run_in_executor"),
    (r"loop\s*=\s*asyncio\.get_running_loop\(\)", "get_running_loop (executor setup)"),
    (r"ThreadPoolExecutor", "ThreadPoolExecutor"),
    (r"ProcessPoolExecutor", "ProcessPoolExecutor"),
]

# Additional patterns for sync database operations
DB_SYNC_PATTERNS = [
    (r"sqlite3\.connect\s*\(", "sqlite3.connect"),
    (r"connection\.execute\s*\(", "connection.execute (sync)"),
    (r"conn\.execute\s*\(", "conn.execute (sync)"),
    (r"cursor\.execute\s*\(", "cursor.execute (sync)"),
    (r"\.executemany\s*\(", "executemany (sync)"),
    (r"\.executescript\s*\(", "executescript (sync)"),
]


def find_function_context(lines, line_idx):
    """Walk backwards to find the containing function/class."""
    current_class = None
    current_func = None

    for i in range(line_idx - 1, -1, -1):
        line = lines[i]

        # Check for function definition
        func_match = re.match(r"^(\s*)(?:async\s+)?def\s+(\w+)", line)
        if func_match and current_func is None:
            indent = len(func_match.group(1))
            current_func = func_match.group(2)
            if indent == 0:
                break
            continue

        # Check for class definition
        class_match = re.match(r"^class\s+(\w+)", line)
        if class_match:
            current_class = class_match.group(1)
            break

    if current_class and current_func:
        return f"{current_class}.{current_func}"
    elif current_func:
        return current_func
    elif current_class:
        return f"{current_class}.<class-level>"
    return "<module-level>"


def scan_file(file_path, patterns):
    """Scan a single file for sync wrapper patterns."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []

    lines = content.split("\n")
    matches = []

    for line_num, line in enumerate(lines, 1):
        for pattern, name in patterns:
            if re.search(pattern, line):
                context = find_function_context(lines, line_num - 1)
                matches.append(
                    {
                        "line": line_num,
                        "pattern": name,
                        "context": context,
                        "code": line.strip()[:120],
                    }
                )

    return matches


def scan_k0_codebase():
    """Scan entire k0 codebase for sync wrappers."""
    results = {
        "executor_wrappers": {},
        "sync_db_operations": {},
    }

    for py_file in K0_PATH.rglob("*.py"):
        # Skip pycache and test files for main audit
        if "__pycache__" in str(py_file):
            continue

        rel_path = py_file.relative_to(K0_PATH)

        # Check for executor wrappers
        executor_matches = scan_file(py_file, SYNC_WRAPPER_PATTERNS)
        if executor_matches:
            results["executor_wrappers"][str(rel_path)] = executor_matches

        # Check for sync DB operations (only in non-test files)
        if "test" not in str(rel_path).lower():
            db_matches = scan_file(py_file, DB_SYNC_PATTERNS)
            if db_matches:
                results["sync_db_operations"][str(rel_path)] = db_matches

    return results


def generate_markdown_report(results):
    """Generate markdown report from scan results."""
    lines = []

    # Header
    lines.append("# K0 Sync Wrapper Audit Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().isoformat()}")
    lines.append("")
    lines.append(
        "This report identifies all synchronous wrapper patterns that need conversion for full async support."
    )
    lines.append("")

    # Summary
    executor_count = sum(len(v) for v in results["executor_wrappers"].values())
    db_sync_count = sum(len(v) for v in results["sync_db_operations"].values())

    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Files | Occurrences |")
    lines.append("|----------|-------|-------------|")
    lines.append(
        f"| Executor Wrappers (run_in_executor, etc.) | {len(results['executor_wrappers'])} | {executor_count} |"
    )
    lines.append(
        f"| Sync DB Operations (sqlite3) | {len(results['sync_db_operations'])} | {db_sync_count} |"
    )
    lines.append(
        f"| **Total** | **{len(results['executor_wrappers']) + len(results['sync_db_operations'])}** | **{executor_count + db_sync_count}** |"
    )
    lines.append("")

    # Executor Wrappers Section
    lines.append("---")
    lines.append("")
    lines.append("## 1. Executor Wrappers (Priority: HIGH)")
    lines.append("")
    lines.append(
        "These patterns wrap synchronous code to run in thread pools. They should be replaced with native async operations."
    )
    lines.append("")

    if results["executor_wrappers"]:
        for file_path in sorted(results["executor_wrappers"].keys()):
            matches = results["executor_wrappers"][file_path]
            lines.append(f"### `k0/{file_path}`")
            lines.append("")
            lines.append("| Line | Function/Method | Pattern | Code Snippet |")
            lines.append("|------|-----------------|---------|--------------|")
            for m in matches:
                code = m["code"].replace("|", "\\|")[:80]
                lines.append(f"| {m['line']} | `{m['context']}` | `{m['pattern']}` | `{code}` |")
            lines.append("")
    else:
        lines.append("*No executor wrappers found.*")
        lines.append("")

    # Sync DB Operations Section
    lines.append("---")
    lines.append("")
    lines.append("## 2. Synchronous Database Operations (Priority: MEDIUM)")
    lines.append("")
    lines.append(
        "These are direct SQLite synchronous calls that need async alternatives (aiosqlite or asyncpg)."
    )
    lines.append("")

    if results["sync_db_operations"]:
        for file_path in sorted(results["sync_db_operations"].keys()):
            matches = results["sync_db_operations"][file_path]
            lines.append(f"### `k0/{file_path}`")
            lines.append("")
            lines.append("| Line | Function/Method | Pattern | Code Snippet |")
            lines.append("|------|-----------------|---------|--------------|")
            for m in matches:
                code = m["code"].replace("|", "\\|")[:80]
                lines.append(f"| {m['line']} | `{m['context']}` | `{m['pattern']}` | `{code}` |")
            lines.append("")
    else:
        lines.append("*No sync DB operations found in production code.*")
        lines.append("")

    # Migration Notes
    lines.append("---")
    lines.append("")
    lines.append("## Migration Notes")
    lines.append("")
    lines.append("### Replacement Strategy")
    lines.append("")
    lines.append("| Current Pattern | Async Replacement |")
    lines.append("|-----------------|-------------------|")
    lines.append("| `loop.run_in_executor(None, func)` | Native async function |")
    lines.append("| `sqlite3.connect()` | `aiosqlite.connect()` or `asyncpg.connect()` |")
    lines.append("| `conn.execute()` | `await conn.execute()` |")
    lines.append("| `ThreadPoolExecutor` | `asyncio.TaskGroup` or remove |")
    lines.append("")
    lines.append("### Files Requiring Most Work")
    lines.append("")

    # Sort by number of occurrences
    all_files = {}
    for file_path, matches in results["executor_wrappers"].items():
        all_files[file_path] = all_files.get(file_path, 0) + len(matches)
    for file_path, matches in results["sync_db_operations"].items():
        all_files[file_path] = all_files.get(file_path, 0) + len(matches)

    sorted_files = sorted(all_files.items(), key=lambda x: x[1], reverse=True)[:10]

    lines.append("| File | Total Sync Operations |")
    lines.append("|------|----------------------|")
    for file_path, count in sorted_files:
        lines.append(f"| `k0/{file_path}` | {count} |")
    lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point."""
    print(f"Scanning k0 codebase at: {K0_PATH}")
    print("")

    results = scan_k0_codebase()

    # Generate report
    report = generate_markdown_report(results)

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write report
    OUTPUT_FILE.write_text(report, encoding="utf-8")

    print(f"Report written to: {OUTPUT_FILE}")
    print("")

    # Also print to console
    print(report)


if __name__ == "__main__":
    main()
