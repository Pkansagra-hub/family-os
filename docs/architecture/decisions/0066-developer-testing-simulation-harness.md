# ADR-0066: Developer Testing & Simulation Harness

**Status:** Proposed ðŸ”„ (Requirements Gathering - Ready for Detailed Design)
**Decision Date:** 2025-10-16
**Implementation Date:** TBD
**Authors:** K1 Architecture Team
**Category:** Developer Tooling & Quality Assurance
**Related ADRs:**
- [ADR-0007 (4-Stage Planning Pipeline)](0007-4stage-planning-pipeline.md) - Planner stage being tested
- [ADR-0004 (52-Module 5-Layer Architecture)](0004-52-module-5-layer-architecture.md) - Module structure for testing
- [ADR-0005 (Agent Lifecycle FSM)](0005-agent-lifecycle-fsm.md) - Agent states being simulated
- [ADR-0006 (3-Phase Orchestration)](0006-3phase-orchestration-contract-net.md) - Orchestration workflow testing
- [ADR-0011 (FlatBuffers Serialization)](0011-flatbuffers-serialization.md) - Message mocking
- [ADR-0014 (JSON REST API)](0014-json-rest-api-dual-format.md) - API contract testing
- [ADR-0015 (WebSocket Binary Protocol)](0015-websocket-binary-protocol.md) - WebSocket client simulation
- [ADR-0024 (Performance Budgets)](0024-performance-budgets-p95-targets.md) - Latency targets for regression detection
- [ADR-0029 (Prometheus Metrics & RED)](0029-prometheus-metrics-red-method.md) - Observability in tests
- [ADR-0051 (Testing & Integration Standards)](0001-k0-k1-kernel-split.md) - WARD framework foundation

---

## Context

### Problem Statement

K1 Intelligence Module requires robust testing infrastructure for AI agent interactions:

1. **Complex Agent Interactions:** Multi-agent orchestration, LLM-based planning, tool execution difficult to test without live system
2. **Regression Detection:** Cannot quantify conversation quality improvements over time
3. **Developer Friction:** Developers must run full system to test agent responses (slow, error-prone)
4. **No Synthetic Test Users:** Cannot simulate diverse user personas (casual, technical, confused, adversarial)
5. **Prompt Quality Regression:** No automated way to detect when planner prompts degrade

**Key Challenges:**

- **LLM Non-Determinism:** Same input produces different outputs (sampling, temperature)
- **Tool Latency Variability:** Tool calls have variable latency, complicating performance testing
- **State Interactions:** Agent behavior depends on SessionState, context, history
- **Coverage Gaps:** Cannot test all edge cases (rare user inputs, failure modes)

### Current Landscape

**Industry Patterns:**

1. **LLMOps Testing (Hugging Face):**
   - **Pattern:** Version prompts, compare outputs across prompt versions, track metrics
   - **Strength:** Lightweight, integrates with LLM APIs
   - **Weakness:** No agent orchestration testing, no tool interaction simulation

2. **ward + Fixtures (Standard Python):**
   - **Pattern:** Unit tests with mocked dependencies
   - **Strength:** Simple, well-known
   - **Weakness:** Heavy mocking, tests don't reflect real behavior

3. **LangSmith (LangChain):**
   - **Pattern:** Record conversations, create datasets, evaluate output quality
   - **Strength:** Dataset versioning, LLM eval models
   - **Weakness:** Cloud dependency, expensive at scale

4. **WARD Framework (K1):**
   - **Pattern:** Async integration tests with real components
   - **Strength:** Tests real agent interactions, comprehensive
   - **Weakness:** No synthetic user simulation, no eval infrastructure

5. **Synthetic Conversation Generation (Anthropic):**
   - **Pattern:** Use LLM to generate synthetic conversations for eval
   - **Strength:** Scale, diversity
   - **Weakness:** LLM-generated data biased, quality uneven

### Research Foundations

**Automated Evaluation:**
- **BLEU, ROUGE (Papineni et al., 2002)** â€” Text similarity metrics for evaluation
- **BERTScore (Zhang et al., 2020)** â€” Semantic similarity using embeddings
- **LLM-as-Evaluator (Fu et al., 2023)** â€” Use LLM to evaluate outputs

