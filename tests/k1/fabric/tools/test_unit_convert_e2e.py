"""
Integration tests for Phase 2 -- Unit Convert WASM Tool.

Tests the full unit_convert tool stack:
  - executor.execute() -- pure conversion functions for 4 categories
  - UnitConvertRuntime (IWASMRuntime protocol adapter)
  - Contract YAML parsing and validation

NO MOCKS -- all tests use real components.

References:
  - fabric_tool_implementation_plan.md Phase 2, Section 4.2
  - tests/k1/fabric/tools/test_date_calc_e2e.py (pattern)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.contracts import parse_contract
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.providers.wasm_provider import WASMSandboxConfig
from k1.fabric.types import CapabilityContract
from k1.tools.wasm_modules.unit_convert.executor import UnitConvertError, execute
from k1.tools.wasm_modules.unit_convert.runtime import UnitConvertRuntime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "k1" / "contracts" / "tools"


# =========================================================================
# Section 1: Temperature conversions
# =========================================================================


class TestTemperatureConversion:
    """Temperature conversion between celsius, fahrenheit, kelvin."""

    def test_celsius_to_fahrenheit(self) -> None:
        r = execute(
            {"category": "temperature", "from_unit": "celsius", "to_unit": "fahrenheit", "value": 0}
        )
        assert r["result"] == 32.0
        assert r["category"] == "temperature"

    def test_fahrenheit_to_celsius(self) -> None:
        r = execute(
            {
                "category": "temperature",
                "from_unit": "fahrenheit",
                "to_unit": "celsius",
                "value": 212,
            }
        )
        assert r["result"] == 100.0

    def test_celsius_to_kelvin(self) -> None:
        r = execute(
            {"category": "temperature", "from_unit": "celsius", "to_unit": "kelvin", "value": 0}
        )
        assert r["result"] == 273.15

    def test_kelvin_to_celsius(self) -> None:
        r = execute(
            {
                "category": "temperature",
                "from_unit": "kelvin",
                "to_unit": "celsius",
                "value": 373.15,
            }
        )
        assert r["result"] == 100.0

    def test_fahrenheit_to_kelvin(self) -> None:
        r = execute(
            {"category": "temperature", "from_unit": "fahrenheit", "to_unit": "kelvin", "value": 32}
        )
        assert r["result"] == 273.15

    def test_kelvin_to_fahrenheit(self) -> None:
        r = execute(
            {
                "category": "temperature",
                "from_unit": "kelvin",
                "to_unit": "fahrenheit",
                "value": 273.15,
            }
        )
        assert r["result"] == 32.0

    def test_same_unit_identity(self) -> None:
        r = execute(
            {"category": "temperature", "from_unit": "celsius", "to_unit": "celsius", "value": 42.5}
        )
        assert r["result"] == 42.5

    def test_boiling_point_roundtrip(self) -> None:
        # C -> F -> C
        r1 = execute(
            {
                "category": "temperature",
                "from_unit": "celsius",
                "to_unit": "fahrenheit",
                "value": 100,
            }
        )
        r2 = execute(
            {
                "category": "temperature",
                "from_unit": "fahrenheit",
                "to_unit": "celsius",
                "value": r1["result"],
            }
        )
        assert abs(r2["result"] - 100.0) < 0.01

    def test_negative_temperature(self) -> None:
        r = execute(
            {
                "category": "temperature",
                "from_unit": "celsius",
                "to_unit": "fahrenheit",
                "value": -40,
            }
        )
        assert r["result"] == -40.0  # -40 is the same in C and F

    def test_unknown_temperature_unit(self) -> None:
        with pytest.raises(UnitConvertError, match="Unknown temperature unit"):
            execute(
                {
                    "category": "temperature",
                    "from_unit": "rankine",
                    "to_unit": "celsius",
                    "value": 100,
                }
            )


# =========================================================================
# Section 2: Distance conversions
# =========================================================================


class TestDistanceConversion:
    """Distance conversion between km, mile, meter, foot, yard, inch."""

    def test_km_to_mile(self) -> None:
        r = execute(
            {"category": "distance", "from_unit": "kilometer", "to_unit": "mile", "value": 1}
        )
        assert abs(r["result"] - 0.621371) < 0.001

    def test_mile_to_km(self) -> None:
        r = execute(
            {"category": "distance", "from_unit": "mile", "to_unit": "kilometer", "value": 1}
        )
        assert abs(r["result"] - 1.609344) < 0.001

    def test_meter_to_foot(self) -> None:
        r = execute({"category": "distance", "from_unit": "meter", "to_unit": "foot", "value": 1})
        assert abs(r["result"] - 3.28084) < 0.001

    def test_foot_to_meter(self) -> None:
        r = execute({"category": "distance", "from_unit": "foot", "to_unit": "meter", "value": 1})
        assert abs(r["result"] - 0.3048) < 0.001

    def test_yard_to_meter(self) -> None:
        r = execute({"category": "distance", "from_unit": "yard", "to_unit": "meter", "value": 1})
        assert abs(r["result"] - 0.9144) < 0.001

    def test_inch_to_meter(self) -> None:
        r = execute({"category": "distance", "from_unit": "inch", "to_unit": "meter", "value": 1})
        assert abs(r["result"] - 0.0254) < 0.001

    def test_same_unit_identity(self) -> None:
        r = execute(
            {"category": "distance", "from_unit": "meter", "to_unit": "meter", "value": 42.0}
        )
        assert r["result"] == 42.0

    def test_zero_distance(self) -> None:
        r = execute(
            {"category": "distance", "from_unit": "kilometer", "to_unit": "mile", "value": 0}
        )
        assert r["result"] == 0.0

    def test_unknown_distance_unit(self) -> None:
        with pytest.raises(UnitConvertError, match="Unknown distance unit"):
            execute({"category": "distance", "from_unit": "league", "to_unit": "meter", "value": 1})


# =========================================================================
# Section 3: Weight conversions
# =========================================================================


class TestWeightConversion:
    """Weight conversion between kg, pound, ounce, gram, stone."""

    def test_kg_to_pound(self) -> None:
        r = execute({"category": "weight", "from_unit": "kilogram", "to_unit": "pound", "value": 1})
        assert abs(r["result"] - 2.20462) < 0.001

    def test_pound_to_kg(self) -> None:
        r = execute({"category": "weight", "from_unit": "pound", "to_unit": "kilogram", "value": 1})
        assert abs(r["result"] - 0.453592) < 0.001

    def test_ounce_to_gram(self) -> None:
        r = execute({"category": "weight", "from_unit": "ounce", "to_unit": "gram", "value": 1})
        assert abs(r["result"] - 28.3495) < 0.001

    def test_stone_to_kg(self) -> None:
        r = execute({"category": "weight", "from_unit": "stone", "to_unit": "kilogram", "value": 1})
        assert abs(r["result"] - 6.35029) < 0.001

    def test_gram_to_ounce(self) -> None:
        r = execute({"category": "weight", "from_unit": "gram", "to_unit": "ounce", "value": 100})
        assert abs(r["result"] - 3.5274) < 0.01

    def test_same_unit_identity(self) -> None:
        r = execute(
            {"category": "weight", "from_unit": "kilogram", "to_unit": "kilogram", "value": 5.5}
        )
        assert r["result"] == 5.5

    def test_unknown_weight_unit(self) -> None:
        with pytest.raises(UnitConvertError, match="Unknown weight unit"):
            execute({"category": "weight", "from_unit": "ton", "to_unit": "kilogram", "value": 1})


# =========================================================================
# Section 4: Volume conversions
# =========================================================================


class TestVolumeConversion:
    """Volume conversion between liter, gallon, milliliter, cup, pint, quart."""

    def test_liter_to_gallon(self) -> None:
        r = execute({"category": "volume", "from_unit": "liter", "to_unit": "gallon", "value": 1})
        assert abs(r["result"] - 0.264172) < 0.001

    def test_gallon_to_liter(self) -> None:
        r = execute({"category": "volume", "from_unit": "gallon", "to_unit": "liter", "value": 1})
        assert abs(r["result"] - 3.78541) < 0.001

    def test_cup_to_ml(self) -> None:
        r = execute({"category": "volume", "from_unit": "cup", "to_unit": "milliliter", "value": 1})
        assert abs(r["result"] - 236.588) < 0.01

    def test_pint_to_liter(self) -> None:
        r = execute({"category": "volume", "from_unit": "pint", "to_unit": "liter", "value": 1})
        assert abs(r["result"] - 0.473176) < 0.001

    def test_quart_to_liter(self) -> None:
        r = execute({"category": "volume", "from_unit": "quart", "to_unit": "liter", "value": 1})
        assert abs(r["result"] - 0.946353) < 0.001

    def test_ml_to_cup(self) -> None:
        r = execute(
            {"category": "volume", "from_unit": "milliliter", "to_unit": "cup", "value": 236.588}
        )
        assert abs(r["result"] - 1.0) < 0.001

    def test_same_unit_identity(self) -> None:
        r = execute({"category": "volume", "from_unit": "liter", "to_unit": "liter", "value": 2.5})
        assert r["result"] == 2.5

    def test_unknown_volume_unit(self) -> None:
        with pytest.raises(UnitConvertError, match="Unknown volume unit"):
            execute({"category": "volume", "from_unit": "barrel", "to_unit": "liter", "value": 1})


# =========================================================================
# Section 5: Error handling
# =========================================================================


class TestUnitConvertErrors:
    """Error paths for unit conversion executor."""

    def test_missing_category(self) -> None:
        with pytest.raises(UnitConvertError, match="category is required"):
            execute({"from_unit": "celsius", "to_unit": "fahrenheit", "value": 0})

    def test_missing_from_unit(self) -> None:
        with pytest.raises(UnitConvertError, match="from_unit is required"):
            execute({"category": "temperature", "to_unit": "fahrenheit", "value": 0})

    def test_missing_to_unit(self) -> None:
        with pytest.raises(UnitConvertError, match="to_unit is required"):
            execute({"category": "temperature", "from_unit": "celsius", "value": 0})

    def test_missing_value(self) -> None:
        with pytest.raises(UnitConvertError, match="value is required"):
            execute({"category": "temperature", "from_unit": "celsius", "to_unit": "fahrenheit"})

    def test_value_not_a_number(self) -> None:
        with pytest.raises(UnitConvertError, match="value must be a number"):
            execute(
                {
                    "category": "temperature",
                    "from_unit": "celsius",
                    "to_unit": "fahrenheit",
                    "value": "cold",
                }
            )

    def test_unknown_category(self) -> None:
        with pytest.raises(UnitConvertError, match="Unknown category"):
            execute({"category": "pressure", "from_unit": "psi", "to_unit": "bar", "value": 14.7})

    def test_output_has_metadata(self) -> None:
        r = execute(
            {"category": "distance", "from_unit": "kilometer", "to_unit": "mile", "value": 10}
        )
        assert r["from_unit"] == "kilometer"
        assert r["to_unit"] == "mile"
        assert r["category"] == "distance"

    def test_case_insensitive_category(self) -> None:
        r = execute(
            {
                "category": "TEMPERATURE",
                "from_unit": "celsius",
                "to_unit": "fahrenheit",
                "value": 100,
            }
        )
        assert r["result"] == 212.0

    def test_case_insensitive_units(self) -> None:
        r = execute(
            {"category": "distance", "from_unit": "Kilometer", "to_unit": "Mile", "value": 1}
        )
        assert abs(r["result"] - 0.621371) < 0.001


# =========================================================================
# Section 6: UnitConvertRuntime (IWASMRuntime protocol)
# =========================================================================


class TestUnitConvertRuntime:
    """UnitConvertRuntime adapter implementing IWASMRuntime protocol."""

    @pytest.fixture()
    def runtime(self) -> UnitConvertRuntime:
        return UnitConvertRuntime()

    @pytest.mark.asyncio
    async def test_load_module(self, runtime: UnitConvertRuntime) -> None:
        handle = await runtime.load_module("unit_convert.wasm")
        assert handle.loaded is True
        assert handle.module_id == "unit_convert-v1"
        assert "unit_convert" in handle.module_path

    @pytest.mark.asyncio
    async def test_load_module_cached(self, runtime: UnitConvertRuntime) -> None:
        h1 = await runtime.load_module("unit_convert.wasm")
        h2 = await runtime.load_module("unit_convert.wasm")
        assert h1 is h2  # same handle object

    @pytest.mark.asyncio
    async def test_load_unknown_module(self, runtime: UnitConvertRuntime) -> None:
        with pytest.raises(RuntimeError, match="Unknown WASM module"):
            await runtime.load_module("something_else.wasm")

    @pytest.mark.asyncio
    async def test_execute_success(self, runtime: UnitConvertRuntime) -> None:
        handle = await runtime.load_module("unit_convert.wasm")
        sandbox = WASMSandboxConfig()
        result = await runtime.execute(
            handle,
            "execute",
            {
                "category": "temperature",
                "from_unit": "celsius",
                "to_unit": "fahrenheit",
                "value": 100,
            },
            sandbox,
        )
        assert result.success is True
        assert result.output["result"] == 212.0
        assert result.memory_used_mb >= 0
        assert result.execution_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_error(self, runtime: UnitConvertRuntime) -> None:
        handle = await runtime.load_module("unit_convert.wasm")
        sandbox = WASMSandboxConfig()
        result = await runtime.execute(
            handle,
            "execute",
            {"category": "pressure", "from_unit": "psi", "to_unit": "bar", "value": 14.7},
            sandbox,
        )
        assert result.success is False
        assert "Unknown category" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_unloaded_handle(self, runtime: UnitConvertRuntime) -> None:
        from k1.fabric.providers.wasm_provider import WASMModuleHandle

        bad_handle = WASMModuleHandle(module_path="x", module_id="x", loaded=False)
        sandbox = WASMSandboxConfig()
        result = await runtime.execute(bad_handle, "execute", {}, sandbox)
        assert result.success is False
        assert "not loaded" in result.error_message.lower()

    def test_is_available(self, runtime: UnitConvertRuntime) -> None:
        assert runtime.is_available() is True

    def test_set_unavailable(self, runtime: UnitConvertRuntime) -> None:
        runtime.set_available(False)
        assert runtime.is_available() is False

    @pytest.mark.asyncio
    async def test_execute_distance(self, runtime: UnitConvertRuntime) -> None:
        handle = await runtime.load_module("unit_convert.wasm")
        sandbox = WASMSandboxConfig()
        result = await runtime.execute(
            handle,
            "execute",
            {"category": "distance", "from_unit": "kilometer", "to_unit": "mile", "value": 1},
            sandbox,
        )
        assert result.success is True
        assert abs(result.output["result"] - 0.621371) < 0.001

    @pytest.mark.asyncio
    async def test_execute_weight(self, runtime: UnitConvertRuntime) -> None:
        handle = await runtime.load_module("unit_convert.wasm")
        sandbox = WASMSandboxConfig()
        result = await runtime.execute(
            handle,
            "execute",
            {"category": "weight", "from_unit": "kilogram", "to_unit": "pound", "value": 1},
            sandbox,
        )
        assert result.success is True
        assert abs(result.output["result"] - 2.20462) < 0.001

    @pytest.mark.asyncio
    async def test_execute_volume(self, runtime: UnitConvertRuntime) -> None:
        handle = await runtime.load_module("unit_convert.wasm")
        sandbox = WASMSandboxConfig()
        result = await runtime.execute(
            handle,
            "execute",
            {"category": "volume", "from_unit": "liter", "to_unit": "gallon", "value": 1},
            sandbox,
        )
        assert result.success is True
        assert abs(result.output["result"] - 0.264172) < 0.001


# =========================================================================
# Section 7: Contract YAML parsing
# =========================================================================


class TestUnitConvertContract:
    """Parse and validate the unit_convert contract YAML."""

    @pytest.fixture()
    def validator(self) -> ContractValidator:
        return ContractValidator()

    def test_contract_parses(self, validator: ContractValidator) -> None:
        path = CONTRACTS_DIR / "unit_convert.yaml"
        contract = parse_contract(path, validator=validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.execute.unit_convert"
        assert contract.version == "1.0.0"

    def test_contract_is_green_band(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "unit_convert.yaml", validator=validator)
        assert contract.safety_band_min == "GREEN"

    def test_contract_provider_type_wasm(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "unit_convert.yaml", validator=validator)
        assert contract.provider_type == "WASM"
        assert contract.provider_id == "unit_convert_wasm"

    def test_contract_required_inputs(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "unit_convert.yaml", validator=validator)
        required_names = [inp.name for inp in contract.required_inputs]
        assert "category" in required_names
        assert "from_unit" in required_names
        assert "to_unit" in required_names
        assert "value" in required_names

    def test_contract_category_enum(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "unit_convert.yaml", validator=validator)
        cat_input = next(inp for inp in contract.required_inputs if inp.name == "category")
        assert cat_input.enum is not None
        assert set(cat_input.enum) == {"temperature", "distance", "weight", "volume"}

    def test_contract_output_schema(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "unit_convert.yaml", validator=validator)
        props = contract.output.get("properties", {})
        assert "result" in props
        assert "from_unit" in props
        assert "to_unit" in props
        assert "category" in props

    def test_contract_domain(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "unit_convert.yaml", validator=validator)
        assert "UTILITY" in contract.domain

    def test_contract_profile_metadata(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "unit_convert.yaml", validator=validator)
        assert contract.activity_profile == "wasm.generic.v1"
        assert contract.prompt_template == "wasm_generic_activity_v1"
        assert contract.tool_instructions is not None
