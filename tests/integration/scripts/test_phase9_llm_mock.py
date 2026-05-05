"""CI lockdown: replay the M11 phase-9 probe in mock-LLM mode (M11.E1.I2).

Asserts the four scripted prompts each yield ``PASS`` against the
golden transcript, so any regression in:

* selfmodel composer / capsule renderer (grounding),
* ``ConscienceDigest`` semantics (forbidden / must_ask),
* default-ALLOW paradigm (anything not enumerated),

is caught at unit-test speed without an LLM in the loop.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.kernel_probe_phase9_v2 import (
    DEFAULT_SEED,
    GOLDEN_PATH,
    MockLLM,
    run_probe,
)

pytestmark = pytest.mark.anyio


def test_phase9_mock_replay_all_pass() -> None:
    assert GOLDEN_PATH.exists(), f"missing golden transcript at {GOLDEN_PATH}"
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    report = run_probe(seed_path=DEFAULT_SEED, llm_factory=lambda: MockLLM(golden))

    assert report["summary"]["failed"] == 0, report
    assert report["summary"]["passed"] == 4

    by_name = {r["name"]: r for r in report["records"]}
    assert by_name["grounding"]["passed"]
    assert by_name["must_ask"]["observed"]["decision"] == "REQUIRE_CONFIRMATION"
    assert by_name["forbidden"]["observed"]["decision"] == "DENY"
    assert by_name["forbidden"]["observed"]["reason"] == "capability_not_granted"
    assert by_name["default_allow"]["observed"]["decision"] == "ALLOW"


def test_phase9_mock_writes_report(tmp_path: Path) -> None:
    """End-to-end via main(): verifies CLI wiring + JSON shape."""
    from scripts.kernel_probe_phase9_v2 import main

    out = tmp_path / "report.json"
    rc = main(["--mode", "mock", "--out", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["summary"]["passed"] == 4
    assert len(payload["records"]) == 4