**Synthetic Data Generation:**
- **GPT-3 Prompting (Brown et al., 2020)** â€” Few-shot learning for generation
- **Data Augmentation (Wei & Zou, 2018)** â€” Perturbations for robustness testing
- **Conversation Simulation (Purwana et al., 2022)** â€” Generate dialogue datasets

**Regression Testing:**
- **Continuous Integration (Fowler, 2006)** â€” Automate test runs on every commit
- **Performance Regression Detection (Jones & Mueller, 2013)** â€” Statistical methods for latency tracking
- **Mutation Testing (DeMillo et al., 1978)** â€” Verify test effectiveness

### K1 Requirements

**Performance Targets (from ADR-0024):**

- **E2E Turn Latency:** <2000ms P95
- **Intent Classification:** <50ms P95
- **Clarification Rate:** <15% (goal)
- **Repair Success Rate:** >80% (goal)
- **Barge-in Latency:** <120ms P95

**Testing Requirements:**

- **Coverage:** All 6 core protocols (ADR-0003b), all 4 AI agents (planner, tool runner, dialogue manager, intent classifier)
- **Regression Detection:** Detect 5% quality regression with 95% confidence
- **Test Execution:** Complete suite <5 minutes (developer feedback loop)
- **Synthetic Users:** 5+ personas (casual, technical, confused, adversarial, multilingual)

---

## Decision

We will implement a **2-tier testing harness** for agent interactions:

### Architecture Overview

```
Developer â†’ Developer CLI
              â†“
         â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
         â”‚ TIER 1: Conversation Simulator     â”‚
         â”‚  - Synthetic user personas        â”‚
         â”‚  - Multi-turn generation          â”‚
         â”‚  - Rapid-fire message injection   â”‚
         â”‚  - Interruption/barge-in sim      â”‚
         â”‚  Duration: <5 minutes (10 runs)   â”‚
         â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
              â†“
         â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
         â”‚ TIER 2: Regression Eval Suites    â”‚
         â”‚  - Intent classification accuracy â”‚
         â”‚  - Clarification rate tracking    â”‚
         â”‚  - Repair success rate tracking   â”‚
         â”‚  - Latency regression detection   â”‚
         â”‚  - User satisfaction proxy        â”‚
         â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
              â†“
         Eval Report (Metrics + Regression Alerts)
```

---

## Sub-ADR 0066a: Conversation Simulator (Synthetic Users)

**Purpose:** Simulated user personas for testing agent responses
**Type:** Sub-ADR (links to main ADR-0066)
**Estimated Length:** 1,300 lines

### Synthetic User Personas

#### Persona 1: Casual User

```python
@dataclass
class CasualUserPersona:
    """Casual, natural language user (non-technical)"""
    name: str = "Sarah"
    age: int = 35
    tech_level: str = "low"
    speech_style: str = "conversational"

    # Message generation patterns
    message_patterns: List[str] = field(default_factory=lambda: [
        "hey, can you {action}?",
        "um, {action} please",
        "{action} for me would be nice",
        "could you maybe {action}?",
        "so like, {action}",
    ])

    # Common errors
    error_rate: float = 0.15  # 15% of messages have typos/grammar
    interruption_rate: float = 0.10  # 10% interrupt mid-response
    clarification_requests: float = 0.20  # 20% ask for clarification

    # Personality
    patience: float = 0.7  # On scale 0-1, how patient
    frustration_threshold: int = 3  # Interrupts after 3 misunderstandings
```

#### Persona 2: Technical User

```python
@dataclass
class TechnicalUserPersona:
    """Technical, API-aware user (developer)"""
    name: str = "Alex"
    age: int = 28
    tech_level: str = "high"
    speech_style: str = "precise"

    message_patterns: List[str] = field(default_factory=lambda: [
        "{action} with {param}={value}",
        "call {tool} and {action}",
        "execute: {action}",
        "{action} in {format} format",
    ])

    error_rate: float = 0.01  # Few typos
    interruption_rate: float = 0.05  # Rarely interrupts
    clarification_requests: float = 0.05  # Rarely needs clarification

    patience: float = 0.95  # Very patient
    frustration_threshold: int = 10  # Many misunderstandings tolerated
```

#### Persona 3: Confused User

