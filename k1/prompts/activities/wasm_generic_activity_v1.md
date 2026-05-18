# WASM generic activity profile v1

Use this profile as procedural guidance only. The resolved capability contract, input schema, sandbox limits, safety band, HIL policy, tool grants, and caller role remain authoritative.

- Treat WASM calls as deterministic sandbox utilities with no memory of prior work. Provide only schema-declared inputs.
- Validate required units, dates, operation names, and numeric values against the selected contract before execution.
- Do not use WASM utility output as system-of-record truth for family data. Use it only as computation evidence for the current step.
- Do not invent supported operations or unit names. If the schema does not support a conversion or calculation, ask for a supported input or use another discovered contract.
- Keep prompt/profile metadata out of business params; only schema-declared fields belong in the operation payload.
