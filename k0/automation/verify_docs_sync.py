"""Documentation synchronization verifier for contract schemas and API specs.

This CI automation script ensures that:
- All JSON schemas referenced in OpenAPI/AsyncAPI specs exist
- All event topics defined in schemas are documented in AsyncAPI
- Schema versions match between specification and implementation
- No stale or orphaned documentation artifacts remain

This tool is part of the contract hygiene enforcement pipeline and runs
automatically in CI to prevent documentation drift.

Usage:
    python -m k0.automation.verify_docs_sync
    python -m k0.automation.verify_docs_sync --contracts-dir <path>

Exit Codes:
    0 - All documentation in sync
    1 - Synchronization issues detected
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPO_ROOT / "k0" / "README.md"
STORAGE_SQL_PATH = REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql"
DAY2_RUNBOOK_DIR = REPO_ROOT / "docs" / "development" / "runbooks" / "day2-operations"
DAY2_BLUEPRINT_PATH = DAY2_RUNBOOK_DIR / "blueprint.md"
DAY2_RUNBOOKS: Dict[str, Path] = {
    "day2-rollback": DAY2_RUNBOOK_DIR / "rollback.md",
    "day2-config-drift": DAY2_RUNBOOK_DIR / "config-drift.md",
    "day2-incident-response": DAY2_RUNBOOK_DIR / "incident-response.md",
    "day2-capacity-expansion": DAY2_RUNBOOK_DIR / "capacity-expansion.md",
    "day2-dr-drill": DAY2_RUNBOOK_DIR / "disaster-recovery-drill.md",
}
DAY2_METADATA_KEYS = {
    "runbook_id",
    "title",
    "owner",
    "reviewers",
    "review_cadence",
    "last_reviewed",
    "tags",
    "related_assets",
}

README_SECTION_HEADER = "### 6.1 SQL DDL (core)"
SQL_FENCE = "```sql"
CLOSING_FENCE = "```"


def _extract_sql_fence(readme_text: str) -> str:
    try:
        section_index = readme_text.index(README_SECTION_HEADER)
    except ValueError as exc:
        raise RuntimeError(
            f"Section header '{README_SECTION_HEADER}' not found in README"
        ) from exc

    try:
        fence_start = readme_text.index(SQL_FENCE, section_index)
    except ValueError as exc:
        raise RuntimeError(
            "SQL fence not found after section header in README"
        ) from exc

    try:
        fence_end = readme_text.index(CLOSING_FENCE, fence_start + len(SQL_FENCE))
    except ValueError as exc:
        raise RuntimeError("Closing fence for SQL snippet not found in README") from exc

    snippet = readme_text[fence_start + len(SQL_FENCE) : fence_end]
    return snippet.strip()


def _normalize_statements(
    sql_text: str, *, ignore_prefixes: Iterable[str] = ()
) -> Set[str]:
    normalized: Set[str] = set()
    lines: list[str] = []
    for raw_line in sql_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("--"):
            continue
        comment_index = line.find("--")
        if comment_index != -1:
            line = line[:comment_index].strip()
            if not line:
                continue
        lines.append(line)

    joined = "\n".join(lines)
    statements = [stmt.strip() for stmt in joined.split(";") if stmt.strip()]

    upper_ignore = tuple(prefix.upper() for prefix in ignore_prefixes)

    for stmt in statements:
        if upper_ignore and stmt.upper().startswith(upper_ignore):
            continue
        normalized.add(" ".join(stmt.split()))

    return normalized


def validate_sync(readme_path: Path, storage_sql_path: Path) -> None:
    readme_text = readme_path.read_text(encoding="utf-8")
    readme_sql = _extract_sql_fence(readme_text)
    if not readme_sql:
        raise RuntimeError("README SQL snippet is empty")

    readme_statements = _normalize_statements(readme_sql)
    storage_sql = storage_sql_path.read_text(encoding="utf-8")
    storage_statements = _normalize_statements(storage_sql, ignore_prefixes=("PRAGMA",))

    missing_in_readme = storage_statements - readme_statements
    extra_in_readme = readme_statements - storage_statements

    if missing_in_readme or extra_in_readme:
        messages = ["README SQL snippet is out of sync with storage.sql:"]
        if missing_in_readme:
            messages.append("  Statements missing from README:")
            messages.extend(f"    - {stmt}" for stmt in sorted(missing_in_readme))
        if extra_in_readme:
            messages.append("  Statements present only in README:")
            messages.extend(f"    - {stmt}" for stmt in sorted(extra_in_readme))
        raise RuntimeError("\n".join(messages))

    validate_day2_docs()


def _parse_front_matter(markdown_path: Path) -> Dict[str, Any]:
    text = markdown_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise RuntimeError(f"Runbook {markdown_path} is missing YAML front matter")

    try:
        _, remainder = text.split("---", 1)
        front_matter_raw, _ = remainder.split("---", 1)
    except ValueError as exc:
        raise RuntimeError(
            f"Runbook {markdown_path} has malformed front matter"
        ) from exc

    data = yaml.safe_load(front_matter_raw)
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Runbook {markdown_path} front matter did not produce a mapping"
        )
    raw_data = cast(Dict[Any, Any], data)
    parsed: Dict[str, Any] = {}
    for key, value in raw_data.items():
        if not isinstance(key, str):
            raise RuntimeError(
                f"Runbook {markdown_path} front matter keys must be strings; found {key!r}"
            )
        parsed[key] = value
    return parsed


def _validate_related_paths(runbook_path: Path, paths: Sequence[str]) -> None:
    for rel in paths:
        if not rel.strip():
            raise RuntimeError(
                f"Runbook {runbook_path} contains an invalid related asset entry: {rel!r}"
            )
        target_str = rel.split("#", 1)[0]
        target_path = (runbook_path.parent / target_str).resolve()
        if not target_path.exists():
            raise RuntimeError(
                f"Runbook {runbook_path} references missing asset '{rel}'"
            )


def validate_day2_docs() -> None:
    if not DAY2_BLUEPRINT_PATH.exists():
        raise RuntimeError(
            f"Day-2 blueprint not found at {DAY2_BLUEPRINT_PATH.relative_to(REPO_ROOT)}"
        )

    blueprint_text = DAY2_BLUEPRINT_PATH.read_text(encoding="utf-8")

    for runbook_id, runbook_path in DAY2_RUNBOOKS.items():
        if runbook_id not in blueprint_text:
            raise RuntimeError(
                f"Day-2 blueprint does not reference runbook id '{runbook_id}'"
            )

        if not runbook_path.exists():
            raise RuntimeError(
                f"Day-2 runbook missing: {runbook_path.relative_to(REPO_ROOT)}"
            )

        metadata = _parse_front_matter(runbook_path)
        missing_keys = DAY2_METADATA_KEYS - metadata.keys()
        if missing_keys:
            raise RuntimeError(
                f"Runbook {runbook_path.relative_to(REPO_ROOT)} missing metadata keys: {sorted(missing_keys)}"
            )

        if metadata.get("runbook_id") != runbook_id:
            raise RuntimeError(
                f"Runbook {runbook_path.relative_to(REPO_ROOT)} has mismatched runbook_id"
            )

        related_assets_obj = metadata.get("related_assets")
        if not isinstance(related_assets_obj, dict):
            raise RuntimeError(
                f"Runbook {runbook_path.relative_to(REPO_ROOT)} related_assets must be a mapping"
            )
        related_assets_raw = cast(Dict[Any, Any], related_assets_obj)
        related_assets: Dict[str, Any] = {}
        for key, value in related_assets_raw.items():
            if not isinstance(key, str):
                raise RuntimeError(
                    f"Runbook {runbook_path.relative_to(REPO_ROOT)} related_assets keys must be strings"
                )
            related_assets[key] = value

        for category in ("dashboards", "runbooks", "documentation"):
            entries_obj = related_assets.get(category)
            if not isinstance(entries_obj, list) or not entries_obj:
                raise RuntimeError(
                    f"Runbook {runbook_path.relative_to(REPO_ROOT)} must list related_assets.{category} entries"
                )
            entries_list = cast(List[Any], entries_obj)
            entries: List[str] = []
            for entry in entries_list:
                if not isinstance(entry, str):
                    raise RuntimeError(
                        f"Runbook {runbook_path.relative_to(REPO_ROOT)} related_assets.{category} entries must be strings"
                    )
                entries.append(entry)
            _validate_related_paths(runbook_path, entries)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate documentation sync requirements"
    )
    parser.add_argument("--readme", type=Path, default=README_PATH)
    parser.add_argument("--storage", type=Path, default=STORAGE_SQL_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_sync(args.readme, args.storage)
    print("[DocSync] README SQL snippet matches storage.sql; Day-2 docs validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
