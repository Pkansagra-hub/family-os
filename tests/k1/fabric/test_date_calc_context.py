"""M1-E10 coverage for date_calc temporal context injection."""

from __future__ import annotations

from pathlib import Path

from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.contracts import parse_contract
from k1.fabric.core.context_builder import ContextBuilder
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.types import CapabilityContract

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "k1" / "contracts" / "tools"
SESSION_ID = "sess-date-calc-temporal"

TEMPORAL_SECTION = {
    "anchor": {
        "anchor_id": "anchor-date-calc",
        "now_utc": "2026-05-18T15:00:00+00:00",
        "timezone": "America/Chicago",
        "local_date": "2026-05-18",
        "local_time": "10:00:00",
        "weekday": "Monday",
        "is_weekend": False,
    },
    "windows": {
        "today": {
            "window_id": "today",
            "start_utc": "2026-05-18T05:00:00+00:00",
            "end_utc": "2026-05-19T05:00:00+00:00",
        }
    },
}


def _load_date_calc_contract() -> CapabilityContract:
    contract = parse_contract(CONTRACTS_DIR / "date_calc.yaml", validator=ContractValidator())
    assert isinstance(contract, CapabilityContract)
    return contract


def test_date_calc_contract_requires_temporal_context() -> None:
    contract = _load_date_calc_contract()

    assert contract.required_context == ["temporal"]


def test_date_calc_context_builder_injects_temporal_section() -> None:
    reader = TestSessionStateReaderAdapter()
    reader.load(SESSION_ID, "temporal", TEMPORAL_SECTION)

    result = ContextBuilder(state_reader=reader).build(
        contract=_load_date_calc_contract(),
        params={"operation": "weekday", "date": "2026-05-18"},
        session_id=SESSION_ID,
        trace_id="tr-date-calc",
    )

    assert result.missing_required == []
    assert result.context.session_sections["temporal"] == TEMPORAL_SECTION
    assert result.context.params["operation"] == "weekday"
