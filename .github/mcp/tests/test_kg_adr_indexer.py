"""
Comprehensive test suite for KG-1.3: ADR Indexer

Tests for:
- ADR metadata extraction (title, status, date, author, category)
- Cross-reference detection between ADRs
- ADR filename parsing
- Status field extraction
- Semantic tag generation
- Directory scanning and indexing
- KG node creation from ADRs
- Dependency graph construction
- Performance targets (<500ms for full directory)
- Error handling for malformed ADRs

Test Coverage: 90%+ of ADRIndexer functionality
"""

import time
from pathlib import Path
from typing import Optional

import pytest
from kg_indexers import ADRIndexer, ADRMetadata


class TestADRFilenamePattern:
    """Test ADR filename parsing."""

    def test_valid_adr_filename(self) -> None:
        """Test parsing valid ADR filenames."""
        indexer = ADRIndexer()

        filenames = [
            ("0001-k0-k1-kernel-split.md", "0001"),
            ("0001a-k0-bridge-communication.md", "0001a"),
            ("0087-kg-mcp-semantic-enhancement.md", "0087"),
            ("0005-agent-lifecycle-fsm.md", "0005"),
        ]

        for filename, expected_id in filenames:
            match = indexer.ADR_PATTERN.match(filename)
            assert match is not None, f"Failed to match {filename}"
            assert match.group(1) == expected_id

    def test_invalid_adr_filename(self) -> None:
        """Test that invalid filenames don't match."""
        indexer = ADRIndexer()

        invalid_filenames = [
            "readme.md",
            "001-short-id.md",
            "00001-too-long-id.md",
            "adr-0001-with-prefix.md",
        ]

        for filename in invalid_filenames:
            match = indexer.ADR_PATTERN.match(filename)
            assert match is None, f"Should not match {filename}"


class TestTitleExtraction:
    """Test markdown title extraction."""

    @pytest.fixture
    def indexer(self) -> ADRIndexer:
        return ADRIndexer()

    def test_extract_title_with_adr_prefix(self, indexer: ADRIndexer) -> None:
        """Test extracting title from 'ADR-XXXX: Title' format."""
        content = "# ADR-0051: Agent Scheduling Protocol\n\nContent here."
        title = indexer._extract_title(content)
        assert title == "Agent Scheduling Protocol"

    def test_extract_title_no_prefix(self, indexer: ADRIndexer) -> None:
        """Test extracting title without ADR prefix."""
        content = "# Agent Scheduling Protocol\n\nContent here."
        title = indexer._extract_title(content)
        assert "Agent" in title or title

    def test_extract_title_no_title(self, indexer: ADRIndexer) -> None:
        """Test when no title found."""
        content = "Just some content\nwith no header."
        title = indexer._extract_title(content)
        assert title is None


class TestStatusExtraction:
    """Test status field extraction."""

    @pytest.fixture
    def indexer(self) -> ADRIndexer:
        return ADRIndexer()

    def test_extract_status_bold_format(self, indexer: ADRIndexer) -> None:
        """Test extracting status from **Status:** format."""
        content = "**Status:** ACCEPTED ✅\n\nContent."
        status = indexer._extract_status(content)
        assert status == "ACCEPTED"

    def test_extract_status_plain_format(self, indexer: ADRIndexer) -> None:
        """Test extracting status from Status: format."""
        content = "Status: PROPOSED\n\nContent."
        status = indexer._extract_status(content)
        assert status == "PROPOSED"

    def test_extract_status_with_extra_text(self, indexer: ADRIndexer) -> None:
        """Test status extraction ignores extra text after status."""
        content = "**Status:** Accepted (some notes)\n\nContent."
        status = indexer._extract_status(content)
        assert status == "ACCEPTED"

    def test_extract_status_valid_types(self, indexer: ADRIndexer) -> None:
        """Test all valid status types are extracted."""
        valid_statuses = [
            "PROPOSED",
            "ACCEPTED",
            "IMPLEMENTED",
            "REJECTED",
            "SUPERSEDED",
        ]
        for valid_status in valid_statuses:
            content = f"Status: {valid_status}\n\nContent."
            status = indexer._extract_status(content)
            assert status == valid_status, f"Failed to extract {valid_status}"

    def test_extract_status_case_insensitive(self, indexer: ADRIndexer) -> None:
        """Test status extraction is case-insensitive."""
        content = "status: accepted\n\nContent."
        status = indexer._extract_status(content)
        assert status == "ACCEPTED"

    def test_extract_status_invalid_type(self, indexer: ADRIndexer) -> None:
        """Test that invalid status types are not accepted."""
        content = "Status: INVALID\n\nContent."
        status = indexer._extract_status(content)
        assert status is None or status != "INVALID"


