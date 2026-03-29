"""
Unit tests for P03 Version Manager.

Tests checksum generation, integrity checking, version bumping, and changelog.
"""

import pytest

from governance.k0.scripts.p03_version_manager import (
    FileChecksum,
    IntegrityReport,
    IntegrityResult,
    VersionManifest,
    bump_version,
    check_version_integrity,
    compute_file_sha256,
    format_version,
    generate_changelog,
    generate_version_file,
    load_version_file,
    parse_version,
    scan_directory_files,
)


class TestDataClasses:
    """Tests for data class functionality."""

    def test_version_manifest_to_dict(self):
        manifest = VersionManifest(
            version="1.0.0",
            generated_at="2026-01-17T12:00:00",
            generator="test",
            directory="test/dir",
            file_count=2,
            total_size_bytes=1000,
            files=[
                FileChecksum(
                    relative_path="file1.py",
                    sha256="abc123",
                    size_bytes=500,
                    last_modified="2026-01-17T10:00:00",
                ),
            ],
        )
        d = manifest.to_dict()
        assert d["version"] == "1.0.0"
        assert d["file_count"] == 2
        assert len(d["files"]) == 1
        assert d["files"][0]["path"] == "file1.py"

    def test_version_manifest_from_dict(self):
        data = {
            "version": "2.0.0",
            "generated_at": "2026-01-17T12:00:00",
            "generator": "test",
            "directory": "test/dir",
            "file_count": 1,
            "total_size_bytes": 500,
            "files": [
                {
                    "path": "file1.py",
                    "sha256": "abc123",
                    "size": 500,
                    "modified": "2026-01-17T10:00:00",
                }
            ],
        }
        manifest = VersionManifest.from_dict(data)
        assert manifest.version == "2.0.0"
        assert len(manifest.files) == 1
        assert manifest.files[0].relative_path == "file1.py"

    def test_integrity_report_is_clean(self):
        report = IntegrityReport(
            version="1.0.0",
            checked_at="2026-01-17T12:00:00",
            total_files=10,
            ok_count=10,
            modified_count=0,
            added_count=0,
            deleted_count=0,
        )
        assert report.is_clean is True

    def test_integrity_report_not_clean_with_modifications(self):
        report = IntegrityReport(
            version="1.0.0",
            checked_at="2026-01-17T12:00:00",
            total_files=10,
            ok_count=9,
            modified_count=1,
            added_count=0,
            deleted_count=0,
        )
        assert report.is_clean is False

    def test_integrity_report_changes(self):
        report = IntegrityReport(
            version="1.0.0",
            checked_at="2026-01-17T12:00:00",
            total_files=10,
            ok_count=8,
            modified_count=1,
            added_count=1,
            deleted_count=0,
            results=[
                IntegrityResult(path="a.py", status="ok"),
                IntegrityResult(path="b.py", status="modified"),
                IntegrityResult(path="c.py", status="added"),
            ],
        )
        changes = report.changes
        assert len(changes) == 2
        assert all(r.status != "ok" for r in changes)


