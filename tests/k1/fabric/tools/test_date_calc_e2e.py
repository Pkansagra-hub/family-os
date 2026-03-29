"""
Integration tests for Phase 1 -- date_calc WASM tool.

Tests the full date_calc tool stack:
  - Pure executor functions (days_between, add_days, weekday, is_weekend)
  - DateCalcRuntime (IWASMRuntime protocol compliance)
  - Contract YAML parsing and validation
  - Error paths (invalid date, unknown operation, missing params)

NO MOCKS -- uses real executor and runtime with real computation.

References:
  - fabric_tool_implementation_plan.md Phase 1, Section 3.2
  - tests/k1/fabric/test_providers_333_334.py (WASM test patterns)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.contracts import parse_contract
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.providers.wasm_provider import (
    WASMExecutionResult,
    WASMModuleHandle,
    WASMSandboxConfig,
)
from k1.fabric.types import CapabilityContract
from k1.tools.wasm_modules.date_calc.executor import DateCalcError, execute
from k1.tools.wasm_modules.date_calc.runtime import DateCalcRuntime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "k1" / "contracts" / "tools"

# Default sandbox config for runtime tests
_SANDBOX = WASMSandboxConfig(memory_limit_mb=64, timeout_ms=5000)


# =========================================================================
# Section 1: Pure executor -- days_between
# =========================================================================


class TestDaysBetween:
    """executor.execute() with operation=days_between."""

    def test_same_date(self) -> None:
        result = execute({"operation": "days_between", "date": "2025-03-15", "date2": "2025-03-15"})
        assert result["result"] == 0
        assert result["operation"] == "days_between"
        assert result["input_date"] == "2025-03-15"

    def test_positive_difference(self) -> None:
        result = execute({"operation": "days_between", "date": "2025-03-01", "date2": "2025-03-31"})
        assert result["result"] == 30

    def test_negative_difference(self) -> None:
        result = execute({"operation": "days_between", "date": "2025-03-31", "date2": "2025-03-01"})
        assert result["result"] == -30

    def test_cross_year_boundary(self) -> None:
        result = execute({"operation": "days_between", "date": "2024-12-31", "date2": "2025-01-01"})
        assert result["result"] == 1

    def test_missing_date2(self) -> None:
        with pytest.raises(DateCalcError, match="date2"):
            execute({"operation": "days_between", "date": "2025-03-15"})

    def test_invalid_date2(self) -> None:
        with pytest.raises(DateCalcError, match="date2"):
            execute({"operation": "days_between", "date": "2025-03-15", "date2": "not-a-date"})


# =========================================================================
# Section 2: Pure executor -- add_days
# =========================================================================


class TestAddDays:
    """executor.execute() with operation=add_days."""

    def test_add_positive(self) -> None:
        result = execute({"operation": "add_days", "date": "2025-03-15", "days": 10})
        assert result["result"] == "2025-03-25"

    def test_add_zero(self) -> None:
        result = execute({"operation": "add_days", "date": "2025-03-15", "days": 0})
        assert result["result"] == "2025-03-15"

    def test_add_negative(self) -> None:
        result = execute({"operation": "add_days", "date": "2025-03-15", "days": -15})
        assert result["result"] == "2025-02-28"

    def test_cross_month_boundary(self) -> None:
        result = execute({"operation": "add_days", "date": "2025-01-30", "days": 5})
        assert result["result"] == "2025-02-04"

    def test_leap_year_feb_29(self) -> None:
        result = execute({"operation": "add_days", "date": "2024-02-28", "days": 1})
        assert result["result"] == "2024-02-29"  # 2024 is a leap year

    def test_default_days_is_zero(self) -> None:
        result = execute({"operation": "add_days", "date": "2025-03-15"})
        assert result["result"] == "2025-03-15"

    def test_invalid_days_type(self) -> None:
        with pytest.raises(DateCalcError, match="days"):
            execute({"operation": "add_days", "date": "2025-03-15", "days": "ten"})


# =========================================================================
# Section 3: Pure executor -- weekday
# =========================================================================


class TestWeekday:
    """executor.execute() with operation=weekday."""

    def test_monday(self) -> None:
        # 2025-03-10 is a Monday
        result = execute({"operation": "weekday", "date": "2025-03-10"})
        assert result["result"] == "Monday"

    def test_saturday(self) -> None:
        # 2025-03-15 is a Saturday
        result = execute({"operation": "weekday", "date": "2025-03-15"})
        assert result["result"] == "Saturday"

    def test_sunday(self) -> None:
        # 2025-03-16 is a Sunday
        result = execute({"operation": "weekday", "date": "2025-03-16"})
        assert result["result"] == "Sunday"


# =========================================================================
# Section 4: Pure executor -- is_weekend
# =========================================================================


class TestIsWeekend:
    """executor.execute() with operation=is_weekend."""

    def test_weekday_is_not_weekend(self) -> None:
        result = execute({"operation": "is_weekend", "date": "2025-03-10"})  # Monday
        assert result["result"] is False

    def test_saturday_is_weekend(self) -> None:
        result = execute({"operation": "is_weekend", "date": "2025-03-15"})
        assert result["result"] is True

    def test_sunday_is_weekend(self) -> None:
        result = execute({"operation": "is_weekend", "date": "2025-03-16"})
        assert result["result"] is True

    def test_friday_is_not_weekend(self) -> None:
        result = execute({"operation": "is_weekend", "date": "2025-03-14"})  # Friday
        assert result["result"] is False


# =========================================================================
# Section 5: Pure executor -- error paths
# =========================================================================


class TestExecutorErrors:
    """Global error handling in executor.execute()."""

    def test_missing_operation(self) -> None:
        with pytest.raises(DateCalcError, match="operation"):
            execute({"date": "2025-03-15"})

    def test_missing_date(self) -> None:
        with pytest.raises(DateCalcError, match="date"):
            execute({"operation": "weekday"})

    def test_invalid_date_format(self) -> None:
        with pytest.raises(DateCalcError, match="Invalid date"):
            execute({"operation": "weekday", "date": "not-a-date"})

    def test_unknown_operation(self) -> None:
        with pytest.raises(DateCalcError, match="Unknown operation"):
            execute({"operation": "moon_phase", "date": "2025-03-15"})

    def test_empty_operation(self) -> None:
        with pytest.raises(DateCalcError, match="operation"):
            execute({"operation": "", "date": "2025-03-15"})

    def test_empty_date(self) -> None:
        with pytest.raises(DateCalcError, match="date"):
            execute({"operation": "weekday", "date": ""})


# =========================================================================
# Section 6: DateCalcRuntime (IWASMRuntime protocol)
# =========================================================================


class TestDateCalcRuntime:
    """DateCalcRuntime IWASMRuntime protocol compliance."""

    @pytest.fixture()
    def runtime(self) -> DateCalcRuntime:
        return DateCalcRuntime()

    # -- load_module -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_load_module_success(self, runtime: DateCalcRuntime) -> None:
        handle = await runtime.load_module("wasm/date_calc.wasm")
        assert isinstance(handle, WASMModuleHandle)
        assert handle.loaded is True
        assert handle.module_id == "date_calc-v1"

    @pytest.mark.asyncio
    async def test_load_module_caches(self, runtime: DateCalcRuntime) -> None:
        h1 = await runtime.load_module("wasm/date_calc.wasm")
        h2 = await runtime.load_module("wasm/date_calc.wasm")
        assert h1 is h2  # Same object (cached)

    @pytest.mark.asyncio
    async def test_load_module_unknown(self, runtime: DateCalcRuntime) -> None:
        with pytest.raises(RuntimeError, match="Unknown WASM module"):
            await runtime.load_module("wasm/unknown.wasm")

    # -- execute -----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_execute_days_between(self, runtime: DateCalcRuntime) -> None:
        handle = await runtime.load_module("wasm/date_calc.wasm")
        result = await runtime.execute(
            handle,
            "execute",
            {"operation": "days_between", "date": "2025-01-01", "date2": "2025-01-31"},
            _SANDBOX,
        )
        assert isinstance(result, WASMExecutionResult)
        assert result.success is True
        assert result.output["result"] == 30
        assert result.memory_used_mb >= 0
        assert result.execution_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_add_days(self, runtime: DateCalcRuntime) -> None:
        handle = await runtime.load_module("wasm/date_calc.wasm")
        result = await runtime.execute(
            handle, "execute", {"operation": "add_days", "date": "2025-03-15", "days": 7}, _SANDBOX
        )
        assert result.success is True
        assert result.output["result"] == "2025-03-22"

    @pytest.mark.asyncio
    async def test_execute_weekday(self, runtime: DateCalcRuntime) -> None:
        handle = await runtime.load_module("wasm/date_calc.wasm")
        result = await runtime.execute(
            handle, "execute", {"operation": "weekday", "date": "2025-03-15"}, _SANDBOX
        )
        assert result.success is True
        assert result.output["result"] == "Saturday"

    @pytest.mark.asyncio
    async def test_execute_is_weekend(self, runtime: DateCalcRuntime) -> None:
        handle = await runtime.load_module("wasm/date_calc.wasm")
        result = await runtime.execute(
            handle, "execute", {"operation": "is_weekend", "date": "2025-03-15"}, _SANDBOX
        )
        assert result.success is True
        assert result.output["result"] is True

    @pytest.mark.asyncio
    async def test_execute_error_returns_failed_result(self, runtime: DateCalcRuntime) -> None:
        handle = await runtime.load_module("wasm/date_calc.wasm")
        result = await runtime.execute(
            handle, "execute", {"operation": "weekday", "date": "bad-date"}, _SANDBOX
        )
        assert result.success is False
        assert "Invalid date" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_unloaded_handle(self, runtime: DateCalcRuntime) -> None:
        unloaded = WASMModuleHandle(module_path="x", module_id="x", loaded=False)
        result = await runtime.execute(
            unloaded, "execute", {"operation": "weekday", "date": "2025-03-15"}, _SANDBOX
        )
        assert result.success is False
        assert "not loaded" in result.error_message.lower()

    # -- is_available ------------------------------------------------------

    def test_is_available_default(self, runtime: DateCalcRuntime) -> None:
        assert runtime.is_available() is True

    def test_set_unavailable(self, runtime: DateCalcRuntime) -> None:
        runtime.set_available(False)
        assert runtime.is_available() is False

    def test_restore_availability(self, runtime: DateCalcRuntime) -> None:
        runtime.set_available(False)
        runtime.set_available(True)
        assert runtime.is_available() is True


# =========================================================================
# Section 7: Contract YAML parsing
# =========================================================================


class TestDateCalcContract:
    """Parse and validate the date_calc contract YAML."""

    @pytest.fixture()
    def validator(self) -> ContractValidator:
        return ContractValidator()

    def test_contract_parses(self, validator: ContractValidator) -> None:
        path = CONTRACTS_DIR / "date_calc.yaml"
        contract = parse_contract(path, validator=validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.execute.date_calc"
        assert contract.version == "1.0.0"

    def test_contract_is_green_band(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "date_calc.yaml", validator=validator)
        assert contract.safety_band_min == "GREEN"

    def test_contract_provider_type_wasm(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "date_calc.yaml", validator=validator)
        assert contract.provider_type == "WASM"
        assert contract.provider_id == "date_calc_wasm"

    def test_contract_required_inputs(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "date_calc.yaml", validator=validator)
        required_names = [inp.name for inp in contract.required_inputs]
        assert "operation" in required_names
        assert "date" in required_names

    def test_contract_operation_enum(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "date_calc.yaml", validator=validator)
        op_input = next(inp for inp in contract.required_inputs if inp.name == "operation")
        assert op_input.enum is not None
        assert set(op_input.enum) == {"days_between", "add_days", "weekday", "is_weekend"}

    def test_contract_output_schema(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "date_calc.yaml", validator=validator)
        assert "result" in contract.output.get("properties", {})
        assert "operation" in contract.output.get("properties", {})
        assert "input_date" in contract.output.get("properties", {})

    def test_contract_domain(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "date_calc.yaml", validator=validator)
        assert "UTILITY" in contract.domain
