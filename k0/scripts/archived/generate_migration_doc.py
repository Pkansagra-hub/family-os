"""
Generate K0 PostgreSQL & Async Migration document.
Lists all production files requiring changes.
"""

import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

K0_PATH = Path("D:/familyos/k0")
OUTPUT_FILE = K0_PATH / "docs" / "k0_postgresql_migration.md"

# SQLite patterns
SQLITE_PATTERNS = [
    (r"^import sqlite3", "import sqlite3"),
    (r"sqlite3\.connect", "sqlite3.connect()"),
    (r"sqlite3\.Connection", "sqlite3.Connection type"),
    (r"sqlite3\.Cursor", "sqlite3.Cursor type"),
    (r"sqlite3\.Row", "sqlite3.Row"),
    (r"row_factory", "row_factory"),
    (r"PRAGMA\s+\w+", "PRAGMA command"),
]

# Async wrapper patterns
ASYNC_PATTERNS = [
    (r"run_in_executor", "run_in_executor"),
    (r"ThreadPoolExecutor", "ThreadPoolExecutor"),
    (r"ProcessPoolExecutor", "ProcessPoolExecutor"),
    (r"asyncio\.to_thread", "asyncio.to_thread"),
]

# Execute patterns
EXEC_PATTERNS = [
    (r"\.execute\s*\(", "execute()"),
    (r"\.fetchone\s*\(", "fetchone()"),
    (r"\.fetchall\s*\(", "fetchall()"),
    (r"\.executescript\s*\(", "executescript()"),
    (r"\.executemany\s*\(", "executemany()"),
]

SKIP_PATTERNS = ["__pycache__", "test", "docs", "_archived"]


