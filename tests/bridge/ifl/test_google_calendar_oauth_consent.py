"""Tests for the GCal OAuth helper and consent ledger."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bridge.ifl.adapters.google_calendar.consent import (
    ConsentLedger,
)
from bridge.ifl.adapters.google_calendar.oauth import (
    AccessToken,
    OAuthError,
    exchange_refresh_token,
)


class TestExchangeRefreshToken:
    def test_returns_access_token_on_success(self) -> None:
        captured: dict[str, object] = {}

        def fake_post(url: str, data: dict[str, str]) -> dict[str, object]:
            captured["url"] = url
            captured["data"] = dict(data)
            return {
                "access_token": "tkn",
                "expires_in": 1234,
                "token_type": "Bearer",
                "scope": "calendar.readonly",
            }

        token = exchange_refresh_token(
            refresh_token="rt",
            client_id="cid",
            client_secret="csec",
            http_post=fake_post,
        )
        assert isinstance(token, AccessToken)
        assert token.access_token == "tkn"
        assert token.expires_in == 1234
        assert captured["data"]["grant_type"] == "refresh_token"
        assert captured["data"]["refresh_token"] == "rt"

    def test_rejects_empty_refresh_token(self) -> None:
        with pytest.raises(ValueError, match="refresh_token"):
            exchange_refresh_token(
                refresh_token="",
                client_id="cid",
                client_secret="csec",
                http_post=lambda *a, **k: {},
            )

    def test_rejects_empty_client_credentials(self) -> None:
        with pytest.raises(ValueError, match="client_id"):
            exchange_refresh_token(
                refresh_token="rt",
                client_id="",
                client_secret="csec",
                http_post=lambda *a, **k: {},
            )

    def test_raises_on_malformed_response(self) -> None:
        def fake_post(url: str, data: dict[str, str]) -> dict[str, object]:
            return {"oops": "nope"}

        with pytest.raises(OAuthError, match="malformed"):
            exchange_refresh_token(
                refresh_token="rt",
                client_id="cid",
                client_secret="csec",
                http_post=fake_post,
            )


class TestConsentLedger:
    def test_record_grant_creates_jsonl_entry(self, tmp_path: Path) -> None:
        ledger = ConsentLedger(tmp_path / "consent.jsonl")
        entry = ledger.record_grant(
            account_id="acc_1",
            scope="calendar.readonly",
            granted_by="prince",
        )
        assert entry.decision == "granted"
        lines = (tmp_path / "consent.jsonl").read_text().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["account_id"] == "acc_1"

    def test_grants_for_account_filters_by_account(self, tmp_path: Path) -> None:
        ledger = ConsentLedger(tmp_path / "consent.jsonl")
        ledger.record_grant(account_id="acc_1", scope="cal", granted_by="p")
        ledger.record_grant(account_id="acc_2", scope="cal", granted_by="p")
        rows = ledger.grants_for_account("acc_1")
        assert len(rows) == 1
        assert rows[0].account_id == "acc_1"

    def test_has_active_grant_respects_revocation(self, tmp_path: Path) -> None:
        ledger = ConsentLedger(tmp_path / "consent.jsonl")
        ledger.record_grant(account_id="a", scope="cal", granted_by="p")
        assert ledger.has_active_grant(account_id="a", scope="cal") is True
        ledger.record_grant(
            account_id="a",
            scope="cal",
            granted_by="p",
            decision="revoked",
        )
        assert ledger.has_active_grant(account_id="a", scope="cal") is False

    def test_record_grant_rejects_empty_args(self, tmp_path: Path) -> None:
        ledger = ConsentLedger(tmp_path / "consent.jsonl")
        with pytest.raises(ValueError):
            ledger.record_grant(
                account_id="",
                scope="cal",
                granted_by="p",
            )

    def test_has_active_grant_is_false_when_no_entries(self, tmp_path: Path) -> None:
        ledger = ConsentLedger(tmp_path / "consent.jsonl")
        assert ledger.has_active_grant(account_id="a", scope="cal") is False
