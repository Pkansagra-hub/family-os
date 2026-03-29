"""
k1.tools.wasm_modules.date_calc -- Date Calculator WASM module.

Pure-Python computation logic for date arithmetic operations.
In production, this logic compiles to a .wasm binary. For testing,
DateCalcExecutor provides the same interface used by the
IWASMRuntime test adapter.

Provides these date operations:
  - days_between: Calendar days between two dates
  - add_days: Add/subtract days from a date
  - weekday: Day-of-week name for a date
  - is_weekend: Whether a date falls on Saturday or Sunday

All dates must be ISO 8601 format (YYYY-MM-DD).
No timezone awareness (Phase 1 scope limitation).

References:
  - date_calc.yaml contract
  - fabric_tool_implementation_plan.md Phase 1, Section 3.2
"""
