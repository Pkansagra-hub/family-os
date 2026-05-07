"""Tests for :class:`bridge.connector.vault.keyring_vault.KeyringVault`.

We use a fake in-memory keyring shim instead of the real OS keyring so
tests run identically on CI runners that lack DPAPI / Keychain. The
fake faithfully implements ``set_password / get_password /
delete_password`` and surfaces the same ``PasswordDeleteError`` shape
keyring raises on missing entries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bridge.connector.credential_vault import CredentialNotFoundError
from bridge.connector.vault.audit_log import VaultAuditLog
from bridge.connector.vault.keyring_vault import KeyringVault


class _PasswordDeleteError(Exception):
    """Mimics keyring.errors.PasswordDeleteError."""


class _FakeKeyring:
    """In-memory stand-in for the keyring module surface we use."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}
        # Probe-style hooks: tests can flip these to simulate failures.
        self.set_should_raise: BaseException | None = None
        self.get_should_raise: BaseException | None = None

    def set_password(self, service: str, username: str, password: str) -> None:
        if self.set_should_raise is not None:
            raise self.set_should_raise
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        if self.get_should_raise is not None:
            raise self.get_should_raise
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self._store:
            raise _PasswordDeleteError("not found")
        del self._store[(service, username)]


@pytest.fixture()
def fake_keyring() -> _FakeKeyring:
    return _FakeKeyring()


@pytest.fixture()
def audit_log(tmp_path: Path) -> VaultAuditLog:
    return VaultAuditLog(path=tmp_path / "vault_audit.jsonl")


@pytest.fixture()
def vault(fake_keyring: _FakeKeyring, audit_log: VaultAuditLog) -> KeyringVault:
    return KeyringVault(keyring_module=fake_keyring, audit_log=audit_log)


class TestKeyringVaultRoundTrip:
    def test_backend_name_is_keyring(self, vault: KeyringVault) -> None:
        assert vault.backend_name == "keyring"

    def test_store_then_retrieve_roundtrip(self, vault: KeyringVault) -> None:
        vault.store(adapter_id="adapter_a", key="oauth.refresh", secret="s3cr3t")
        assert vault.retrieve(adapter_id="adapter_a", key="oauth.refresh") == "s3cr3t"

    def test_retrieve_unknown_raises_not_found(self, vault: KeyringVault) -> None:
        with pytest.raises(CredentialNotFoundError):
            vault.retrieve(adapter_id="adapter_a", key="absent")

    def test_delete_is_idempotent(self, vault: KeyringVault) -> None:
        vault.store(adapter_id="a", key="k", secret="v")
        vault.delete(adapter_id="a", key="k")
        # Idempotent — second delete does not raise.
        vault.delete(adapter_id="a", key="k")
        with pytest.raises(CredentialNotFoundError):
            vault.retrieve(adapter_id="a", key="k")

    def test_rotate_replaces_existing_secret(self, vault: KeyringVault) -> None:
        vault.store(adapter_id="a", key="k", secret="old")
        vault.rotate(adapter_id="a", key="k", new_secret="new")
        assert vault.retrieve(adapter_id="a", key="k") == "new"

    def test_rotate_missing_key_raises(self, vault: KeyringVault) -> None:
        with pytest.raises(CredentialNotFoundError):
            vault.rotate(adapter_id="a", key="missing", new_secret="new")

    def test_list_keys_returns_only_requested_adapter(self, vault: KeyringVault) -> None:
        vault.store(adapter_id="a", key="k1", secret="v")
        vault.store(adapter_id="a", key="k2", secret="v")
        vault.store(adapter_id="b", key="k3", secret="v")
        assert vault.list_keys(adapter_id="a") == ["k1", "k2"]
        assert vault.list_keys(adapter_id="b") == ["k3"]
        assert vault.list_keys(adapter_id="c") == []


