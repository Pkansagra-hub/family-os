"""Tests for the Google Calendar IFL adapter (MS-5 PR#4).

These cover three layers without requiring real Google API access:

1. Pure-Python ``events_list_handler`` against fixture mode.
2. The K0 ``google_calendar_normalizer`` + ``ingest`` pipeline.
3. The MS-5 EXIT criterion — a full round-trip through:
   ``RealMCPProcessManager`` → fastmcp stdio subprocess → fixture
   server → ``CABundleAdapterVerifier`` (production verifier, no
   ``trust_unsigned``) → ``ConnectorGateway.invoke`` →
   ``google_calendar_normalizer`` → ``p_ifl.ingest.ingest_atoms`` →
   P02 write-ack.

The fixture server replays a deterministic JSON payload so the test
is hermetic. Real-world OAuth + API hits are exercised manually
during operator-run cassette capture (see PR#4 plan locked
decision #9).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from bridge.connector import (
    CABundleAdapterVerifier,
    ConnectorCaller,
    ConnectorGateway,
    InMemoryCredentialVault,
    RealMCPProcessManager,
)
from bridge.ifl.adapters.google_calendar.server import events_list_handler
from k0.pipelines.p_ifl import google_calendar_normalizer as gcal_normalizer
from k0.pipelines.p_ifl import ingest as ifl_ingest
from tooling.contracts.sign_manifest import sign_manifest

pytestmark = pytest.mark.asyncio

_REPO = Path(__file__).resolve().parents[3]
_GCAL_MANIFEST_PATH = (
    _REPO / "bridge" / "contracts" / "manifests" / "ifl.google_calendar.events.list.v1.yaml"
)
_DEV_PRIV = _REPO / "tests" / "fixtures" / "dev_trust_anchor.priv.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fixture_payload() -> dict[str, Any]:
    return {
        "events": [
            {
                "id": "evt_1",
                "summary": "Coffee with Rachel",
                "start": {
                    "date_time": "2026-06-01T09:00:00-07:00",
                    "time_zone": "America/Los_Angeles",
                },
                "end": {
                    "date_time": "2026-06-01T10:00:00-07:00",
                    "time_zone": "America/Los_Angeles",
                },
                "status": "confirmed",
                "location": "Starbucks",
            },
            {
                "id": "evt_2",
                "summary": "Project review",
                "start": {"date_time": "2026-06-02T14:00:00-07:00"},
                "end": {"date_time": "2026-06-02T15:00:00-07:00"},
                "status": "confirmed",
            },
        ],
    }


@pytest.fixture()
def fixture_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    payload = _fixture_payload()
    p = tmp_path / "gcal_fixture.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("BRIDGE_GCAL_FIXTURE_PATH", str(p))
    return p


# ---------------------------------------------------------------------------
# Layer 1: handler
# ---------------------------------------------------------------------------


class TestEventsListHandler:
    def test_returns_fixture_in_fixture_mode(self, fixture_path: Path) -> None:
        result = events_list_handler(
            {
                "account_id": "acc_1",
                "time_min": "2026-06-01T00:00:00Z",
                "time_max": "2026-06-30T00:00:00Z",
            }
        )
        assert "events" in result
        assert len(result["events"]) == 2
        assert result["events"][0]["id"] == "evt_1"

    def test_requires_account_id(self, fixture_path: Path) -> None:
        with pytest.raises(ValueError, match="account_id"):
            events_list_handler(
                {
                    "account_id": "",
                    "time_min": "2026-06-01T00:00:00Z",
                    "time_max": "2026-06-30T00:00:00Z",
                }
            )

    def test_requires_time_min_and_time_max(self, fixture_path: Path) -> None:
        with pytest.raises(ValueError, match="time_min"):
            events_list_handler(
                {
                    "account_id": "acc_1",
                    "time_min": "",
                    "time_max": "2026-06-30T00:00:00Z",
                }
            )


# ---------------------------------------------------------------------------
# Layer 2: normalizer + ingest
# ---------------------------------------------------------------------------


class TestNormalizerAndIngest:
    def test_normalize_response_yields_one_atom_per_event(self) -> None:
        atoms = gcal_normalizer.normalize_response(
            _fixture_payload(),
            account_id="acc_1",
            session_id="sess_1",
        )
        assert len(atoms) == 2
        for atom in atoms:
            assert atom["schema_version"] == "2.2"
            assert atom["operation"] == "UPSERT"
            assert atom["source_type"] == "device_observed"

    def test_normalize_event_requires_id(self) -> None:
        with pytest.raises(ValueError, match="event.id"):
            gcal_normalizer.normalize_event(
                {"summary": "no id"},
                account_id="acc_1",
                session_id="sess_1",
            )

    def test_text_includes_summary_and_start(self) -> None:
        atom = gcal_normalizer.normalize_event(
            {
                "id": "evt_1",
                "summary": "Coffee",
                "start": {"date_time": "2026-06-01T09:00:00-07:00"},
            },
            account_id="acc_1",
            session_id="sess_1",
        )
        assert "Coffee" in atom["text"]
        assert "2026-06-01" in atom["text"]

    def test_session_id_encodes_provenance(self) -> None:
        atom = gcal_normalizer.normalize_event(
            {
                "id": "evt_1",
                "summary": "x",
                "start": {"date_time": "2026-06-01T09:00:00-07:00"},
            },
            account_id="acc_1",
            session_id="sess_outer",
        )
        assert "ifl_gcal" in atom["session_id"]
        assert "acc_1" in atom["session_id"]
        assert "evt_1" in atom["session_id"]

    def test_ingest_atoms_returns_one_ack_per_atom(self) -> None:
        atoms = gcal_normalizer.normalize_response(
            _fixture_payload(),
            account_id="acc_1",
            session_id="sess_1",
        )
        results = ifl_ingest.ingest_atoms(atoms)
        assert len(results) == 2
        for r in results:
            assert r.ack is True
            assert r.topic == "memory.write.v1"
            assert r.atom_id.startswith("atom-")


# ---------------------------------------------------------------------------
# Layer 3: MS-5 EXIT round-trip
# ---------------------------------------------------------------------------


class TestMS5ExitGoogleCalendarRoundTrip:
    async def test_ifl_google_calendar_events_list_round_trips_via_gateway(
        self, fixture_path: Path, tmp_path: Path
    ) -> None:
        """MS-5 EXIT criterion (Epic 5.6).

        Validates the full IFL round-trip with the *production*
        verifier (signature must match against ca_bundle):

        K1 caller → ConnectorGateway → RealMCPProcessManager
        → real fastmcp stdio subprocess (GCal fixture mode)
        → events_list tool → response normalized → P02 ingest acks.
        """
        manifest = yaml.safe_load(_GCAL_MANIFEST_PATH.read_text(encoding="utf-8"))
        # Replace the manifest's server_command so we run the GCal
        # adapter using THIS interpreter (the manifest pins
        # ``python``, which on Windows CI may resolve to a different
        # interpreter than the one running pytest).
        manifest["mcp"]["server_command"] = [
            sys.executable,
            "-m",
            "bridge.ifl.adapters.google_calendar.server",
        ]
        # Forward the fixture env var into the child process via the
        # manifest's mcp.env block (RealMCPProcessManager._build_env
        # only forwards a tiny safelist plus mcp.env entries).
        manifest["mcp"].setdefault("env", {})
        manifest["mcp"]["env"]["BRIDGE_GCAL_FIXTURE_PATH"] = os.environ["BRIDGE_GCAL_FIXTURE_PATH"]
        # We mutated the manifest after loading it from disk, so the
        # baked-in signature no longer matches. Re-sign with the dev
        # trust anchor in a tmp file so the production verifier
        # (no trust_unsigned) accepts it.
        signed_path = tmp_path / "ifl.google_calendar.events.list.v1.yaml"
        signed_path.write_text(
            yaml.safe_dump(manifest, sort_keys=False),
            encoding="utf-8",
        )
        sign_manifest(
            manifest_path=signed_path,
            priv_key_path=_DEV_PRIV,
            ca_id="dev_familyos_root_v1",
        )
        manifest = yaml.safe_load(signed_path.read_text(encoding="utf-8"))

        adapter_id = "google_calendar_acc_1"

        pm = RealMCPProcessManager(init_timeout_s=15)
        gw = ConnectorGateway(
            process_manager=pm,
            credential_vault=InMemoryCredentialVault(),
            # Production verifier: no trust_unsigned. Manifest carries a
            # real Ed25519 signature, ca_bundle.json is the dev anchor.
            adapter_verifier=CABundleAdapterVerifier(),
        )
        gw.register(adapter_id=adapter_id, manifest=manifest)
        try:
            await pm.start(adapter_id=adapter_id, manifest=manifest)
            result = await gw.invoke(
                adapter_id=adapter_id,
                tool="events_list",
                args={
                    "account_id": "acc_1",
                    "time_min": "2026-06-01T00:00:00Z",
                    "time_max": "2026-06-30T00:00:00Z",
                },
                caller=ConnectorCaller(
                    session_id="sess_exit",
                    tenant_id="tenant_exit",
                    trace_id="trace_exit",
                ),
            )
            assert result.success is True, result.error
            assert "events" in result.data
            assert len(result.data["events"]) == 2

            atoms = gcal_normalizer.normalize_response(
                result.data,
                account_id="acc_1",
                session_id="sess_exit",
            )
            acks = ifl_ingest.ingest_atoms(atoms)
            assert len(acks) == 2
            assert all(a.ack and a.topic == "memory.write.v1" for a in acks)
        finally:
            await pm.stop(adapter_id=adapter_id)
