"""Tests for the IFL manifest schema additions (MS-5 PR#1)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from tooling.contracts.manifest_loader import (
    ManifestValidationError,
    load_manifests,
    load_meta_schema,
)

CONTRACTS_ROOT = Path("bridge/contracts").resolve()
GCAL_PATH = CONTRACTS_ROOT / "manifests" / "ifl.google_calendar.events.list.v1.yaml"


def _gcal_manifest() -> dict:
    return yaml.safe_load(GCAL_PATH.read_text(encoding="utf-8"))


def _validator() -> Draft202012Validator:
    return Draft202012Validator(load_meta_schema(CONTRACTS_ROOT))


# ---------------------------------------------------------------------------
# Whole-bundle parse
# ---------------------------------------------------------------------------


def test_loader_parses_ifl_google_calendar_manifest() -> None:
    manifests = load_manifests(CONTRACTS_ROOT)
    topics = {m.topic for m in manifests}
    assert "ifl.google_calendar.events.list.v1" in topics
    gcal = next(m for m in manifests if m.topic == "ifl.google_calendar.events.list.v1")
    assert gcal.direction == "k0_to_device"
    assert gcal.status == "proposed"
    assert gcal.raw["delivery"]["transport"] == "mcp_stdio"
    assert gcal.raw["mcp"]["sandbox"]["memory_max"] == "256M"


# ---------------------------------------------------------------------------
# Schema-level rules
# ---------------------------------------------------------------------------


def test_mcp_stdio_transport_requires_mcp_block() -> None:
    raw = _gcal_manifest()
    raw.pop("mcp")
    errors = list(_validator().iter_errors(raw))
    msgs = [e.message for e in errors]
    assert any("'mcp'" in m and "required" in m for m in msgs), msgs


def test_mcp_stdio_transport_requires_signing_block() -> None:
    raw = _gcal_manifest()
    raw.pop("signing")
    errors = list(_validator().iter_errors(raw))
    msgs = [e.message for e in errors]
    assert any("'signing'" in m and "required" in m for m in msgs), msgs


def test_mcp_sandbox_memory_max_pattern_enforced() -> None:
    raw = _gcal_manifest()
    raw["mcp"]["sandbox"]["memory_max"] = "256MB"  # must be ^[0-9]+[KMG]$
    errors = list(_validator().iter_errors(raw))
    assert any("memory_max" in str(e.path) or "256MB" in e.message for e in errors)


def test_mcp_health_ping_interval_bounds() -> None:
    raw = _gcal_manifest()
    raw["mcp"]["health"]["ping_interval_s"] = 0
    errors = list(_validator().iter_errors(raw))
    assert errors

    raw = _gcal_manifest()
    raw["mcp"]["health"]["ping_interval_s"] = 120
    errors = list(_validator().iter_errors(raw))
    assert errors


def test_mcp_sandbox_network_enum() -> None:
    raw = _gcal_manifest()
    raw["mcp"]["sandbox"]["network"] = "wide_open"
    errors = list(_validator().iter_errors(raw))
    assert errors


def test_reserved_rate_limit_field_is_accepted() -> None:
    raw = _gcal_manifest()
    raw["rate_limit"] = {"requests_per_minute": 60, "burst": 10}
    errors = list(_validator().iter_errors(raw))
    assert not errors, [e.message for e in errors]


def test_reserved_circuit_breaker_field_is_accepted() -> None:
    raw = _gcal_manifest()
    raw["circuit_breaker"] = {
        "failure_threshold": 5,
        "timeout_s": 30,
        "half_open_probes": 1,
    }
    errors = list(_validator().iter_errors(raw))
    assert not errors, [e.message for e in errors]


def test_signing_signature_field_now_allowed() -> None:
    raw = _gcal_manifest()
    raw["signing"]["signature"] = "abc"
    errors = list(_validator().iter_errors(raw))
    assert not errors, [e.message for e in errors]


def test_signing_payload_sha256_pattern() -> None:
    raw = _gcal_manifest()
    raw["signing"]["payload_sha256"] = "not-hex"
    errors = list(_validator().iter_errors(raw))
    assert errors


# ---------------------------------------------------------------------------
# JSON Schema files for the GCal contract exist and parse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    [
        "ifl.google_calendar.events.list.v1.request.json",
        "ifl.google_calendar.events.list.v1.response.json",
    ],
)
def test_ifl_schema_files_parse(filename: str) -> None:
    path = CONTRACTS_ROOT / "schemas" / filename
    assert path.exists(), f"missing schema file: {filename}"
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed["$schema"].startswith("https://json-schema.org/")
    Draft202012Validator.check_schema(parsed)


# ---------------------------------------------------------------------------
# Whole-bundle smoke: dropping mcp from the GCal manifest fails the loader
# ---------------------------------------------------------------------------


def test_loader_rejects_mcp_stdio_without_mcp_block(tmp_path: Path) -> None:
    """If we copy the manifests dir but break the GCal manifest, load fails."""

    src_root = CONTRACTS_ROOT
    dst_root = tmp_path / "contracts"
    (dst_root / "manifests").mkdir(parents=True)
    (dst_root / "schemas").mkdir()
    (dst_root / "_meta").mkdir()
    (dst_root / "_meta" / "manifest.schema.json").write_bytes(
        (src_root / "_meta" / "manifest.schema.json").read_bytes()
    )
    # Copy only the GCal manifest + its schemas (loader only checks YAMLs).
    raw = _gcal_manifest()
    broken = deepcopy(raw)
    broken.pop("mcp")
    (dst_root / "manifests" / "ifl.google_calendar.events.list.v1.yaml").write_text(
        yaml.safe_dump(broken, sort_keys=False), encoding="utf-8"
    )
    (dst_root / "schemas" / "ifl.google_calendar.events.list.v1.request.json").write_bytes(
        (src_root / "schemas" / "ifl.google_calendar.events.list.v1.request.json").read_bytes()
    )

    with pytest.raises(ManifestValidationError):
        load_manifests(dst_root)
