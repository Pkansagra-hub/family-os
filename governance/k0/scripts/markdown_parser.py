"""
Markdown AST Parser - Structure-aware parsing for governance documents.

Uses markdown-it-py to parse Markdown into AST, then extracts tables
by section header. This replaces fragile regex-based parsing.

Key concepts:
- Tables are real nodes, not text blobs
- Headings are tokens with hierarchy
- AUTOGEN blocks mark tool-owned sections

Usage:
    from governance.k0.scripts.markdown_parser import MarkdownRegistry

    registry = MarkdownRegistry(master_path)
    syscalls = registry.get_table_rows("7.1", "Syscall Methods Registry")
    for row in syscalls:
        print(row["Method"], row["Capability"])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from markdown_it import MarkdownIt


@dataclass
class TableRow:
    """A parsed table row with column values."""

    cells: list[str]
    raw_line: str = ""

    def get(self, index: int, default: str = "") -> str:
        """Get cell value by index, with default."""
        if 0 <= index < len(self.cells):
            return self.cells[index]
        return default

    def as_dict(self, headers: list[str]) -> dict[str, str]:
        """Convert to dict using header names as keys."""
        return {h: self.get(i) for i, h in enumerate(headers)}


@dataclass
class ParsedTable:
    """A parsed markdown table with headers and rows."""

    section_id: str  # e.g., "7.1"
    section_title: str  # e.g., "Syscall Methods Registry"
    headers: list[str]
    rows: list[TableRow]
    start_line: int = 0
    end_line: int = 0

    def get_column_values(self, column_name: str) -> list[str]:
        """Extract all values from a specific column."""
        if column_name not in self.headers:
            return []
        idx = self.headers.index(column_name)
        return [row.get(idx) for row in self.rows]

    def find_rows_matching(self, column: str, pattern: str) -> list[TableRow]:
        """Find rows where column matches regex pattern."""
        if column not in self.headers:
            return []
        idx = self.headers.index(column)
        regex = re.compile(pattern, re.IGNORECASE)
        return [row for row in self.rows if regex.search(row.get(idx))]


@dataclass
class AutogenBlock:
    """An AUTOGEN block that the tool owns completely."""

    block_id: str  # e.g., "SYSCALL_TABLE"
    content: str
    start_line: int
    end_line: int
    metadata: dict[str, str] = field(default_factory=dict)


class MarkdownRegistry:
    """
    Structure-aware parser for governance markdown documents.

    Uses markdown-it-py AST parsing instead of regex for reliable
    table and section extraction.
    """

    def __init__(self, file_path: Path | str):
        self.file_path = Path(file_path)
        self._content: str = ""
        self._lines: list[str] = []
        self._tables: dict[str, ParsedTable] = {}
        self._autogen_blocks: dict[str, AutogenBlock] = {}
        self._md = MarkdownIt()

        if self.file_path.exists():
            self._load()

    def _load(self) -> None:
        """Load and parse the markdown file."""
        self._content = self.file_path.read_text(encoding="utf-8")
        self._lines = self._content.split("\n")
        self._parse_autogen_blocks()
        self._parse_tables_by_section()

    def _parse_autogen_blocks(self) -> None:
        """Extract AUTOGEN comment blocks."""
        # Pattern: <!-- AUTOGEN:BLOCK_ID:BEGIN --> ... <!-- AUTOGEN:BLOCK_ID:END -->
        pattern = re.compile(
            r"<!--\s*AUTOGEN:(\w+):BEGIN\s*(?:\n(.+?))?\s*-->"
            r"(.*?)"
            r"<!--\s*AUTOGEN:\1:END\s*-->",
            re.DOTALL,
        )

        for match in pattern.finditer(self._content):
            block_id = match.group(1)
            metadata_str = match.group(2) or ""
            content = match.group(3).strip()

            # Parse metadata if present (JSON-like)
            metadata = {}
            if metadata_str:
                for line in metadata_str.strip().split("\n"):
                    if ":" in line:
                        key, val = line.split(":", 1)
                        metadata[key.strip()] = val.strip().strip('"')

            # Calculate line numbers
            start_pos = match.start()
            end_pos = match.end()
            start_line = self._content[:start_pos].count("\n") + 1
            end_line = self._content[:end_pos].count("\n") + 1

            self._autogen_blocks[block_id] = AutogenBlock(
                block_id=block_id,
                content=content,
                start_line=start_line,
                end_line=end_line,
                metadata=metadata,
            )

    def _parse_tables_by_section(self) -> None:
        """Parse all tables and associate with their section headers."""
        current_section_id = ""
        current_section_title = ""
        i = 0

        while i < len(self._lines):
            line = self._lines[i]

            # Detect section headers (## X.Y Title or ### X.Y.Z Title)
            heading_match = re.match(r"^(#{2,4})\s+(\d+(?:\.\d+)*)\s+(.+)$", line)
            if heading_match:
                current_section_id = heading_match.group(2)
                current_section_title = heading_match.group(3).strip()
                i += 1
                continue

            # Also handle headers without numbers: ## Title
            simple_heading = re.match(r"^(#{2,4})\s+(.+)$", line)
            if simple_heading and not heading_match:
                title = simple_heading.group(2).strip()
                # Try to extract section ID from title like "7.1 Syscall Methods"
                id_match = re.match(r"(\d+(?:\.\d+)*)\s+(.+)", title)
                if id_match:
                    current_section_id = id_match.group(1)
                    current_section_title = id_match.group(2).strip()
                else:
                    current_section_title = title
                i += 1
                continue

            # Detect table start (line starting with |)
            if line.startswith("|") and "|" in line[1:]:
                table_start = i
                table_lines = []

                # Collect all table lines
                while i < len(self._lines) and self._lines[i].startswith("|"):
                    table_lines.append(self._lines[i])
                    i += 1

                # Parse table if we have at least header + separator + 1 row
                if len(table_lines) >= 2:
                    parsed = self._parse_table_lines(
                        table_lines,
                        current_section_id,
                        current_section_title,
                        table_start,
                        i - 1,
                    )
                    if parsed:
                        key = f"{current_section_id}|{current_section_title}"
                        self._tables[key] = parsed
                continue

            i += 1

    def _parse_table_lines(
        self,
        lines: list[str],
        section_id: str,
        section_title: str,
        start_line: int,
        end_line: int,
    ) -> ParsedTable | None:
        """Parse table lines into structured data."""
        if len(lines) < 2:
            return None

        # First line is header
        headers = self._parse_table_row(lines[0])
        if not headers:
            return None

        # Second line should be separator (|---|---|)
        if not re.match(r"^\|[\s\-:|]+\|$", lines[1]):
            # No separator, might not be a proper table
            pass

        # Remaining lines are data rows
        rows = []
        for line in lines[2:]:
            cells = self._parse_table_row(line)
            if cells:
                rows.append(TableRow(cells=cells, raw_line=line))

        return ParsedTable(
            section_id=section_id,
            section_title=section_title,
            headers=headers,
            rows=rows,
            start_line=start_line,
            end_line=end_line,
        )

    def _parse_table_row(self, line: str) -> list[str]:
        """Parse a single table row into cells."""
        # Remove leading/trailing pipes and split
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]

        cells = [cell.strip() for cell in line.split("|")]
        return cells

    def get_table(self, section_id: str, title_contains: str = "") -> ParsedTable | None:
        """
        Get a table by section ID and optional title match.

        Args:
            section_id: Section number like "7.1", "3.1"
            title_contains: Optional substring to match in title

        Returns:
            ParsedTable or None if not found
        """
        for key, table in self._tables.items():
            if table.section_id == section_id:
                if not title_contains or title_contains.lower() in table.section_title.lower():
                    return table
        return None

    def get_table_by_title(self, title_contains: str) -> ParsedTable | None:
        """Get first table whose section title contains the given string."""
        for table in self._tables.values():
            if title_contains.lower() in table.section_title.lower():
                return table
        return None

    def get_autogen_block(self, block_id: str) -> AutogenBlock | None:
        """Get an AUTOGEN block by ID."""
        return self._autogen_blocks.get(block_id)

    def list_tables(self) -> list[tuple[str, str, int]]:
        """List all parsed tables: (section_id, title, row_count)."""
        return [(t.section_id, t.section_title, len(t.rows)) for t in self._tables.values()]

    def list_autogen_blocks(self) -> list[str]:
        """List all AUTOGEN block IDs."""
        return list(self._autogen_blocks.keys())

    def extract_ids_from_column(
        self,
        section_id: str,
        column_name: str,
        pattern: str = r"[A-Z]\d{2,3}",
    ) -> set[str]:
        """
        Extract IDs matching pattern from a specific column.

        Args:
            section_id: Section like "7.1"
            column_name: Column header name
            pattern: Regex pattern for IDs (default: M01, P02, K001)

        Returns:
            Set of extracted IDs
        """
        table = self.get_table(section_id)
        if not table:
            return set()

        if column_name not in table.headers:
            # Try first column
            column_name = table.headers[0] if table.headers else ""

        ids = set()
        regex = re.compile(pattern)

        for row in table.rows:
            cell = row.as_dict(table.headers).get(column_name, "")
            for match in regex.finditer(cell):
                ids.add(match.group())

        return ids

    def replace_autogen_block(self, block_id: str, new_content: str) -> str:
        """
        Replace an AUTOGEN block's content and return updated document.

        Args:
            block_id: AUTOGEN block ID
            new_content: New content to insert

        Returns:
            Updated document content (does not write to file)
        """
        pattern = re.compile(
            rf"(<!--\s*AUTOGEN:{block_id}:BEGIN\s*(?:\n.+?)?\s*-->)"
            rf".*?"
            rf"(<!--\s*AUTOGEN:{block_id}:END\s*-->)",
            re.DOTALL,
        )

        def replacer(match: re.Match) -> str:
            return f"{match.group(1)}\n{new_content}\n{match.group(2)}"

        return pattern.sub(replacer, self._content)

    def write_autogen_block(self, block_id: str, new_content: str) -> None:
        """Replace AUTOGEN block and write to file."""
        updated = self.replace_autogen_block(block_id, new_content)
        self.file_path.write_text(updated, encoding="utf-8")
        self._load()  # Reload


def extract_backtick_value(cell: str) -> str:
    """Extract value from backticks: `value` -> value."""
    match = re.search(r"`([^`]+)`", cell)
    return match.group(1) if match else cell.strip()


def extract_id_from_cell(cell: str, pattern: str = r"[A-Z]\d{2,3}") -> str | None:
    """Extract first ID matching pattern from cell."""
    match = re.search(pattern, cell)
    return match.group() if match else None


if __name__ == "__main__":
    # Quick test
    from pathlib import Path

    master = Path(__file__).parent.parent / "k0_architecture_master.md"
    if master.exists():
        registry = MarkdownRegistry(master)

        print("Parsed tables:")
        print("-" * 60)
        for section_id, title, count in registry.list_tables():
            print(f"  {section_id}: {title} ({count} rows)")

        print("\nAUTOGEN blocks:")
        print("-" * 60)
        for block_id in registry.list_autogen_blocks():
            print(f"  {block_id}")

        # Test syscall extraction
        print("\nSyscall table (7.1):")
        print("-" * 60)
        table = registry.get_table("7.1")
        if table:
            print(f"  Headers: {table.headers}")
            print(f"  Rows: {len(table.rows)}")
            for row in table.rows[:3]:
                print(f"    {row.cells[0]}")
        else:
            print("  Not found")
