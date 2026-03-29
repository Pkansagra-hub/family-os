# Tool Registry
# Auto-registers from contract.yaml
# Tool install + lookup + versions


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register_tool(self, tool_name, tool_contract, impl):
        self.tools[tool_name] = {"contract": tool_contract, "impl": impl}

    def get_tool(self, tool_name):
        return self.tools.get(tool_name)

    def list_tools(self):
        return list(self.tools.keys())
