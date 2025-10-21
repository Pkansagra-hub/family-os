# ADR-0031b: Cost Model & Pricing Configuration (Corporate Usage Tracking)

**Status:** ✅ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0031: Cost Tracking Per Session](0031-cost-tracking-per-session.md)
**Authors:** K1 Architecture Team
**Category:** Corporate Governance & Compliance
**Related ADRs:** ADR-0027 (Model Placement), ADR-0031a (Budget Enforcement), ADR-0031d (Observability)

---

## Context

### Problem Statement

**In corporate BYOK environments, organizations need to track actual costs their employees incur on LLM provider accounts for chargeback, budget planning, and cost optimization.**

**Corporate BYOK Scenario:**
- Employees use personal API keys (OpenAI, Anthropic, Google)
- Company reimburses employees for work-related API usage
- Finance needs departmental cost attribution for chargeback
- IT needs cost visibility to optimize model/tool selection
- Compliance needs audit trail of actual spending

**Without Cost Model:**
```
End of Month:
- Employee A: "I spent $150 on OpenAI this month"
- Employee B: "I spent $80 on Anthropic"
- Employee C: "Not sure, maybe $50?"

Finance Problems:
- Cannot verify actual costs (no receipts)
- Cannot attribute costs to projects/departments
- Cannot optimize (which models/tools expensive?)
- Cannot forecast budgets for next quarter

IT Problems:
- No visibility into expensive operations
- Cannot recommend cheaper alternatives
- Cannot enforce cost-effective practices
```

**With This Sub-ADR:**
```
End of Month:
- K1 tracks every API call with actual costs
- Finance dashboard shows:
  * Engineering: $4,200 (GPT-4o: $2,800, Claude: $1,400)
  * Product: $1,800 (GPT-4o: $1,200, Gemini: $600)
- IT dashboard shows:
  * Code generation: $3,500 (83% of budget)
  * Q&A: $600 (14% of budget)
  * Image gen: $900 (expensive, recommend alternatives)
- Forecast Q4: $18,000/month based on trends

Benefits:
- Accurate cost tracking per operation ✅
- Department/project attribution for chargeback ✅
- Model/tool cost breakdown for optimization ✅
- Automated billing reconciliation ✅
```

### System Constraints

1. **Performance Requirements:**
   - Cost calculation: <0.5ms per operation
   - Pricing lookup: <0.1ms (in-memory cache)
   - Config hot-reload: <100ms (no restart)

2. **Pricing Accuracy:**
   - Track actual provider pricing (OpenAI, Anthropic, Google)
   - Update pricing monthly (provider rate changes)
   - Support volume discounts (enterprise contracts)

3. **Storage Requirements:**
   - Cost history: 90 days detailed, 2 years aggregated
   - Estimated size: 100MB/year (1M operations × 100 bytes)

---

## Decision

### Cost Model Architecture

**3-Layer Cost Calculation:**
1. **Token Costs:** Input/output tokens × provider pricing
2. **Tool Costs:** Per-call pricing for external APIs
3. **Compute Costs:** Local inference costs (NPU/GPU/CPU)

### Pricing Configuration Schema

