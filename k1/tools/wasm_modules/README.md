# K1 WASM Tool Modules

WASM module contracts live under `k1/contracts/tools/`; Python executor modules live here for the current edge runtime. M8 adds representative contracts for the existing deterministic utilities:

- `tool.execute.date_calc`
- `tool.execute.unit_convert`

Generic WASM tools should declare `prompt_template: "wasm_generic_activity_v1"` and `activity_profile: "wasm.generic.v1"` unless a reviewed domain-specific prompt contract exists. WASM profile guidance is procedural only: the selected contract schema, sandbox limits, safety band, HIL, provider grants, and policy remain authoritative. WASM utility output is computation evidence for the current step, not system-of-record family truth.