```python
@dataclass
class ConfusedUserPersona:
    """Confused, uncertain user (frequent clarification)"""
    name: str = "Jamie"
    age: int = 42
    tech_level: str = "low"
    speech_style: str = "uncertain"

    message_patterns: List[str] = field(default_factory=lambda: [
        "um, {action}? or like...?",
        "wait, can you {action}?",
        "I'm not sure but {action}",
        "{action}? does that work?",
    ])

    error_rate: float = 0.25  # Many typos/grammar issues
    interruption_rate: float = 0.20  # Frequently interrupts (confused)
    clarification_requests: float = 0.60  # Needs lots of clarification

    patience: float = 0.4  # Low patience
    frustration_threshold: int = 2  # Frustrated quickly
```

#### Persona 4: Adversarial User

```python
@dataclass
class AdversarialUserPersona:
    """Adversarial, testing system limits"""
    name: str = "Sam"
    age: int = 25
    tech_level: str = "high"
    speech_style: str = "hostile"

    message_patterns: List[str] = field(default_factory=lambda: [
        "try this: {action} OR BREAK",
        "{action} and then {harmful_action}",
        "what if I {edge_case}?",
        "can you {action} with {invalid_param}?",
    ])

    error_rate: float = 0.30  # Intentional errors
    interruption_rate: float = 0.30  # Aggressive interruption
    clarification_requests: float = 0.05  # No patience for clarification

    # Adversarial-specific
    tries_exploits: float = 0.8  # 80% of messages try to find edge cases
    tries_jailbreaks: float = 0.3  # 30% try safety workarounds
    patience: float = 0.1  # Very low patience
    frustration_threshold: int = 1  # Frustrated immediately
```

### Conversation Simulator Implementation

