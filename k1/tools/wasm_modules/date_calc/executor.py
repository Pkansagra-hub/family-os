"""
k1.tools.wasm_modules.date_calc.executor -- Date arithmetic computation.

Pure function implementations for the date_calc WASM tool.
No I/O, no state, no side effects. These functions represent the
logic that would execute inside a WASM sandbox.

Each function takes a params dict and returns a result dict matching
the contract output schema.

Errors:
  - ValueError for invalid dates or unknown operations
  - All errors are deterministic and reproducible
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict

# Day-of-week names matching Python's weekday() (0=Monday, 6=Sunday)
_WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


class DateCalcError(Exception):
    """Error during date calculation."""


def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main dispatch: route to the correct date operation.

    Args:
        params: Must contain 'operation' and 'date'.
            Optional: 'date2' (for days_between), 'days' (for add_days).

    Returns:
        Dict with 'result', 'operation', and 'input_date' keys.

    Raises:
        DateCalcError: On invalid input or unknown operation.
    """
    operation = params.get("operation", "")
    date_str = params.get("date", "")

    if not operation:
        raise DateCalcError("operation is required")
    if not date_str:
        raise DateCalcError("date is required")

    try:
        parsed_date = _parse_date(date_str)
    except ValueError as exc:
        raise DateCalcError(f"Invalid date format '{date_str}': {exc}") from exc

    if operation == "days_between":
        result = _days_between(parsed_date, params)
    elif operation == "add_days":
        result = _add_days(parsed_date, params)
    elif operation == "weekday":
        result = _weekday(parsed_date)
    elif operation == "is_weekend":
        result = _is_weekend(parsed_date)
    else:
        raise DateCalcError(
            f"Unknown operation '{operation}'. "
            f"Expected: days_between, add_days, weekday, is_weekend"
        )

    return {
        "result": result,
        "operation": operation,
        "input_date": date_str,
    }


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def _days_between(d1: date, params: Dict[str, Any]) -> int:
    """Calculate calendar days between two dates."""
    date2_str = params.get("date2", "")
    if not date2_str:
        raise DateCalcError("date2 is required for days_between operation")

    try:
        d2 = _parse_date(date2_str)
    except ValueError as exc:
        raise DateCalcError(f"Invalid date2 format '{date2_str}': {exc}") from exc

    return (d2 - d1).days


def _add_days(d: date, params: Dict[str, Any]) -> str:
    """Add (or subtract) days from a date. Returns ISO 8601 string."""
    days = params.get("days", 0)
    if not isinstance(days, (int, float)):
        raise DateCalcError(f"days must be a number, got {type(days).__name__}")
    result_date = d + timedelta(days=int(days))
    return result_date.isoformat()


def _weekday(d: date) -> str:
    """Return the day-of-week name for a date."""
    return _WEEKDAY_NAMES[d.weekday()]


def _is_weekend(d: date) -> bool:
    """Return True if the date is Saturday or Sunday."""
    return d.weekday() >= 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(date_str: str) -> date:
    """Parse an ISO 8601 date string (YYYY-MM-DD)."""
    return date.fromisoformat(date_str)