```yaml
# File: k1/config/cost_model.yml
# Corporate cost tracking configuration

cost_model:
  version: "1.0"
  last_updated: "2025-10-13"

  # Provider Pricing (actual costs from BYOK accounts)
  providers:
    openai:
      models:
        - model_id: "gpt-4o"
          input_cost_per_1k_tokens: 0.0050   # $5 per 1M input tokens
          output_cost_per_1k_tokens: 0.0150  # $15 per 1M output tokens
          context_window: 128000

        - model_id: "gpt-4o-mini"
          input_cost_per_1k_tokens: 0.00015  # $0.15 per 1M
          output_cost_per_1k_tokens: 0.00060 # $0.60 per 1M
          context_window: 128000

    anthropic:
      models:
        - model_id: "claude-3-5-sonnet"
          input_cost_per_1k_tokens: 0.0030   # $3 per 1M
          output_cost_per_1k_tokens: 0.0150  # $15 per 1M
          context_window: 200000

    google:
      models:
        - model_id: "gemini-1.5-pro"
          input_cost_per_1k_tokens: 0.00125  # $1.25 per 1M
          output_cost_per_1k_tokens: 0.00500 # $5 per 1M
          context_window: 2000000

  # Tool Call Pricing
  tools:
    web_search:
      provider: "google_search_api"
      cost_per_call: 0.002  # $0.002 per search

    image_generation:
      provider: "dall-e-3"
      cost_per_image: 0.040  # $0.04 per 1024x1024 image

    web_scraping:
      provider: "firecrawl"
      cost_per_page: 0.001  # $0.001 per page

    code_execution:
      provider: "local"
      cost_per_execution: 0.0  # Free (local sandbox)

  # Local Inference Costs (hardware amortization)
  local_inference:
    npu:
      cost_per_second: 0.00001  # Amortized hardware cost
      models: ["gemma-2-9b", "phi-3-mini"]

    gpu:
      cost_per_second: 0.00005  # Amortized GPU cost
      models: ["llama-3-8b", "mistral-7b"]

    cpu:
      cost_per_second: 0.000001  # Negligible cost
      models: ["llama-3-1b", "phi-2"]

  # Volume Discounts (enterprise contracts)
  volume_discounts:
    - provider: "openai"
      monthly_spend_threshold: 10000.00  # $10K/month
      discount_percent: 10  # 10% discount

    - provider: "anthropic"
      monthly_spend_threshold: 5000.00
      discount_percent: 15  # 15% discount
```

### Cost Calculation Implementation

```python
# File: k1/cost_tracking/cost_calculator.py

from dataclasses import dataclass
from typing import Dict, Optional
import yaml

@dataclass
class CostBreakdown:
    """Detailed cost breakdown for single operation"""
    inference_cost_usd: float = 0.0
    tool_cost_usd: float = 0.0
    compute_cost_usd: float = 0.0
    total_usd: float = 0.0

    # Attribution fields
    model_name: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    tools_called: list = None
    compute_duration_sec: float = 0.0

    def __post_init__(self):
        if self.tools_called is None:
            self.tools_called = []
        self.total_usd = (
            self.inference_cost_usd +
            self.tool_cost_usd +
            self.compute_cost_usd
        )

class CostCalculator:
    """Calculate actual costs for corporate chargeback"""

    def __init__(self, config_path: str = "config/cost_model.yml"):
        self.config = self._load_config(config_path)
        self.pricing_cache: Dict[str, dict] = {}
        self._build_pricing_cache()

    def _load_config(self, path: str) -> dict:
        """Load pricing configuration"""
        with open(path) as f:
            return yaml.safe_load(f)

    def _build_pricing_cache(self):
        """Build in-memory pricing cache for fast lookup"""
        for provider_name, provider_data in self.config['cost_model']['providers'].items():
            for model in provider_data['models']:
                model_id = model['model_id']
                self.pricing_cache[model_id] = {
                    'provider': provider_name,
                    'input_cost_per_1k': model['input_cost_per_1k_tokens'],
                    'output_cost_per_1k': model['output_cost_per_1k_tokens']
                }

    def calculate_inference_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Calculate LLM inference cost (<0.5ms)
        Based on actual provider pricing
        """
        if model_id not in self.pricing_cache:
            # Unknown model - log warning but don't fail
            logger.warning(f"Unknown model {model_id}, assuming $0 cost")
            return 0.0

        pricing = self.pricing_cache[model_id]

        input_cost = (input_tokens / 1000) * pricing['input_cost_per_1k']
        output_cost = (output_tokens / 1000) * pricing['output_cost_per_1k']

        total = input_cost + output_cost

        # Apply volume discount if applicable
        total = self._apply_volume_discount(pricing['provider'], total)

        return round(total, 6)  # 6 decimal places ($0.000001 precision)

    def calculate_tool_cost(self, tool_name: str, call_count: int = 1) -> float:
        """Calculate tool call cost (<0.1ms)"""
        tools_config = self.config['cost_model']['tools']

        if tool_name not in tools_config:
            return 0.0  # Unknown tool, assume free

        tool_pricing = tools_config[tool_name]

        if 'cost_per_call' in tool_pricing:
            return tool_pricing['cost_per_call'] * call_count
        elif 'cost_per_image' in tool_pricing:
            return tool_pricing['cost_per_image'] * call_count
        elif 'cost_per_page' in tool_pricing:
            return tool_pricing['cost_per_page'] * call_count
        else:
            return 0.0

    def calculate_compute_cost(
        self,
        placement: str,  # "npu", "gpu", "cpu"
        duration_sec: float
    ) -> float:
        """Calculate local inference compute cost"""
        local_config = self.config['cost_model']['local_inference']

        if placement not in local_config:
            return 0.0

        cost_per_sec = local_config[placement]['cost_per_second']
        return cost_per_sec * duration_sec

    def calculate_full_breakdown(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        tools_called: list,
        placement: str = "remote",
        duration_sec: float = 0.0
    ) -> CostBreakdown:
        """
        Calculate full cost breakdown for chargeback
        Returns detailed attribution for finance reports
        """
        # Inference cost
        inference_cost = self.calculate_inference_cost(
            model_id, input_tokens, output_tokens
        )

        # Tool costs
        tool_cost = sum(
            self.calculate_tool_cost(tool_name)
            for tool_name in tools_called
        )

        # Compute cost (for local models)
        compute_cost = 0.0
        if placement != "remote":
            compute_cost = self.calculate_compute_cost(placement, duration_sec)

        return CostBreakdown(
            inference_cost_usd=inference_cost,
            tool_cost_usd=tool_cost,
            compute_cost_usd=compute_cost,
            model_name=model_id,
            provider=self.pricing_cache.get(model_id, {}).get('provider', 'unknown'),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tools_called=tools_called,
            compute_duration_sec=duration_sec
        )

    def _apply_volume_discount(self, provider: str, cost: float) -> float:
        """Apply enterprise volume discounts"""
        discounts = self.config['cost_model']['volume_discounts']

        for discount in discounts:
            if discount['provider'] == provider:
                # Check if this month's spend qualifies
                monthly_spend = self._get_monthly_spend(provider)
                if monthly_spend >= discount['monthly_spend_threshold']:
                    discount_factor = 1.0 - (discount['discount_percent'] / 100.0)
                    return cost * discount_factor

        return cost

    def hot_reload_config(self):
        """Reload pricing config without restart (<100ms)"""
        logger.info("Hot-reloading cost model configuration")
        self.config = self._load_config(self.config_path)
        self.pricing_cache.clear()
        self._build_pricing_cache()
        logger.info("Cost model configuration reloaded successfully")
```

