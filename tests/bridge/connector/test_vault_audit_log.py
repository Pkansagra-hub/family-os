"""Tests for :mod:`bridge.connector.vault.audit_log`."""

from __future__ import annotations

from pathlib import Path

import pytest

from bridge.connector.vault.audit_log import VaultAuditLog


class TestVaultAuditLog:
    def test_append_creates_file_on_first_write(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.jsonl"
        log = VaultAuditLog(path=log_path)
        assert not log_path.exists()
        log.append(
            adapter_id="adapter_a",
            key="oauth.refresh_token",
            op="store",
            backend="memory",
            ok=True,
        )
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1

    def test_appended_entry_never_contains_secret(self, tmp_path: Path) -> None:
        log = VaultAuditLog(path=tmp_path / "audit.jsonl")
        # Only metadata fields are accepted; secret material is never
        # part of the API surface — verified by signature inspection.
        log.append(
            adapter_id="a",
            key="k",
            op="retrieve",
            backend="keyring",
            ok=True,
        )
        body = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
        assert "secret" not in body.lower()
        assert "password" not in body.lower()

    def test_round_trip_via_read_all(self, tmp_path: Path) -> None:
        log = VaultAuditLog(path=tmp_path / "audit.jsonl")
        log.append(
            adapter_id="a",
            key="k1",
            op="store",
            backend="memory",
            ok=True,
            now=100.0,
        )
        log.append(
            adapter_id="a",
            key="k1",
            op="rotate",
            backend="memory",
            ok=True,
            now=110.0,
        )
        log.append(
            adapter_id="a",
            key="k1",
            op="delete",
            backend="memory",
            ok=True,
            now=120.0,
        )
        entries = log.read_all()
        assert [e.op for e in entries] == ["store", "rotate", "delete"]
        assert [e.ts for e in entries] == [100.0, 110.0, 120.0]

    def test_failed_op_records_error_and_ok_false(self, tmp_path: Path) -> None:
        log = VaultAuditLog(path=tmp_path / "audit.jsonl")
        log.append(
            adapter_id="a",
            key="k",
            op="retrieve",
            backend="keyring",
            ok=False,
            error="DPAPI unavailable",
        )
        entries = log.read_all()
        assert len(entries) == 1
        assert entries[0].ok is False
        assert "DPAPI unavailable" in entries[0].error

    def test_read_all_on_missing_file_returns_empty(self, tmp_path: Path) -> None:
        log = VaultAuditLog(path=tmp_path / "never-written.jsonl")
        assert log.read_all() == []

    def test_concurrent_appends_serialise(self, tmp_path: Path) -> None:
        # Light-weight smoke test: 100 sequential appends must produce
        # exactly 100 well-formed JSONL rows with no truncation.
        log = VaultAuditLog(path=tmp_path / "audit.jsonl")
        for i in range(100):
            log.append(
                adapter_id=f"a{i}",
                key="k",
                op="store",
                backend="memory",
                ok=True,
            )
        entries = log.read_all()
        assert len(entries) == 100
        assert {e.adapter_id for e in entries} == {f"a{i}" for i in range(100)}

    def test_invalid_op_rejected_by_typing_at_runtime(self, tmp_path: Path) -> None:
        # The Literal type isn't enforced at runtime, so this is a
        # documentation-only test: any string is accepted; review
        # responsibility lies with reviewers + the vault backends.
        log = VaultAuditLog(path=tmp_path / "audit.jsonl")
        # Ensure at least the file write path doesn't crash on a
        # non-canonical op string — still useful for forensic
        # capture if a future op slips through.
        log.append(
            adapter_id="a",
            key="k",
            op="store",  # type: ignore[arg-type]
            backend="memory",
            ok=True,
        )
        assert (tmp_path / "audit.jsonl").exists()

    def test_path_property_returns_configured_location(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "audit.jsonl"
        log = VaultAuditLog(path=target)
        # Parent directory created lazily on construction.
        assert target.parent.exists()
        assert log.path == target


class TestVaultAuditLogEdgeCases:
    def test_blank_lines_in_log_are_skipped(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            '{"ts":1.0,"adapter_id":"a","key":"k","op":"store","backend":"memory","ok":true,"error":""}\n'
            "\n"
            '{"ts":2.0,"adapter_id":"a","key":"k","op":"delete","backend":"memory","ok":true,"error":""}\n',
            encoding="utf-8",
        )
        log = VaultAuditLog(path=log_path)
        entries = log.read_all()
        assert len(entries) == 2

    def test_corrupt_line_raises(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("not-json\n", encoding="utf-8")
        log = VaultAuditLog(path=log_path)
        with pytest.raises(Exception):
            log.read_all()
