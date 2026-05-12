"""Append-only audit log for vault operations (MS-5 PR#2).

Every ``store / retrieve / rotate / delete`` call is recorded as a
single JSONL line in the configured audit file. The log is the
operator-visible source of truth for "which adapter touched which
credential when" — and is the data feed the K0
``st_ifl_credentials_audit`` table is hydrated from.

Critically: secrets are *never* written. The log records ``adapter_id``,
``key``, ``op``, ``backend``, ``ts``, and an ``ok`` flag. If audit-log
writes themselves fail, the vault MUST surface the error to the caller
— per D17, silent audit gaps are a gate failure.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

VaultOp = Literal["store", "retrieve", "rotate", "delete"]


@dataclass(frozen=True, slots=True)
class VaultAuditEntry:
    """One audit line.

    Attributes:
        ts: Wall-clock epoch seconds (UTC). Used by the K0 ingester to
            populate ``st_ifl_credentials_audit.observed_at``.
        adapter_id: Owning adapter (e.g. ``google_calendar_father``).
        key: Credential key (e.g. ``oauth.refresh_token``).
        op: One of ``store``, ``retrieve``, ``rotate``, ``delete``.
        backend: Reporting vault's ``backend_name`` (``keyring``,
            ``memory``, ``sqlcipher``).
        ok: True for success, False if the underlying op raised.
        error: Optional one-line error description (only set when
            ``ok=False``). Never includes secret material.
    """

    ts: float
    adapter_id: str
    key: str
    op: VaultOp
    backend: str
    ok: bool
    error: str = ""


class VaultAuditLog:
    """Thread-safe JSONL appender.

    Files are opened lazily on first :meth:`append` and re-opened if
    truncated externally. Writes are flushed on every line so a power
    cut at most loses an in-progress single line — sufficient for the
    family-OS threat model documented in
    ``docs/architecture/security/credential_vault.md``.
    """

    def __init__(self, *, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        # Ensure parent dir exists so first write doesn't race with
        # mkdir on platforms where tmp dirs are auto-cleaned.
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(
        self,
        *,
        adapter_id: str,
        key: str,
        op: VaultOp,
        backend: str,
        ok: bool,
        error: str = "",
        now: float | None = None,
    ) -> VaultAuditEntry:
        """Append one entry; returns the persisted row.

        Raises:
            OSError: if the log file cannot be opened or written.
        """
        entry = VaultAuditEntry(
            ts=time.time() if now is None else now,
            adapter_id=adapter_id,
            key=key,
            op=op,
            backend=backend,
            ok=ok,
            error=error,
        )
        line = json.dumps(asdict(entry), separators=(",", ":"), sort_keys=True)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
        return entry

    def read_all(self) -> list[VaultAuditEntry]:
        """Re-hydrate every entry. Used by tests + K0 ingest backfill."""
        if not self._path.exists():
            return []
        out: list[VaultAuditEntry] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                obj = json.loads(raw)
                out.append(VaultAuditEntry(**obj))
        return out


__all__ = ["VaultAuditEntry", "VaultAuditLog", "VaultOp"]
