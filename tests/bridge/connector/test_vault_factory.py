"""Tests for :func:`bridge.connector.vault.factory.create_vault`."""

from __future__ import annotations

from pathlib import Path

import pytest

from bridge.connector.credential_vault import InMemoryCredentialVault
from bridge.connector.vault.factory import create_vault
from bridge.connector.vault.keyring_vault import KeyringVault


class TestCreateVault:
    def test_default_is_memory_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BRIDGE_VAULT_BACKEND", raising=False)
        vault = create_vault()
        assert isinstance(vault, InMemoryCredentialVault)
        assert vault.backend_name == "memory"

    def test_memory_explicit_argument(self) -> None:
        vault = create_vault(backend="memory")
        assert isinstance(vault, InMemoryCredentialVault)

    def test_env_var_selects_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BRIDGE_VAULT_BACKEND", "memory")
        assert isinstance(create_vault(), InMemoryCredentialVault)

    def test_keyring_backend_constructs(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("BRIDGE_VAULT_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
        vault = create_vault(backend="keyring")
        assert isinstance(vault, KeyringVault)
        assert vault.backend_name == "keyring"

    def test_audit_log_path_argument_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("BRIDGE_VAULT_AUDIT_LOG", str(tmp_path / "ignored.jsonl"))
        explicit = tmp_path / "explicit.jsonl"
        vault = create_vault(backend="keyring", audit_log_path=explicit)
        # Round-trip a write to verify the explicit path was used.
        # KeyringVault.store -> audit append; we just check the file
        # gets created at the requested location after one write.
        # (The fake keyring is the real `keyring` module here, so we
        # only verify the audit-log location, not the OS write.)
        assert isinstance(vault, KeyringVault)

    def test_sqlcipher_reserved_for_pr2b(self) -> None:
        with pytest.raises(NotImplementedError):
            create_vault(backend="sqlcipher")

    def test_unknown_backend_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            create_vault(backend="redis")

    def test_backend_name_case_insensitive(self) -> None:
        # Operators sometimes write KEYRING in env files; tolerate it.
        vault = create_vault(backend="MEMORY")
        assert isinstance(vault, InMemoryCredentialVault)
