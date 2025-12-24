"""
Filter K0 production Python files that require SQLite → PostgreSQL migration.
Excludes tests, docs, and non-Python files.
"""

import re
from collections import defaultdict
from pathlib import Path

K0_PATH = Path("D:/familyos/k0")

# Patterns for SQLite usage
PATTERNS = [
    (r"^import sqlite3", "import sqlite3"),
    (r"sqlite3\.connect", "sqlite3.connect"),
    (r"sqlite3\.Connection", "sqlite3.Connection"),
    (r"sqlite3\.Cursor", "sqlite3.Cursor"),
    (r"sqlite3\.Row", "sqlite3.Row"),
    (r"\.execute\s*\(", "execute()"),
    (r"\.fetchone\s*\(", "fetchone()"),
    (r"\.fetchall\s*\(", "fetchall()"),
    (r"\.executescript\s*\(", "executescript()"),
    (r"\.executemany\s*\(", "executemany()"),
    (r"run_in_executor", "run_in_executor"),
    (r"PRAGMA\s+\w+", "PRAGMA"),
    (r"row_factory", "row_factory"),
]

# Skip these patterns in file paths
SKIP_PATTERNS = [
    "__pycache__",
    "test",
    "docs",
    "_archived",
]


def scan_file(file_path: Path) -> dict | None:
    """Scan a single file for SQLite patterns."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    # Quick check - skip if no sqlite3 or run_in_executor
    if "sqlite3" not in content and "run_in_executor" not in content:
        return None

    lines = content.split("\n")
    matches = []

    for line_num, line in enumerate(lines, 1):
        for pattern, name in PATTERNS:
            if re.search(pattern, line):
                matches.append({"line": line_num, "pattern": name, "code": line.strip()[:80]})
                break  # Only count first match per line

    if matches:
        return {"count": len(matches), "matches": matches}
    return None


def main():
    results = {}

    for py_file in K0_PATH.rglob("*.py"):
        rel_path = str(py_file.relative_to(K0_PATH))

        # Skip tests, docs, archived
        if any(skip in rel_path.lower() for skip in SKIP_PATTERNS):
            continue

        result = scan_file(py_file)
        if result:
            results[rel_path] = result

    # Sort by count descending
    sorted_results = sorted(results.items(), key=lambda x: x[1]["count"], reverse=True)

    total_files = len(sorted_results)
    total_occurrences = sum(r[1]["count"] for r in sorted_results)

    print("=" * 80)
    print("K0 PRODUCTION CODE FILES REQUIRING POSTGRESQL MIGRATION")
    print("=" * 80)
    print(f"Total files: {total_files}")
    print(f"Total occurrences: {total_occurrences}")
    print("=" * 80)
    print()

    # Group by folder
    by_folder = defaultdict(list)
    for file_path, data in sorted_results:
        folder = file_path.split("\\")[0] if "\\" in file_path else file_path.split("/")[0]
        by_folder[folder].append((file_path, data))

    for folder in sorted(by_folder.keys()):
        files = by_folder[folder]
        folder_total = sum(f[1]["count"] for f in files)
        print(f"### {folder}/ ({len(files)} files, {folder_total} changes)")
        print()

        for file_path, data in sorted(files, key=lambda x: x[1]["count"], reverse=True):
            print(f"  **{file_path}** ({data['count']} changes)")
            for m in data["matches"][:3]:
                code = m["code"][:55]
                print(f"    L{m['line']:4d}: [{m['pattern']:15s}] {code}")
            if data["count"] > 3:
                print(f"    ... and {data['count'] - 3} more")
            print()


if __name__ == "__main__":
    main()
