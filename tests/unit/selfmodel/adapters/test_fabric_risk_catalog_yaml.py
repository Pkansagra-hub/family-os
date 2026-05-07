"""M12.E2.I4 — every YAML contract under ``k1/contracts/tools/`` resolves to
its declared ``risk_class`` (no fallback to ``FAIL_CLOSED_DEFAULT``).

This locks in the M12.E2.I0 parser fix + M12.E2.I2 YAML annotations so a
future contract added without ``risk_class:`` is caught loudly instead of
silently falling through to the (now ``LOW``) default.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from k1.fabric.contracts.tool_contract import ToolContractParser
from k1.selfmodel.contracts.policy import RiskClass

CONTRACTS_DIR = Path("k1/contracts/tools")

_VALID_RISK_STRINGS = {"low", "medium", "high", "safety_sensitive"}


def _yaml_files() -> list[Path]:
    if not CONTRACTS_DIR.is_dir():  # pragma: no cover - environment guard
        pytest.skip(f"{CONTRACTS_DIR} not present")
    return sorted(p for p in CONTRACTS_DIR.glob("*.yaml") if p.is_file())


@pytest.mark.parametrize("yaml_path", _yaml_files(), ids=lambda p: p.name)
def test_contract_yaml_declares_risk_class(yaml_path: Path) -> None:
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict), f"{yaml_path.name}: top-level must be a mapping"
    body = raw.get("tool_contract", raw)
    risk_class = body.get("risk_class")
    assert risk_class is not None, (
        f"{yaml_path.name}: missing required 'risk_class' field "
        "(M12.E2.I2 — every contract YAML must declare its risk class)"
    )
    assert (
        risk_class in _VALID_RISK_STRINGS
    ), f"{yaml_path.name}: risk_class={risk_class!r} not one of {_VALID_RISK_STRINGS}"


@pytest.mark.parametrize("yaml_path", _yaml_files(), ids=lambda p: p.name)
def test_parser_propagates_risk_class(yaml_path: Path) -> None:
    """M12.E2.I0 — ToolContractParser must propagate risk_class into the
    constructed CapabilityContract."""
    parser = ToolContractParser()
    contract = parser.parse(yaml_path)
    body = yaml.safe_load(yaml_path.read_text(encoding="utf-8")).get("tool_contract", {})
    declared = body.get("risk_class")
    assert contract.risk_class == declared, (
        f"{yaml_path.name}: parsed risk_class={contract.risk_class!r}, "
        f"YAML declares {declared!r}"
    )


def test_fail_closed_default_is_low() -> None:
    """M12.E2.I1 — fail-open default is LOW; conscience risk_overrides
    + Fabric-level conscience gate are the escalation mechanism."""
    from k1.selfmodel.contracts.risk_class_registry import FAIL_CLOSED_DEFAULT

    assert FAIL_CLOSED_DEFAULT == RiskClass.LOW
