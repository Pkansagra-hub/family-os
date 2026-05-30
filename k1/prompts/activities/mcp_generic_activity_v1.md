# MCP generic activity profile v1

Use this profile as procedural guidance only. The resolved capability contract, input schema, safety band, HIL policy, tool grants, and caller role remain authoritative.

- Treat MCP calls as registered external or meta-tool operations. Inspect the selected contract schema and limitations before constructing params.
- Use returned contract names, schema fields, and scores as evidence only. Do not treat discovery results as tool grants or side-effect permission.
- For write-capable MCP tools, verify the target contract, required inputs, safety band, and HIL requirements before execution.
- Do not invent MCP server names, provider ids, capability names, prompt names, or prior results. Ask for clarification or perform allowed discovery instead.
- Keep prompt/profile metadata out of business params; only schema-declared fields belong in the operation payload.
