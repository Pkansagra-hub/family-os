"""MS-2.5 Epic 2.5.1 — meta-schema unit tests.

Validates the shape of `bridge/contracts/_meta/manifest.schema.json` and the
`ca_bundle.json` placeholder. Pure offline tests; only filesystem reads, no
network, no time, no randomness — no-mock policy compliant.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
META_DIR = REPO_ROOT / "bridge" / "contracts" / "_meta"
MANIFEST_SCHEMA_PATH = META_DIR / "manifest.schema.json"
CA_BUNDLE_SCHEMA_PATH = META_DIR / "ca_bundle.schema.json"
CA_BUNDLE_PATH = META_DIR / "ca_bundle.json"


@pytest.fixture(scope="module")
def manifest_schema() -> dict:
    return json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ca_bundle_schema() -> dict:
    return json.loads(CA_BUNDLE_SCHEMA_PATH.read_text(encoding="utf-8"))


def _valid_manifest() -> dict:
    """Minimal-valid k1_to_k0 manifest — no sync, no signing required."""
    return {
        "topic": "memory.write.v1",
        "direction": "k1_to_k0",
        "owner_team": "k0",
        "producer": {"kernel": "k1"},
        "consumer": {"kernel": "k0"},
        "schema": "schemas/memory.write.v1.json",
        "delivery": {
            "transport": "http",
            "ordering": "best_effort",
            "ack_required": True,
            "online_required": False,
            "endpoint_class": "cloud_k0",
            "partition_mode": "k0_primary",
        },
        "semantics": {
            "idempotent": True,
            "duplicate_strategy": "dedupe_by_envelope_id",
            "retention": "P30D",
            "description": (
                "Persist a memory atom into K0 episodic storage via the " "P02 ingest pipeline."
            ),
        },
        "sla": {"latency_p99_ms": 250, "throughput_per_sec": 50},
        "versioning": {"semver": "1.0.0", "compat": "compatible"},
        "status": "active",
    }


# ---------------------------------------------------------------------------
# Test 1: meta-schema is itself a valid JSON Schema 2020-12 document.
# ---------------------------------------------------------------------------
def test_meta_schema_is_valid_2020_12(manifest_schema: dict) -> None:
    Draft202012Validator.check_schema(manifest_schema)
    assert manifest_schema["$schema"] == ("https://json-schema.org/draft/2020-12/schema")


# ---------------------------------------------------------------------------
# Test 2: additionalProperties: false at top level (no rogue fields).
# ---------------------------------------------------------------------------
def test_meta_schema_rejects_unknown_top_level_fields(
    manifest_schema: dict,
) -> None:
    assert manifest_schema.get("additionalProperties") is False
    bad = _valid_manifest()
    bad["bogus_field"] = "nope"
    errors = list(Draft202012Validator(manifest_schema).iter_errors(bad))
    assert errors, "Unknown top-level field must produce a validation error"


# ---------------------------------------------------------------------------
# Test 3: topic regex enforces dotted-name + version suffix (4 cases).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("topic", "ok"),
    [
        ("memory.write.v1", True),
        ("family.tool_state.delta.v12", True),
        ("MemoryWrite.v1", False),  # uppercase rejected
        ("memory.write", False),  # missing version suffix
    ],
)
def test_topic_regex(manifest_schema: dict, topic: str, ok: bool) -> None:
    pattern = manifest_schema["properties"]["topic"]["pattern"]
    matched = re.match(pattern, topic) is not None
    assert matched is ok, f"topic={topic!r} expected match={ok}, got {matched}"

    candidate = _valid_manifest()
    candidate["topic"] = topic
    errors = list(Draft202012Validator(manifest_schema).iter_errors(candidate))
    if ok:
        assert errors == [], (
            f"valid topic {topic!r} produced errors: " f"{[e.message for e in errors]}"
        )
    else:
        assert errors, f"invalid topic {topic!r} should fail validation"


# ---------------------------------------------------------------------------
# Test 4: semantics.description minLength: 40 enforces R6.
# ---------------------------------------------------------------------------
def test_description_min_length_enforces_r6(manifest_schema: dict) -> None:
    desc_schema = manifest_schema["properties"]["semantics"]["properties"]["description"]
    assert desc_schema["minLength"] == 40

    candidate = _valid_manifest()
    candidate["semantics"]["description"] = "too short"
    errors = list(Draft202012Validator(manifest_schema).iter_errors(candidate))
    assert any(
        "too short" in e.message.lower() or "minlength" in e.message.lower() for e in errors
    ), (
        "Short description must trigger minLength violation; got: " f"{[e.message for e in errors]}"
    )


# ---------------------------------------------------------------------------
# Test 5: allOf — sync block REQUIRED when direction in {k0_to_k0, k1_to_k1}.
# ---------------------------------------------------------------------------
def test_sync_required_for_intra_kernel_direction(
    manifest_schema: dict,
) -> None:
    candidate = _valid_manifest()
    candidate["direction"] = "k0_to_k0"
    candidate["producer"]["kernel"] = "k0"
    candidate["consumer"]["kernel"] = "k0"
    # No `sync` block.
    errors = list(Draft202012Validator(manifest_schema).iter_errors(candidate))
    assert errors, "k0_to_k0 without sync must fail validation"

    candidate["sync"] = {"layer": "l1_family_memory"}
    errors = list(Draft202012Validator(manifest_schema).iter_errors(candidate))
    assert errors == [], (
        f"k0_to_k0 with valid sync block should pass; got: " f"{[e.message for e in errors]}"
    )


# ---------------------------------------------------------------------------
# Test 6: allOf — sync.tool_class REQUIRED when sync.layer == l2_*.
# ---------------------------------------------------------------------------
def test_tool_class_required_for_l2_family_tool_state(
    manifest_schema: dict,
) -> None:
    candidate = _valid_manifest()
    candidate["direction"] = "k0_to_k0"
    candidate["sync"] = {"layer": "l2_family_tool_state"}
    errors = list(Draft202012Validator(manifest_schema).iter_errors(candidate))
    assert errors, "l2 layer without tool_class must fail"

    candidate["sync"]["tool_class"] = "shared_family"
    errors = list(Draft202012Validator(manifest_schema).iter_errors(candidate))
    assert errors == [], f"l2 + tool_class should pass; got: " f"{[e.message for e in errors]}"


# ---------------------------------------------------------------------------
# Test 7: allOf — signing block REQUIRED when direction is device_*.
# ---------------------------------------------------------------------------
def test_signing_required_for_device_directions(
    manifest_schema: dict,
) -> None:
    candidate = _valid_manifest()
    candidate["direction"] = "device_to_k0"
    candidate["producer"]["kernel"] = "device"
    errors = list(Draft202012Validator(manifest_schema).iter_errors(candidate))
    assert errors, "device_to_k0 without signing must fail"

    candidate["signing"] = {
        "algorithm": "ed25519",
        "key_source": "device_provisioning_ledger",
    }
    errors = list(Draft202012Validator(manifest_schema).iter_errors(candidate))
    assert errors == [], (
        f"device_to_k0 + signing should pass; got: " f"{[e.message for e in errors]}"
    )


# ---------------------------------------------------------------------------
# Test 8: ca_bundle.json placeholder validates against ca_bundle.schema.json.
# ---------------------------------------------------------------------------
def test_ca_bundle_placeholder_validates(ca_bundle_schema: dict) -> None:
    Draft202012Validator.check_schema(ca_bundle_schema)
    bundle = json.loads(CA_BUNDLE_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(ca_bundle_schema).iter_errors(bundle))
    assert errors == [], (
        f"ca_bundle.json must validate against its schema; got: " f"{[e.message for e in errors]}"
    )
    # As of MS-5 PR#3 the bundle ships a real dev keypair
    # (``dev_familyos_root_v1``). Production ceremony will replace
    # this with ``familyos_root_v1`` + a hardware-issued key.
    assert bundle["ca_id"] in {"dev_familyos_root_v1", "familyos_root_v1"}
    assert bundle["status"] == "active"
    # Placeholder marker MUST be gone post-PR#3.
    assert "PLACEHOLDER" not in bundle["ed25519_public_key"]