def scan_file(file_path: Path) -> dict | None:
    """Scan a single file for migration patterns."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    # Quick check
    if (
        "sqlite3" not in content
        and "run_in_executor" not in content
        and "ThreadPoolExecutor" not in content
    ):
        return None

    lines = content.split("\n")
    sqlite_matches = []
    async_matches = []
    exec_matches = []

    for line_num, line in enumerate(lines, 1):
        for pattern, name in SQLITE_PATTERNS:
            if re.search(pattern, line):
                sqlite_matches.append(
                    {"line": line_num, "pattern": name, "code": line.strip()[:70]}
                )
                break

        for pattern, name in ASYNC_PATTERNS:
            if re.search(pattern, line):
                async_matches.append({"line": line_num, "pattern": name, "code": line.strip()[:70]})
                break

        for pattern, name in EXEC_PATTERNS:
            if re.search(pattern, line):
                exec_matches.append({"line": line_num, "pattern": name, "code": line.strip()[:70]})

    if sqlite_matches or async_matches or exec_matches:
        return {
            "sqlite": sqlite_matches,
            "async": async_matches,
            "exec": exec_matches,
        }
    return None


def generate_markdown(results: dict) -> str:
    """Generate the markdown content."""
    lines = []

    # Header
    lines.append("# K0 PostgreSQL & Async Migration")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().isoformat()}")
    lines.append("")
    lines.append("This document identifies all K0 production files requiring changes for:")
    lines.append("1. **SQLite → PostgreSQL migration** (asyncpg, pgvector)")
    lines.append("2. **Sync → Async conversion** (remove run_in_executor wrappers)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Tech Stack
    lines.append("## Target Technology Stack")
    lines.append("")
    lines.append("| Component | Current | Target |")
    lines.append("|-----------|---------|--------|")
    lines.append("| Database | SQLite | PostgreSQL 16+ |")
    lines.append("| Driver | sqlite3 (sync) | asyncpg (native async) |")
    lines.append("| Vector Store | FAISS + SQLite metadata | pgvector extension |")
    lines.append("| Full-Text Search | FTS5 | PostgreSQL tsvector + GIN |")
    lines.append("| Migrations | Raw SQL files | Alembic |")
    lines.append("| Connection Pool | Custom SQLiteConnectionPool | pgbouncer + asyncpg.Pool |")
    lines.append("| Sync Wrappers | run_in_executor | Native async/await |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary stats
    total_files = len(results)
    sqlite_files = sum(1 for r in results.values() if r["sqlite"])
    async_files = sum(1 for r in results.values() if r["async"])
    total_sqlite = sum(len(r["sqlite"]) for r in results.values())
    total_async = sum(len(r["async"]) for r in results.values())
    total_exec = sum(len(r["exec"]) for r in results.values())

    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Files | Occurrences |")
    lines.append("|----------|-------|-------------|")
    lines.append(f"| SQLite imports/types | {sqlite_files} | {total_sqlite} |")
    lines.append(f"| Sync wrappers (run_in_executor) | {async_files} | {total_async} |")
    lines.append(f"| DB execute operations | {total_files} | {total_exec} |")
    lines.append(
        f"| **Total unique files** | **{total_files}** | **{total_sqlite + total_async + total_exec}** |"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Group by folder
    by_folder = defaultdict(list)
    for file_path, data in results.items():
        parts = file_path.replace("\\", "/").split("/")
        folder = parts[0] if len(parts) > 1 else "root"
        by_folder[folder].append((file_path, data))

    lines.append("## Files By Module")
    lines.append("")

    for folder in sorted(by_folder.keys()):
        files = by_folder[folder]
        folder_sqlite = sum(len(f[1]["sqlite"]) for f in files)
        folder_async = sum(len(f[1]["async"]) for f in files)
        folder_exec = sum(len(f[1]["exec"]) for f in files)
        folder_total = folder_sqlite + folder_async + folder_exec

        lines.append(f"### {folder}/ ({len(files)} files, {folder_total} changes)")
        lines.append("")
        lines.append("| File | SQLite | Async | Exec | Total |")
        lines.append("|------|--------|-------|------|-------|")

        for file_path, data in sorted(
            files,
            key=lambda x: len(x[1]["sqlite"]) + len(x[1]["async"]) + len(x[1]["exec"]),
            reverse=True,
        ):
            s = len(data["sqlite"])
            a = len(data["async"])
            e = len(data["exec"])
            t = s + a + e
            lines.append(f"| `{file_path}` | {s} | {a} | {e} | {t} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Detailed File Analysis")
    lines.append("")

    for file_path, data in sorted(
        results.items(),
        key=lambda x: len(x[1]["sqlite"]) + len(x[1]["async"]) + len(x[1]["exec"]),
        reverse=True,
    ):
        s_count = len(data["sqlite"])
        a_count = len(data["async"])
        e_count = len(data["exec"])

        lines.append(f"### `k0/{file_path}`")
        lines.append("")
        lines.append(
            f"**SQLite:** {s_count} | **Async Wrappers:** {a_count} | **Execute Calls:** {e_count}"
        )
        lines.append("")

        if data["sqlite"]:
            lines.append("**SQLite Patterns:**")
            lines.append("")
            lines.append("| Line | Pattern | Code |")
            lines.append("|------|---------|------|")
            for m in data["sqlite"]:
                code = m["code"].replace("|", "\\|")
                lines.append(f"| {m['line']} | {m['pattern']} | `{code}` |")
            lines.append("")

        if data["async"]:
            lines.append("**Sync Wrappers to Remove:**")
            lines.append("")
            lines.append("| Line | Pattern | Code |")
            lines.append("|------|---------|------|")
            for m in data["async"]:
                code = m["code"].replace("|", "\\|")
                lines.append(f"| {m['line']} | {m['pattern']} | `{code}` |")
            lines.append("")

        if data["exec"]:
            lines.append("**Execute Calls:**")
            lines.append("")
            lines.append("| Line | Pattern | Code |")
            lines.append("|------|---------|------|")
            for m in data["exec"]:
                code = m["code"].replace("|", "\\|")
                lines.append(f"| {m['line']} | {m['pattern']} | `{code}` |")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point."""
    print(f"Scanning K0 production files at: {K0_PATH}")

    results = {}

    for py_file in K0_PATH.rglob("*.py"):
        rel_path = str(py_file.relative_to(K0_PATH))
        if any(skip in rel_path.lower() for skip in SKIP_PATTERNS):
            continue

        result = scan_file(py_file)
        if result:
            results[rel_path] = result

    # Generate and write markdown
    content = generate_markdown(results)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(content, encoding="utf-8")

    # Summary
    total_files = len(results)
    total_sqlite = sum(len(r["sqlite"]) for r in results.values())
    total_async = sum(len(r["async"]) for r in results.values())
    total_exec = sum(len(r["exec"]) for r in results.values())

    print(f"Created: {OUTPUT_FILE}")
    print(f"Total files: {total_files}")
    print(f"Total changes: {total_sqlite + total_async + total_exec}")


if __name__ == "__main__":
    main()