### Chargeback Report Generation

```python
# File: k1/cost_tracking/chargeback_reports.py

from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime, timedelta

@dataclass
class ChargebackReport:
    """Monthly chargeback report for finance"""
    department_id: str
    month: str  # "2025-10"
    total_spent_usd: float
    budget_usd: float
    utilization: float

    # Detailed breakdowns
    user_breakdown: Dict[str, float]
    model_breakdown: Dict[str, float]
    tool_breakdown: Dict[str, float]
    project_breakdown: Dict[str, float]

    # Top spenders
    top_users: List[tuple]  # [(user_id, cost), ...]
    top_models: List[tuple]  # [(model_id, cost), ...]

    # Optimization insights
    potential_savings_usd: float
    recommendations: List[str]

class ChargebackReportGenerator:
    """Generate finance chargeback reports"""

    def __init__(self, cost_calculator: CostCalculator):
        self.calculator = cost_calculator

    def generate_monthly_report(
        self,
        department_id: str,
        month: str
    ) -> ChargebackReport:
        """Generate comprehensive chargeback report"""

        # Query all operations for department this month
        operations = self._query_monthly_operations(department_id, month)

        # Aggregate by user
        user_costs = {}
        for op in operations:
            user_id = op['user_id']
            user_costs[user_id] = user_costs.get(user_id, 0.0) + op['cost_usd']

        # Aggregate by model
        model_costs = {}
        for op in operations:
            model = op['model_name']
            model_costs[model] = model_costs.get(model, 0.0) + op['cost_usd']

        # Aggregate by tool
        tool_costs = {}
        for op in operations:
            for tool in op['tools_called']:
                tool_costs[tool] = tool_costs.get(tool, 0.0) + op['tool_cost_usd']

        # Calculate total
        total_spent = sum(user_costs.values())

        # Get budget
        budget = self._get_department_budget(department_id)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            model_costs, tool_costs, total_spent
        )

        return ChargebackReport(
            department_id=department_id,
            month=month,
            total_spent_usd=total_spent,
            budget_usd=budget,
            utilization=total_spent / budget if budget > 0 else 0.0,
            user_breakdown=user_costs,
            model_breakdown=model_costs,
            tool_breakdown=tool_costs,
            project_breakdown={},  # TODO: Add project tagging
            top_users=sorted(user_costs.items(), key=lambda x: x[1], reverse=True)[:10],
            top_models=sorted(model_costs.items(), key=lambda x: x[1], reverse=True)[:5],
            potential_savings_usd=self._calculate_potential_savings(model_costs),
            recommendations=recommendations
        )

    def _generate_recommendations(
        self,
        model_costs: Dict[str, float],
        tool_costs: Dict[str, float],
        total_spent: float
    ) -> List[str]:
        """Generate cost optimization recommendations"""
        recommendations = []

        # Check expensive model usage
        if 'gpt-4o' in model_costs and model_costs['gpt-4o'] > total_spent * 0.5:
            savings = model_costs['gpt-4o'] * 0.7  # 70% savings with gpt-4o-mini
            recommendations.append(
                f"Consider GPT-4o-mini for simple tasks. "
                f"Potential savings: ${savings:.2f}/month (70%)"
            )

        # Check expensive tool usage
        if 'image_generation' in tool_costs and tool_costs['image_generation'] > 500:
            recommendations.append(
                "High image generation costs. "
                "Consider local Stable Diffusion for non-critical images."
            )

        # Check local inference opportunities
        if total_spent > 5000:
            recommendations.append(
                "High spending detected. "
                "Consider on-device models for Q&A and simple tasks."
            )

        return recommendations
```