```python
# k1/testing/conversation_simulator.py

from dataclasses import dataclass
from typing import List, Dict, Callable
import asyncio
import random

@dataclass
class SimulationScenario:
    """Scenario definition for testing"""
    name: str
    description: str
    personas: List[UserPersona]
    actions: List[str]  # e.g., ["book restaurant", "check weather", "send message"]
    num_turns: int = 10
    interruption_rate: float = 0.1
    allow_repairs: bool = True

class ConversationSimulator:
    """
    Tier 1: Simulate agent interactions with synthetic users

    Research: Synthetic data generation (Brown et al. 2020),
              Conversation simulation (Purwana et al. 2022)
    """

    def __init__(self, agent_client, config):
        """
        Args:
            agent_client: Client for communicating with K1 agent
            config: Simulation config (timeouts, personas, etc.)
        """
        self.agent_client = agent_client
        self.config = config
        self.metrics = MetricsCollector()

    async def simulate_conversation(
        self,
        scenario: SimulationScenario,
        trace_id: str,
    ) -> ConversationResult:
        """
        Simulate multi-turn conversation with synthetic user

        Returns: ConversationResult (turns, metrics, success/failure)
        """
        start_time = perf_counter()
        persona = random.choice(scenario.personas)
        turns = []
        session_id = str(uuid4())

        for turn_idx in range(scenario.num_turns):
            # 1. Generate user message
            user_message = self._generate_user_message(
                persona=persona,
                action=random.choice(scenario.actions),
                turn_idx=turn_idx,
            )

            # 2. Send to agent
            try:
                response = await self.agent_client.send_message(
                    message=user_message,
                    session_id=session_id,
                    trace_id=trace_id,
                    timeout_ms=self.config.agent_timeout_ms,
                )
            except asyncio.TimeoutError:
                # Agent timeout
                turns.append(Turn(
                    user_message=user_message,
                    agent_response=None,
                    error="TIMEOUT",
                    latency_ms=self.config.agent_timeout_ms,
                ))
                continue
            except Exception as e:
                # Agent error
                turns.append(Turn(
                    user_message=user_message,
                    agent_response=None,
                    error=f"ERROR: {str(e)}",
                    latency_ms=None,
                ))
                continue

            # 3. Record turn
            turns.append(Turn(
                user_message=user_message,
                agent_response=response.content,
                error=None,
                latency_ms=response.latency_ms,
                intent=response.intent,
                clarified=response.clarified,
            ))

            # 4. Decide to interrupt/retry
            if random.random() < scenario.interruption_rate and turn_idx < scenario.num_turns - 1:
                # User interrupts next turn
                interrupt_msg = self._generate_interrupt(persona)
                turns[-1].interrupted = True
                turns.append(Turn(
                    user_message=interrupt_msg,
                    agent_response=None,
                    error="INTERRUPTION",
                ))

        latency_total = (perf_counter() - start_time) * 1000

        logger.info(
            f"Simulation complete: {scenario.name}",
            extra={
                "persona": persona.name,
                "turns": len(turns),
                "errors": sum(1 for t in turns if t.error),
                "latency_ms": latency_total,
                "trace_id": trace_id,
            }
        )

        return ConversationResult(
            scenario=scenario,
            persona=persona,
            turns=turns,
            total_latency_ms=latency_total,
            session_id=session_id,
        )

    def _generate_user_message(
        self,
        persona: UserPersona,
        action: str,
        turn_idx: int,
    ) -> str:
        """Generate realistic user message from persona"""

        # Select template
        template = random.choice(persona.message_patterns)

        # Render template
        message = template.format(action=action)

        # Add errors (typos, grammar)
        if random.random() < persona.error_rate:
            message = self._introduce_typo(message)

        # Add repetition for emphasis (casual style)
        if persona.speech_style == "conversational" and random.random() < 0.2:
            message += f" please!"

        return message

    def _generate_interrupt(self, persona: UserPersona) -> str:
        """Generate interruption message"""
        interrupts = [
            "wait, nevermind",
            "actually, never mind that",
            "oh never mind",
            "cancel that",
            "actually, {action}",
            "hold on, {action} instead",
        ]
        template = random.choice(interrupts)
        return template.format(action=random.choice(["try this", "do this", "check this"]))

    def _introduce_typo(self, text: str) -> str:
        """Introduce realistic typo"""
        words = text.split()
        if len(words) < 2:
            return text

        # Random typo strategies
        strategy = random.choice(["omit", "swap", "duplicate"])
        idx = random.randint(0, len(words) - 1)

        if strategy == "omit":
            # Omit letter: "booking" â†’ "bocking"
            word = words[idx]
            if len(word) > 2:
                pos = random.randint(1, len(word) - 1)
                words[idx] = word[:pos] + word[pos+1:]
        elif strategy == "swap":
            # Swap adjacent letters: "booking" â†’ "bokoking"
            word = words[idx]
            if len(word) > 2:
                pos = random.randint(0, len(word) - 2)
                words[idx] = word[:pos] + word[pos+1] + word[pos] + word[pos+2:]
        elif strategy == "duplicate":
            # Duplicate letter: "booking" â†’ "boooking"
            word = words[idx]
            pos = random.randint(0, len(word) - 1)
            words[idx] = word[:pos] + word[pos] + word[pos:]

        return " ".join(words)

@dataclass
class ConversationResult:
    """Result of simulated conversation"""
    scenario: SimulationScenario
    persona: UserPersona
    turns: List[Turn]
    total_latency_ms: float
    session_id: str

    def success_rate(self) -> float:
        """Percentage of turns without errors"""
        total = len(self.turns)
        errors = sum(1 for t in self.turns if t.error)
        return (total - errors) / total if total > 0 else 0.0

    def avg_latency_ms(self) -> float:
        """Average latency per turn"""
        latencies = [t.latency_ms for t in self.turns if t.latency_ms]
        return sum(latencies) / len(latencies) if latencies else 0.0

    def clarification_rate(self) -> float:
        """Percentage of turns where agent asked for clarification"""
        total = len(self.turns)
        clarified = sum(1 for t in self.turns if t.clarified)
        return clarified / total if total > 0 else 0.0
```

### Testing Patterns

#### Pattern 1: Scenario-Based Testing

```python
# tests/conversation_simulator/test_scenarios.py

@test("simulator: casual user ordering dinner")
async def _(sim=simulator_fixture):
    scenario = SimulationScenario(
        name="casual_dinner_booking",
        description="Casual user books dinner reservation",
        personas=[CasualUserPersona()],
        actions=[
            "book restaurant for 7pm",
            "find italian restaurant",
            "reserve table for 2",
        ],
        num_turns=8,
        interruption_rate=0.1,
    )

    result = await sim.simulate_conversation(scenario, trace_id="test_casual_1")

    assert result.success_rate() > 0.8, f"Success rate too low: {result.success_rate()}"
    assert result.avg_latency_ms() < 500, f"Latency too high: {result.avg_latency_ms()}"
    assert result.clarification_rate() < 0.3, f"Too many clarifications: {result.clarification_rate()}"
```

