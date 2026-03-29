"""
k1.tools.wasm_modules.unit_convert.executor -- Unit conversion computation.

Pure function implementations for the unit_convert WASM tool.
No I/O, no state, no side effects. These functions represent the
logic that would execute inside a WASM sandbox.

Supported categories:
  - temperature: celsius, fahrenheit, kelvin
  - distance: kilometer, mile, meter, foot, yard, inch
  - weight: kilogram, pound, ounce, gram, stone
  - volume: liter, gallon, milliliter, cup, pint, quart

Errors:
  - UnitConvertError for unsupported category/unit combinations
  - All errors are deterministic and reproducible

References:
  - unit_convert.yaml contract
"""

from __future__ import annotations

from typing import Any, Dict

# ---------------------------------------------------------------------------
# Conversion tables (value in base unit per 1 source unit)
#   temperature is special -- handled separately
#   distance base = meter
#   weight base = gram
#   volume base = milliliter
# ---------------------------------------------------------------------------

_DISTANCE: Dict[str, float] = {
    "kilometer": 1000.0,
    "mile": 1609.344,
    "meter": 1.0,
    "foot": 0.3048,
    "yard": 0.9144,
    "inch": 0.0254,
}

_WEIGHT: Dict[str, float] = {
    "kilogram": 1000.0,
    "pound": 453.592,
    "ounce": 28.3495,
    "gram": 1.0,
    "stone": 6350.29,
}

_VOLUME: Dict[str, float] = {
    "liter": 1000.0,
    "gallon": 3785.41,
    "milliliter": 1.0,
    "cup": 236.588,
    "pint": 473.176,
    "quart": 946.353,
}

_TABLES: Dict[str, Dict[str, float]] = {
    "distance": _DISTANCE,
    "weight": _WEIGHT,
    "volume": _VOLUME,
}

_VALID_CATEGORIES = {"temperature", "distance", "weight", "volume"}


class UnitConvertError(Exception):
    """Error during unit conversion."""


def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main dispatch: perform unit conversion.

    Args:
        params: Must contain 'category', 'from_unit', 'to_unit', 'value'.

    Returns:
        Dict with 'result', 'from_unit', 'to_unit', 'category' keys.

    Raises:
        UnitConvertError: On invalid input or unsupported conversion.
    """
    category = params.get("category", "")
    from_unit = params.get("from_unit", "")
    to_unit = params.get("to_unit", "")
    value = params.get("value")

    if not category:
        raise UnitConvertError("category is required")
    if not from_unit:
        raise UnitConvertError("from_unit is required")
    if not to_unit:
        raise UnitConvertError("to_unit is required")
    if value is None:
        raise UnitConvertError("value is required")

    if not isinstance(value, (int, float)):
        raise UnitConvertError(f"value must be a number, got {type(value).__name__}")

    category = category.lower()
    from_unit = from_unit.lower()
    to_unit = to_unit.lower()

    if category not in _VALID_CATEGORIES:
        raise UnitConvertError(
            f"Unknown category '{category}'. " f"Expected: {', '.join(sorted(_VALID_CATEGORIES))}"
        )

    if category == "temperature":
        result = _convert_temperature(float(value), from_unit, to_unit)
    else:
        result = _convert_linear(float(value), from_unit, to_unit, category)

    return {
        "result": result,
        "from_unit": from_unit,
        "to_unit": to_unit,
        "category": category,
    }


# ---------------------------------------------------------------------------
# Temperature conversion (non-linear)
# ---------------------------------------------------------------------------


def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """Convert between celsius, fahrenheit, kelvin."""
    valid = {"celsius", "fahrenheit", "kelvin"}
    if from_unit not in valid:
        raise UnitConvertError(
            f"Unknown temperature unit '{from_unit}'. Expected: {', '.join(sorted(valid))}"
        )
    if to_unit not in valid:
        raise UnitConvertError(
            f"Unknown temperature unit '{to_unit}'. Expected: {', '.join(sorted(valid))}"
        )

    if from_unit == to_unit:
        return round(value, 4)

    # Convert to Celsius first
    celsius = _to_celsius(value, from_unit)
    # Then convert from Celsius to target
    return _from_celsius(celsius, to_unit)


def _to_celsius(value: float, unit: str) -> float:
    if unit == "celsius":
        return value
    if unit == "fahrenheit":
        return (value - 32.0) * 5.0 / 9.0
    if unit == "kelvin":
        return value - 273.15
    raise UnitConvertError(f"Cannot convert from {unit} to celsius")


def _from_celsius(celsius: float, unit: str) -> float:
    if unit == "celsius":
        return round(celsius, 4)
    if unit == "fahrenheit":
        return round(celsius * 9.0 / 5.0 + 32.0, 4)
    if unit == "kelvin":
        return round(celsius + 273.15, 4)
    raise UnitConvertError(f"Cannot convert from celsius to {unit}")


# ---------------------------------------------------------------------------
# Linear conversion (distance, weight, volume)
# ---------------------------------------------------------------------------


def _convert_linear(value: float, from_unit: str, to_unit: str, category: str) -> float:
    """Convert using base-unit factor tables."""
    table = _TABLES[category]

    if from_unit not in table:
        raise UnitConvertError(
            f"Unknown {category} unit '{from_unit}'. Expected: {', '.join(sorted(table.keys()))}"
        )
    if to_unit not in table:
        raise UnitConvertError(
            f"Unknown {category} unit '{to_unit}'. Expected: {', '.join(sorted(table.keys()))}"
        )

    if from_unit == to_unit:
        return round(value, 6)

    # value_in_base = value * from_factor
    # result = value_in_base / to_factor
    base_value = value * table[from_unit]
    result = base_value / table[to_unit]
    return round(result, 6)