class TestChecksumFunctions:
    """Tests for checksum computation."""

    def test_compute_file_sha256(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        sha = compute_file_sha256(test_file)
        assert len(sha) == 64  # SHA256 hex is 64 chars
        # Same content should produce same hash
        sha2 = compute_file_sha256(test_file)
        assert sha == sha2

    def test_compute_file_sha256_different_content(self, tmp_path):
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"
        file1.write_text("content1")
        file2.write_text("content2")
        sha1 = compute_file_sha256(file1)
        sha2 = compute_file_sha256(file2)
        assert sha1 != sha2

    def test_scan_directory_files(self, tmp_path):
        # Create test structure
        (tmp_path / "file1.py").write_text("# file 1")
        (tmp_path / "file2.py").write_text("# file 2")
        (tmp_path / "__init__.py").write_text("")  # Should be excluded
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.py").write_text("# file 3")

        checksums = scan_directory_files(tmp_path)
        paths = [c.relative_path for c in checksums]

        assert len(checksums) == 3
        assert "file1.py" in paths
        assert "file2.py" in paths
        assert "__init__.py" not in paths  # Excluded


class TestVersionParsing:
    """Tests for version string parsing."""

    def test_parse_version(self):
        major, minor, patch = parse_version("1.2.3")
        assert major == 1
        assert minor == 2
        assert patch == 3

    def test_parse_version_zero(self):
        major, minor, patch = parse_version("0.0.0")
        assert major == 0
        assert minor == 0
        assert patch == 0

    def test_format_version(self):
        v = format_version(1, 2, 3)
        assert v == "1.2.3"

    def test_parse_version_invalid(self):
        with pytest.raises(ValueError):
            parse_version("1.2")


class TestVersionFileGeneration:
    """Tests for VERSION.yaml generation."""

    def test_generate_version_file(self, tmp_path):
        # Create test files
        (tmp_path / "file1.py").write_text("# file 1\nprint('hello')")
        (tmp_path / "file2.py").write_text("# file 2\nprint('world')")

        manifest = generate_version_file(tmp_path, version="1.0.0", write=True)

        assert manifest.version == "1.0.0"
        assert manifest.file_count == 2
        assert manifest.total_size_bytes > 0
        assert len(manifest.files) == 2

        # Check file was written
        version_file = tmp_path / "VERSION.yaml"
        assert version_file.exists()

    def test_load_version_file(self, tmp_path):
        # Create test file
        (tmp_path / "test.py").write_text("# test")
        generate_version_file(tmp_path, version="2.0.0", write=True)

        loaded = load_version_file(tmp_path)
        assert loaded is not None
        assert loaded.version == "2.0.0"

    def test_load_version_file_not_exists(self, tmp_path):
        loaded = load_version_file(tmp_path)
        assert loaded is None


class TestIntegrityCheck:
    """Tests for integrity checking."""

    def test_check_integrity_clean(self, tmp_path):
        (tmp_path / "file1.py").write_text("# test")
        generate_version_file(tmp_path, version="1.0.0", write=True)

        report = check_version_integrity(tmp_path)
        assert report.is_clean
        assert report.ok_count == 1
        assert report.modified_count == 0

    def test_check_integrity_modified(self, tmp_path):
        test_file = tmp_path / "file1.py"
        test_file.write_text("# original")
        generate_version_file(tmp_path, version="1.0.0", write=True)

        # Modify the file
        test_file.write_text("# modified content")

        report = check_version_integrity(tmp_path)
        assert not report.is_clean
        assert report.modified_count == 1

    def test_check_integrity_added(self, tmp_path):
        (tmp_path / "file1.py").write_text("# test")
        generate_version_file(tmp_path, version="1.0.0", write=True)

        # Add new file
        (tmp_path / "file2.py").write_text("# new file")

        report = check_version_integrity(tmp_path)
        assert not report.is_clean
        assert report.added_count == 1

    def test_check_integrity_deleted(self, tmp_path):
        test_file = tmp_path / "file1.py"
        test_file.write_text("# test")
        generate_version_file(tmp_path, version="1.0.0", write=True)

        # Delete the file
        test_file.unlink()

        report = check_version_integrity(tmp_path)
        assert not report.is_clean
        assert report.deleted_count == 1


class TestVersionBumping:
    """Tests for version bumping."""

    def test_bump_patch(self, tmp_path):
        (tmp_path / "file1.py").write_text("# test")
        generate_version_file(tmp_path, version="1.0.0", write=True)

        old, new = bump_version(tmp_path, "patch", write=True)
        assert old == "1.0.0"
        assert new == "1.0.1"

        loaded = load_version_file(tmp_path)
        assert loaded is not None
        assert loaded.version == "1.0.1"

    def test_bump_minor(self, tmp_path):
        (tmp_path / "file1.py").write_text("# test")
        generate_version_file(tmp_path, version="1.2.3", write=True)

        old, new = bump_version(tmp_path, "minor", write=True)
        assert old == "1.2.3"
        assert new == "1.3.0"

    def test_bump_major(self, tmp_path):
        (tmp_path / "file1.py").write_text("# test")
        generate_version_file(tmp_path, version="1.2.3", write=True)

        old, new = bump_version(tmp_path, "major", write=True)
        assert old == "1.2.3"
        assert new == "2.0.0"

    def test_bump_no_existing_version(self, tmp_path):
        (tmp_path / "file1.py").write_text("# test")

        old, new = bump_version(tmp_path, "patch", write=True)
        assert old == "0.0.0"
        assert new == "0.0.1"


class TestChangelog:
    """Tests for changelog generation."""

    def test_generate_changelog_with_changes(self, tmp_path):
        (tmp_path / "file1.py").write_text("# original")
        generate_version_file(tmp_path, version="1.0.0", write=True)

        # Make changes
        (tmp_path / "file1.py").write_text("# modified")
        (tmp_path / "file2.py").write_text("# new")

        entry = generate_changelog(tmp_path)
        assert entry is not None
        assert entry.version == "1.0.0"
        assert len(entry.changes) >= 1

    def test_generate_changelog_no_changes(self, tmp_path):
        (tmp_path / "file1.py").write_text("# test")
        generate_version_file(tmp_path, version="1.0.0", write=True)

        entry = generate_changelog(tmp_path)
        assert entry is None


class TestProductionDirectories:
    """Tests against actual P03 directories."""

    def test_scan_p03_pipeline_files(self):
        from governance.k0.scripts.p03_version_manager import _get_p03_pipeline_dir

        pipeline_dir = _get_p03_pipeline_dir()
        checksums = scan_directory_files(pipeline_dir)
        # We know there are 78 files
        assert len(checksums) >= 70

    def test_scan_consolidation_files(self):
        from governance.k0.scripts.p03_version_manager import _get_consolidation_dir

        consol_dir = _get_consolidation_dir()
        checksums = scan_directory_files(consol_dir)
        # We know there are 89 files
        assert len(checksums) >= 80

    def test_load_existing_version_files(self):
        from governance.k0.scripts.p03_version_manager import (
            _get_consolidation_dir,
            _get_p03_pipeline_dir,
        )

        pipeline_manifest = load_version_file(_get_p03_pipeline_dir())
        algorithm_manifest = load_version_file(_get_consolidation_dir())

        # These were generated earlier
        assert pipeline_manifest is not None
        assert algorithm_manifest is not None
        assert pipeline_manifest.version == "1.0.0"
        assert algorithm_manifest.version == "1.0.0"
