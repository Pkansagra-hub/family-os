"""
K1 Model Hub Plugins -- Provider Plugin Interface
===================================================

ADR: 0001b (Model Hub Architecture & LLM Integration)
Spec: k1/model_hub/model_hub.mmd — PLUGIN_INTERFACE section

EXTENSIBILITY CONTRACT:
  1. Create manifest YAML
  2. Implement IProviderPlugin (5 methods)
  3. Place in plugins/
  4. Auto-discovered on startup
  5. DONE — zero hub code changes
"""