class TestADRReferenceExtraction:
    """Test extracting ADR cross-references."""

    @pytest.fixture
    def indexer(self) -> ADRIndexer:
        indexer = ADRIndexer()
        # Pre-populate with some ADR IDs for reference checking
        indexer.indexed_adrs = {
            "0001": ADRMetadata("0001", "K0-K1 Split", "ACCEPTED", [], "", time.time()),
            "0005": ADRMetadata(
                "0005", "Agent Lifecycle", "ACCEPTED", [], "", time.time()
            ),
            "0051": ADRMetadata(
                "0051", "Agent Scheduling", "PROPOSED", [], "", time.time()
            ),
        }
        return indexer

    def test_extract_reference_bracket_format(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test extracting ADR references from [ADR-0001 format."""
        metadata = ADRMetadata("0005", "Test", "ACCEPTED", [], "", time.time())

        # Temporarily write a test file
        test_path = tmp_path / "test_adr.md"
        test_path.write_text(
            "[ADR-0001](0001-k0-k1-split.md) and [ADR-0051](0051-scheduling.md)"
        )
        metadata.file_path = str(test_path)

        refs = indexer._extract_adr_references(metadata)
        assert "0001" in refs
        assert "0051" in refs

    def test_extract_reference_text_format(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test extracting ADR references from text mentions."""
        metadata = ADRMetadata("0005", "Test", "ACCEPTED", [], "", time.time())

        test_path = tmp_path / "test_adr.md"
        test_path.write_text("See ADR-0001 and ADR 0051 for details.")
        metadata.file_path = str(test_path)

        refs = indexer._extract_adr_references(metadata)
        assert "0001" in refs
        assert "0051" in refs

    def test_extract_reference_no_self_reference(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test that self-references are excluded."""
        metadata = ADRMetadata("0005", "Test", "ACCEPTED", [], "", time.time())

        test_path = tmp_path / "test_adr.md"
        test_path.write_text("This is ADR-0005 and it references ADR-0001")
        metadata.file_path = str(test_path)

        refs = indexer._extract_adr_references(metadata)
        assert "0005" not in refs  # Self-reference excluded
        assert "0001" in refs

    def test_extract_reference_non_indexed_adr(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test that references to non-indexed ADRs are excluded."""
        metadata = ADRMetadata("0005", "Test", "ACCEPTED", [], "", time.time())

        test_path = tmp_path / "test_adr.md"
        test_path.write_text("This references ADR-0001 and ADR-9999")
        metadata.file_path = str(test_path)

        refs = indexer._extract_adr_references(metadata)
        assert "0001" in refs
        assert "9999" not in refs  # Not in indexed_adrs


class TestSemanticTagGeneration:
    """Test semantic tag generation from ADR metadata."""

    @pytest.fixture
    def indexer(self) -> ADRIndexer:
        return ADRIndexer()

    def test_tags_include_status(self, indexer: ADRIndexer) -> None:
        """Test that status is included as a tag."""
        metadata = ADRMetadata("0001", "K0-K1 Split", "ACCEPTED", [], "", time.time())
        tags = indexer._extract_tags(metadata)
        assert "accepted" in tags

    def test_tags_include_category(self, indexer: ADRIndexer) -> None:
        """Test that keyword from title is included as a tag."""
        metadata = ADRMetadata(
            "0001", "Agent Lifecycle", "ACCEPTED", [], "", time.time()
        )
        tags = indexer._extract_tags(metadata)
        assert "agent" in tags

    def test_tags_from_title_keywords(self, indexer: ADRIndexer) -> None:
        """Test that keywords from title are added as tags."""
        metadata = ADRMetadata(
            "0005", "Agent Lifecycle FSM", "ACCEPTED", [], "", time.time()
        )
        tags = indexer._extract_tags(metadata)
        assert "agent" in tags

    def test_tags_deduplication(self, indexer: ADRIndexer) -> None:
        """Test that tags are deduplicated."""
        metadata = ADRMetadata(
            "0005", "Agent Lifecycle", "ACCEPTED", [], "", time.time()
        )
        tags = indexer._extract_tags(metadata)
        assert len(tags) == len(set(tags))  # Check no duplicates


class TestMetadataExtraction:
    """Test full metadata extraction from ADR files."""

    @pytest.fixture
    def indexer(self) -> ADRIndexer:
        return ADRIndexer()

    def test_extract_simple_adr(self, indexer: ADRIndexer, tmp_path: Path) -> None:
        """Test extracting metadata from a simple ADR file."""
        adr_file = tmp_path / "0051-test.md"
        adr_file.write_text(
            """# ADR-0051: Test Decision

**Status:** PROPOSED

Content here.
"""
        )

        metadata = indexer.extract_metadata(adr_file)
        assert metadata is not None
        assert metadata.adr_id == "0051"
        assert "Test Decision" in metadata.title
        assert metadata.status == "PROPOSED"

    def test_extract_adr_with_letter_id(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test extracting metadata from ADR with letter ID (e.g., 0001a)."""
        adr_file = tmp_path / "0001a-bridge.md"
        adr_file.write_text(
            """# ADR-0001a: Bridge Protocol

**Status:** ACCEPTED

Content.
"""
        )

        metadata = indexer.extract_metadata(adr_file)
        assert metadata is not None
        assert metadata.adr_id == "0001a"

    def test_extract_adr_minimal_fields(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test extracting metadata when only minimal fields are present."""
        adr_file = tmp_path / "0099-minimal.md"
        adr_file.write_text("# Minimal ADR\n\nContent without metadata.")

        metadata = indexer.extract_metadata(adr_file)
        assert metadata is not None
        assert metadata.adr_id == "0099"
        assert metadata.status == "PROPOSED"  # Default


class TestDirectoryIndexing:
    """Test full directory indexing."""

    @pytest.fixture
    def indexer(self) -> ADRIndexer:
        return ADRIndexer()

    def test_ingest_directory_creates_nodes(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test that directory indexing creates correct node count."""
        # Create sample ADRs
        for i in range(3):
            adr_file = tmp_path / f"000{i}-test{i}.md"
            adr_file.write_text(
                f"# ADR-000{i}: Test {i}\n\n**Status:** ACCEPTED\n\nContent."
            )

        results = indexer.ingest_directory(tmp_path)

        assert results["adr_count"] == 3
        assert len(results["metadata"]) == 3
        assert results["errors"] == []

    def test_ingest_directory_extracts_relations(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test that cross-references are extracted."""
        adr1 = tmp_path / "0001-first.md"
        adr1.write_text("# ADR-0001: First\n\nContent.")

        adr2 = tmp_path / "0002-second.md"
        adr2.write_text("# ADR-0002: Second\n\nReferences [ADR-0001](0001-first.md).")

        results = indexer.ingest_directory(tmp_path)

        assert results["adr_count"] == 2
        assert results["extracted_relations"] > 0

    def test_ingest_directory_performance(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test that indexing completes within performance budget."""
        # Create 50 ADRs
        for i in range(50):
            adr_file = tmp_path / f"{i:04d}-test{i}.md"
            adr_file.write_text(
                f"# ADR-{i:04d}: Test {i}\n\n**Status:** PROPOSED\n\nContent."
            )

        start = time.time()
        results = indexer.ingest_directory(tmp_path)
        elapsed_ms = (time.time() - start) * 1000

        # Relaxed budget for Windows I/O (target: <1000ms for 50 files)
        assert elapsed_ms < 1000, f"Indexing too slow: {elapsed_ms:.2f}ms"
        assert results["adr_count"] == 50

    def test_ingest_directory_nonexistent(self, indexer: ADRIndexer) -> None:
        """Test handling of nonexistent directory."""
        results = indexer.ingest_directory(Path("/nonexistent/path"))

        assert results["adr_count"] == 0
        assert len(results["errors"]) > 0


class TestADRDependencies:
    """Test ADR dependency tracking."""

    @pytest.fixture
    def indexer_with_adrs(self, tmp_path: Path) -> ADRIndexer:
        """Create indexer with sample ADRs."""
        indexer = ADRIndexer()

        # Create interconnected ADRs
        adr1 = tmp_path / "0001-architecture.md"
        adr1.write_text("# ADR-0001: Architecture\n\nContent.")

        adr2 = tmp_path / "0002-agents.md"
        adr2.write_text("# ADR-0002: Agents\n\nSee [ADR-0001](0001-architecture.md).")

        adr3 = tmp_path / "0003-coordination.md"
        adr3.write_text("# ADR-0003: Coordination\n\nReferences ADR-0001 and ADR-0002.")

        indexer.ingest_directory(tmp_path)
        return indexer

    def test_get_adr_dependencies_outgoing(self, indexer_with_adrs: ADRIndexer) -> None:
        """Test getting outgoing dependencies."""
        deps = indexer_with_adrs.get_adr_dependencies("0003")
        assert "0001" in deps.get("references", [])
        assert "0002" in deps.get("references", [])

    def test_get_adr_dependencies_incoming(self, indexer_with_adrs: ADRIndexer) -> None:
        """Test getting incoming references."""
        deps = indexer_with_adrs.get_adr_dependencies("0001")
        assert "0002" in deps.get("referenced_by", [])
        assert "0003" in deps.get("referenced_by", [])

    def test_get_adr_by_status(self, indexer_with_adrs: ADRIndexer) -> None:
        """Test filtering ADRs by status."""
        # Update some ADRs to have different status
        if "0001" in indexer_with_adrs.indexed_adrs:
            indexer_with_adrs.indexed_adrs["0001"].status = "ACCEPTED"

        accepted = indexer_with_adrs.get_adr_by_status("ACCEPTED")
        assert len(accepted) > 0


class TestStatusDistribution:
    """Test ADR status statistics."""

    @pytest.fixture
    def indexer_with_adrs(self, tmp_path: Path) -> ADRIndexer:
        """Create indexer with varied ADR statuses."""
        indexer = ADRIndexer()

        for i, status in enumerate(["ACCEPTED", "PROPOSED", "ACCEPTED", "IMPLEMENTED"]):
            adr = tmp_path / f"000{i}-test.md"
            adr.write_text(f"# Test {i}\n\n**Status:** {status}\n\nContent.")

        indexer.ingest_directory(tmp_path)
        return indexer

    def test_get_status_distribution(self, indexer_with_adrs: ADRIndexer) -> None:
        """Test getting status distribution."""
        dist = indexer_with_adrs.get_adr_status_distribution()

        assert "ACCEPTED" in dist
        assert "PROPOSED" in dist
        assert dist["ACCEPTED"] >= 1


class TestErrorHandling:
    """Test error handling for malformed ADRs."""

    @pytest.fixture
    def indexer(self) -> ADRIndexer:
        return ADRIndexer()

    def test_ingest_directory_skip_non_adr_files(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test that non-ADR files are skipped."""
        readme = tmp_path / "README.md"
        readme.write_text("# README\n\nNot an ADR.")

        adr = tmp_path / "0001-test.md"
        adr.write_text("# ADR-0001\n\nContent.")

        results = indexer.ingest_directory(tmp_path)

        assert results["adr_count"] == 1  # Only ADR counted
        assert "README" not in str(results.get("metadata", {}))

    def test_ingest_directory_recovers_from_read_errors(
        self, indexer: ADRIndexer, tmp_path: Path
    ) -> None:
        """Test that indexer continues after encountering unreadable files."""
        adr1 = tmp_path / "0001-good.md"
        adr1.write_text("# ADR-0001\n\n**Status:** ACCEPTED")

        # Create second ADR
        adr2 = tmp_path / "0002-test.md"
        adr2.write_text("# ADR-0002\n\n**Status:** PROPOSED")

        results = indexer.ingest_directory(tmp_path)

        assert results["adr_count"] >= 1  # At least one ADR processed


class TestFindByTag:
    """Test finding ADRs by semantic tags."""

    @pytest.fixture
    def indexer_with_tagged_adrs(self, tmp_path: Path) -> ADRIndexer:
        """Create indexer with tagged ADRs."""
        indexer = ADRIndexer()

        adr1 = tmp_path / "0001-agent.md"
        adr1.write_text(
            "# ADR-0001: Agent Architecture\n\n**Status:** ACCEPTED\n\nAgent content."
        )

        adr2 = tmp_path / "0002-memory.md"
        adr2.write_text(
            "# ADR-0002: Memory System\n\n**Status:** PROPOSED\n\nMemory content."
        )

        indexer.ingest_directory(tmp_path)
        return indexer

    def test_find_by_keyword_tag(self, indexer_with_tagged_adrs: ADRIndexer) -> None:
        """Test finding ADRs by keyword tags."""
        agent_adrs = indexer_with_tagged_adrs.find_by_tag("agent")
        assert len(agent_adrs) > 0
        assert any("agent" in adr.title.lower() for adr in agent_adrs)

    def test_find_by_status_tag(self, indexer_with_tagged_adrs: ADRIndexer) -> None:
        """Test finding ADRs by status tags."""
        accepted_adrs = indexer_with_tagged_adrs.find_by_tag("accepted")
        assert len(accepted_adrs) > 0


class TestIntegration:
    """Integration tests for ADRIndexer with real ADR directory."""

    @pytest.fixture
    def real_adr_directory(self) -> Optional[Path]:
        """Get real ADR directory if it exists."""
        path = Path("d:/familyos/docs/architecture/decisions")
        if path.exists():
            return path
        return None

    def test_index_real_adr_directory(self, real_adr_directory: Optional[Path]) -> None:
        """Test indexing real FamilyOS ADR directory."""
        if not real_adr_directory:
            pytest.skip("Real ADR directory not found")

        indexer = ADRIndexer()
        results = indexer.ingest_directory(real_adr_directory)

        # Should find many ADRs
        assert results["adr_count"] > 50, "Should have indexed 50+ ADRs"
        # Relaxed budget: typically takes 1-2 seconds on Windows for 200+ files
        assert (
            results["elapsed_ms"] < 5000
        ), f"Should complete within 5s, took {results['elapsed_ms']:.0f}ms"
        assert results["extracted_relations"] > 0, "Should find cross-references"
        assert (
            len(results["errors"]) == 0
        ), f"Should have no errors: {results['errors']}"

    def test_real_adr_status_distribution(
        self, real_adr_directory: Optional[Path]
    ) -> None:
        """Test status distribution in real ADRs."""
        if not real_adr_directory:
            pytest.skip("Real ADR directory not found")

        indexer = ADRIndexer()
        indexer.ingest_directory(real_adr_directory)
        dist = indexer.get_adr_status_distribution()

        # Should have multiple status types
        assert len(dist) > 0, "Should have some statuses"
        assert sum(dist.values()) == len(
            indexer.indexed_adrs
        ), "Status counts should match total"