---

## Implementation Timeline

### Phase 1: Core Cost Calculation (Weeks 1-3)
- **Week 1:** Token cost calculation with provider pricing
- **Week 2:** Tool cost tracking
- **Week 3:** Compute cost calculation (local inference)

### Phase 2: Configuration System (Weeks 4-5)
- **Week 4:** YAML config schema + hot-reload
- **Week 5:** Volume discount support

### Phase 3: Chargeback Reports (Weeks 6-8)
- **Week 6:** Report generation engine
- **Week 7:** Optimization recommendations
- **Week 8:** WARD tests + validation

---

## Consequences

### Positive
1. **Accurate Tracking:** Real-time cost tracking per operation
2. **Chargeback Ready:** Finance can attribute costs accurately
3. **Optimization:** IT can identify expensive operations
4. **Forecasting:** Predict future costs based on trends

### Negative
1. **Configuration Maintenance:** Pricing must be updated monthly
2. **Storage Overhead:** Detailed cost history requires storage

### Risks
1. **Pricing Drift:** Provider pricing changes not updated
   - Mitigation: Monthly pricing review + alerts
2. **Attribution Errors:** Misattributed costs cause chargeback disputes
   - Mitigation: Audit trail + validation

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Cost Calculation Accuracy | 100% | Verified against provider bills |
| Chargeback Disputes | <1% | Finance validation |
| Performance Impact | <0.5ms | Calculation latency |

---

## Related Documents

- [ADR-0031: Cost Tracking Per Session](0031-cost-tracking-per-session.md)
- [ADR-0031a: Hierarchical Budget Enforcement](0031a-hierarchical-budget-enforcement-corporate-governance.md)
- [ADR-0031c: Automatic Fallback](0031c-automatic-cost-based-fallback.md)
- [ADR-0031d: Cost Observability](0031d-cost-observability-metrics.md)

---

**Status:** ✅ Ready for implementation
**Timeline:** 8 weeks
**Priority:** ⭐⭐⭐ Critical (Corporate chargeback requirement)