#### Pattern 2: Adversarial Testing

```python
# tests/conversation_simulator/test_adversarial.py

@test("simulator: adversarial edge case injection")
async def _(sim=simulator_fixture):
    scenario = SimulationScenario(
        name="adversarial_edge_cases",
        description="Adversarial user tries edge cases",
        personas=[AdversarialUserPersona()],
        actions=[
            "book reservation with 0 people",
            "check weather in year 9999",
            "send message with max unicode chars",
            "call tool with null parameters",
        ],
        num_turns=10,
        interruption_rate=0.3,  # High interruption
    )

    result = await sim.simulate_conversation(scenario, trace_id="test_adversarial_1")

    # System should not crash or produce nonsensical output
    assert result.success_rate() > 0.5, "Agent should handle adversarial input"

    # Check for safety violations
    for turn in result.turns:
        if turn.agent_response:
            assert "ERROR" not in turn.agent_response, f"Unhandled error: {turn.agent_response}"
```

#### Pattern 3: Rapid-Fire Message Injection

```python
# tests/conversation_simulator/test_rapid_fire.py

@test("simulator: rapid-fire messages (barge-in)")
async def _(sim=simulator_fixture):
    # Test agent handles multiple messages sent in quick succession
    session_id = str(uuid4())
    messages = [
        "check weather",
        "actually, check traffic instead",  # Interrupt
        "wait, check both",  # Another interrupt
        "show me results",
    ]

    for msg in messages:
        response = await sim.agent_client.send_message(
            message=msg,
            session_id=session_id,
            timeout_ms=100,  # Very tight timeout
        )
        assert response is not None, f"Agent should respond quickly to: {msg}"
```

---

## Sub-ADR 0066b: Regression Eval Suites

**Purpose:** Automated eval suite for conversation quality metrics
**Type:** Sub-ADR (links to main ADR-0066)
**Estimated Length:** 1,100 lines

### Quality Metrics Tracked

#### Metric 1: Intent Classification Accuracy

```python
# k1/testing/regression_evals.py

class IntentClassificationEval:
    """
    Metric: Intent classification accuracy
    Target: >90% accuracy on labeled test set

    Tracks: Regression if accuracy drops >5%
    """

    async def evaluate(self, test_dataset: LabeledDataset) -> EvalResult:
        """
        Evaluate intent classification accuracy

        Args:
            test_dataset: Labeled intent examples

        Returns: EvalResult(accuracy, errors, trends)
        """
        correct = 0
        total = len(test_dataset.examples)
        errors = []

        for example in test_dataset.examples:
            # Run intent classification
            result = await self.agent_client.classify_intent(
                message=example.text,
                session_id=str(uuid4()),
            )

            # Compare to labeled intent
            if result.intent == example.intent:
                correct += 1
            else:
                errors.append(ClassificationError(
                    input=example.text,
                    expected=example.intent,
                    actual=result.intent,
                    confidence=result.confidence,
                ))

        accuracy = correct / total

        # Check for regression
        prev_baseline = self._load_baseline("intent_classification")
        regression = (prev_baseline - accuracy) / prev_baseline > 0.05  # 5% regression threshold

        logger.info(
            f"Intent classification eval: {accuracy:.1%} accuracy",
            extra={
                "accuracy": accuracy,
                "baseline": prev_baseline,
                "regressed": regression,
                "errors": len(errors),
            }
        )

        return EvalResult(
            metric="intent_classification_accuracy",
            value=accuracy,
            target=0.90,
            regressed=regression,
            errors=errors,
        )
```

#### Metric 2: Clarification Rate

```python
class ClarificationRateEval:
    """
    Metric: Percentage of turns where agent asks for clarification
    Target: <15% (goal from ADR-0024)

    Tracks: Regression if rate increases >2%
    """

    async def evaluate(self, test_dataset: LabeledDataset) -> EvalResult:
        """
        Evaluate clarification rate

        Args:
            test_dataset: Natural language examples (ambiguous and clear)

        Returns: EvalResult(clarification_rate, trends)
        """
        total_turns = 0
        clarifications = 0

        for example in test_dataset.examples:
            response = await self.agent_client.send_message(
                message=example.text,
                session_id=str(uuid4()),
            )

            total_turns += 1
            if response.asked_for_clarification:
                clarifications += 1

        clarification_rate = clarifications / total_turns

        # Check for regression
        prev_baseline = self._load_baseline("clarification_rate")
        regression = (clarification_rate - prev_baseline) > 0.02  # 2% regression threshold

        logger.info(
            f"Clarification rate eval: {clarification_rate:.1%}",
            extra={
                "rate": clarification_rate,
                "baseline": prev_baseline,
                "regressed": regression,
            }
        )

        return EvalResult(
            metric="clarification_rate",
            value=clarification_rate,
            target=0.15,
            regressed=regression,
        )
```

