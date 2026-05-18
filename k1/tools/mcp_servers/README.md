# K1 MCP Tool Servers

MCP tool contracts live under `k1/contracts/tools/` and are loaded into Fabric by the ModuleLoader. M8 representative MCP contracts declare explicit generic profile metadata:

- `tool.read.find_prompts`
- `tool.read.discover_capabilities`
- `tool.write.build_agent`

Use `prompt_template: "mcp_generic_activity_v1"` and `activity_profile: "mcp.generic.v1"` for generic MCP tools unless a reviewed domain-specific prompt contract exists. This metadata is procedural guidance only: schemas, exact capability names, safety bands, HIL, provider grants, and policy remain authoritative. Do not infer profiles from free text, provider ids, or capability-name prefixes.
