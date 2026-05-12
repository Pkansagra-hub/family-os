"""Append-only consent ledger for the Google Calendar IFL adapter
(MS-5 PR#4).

Per the bridge contracts D17 ceremony, each IFL adapter must prove
the user explicitly authorized the data scope before the bridge
runtime allows the corresponding adapter to start. We record those
authorizations in a JSONL file (one event per line) so the ledger
is human-auditable and survives crash without losing entries.

This module is read/write-light: in production a ``ConsentLedger``
instance is constructed once per process; entries are appended via
:meth:`record_grant` and listed via :meth:`grants_for_account`.
There is **no** revoke API by design — revocation is modeled as a
new entry with ``decision="revoked"`` so the audit trail is
immutable.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

ConsentDecision = Literal["granted", "revoked"]


@dataclass(frozen=True, slots=True)
class ConsentEntry:
    """One immutable row in the consent ledger."""

    account_id: str
    scope: str
    decision: ConsentDecision
    granted_at: str  # RFC 3339
    granted_by: str  # operator identity (CLI, web ui, etc.)


class ConsentLedger:
    """Thread-safe JSONL-backed append-only consent ledger."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def record_grant(
        self,
        *,
        account_id: str,
        scope: str,
        granted_by: str,
        decision: ConsentDecision = "granted",
        now: datetime | None = None,
    ) -> ConsentEntry:
        if not account_id or not scope or not granted_by:
            raise ValueError("account_id, scope, and granted_by must all be non-empty")
        ts = (now or datetime.now(tz=timezone.utc)).isoformat(timespec="seconds")
        entry = ConsentEntry(
            account_id=account_id,
            scope=scope,
            decision=decision,
            granted_at=ts,
            granted_by=granted_by,
        )
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def grants_for_account(self, account_id: str) -> list[ConsentEntry]:
        return [e for e in self._read_all() if e.account_id == account_id]

    def has_active_grant(self, *, account_id: str, scope: str) -> bool:
        """True iff the most recent entry for (account_id, scope) is
        a grant (i.e. not yet superseded by a revoke)."""
        latest: ConsentEntry | None = None
        for entry in self._read_all():
            if entry.account_id == account_id and entry.scope == scope:
                latest = entry
        return latest is not None and latest.decision == "granted"

    def _read_all(self) -> Iterable[ConsentEntry]:
        if not self._path.exists():
            return []
        rows: list[ConsentEntry] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                obj = json.loads(raw)
                rows.append(ConsentEntry(**obj))
        return rows