#### Metric 3: Repair Success Rate

```python
class RepairSuccessRateEval:
    """
    Metric: Success rate of repair attempts after misunderstanding
    Target: >80% (goal from ADR-0024)

    Tracks: Regression if success rate drops >5%
    """

    async def evaluate(self, test_dataset: LabeledDataset) -> EvalResult:
        """
        Evaluate repair success rate

        Args:
            test_dataset: Examples of misunderstandings and repairs

        Returns: EvalResult(success_rate, trends)
        """
        repairs_total = 0
        repairs_successful = 0

        for example in test_dataset.examples:
            # First turn: initial misunderstanding
            response1 = await self.agent_client.send_message(
                message=example.initial_message,
                session_id=str(uuid4()),
            )

            # Second turn: repair attempt
            response2 = await self.agent_client.send_message(
                message=example.repair_message,
                session_id=response1.session_id,  # Same session for context
            )

            repairs_total += 1

            # Check if repair successful (agent understood correct intent)
            if response2.intent == example.intended_intent:
                repairs_successful += 1

        success_rate = repairs_successful / repairs_total

        # Check for regression
        prev_baseline = self._load_baseline("repair_success_rate")
        regression = (prev_baseline - success_rate) / prev_baseline > 0.05  # 5% regression

        logger.info(
            f"Repair success rate eval: {success_rate:.1%}",
            extra={
                "success_rate": success_rate,
                "baseline": prev_baseline,
                "regressed": regression,
            }
        )

        return EvalResult(
            metric="repair_success_rate",
            value=success_rate,
            target=0.80,
            regressed=regression,
        )
```

#### Metric 4: Average Turn Latency

```python
class AverageTurnLatencyEval:
    """
    Metric: Average E2E turn latency
    Target: <2000ms P95 (from ADR-0024)

    Tracks: Regression if P95 increases >10%
    """

    async def evaluate(self, test_dataset: LabeledDataset) -> EvalResult:
        """
        Evaluate turn latency

        Args:
            test_dataset: Representative turns for latency measurement

        Returns: EvalResult(p95_latency, trends)
        """
        latencies = []

        for example in test_dataset.examples:
            response = await self.agent_client.send_message(
                message=example.text,
                session_id=str(uuid4()),
                measure_latency=True,
            )
            latencies.append(response.latency_ms)

        # Calculate percentiles
        latencies.sort()
        p50 = latencies[int(0.50 * len(latencies))]
        p95 = latencies[int(0.95 * len(latencies))]
        p99 = latencies[int(0.99 * len(latencies))]

        # Check for regression
        prev_baseline_p95 = self._load_baseline("turn_latency_p95")
        regression = (p95 - prev_baseline_p95) / prev_baseline_p95 > 0.10  # 10% regression

        logger.info(
            f"Turn latency eval: P50={p50}ms, P95={p95}ms, P99={p99}ms",
            extra={
                "p50": p50,
                "p95": p95,
                "p99": p99,
                "baseline_p95": prev_baseline_p95,
                "regressed": regression,
            }
        )

        return EvalResult(
            metric="turn_latency_p95_ms",
            value=p95,
            target=2000,
            regressed=regression,
        )
```

#### Metric 5: User Satisfaction Proxy