class TestKeyringVaultAuditLog:
    def test_store_appends_audit_entry(self, vault: KeyringVault, audit_log: VaultAuditLog) -> None:
        vault.store(adapter_id="a", key="k", secret="v")
        entries = audit_log.read_all()
        assert len(entries) == 1
        assert entries[0].op == "store"
        assert entries[0].ok is True
        assert entries[0].backend == "keyring"

    def test_audit_never_records_secret_value(
        self, vault: KeyringVault, audit_log: VaultAuditLog
    ) -> None:
        vault.store(adapter_id="a", key="k", secret="super-secret-token-xyz")
        body = audit_log.path.read_text(encoding="utf-8")
        assert "super-secret-token-xyz" not in body

    def test_failed_store_records_ok_false(
        self,
        fake_keyring: _FakeKeyring,
        audit_log: VaultAuditLog,
    ) -> None:
        fake_keyring.set_should_raise = RuntimeError("DPAPI offline")
        vault = KeyringVault(keyring_module=fake_keyring, audit_log=audit_log)
        with pytest.raises(RuntimeError):
            vault.store(adapter_id="a", key="k", secret="v")
        entries = audit_log.read_all()
        assert len(entries) == 1
        assert entries[0].ok is False
        assert "DPAPI offline" in entries[0].error

    def test_retrieve_missing_key_records_audit_entry(
        self, vault: KeyringVault, audit_log: VaultAuditLog
    ) -> None:
        with pytest.raises(CredentialNotFoundError):
            vault.retrieve(adapter_id="a", key="missing")
        entries = audit_log.read_all()
        assert len(entries) == 1
        assert entries[0].op == "retrieve"
        assert entries[0].ok is False


class TestKeyringVaultIndexHydration:
    def test_index_hydrates_from_existing_audit_log(
        self,
        fake_keyring: _FakeKeyring,
        tmp_path: Path,
    ) -> None:
        audit_path = tmp_path / "audit.jsonl"
        # First instance stores two records and persists audit history.
        log1 = VaultAuditLog(path=audit_path)
        v1 = KeyringVault(keyring_module=fake_keyring, audit_log=log1)
        v1.store(adapter_id="a", key="k1", secret="v")
        v1.store(adapter_id="a", key="k2", secret="v")
        v1.delete(adapter_id="a", key="k2")
        # Restart simulation: new instance, same fake_keyring + audit
        # log file. Index must be reconstructed from JSONL history.
        log2 = VaultAuditLog(path=audit_path)
        v2 = KeyringVault(keyring_module=fake_keyring, audit_log=log2)
        assert v2.list_keys(adapter_id="a") == ["k1"]


class TestKeyringVaultHealthCheck:
    def test_health_check_ok_round_trip(self, vault: KeyringVault) -> None:
        result = vault.health_check()
        assert result.ok is True
        assert result.backend == "keyring"

    def test_health_check_reports_failure(
        self, fake_keyring: _FakeKeyring, audit_log: VaultAuditLog
    ) -> None:
        vault = KeyringVault(keyring_module=fake_keyring, audit_log=audit_log)
        fake_keyring.set_should_raise = RuntimeError("backend offline")
        result = vault.health_check()
        assert result.ok is False
        assert "backend offline" in result.detail


class TestKeyringVaultErrorSanitisation:
    def test_long_error_message_is_truncated(
        self,
        fake_keyring: _FakeKeyring,
        audit_log: VaultAuditLog,
    ) -> None:
        fake_keyring.set_should_raise = RuntimeError("x" * 1000)
        vault = KeyringVault(keyring_module=fake_keyring, audit_log=audit_log)
        with pytest.raises(RuntimeError):
            vault.store(adapter_id="a", key="k", secret="v")
        entries = audit_log.read_all()
        # Sanitiser caps at 240 chars + "RuntimeError: " prefix.
        assert len(entries[0].error) <= 260

    def test_multiline_error_is_collapsed(
        self,
        fake_keyring: _FakeKeyring,
        audit_log: VaultAuditLog,
    ) -> None:
        fake_keyring.set_should_raise = RuntimeError("line1\nline2\nline3")
        vault = KeyringVault(keyring_module=fake_keyring, audit_log=audit_log)
        with pytest.raises(RuntimeError):
            vault.store(adapter_id="a", key="k", secret="v")
        entries = audit_log.read_all()
        assert "\n" not in entries[0].error
        assert "line2" not in entries[0].error