```python
class UserSatisfactionProxyEval:
    """
    Metric: User satisfaction proxy metrics
    Target: <5% retry rate, <10% abandonment rate

    Proxies measured:
    - Retry Rate: User repeats request (agent misunderstood)
    - Abandonment Rate: User gives up (too many errors/clarifications)
    - Positive Sentiment: User thanks agent, positive emojis
    """

    async def evaluate(self, test_dataset: LabeledDataset) -> EvalResult:
        """
        Evaluate user satisfaction proxy metrics

        Args:
            test_dataset: Multi-turn examples with user feedback labels

        Returns: EvalResult(satisfaction_metrics, trends)
        """
        retry_count = 0
        abandon_count = 0
        positive_sentiment_count = 0
        total_turns = 0

        for example in test_dataset.examples:
            # Simulate multi-turn conversation
            session_id = str(uuid4())

            for turn_idx, turn_text in enumerate(example.turn_texts):
                response = await self.agent_client.send_message(
                    message=turn_text,
                    session_id=session_id,
                )

                total_turns += 1

                # Detect retry (user repeats similar request)
                if turn_idx > 0 and self._is_retry(turn_text, example.turn_texts[turn_idx - 1]):
                    retry_count += 1

                # Detect abandonment (user gives up)
                if turn_idx > 5 and self._is_abandonment(turn_text):
                    abandon_count += 1

                # Detect positive sentiment (thanks, emojis)
                if self._is_positive_sentiment(turn_text):
                    positive_sentiment_count += 1

        retry_rate = retry_count / total_turns
        abandon_rate = abandon_count / total_turns
        positive_sentiment_rate = positive_sentiment_count / total_turns

        # Check for regression
        prev_retry_baseline = self._load_baseline("retry_rate")
        prev_abandon_baseline = self._load_baseline("abandon_rate")

        retry_regression = (retry_rate - prev_retry_baseline) / prev_retry_baseline > 0.10
        abandon_regression = (abandon_rate - prev_abandon_baseline) / prev_abandon_baseline > 0.10

        logger.info(
            f"User satisfaction proxy eval:",
            extra={
                "retry_rate": retry_rate,
                "abandon_rate": abandon_rate,
                "positive_sentiment_rate": positive_sentiment_rate,
                "retry_regressed": retry_regression,
                "abandon_regressed": abandon_regression,
            }
        )

        return EvalResult(
            metric="user_satisfaction_proxy",
            value={
                "retry_rate": retry_rate,
                "abandon_rate": abandon_rate,
                "positive_sentiment_rate": positive_sentiment_rate,
            },
            targets={
                "retry_rate": 0.05,
                "abandon_rate": 0.10,
                "positive_sentiment_rate": 0.30,
            },
            regressed=retry_regression or abandon_regression,
        )

    def _is_retry(self, current_text: str, previous_text: str) -> bool:
        """Detect if user is retrying (semantic similarity >0.7)"""
        similarity = self._semantic_similarity(current_text, previous_text)
        return 0.6 < similarity < 0.95  # Similar but not identical

    def _is_abandonment(self, text: str) -> bool:
        """Detect if user is giving up"""
        abandon_phrases = ["nevermind", "forget it", "never mind", "give up", "doesn't matter"]
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in abandon_phrases)

    def _is_positive_sentiment(self, text: str) -> bool:
        """Detect positive sentiment"""
        positive_phrases = ["thank", "thanks", "appreciate", "great", "awesome", "perfect", "love"]
        positive_emojis = ["ðŸ‘", "ðŸ˜Š", "ðŸŽ‰", "â¤ï¸"]
        text_lower = text.lower()

        has_positive_phrase = any(phrase in text_lower for phrase in positive_phrases)
        has_positive_emoji = any(emoji in text for emoji in positive_emojis)

        return has_positive_phrase or has_positive_emoji

    def _semantic_similarity(self, text1: str, text2: str) -> float:
        """Compute semantic similarity (cosine distance of embeddings)"""
        # Use sentence transformer for efficiency
        import sentence_transformers
        model = sentence_transformers.SentenceTransformer('all-MiniLM-L6-v2')

        emb1 = model.encode(text1)
        emb2 = model.encode(text2)

        # Cosine similarity
        import numpy as np
        return float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2)))
```

### Regression Report Generation

```python
class RegressionReport:
    """Generate comprehensive regression eval report"""

    async def generate_report(
        self,
        evals: List[EvalResult],
        compare_baseline: bool = True,
    ) -> RegressionReportModel:
        """
        Generate regression report with metrics, trends, alerts

        Returns: Report (Markdown + JSON)
        """
        report = RegressionReportModel(
            timestamp=now(),
            evals=evals,
            regressions=[e for e in evals if e.regressed],
        )

        # Format as Markdown
        markdown = f"""
# Regression Eval Report
**Generated:** {report.timestamp}

## Summary
- âœ… Evals Passed: {len([e for e in evals if not e.regressed])}/{len(evals)}
- âš ï¸ Regressions Detected: {len(report.regressions)}

## Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
"""

        for eval_result in evals:
            status = "âœ… PASS" if not eval_result.regressed else "âŒ FAIL"
            markdown += f"| {eval_result.metric} | {eval_result.value:.1%} | {eval_result.target:.1%} | {status} |\n"

        # Alert for regressions
        if report.regressions:
            markdown += "\n## ðŸš¨ Regression Alerts\n\n"
            for reg in report.regressions:
                markdown += f"- **{reg.metric}** regressed: {reg.value:.1%} (was {reg.baseline:.1%})\n"

        report.markdown = markdown
        return report
```

---

## Alternatives Considered

| Alternative | Complexity | Developer Friction | Regression Detection | Synthetic Users | K1 Fit |
|-------------|-----------|-------------------|----------------------|-----------------|--------|
| **1. Manual Testing** | Low | âš ï¸ High | âŒ No | âŒ No | 2/10 |
| **2. WARD Only** | Low | âœ… Low | âš ï¸ Manual | âŒ No | 6/10 |
| **3. LangSmith Cloud** | Medium | âœ… Medium | âœ… Yes | âœ… Yes | 7/10 |
| **4. Conversation Simulator + Regression Evals (ADR-0066)** | Medium | âœ… Low | âœ… Yes | âœ… Yes | **9/10** |
| **5. Full Simulation (with tool execution)** | High | âŒ Very High | âœ… Comprehensive | âœ… Yes | 4/10 |

**Decision: Alternative 4 (ADR-0066) selected** - Optimal balance of developer ergonomics, regression detection, and realistic testing.

---

## Consequences

### âœ… Positive Consequences

1. **Faster Feedback Loop:** Developers test changes locally in <5 minutes
2. **Regression Detection:** Automated quality regression detection (5%+ drop triggers alert)
3. **Diverse Testing:** 5+ synthetic personas test diverse user behaviors
4. **Reproducible Testing:** Same scenarios run identically on all machines
5. **Quality Metrics Tracked:** Intent accuracy, clarification rate, repair success, latency trends

### âŒ Negative Consequences

1. **Synthetic Data Bias:** LLM-generated messages may not reflect real user behavior
2. **Maintenance Overhead:** Persona updates, scenario creation ongoing effort
3. **Latency Variability:** Tool calls have non-deterministic latency (complicate performance regression detection)
4. **Limited Coverage:** Synthetic scenarios cannot cover all real-world edge cases

---

## Implementation Plan

**Phase 1 (Week 1):** Conversation simulator framework + basic personas
**Phase 2 (Week 2):** Regression eval suite + metrics collection
**Phase 3 (Week 3):** Integration into CI/CD pipeline
**Phase 4 (Week 4):** Baseline calibration and tuning

**Time Estimate:** 4 weeks

---

## Configuration

```yaml
# k1/config/testing.yml

testing:
  conversation_simulator:
    agent_timeout_ms: 5000
    max_retries: 3
    personas:
      - CasualUserPersona
      - TechnicalUserPersona
      - ConfusedUserPersona
      - AdversarialUserPersona

  regression_evals:
    thresholds:
      intent_classification_accuracy: 0.90
      clarification_rate: 0.15
      repair_success_rate: 0.80
      turn_latency_p95_ms: 2000
      retry_rate: 0.05
      abandon_rate: 0.10

    regression_thresholds:
      intent_accuracy_drop: 0.05  # 5% drop = regression alert
      clarification_rate_increase: 0.02  # 2% increase = regression alert
      latency_increase: 0.10  # 10% increase = regression alert
      retry_rate_increase: 0.10  # 10% increase = regression alert
```

---

## Research Citations

1. Brown et al. (2020) - "Language Models are Few-Shot Learners" - Few-shot data generation
2. Purwana et al. (2022) - "Dialogue State Tracking with Machine Reading Comprehension" - Conversation simulation
3. Zhang et al. (2020) - "BERTScore: Evaluating Text Generation with BERT" - Text quality metrics
4. Fu et al. (2023) - "GPT-4 Evaluates GPT-4" - LLM-as-Evaluator
5. Papineni et al. (2002) - "BLEU: Automatic Evaluation of Machine Translation" - Similarity metrics

---

**ADR-0066 END**

