# 🚀 Chat Experience PoC - Complete K1 System

**Project**: K1 Intelligence Module - Complete Chat Experience Architecture
**Goal**: Build end-to-end PoC demonstrating full K1 system without actual K0 persistence
**LLM Provider**: Groq API
**Validation**: Mock K0/MCP servers validate request format only
**Status**: 🔨 In Development (Milestone 1: Foundation)

---

## 📊 Architecture Overview

### Layers

| Layer | Components | Status |
|-------|-----------|--------|
| **L1: Input** | Intent Router, SessionState Bootstrap | 🔴 Not Started |
| **L2: Orchestration** | Orchestrator (3-phase), Planner (4-stage) | 🔴 Not Started |
| **L3: Execution** | Concierge, Specialists, Writers (58 agents) | 🔴 Not Started |
| **L4: Runtime** | SessionState, DeltaBus, Mailbox, Lifecycle FSM | 🔴 Not Started |
| **L5: Infrastructure** | Agent Factory, K0 Bridge, Tool/Prompt Registry | 🟡 In Progress |

### Key Features

- **2 Interaction Paths**:
  - PATH 1: Specialist Agents (Query/Retrieval from K0)
  - PATH 2: Planner Path (Action/Execution with DAG)
- **Full SessionState** with field-level delta tracking
- **Agent Lifecycle FSM** (6 states: PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
- **Proactive Flow** with temporal scheduling and time-based triggers
- **User Knowledge Graph** for personalization and user self-model
- **Mock K0/MCP** validation (format checking, no actual persistence)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Groq API key (get at [console.groq.com](https://console.groq.com))

### Installation

```bash
# 1. Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate     # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure Groq API
cp .env.template .env
# Edit .env and add your GROQ_API_KEY

# 4. Run tests
python -m pytest tests/ -v
```

### Configuration

Configuration is defined in two places (environment variables override YAML):

1. **`config/poc_config.yml`** - YAML configuration (session, performance, agent, K0 bridge, temporal settings)
2. **Environment variables** - Prefix `K1_POC_` (e.g., `K1_POC_AGENT_POOL_SIZE=5`)

Load configuration in code:

```python
from config.config_loader import get_config

config = get_config()
print(config.session.session_timeout_seconds)  # 600
print(config.agent.agent_pool_size)             # 5
```

---

## 📁 Project Structure

```
poc/chat_experience_poc/
├── l1_input/                    # Layer 1: Intent routing
├── l2_orchestration/            # Layer 2: Orchestration (3-phase, Planner)
├── l3_execution/
│   └── agents/                  # Layer 3: Agent implementations
├── l4_runtime/                  # Layer 4: SessionState, DeltaBus, Mailbox, Lifecycle
├── l5_infrastructure/           # Layer 5: Registries, Temporal, K0 Bridge, Groq client
│   ├── registries/              # Tool and Prompt registries
│   ├── user_kg/                 # User Knowledge Graph
│   ├── temporal/                # Temporal module (scheduling)
│   ├── k0_bridge/               # K0 Bridge communication
│   └── groq_client.py           # Groq API wrapper
├── models/
│   └── config_models.py         # Pydantic configuration models
├── mock_services/               # Mock K0 API, Mock MCP, Mock SSE
├── config/
│   ├── poc_config.yml           # Main configuration (YAML)
│   ├── groq_config.py           # Groq model/temperature settings
│   └── config_loader.py         # Configuration loading and merging
├── tests/                       # Integration and unit tests
├── main.py                      # Entry point (extensible for testing)
├── requirements.txt             # Python dependencies
├── .env.template                # Environment variables template
└── README.md                    # This file
```

---

## 🎯 Milestones

### ✅ Milestone 1: Foundation & Infrastructure (In Progress)

**Goal**: Set up project scaffolding, external integrations, and core registries

- ✅ **Epic 1.1**: Project Scaffolding & Groq API Integration
  - ✅ Issue 1.1.1: Initialize PoC Project Structure
  - ✅ Issue 1.1.2: Install Dependencies & Configure Groq API
  - ✅ Issue 1.1.3: Create Base Configuration System
- 🔴 **Epic 1.2**: MCP Tool Registry & Mock MCP Servers
- 🔴 **Epic 1.3**: Prompt Registry
- 🔴 **Epic 1.4**: User Knowledge Graph Setup
- 🔴 **Epic 1.5**: Temporal Module (Scheduling & Time Context)

### 🔴 Milestone 2: Layer 4 - Runtime Core

Build SessionState, DeltaBus, Mailbox, Agent Lifecycle FSM

- **Epic 2.1**: SessionState (6-Section Working Memory)
- **Epic 2.2**: DeltaBus (In-Process Event Bus)
- **Epic 2.3**: Mailbox System (MPSC with 4 Priority Levels)
- **Epic 2.4**: Agent Lifecycle FSM (6-State Machine)

### 🔴 Milestone 3: Layer 5 - Infrastructure

Build agent spawning, K0 bridge communication, mock K0 services

- **Epic 3.1**: Agent Factory (Spawn Agents with Prompt + Tools + Context)
- **Epic 3.2**: K0 Bridge (SessionState Deltas → Mock K0 Validation)
- **Epic 3.3**: Mock K0 SSE Server (Proactive Ticks)

### 🔴 Milestone 4: Layers 2-3 - Orchestration & Execution

Build Orchestrator (3-phase), Planner (4-stage), and Agent implementations

### 🔴 Milestone 5: Testing & Validation

End-to-end tests, performance validation, documentation

---

## 📚 Configuration Reference

### Session Settings

```yaml
session:
  session_timeout_seconds: 600     # Idle timeout (10 min)
  max_turns: 100                   # Max conversation turns
  max_session_memory_mb: 50.0      # Memory per session
```

### Performance Budgets (P95)

```yaml
performance:
  ttft_budget_ms: 150              # Time To First Token
  e2e_latency_budget_ms: 2000      # End-to-End latency
  memory_budget_mb: 500.0          # Total system memory
```

### Agent Configuration

```yaml
agent:
  max_concurrent_agents: 3         # Max agents per session
  agent_pool_size: 5               # Pooled agents per type
  agent_idle_ttl_seconds: 600      # Idle timeout (10 min)
  warming_timeout_seconds: 35      # WARMING state timeout
```

### K0 Bridge Configuration

```yaml
k0_bridge:
  batch_interval_ms: 250           # Flush interval (250ms)
  batch_size_max_deltas: 100       # Max deltas per batch
  batch_size_max_bytes: 65536      # Max batch size (64KB)
  k0_api_url: "http://localhost:8003"
  k0_timeout_seconds: 10.0
  k0_max_retries: 3
```

### Temporal Configuration

```yaml
temporal:
  tick_interval_seconds: 60        # Scheduler interval (1 min)
  max_triggers: 1000               # Max active triggers
```

---

## 🔗 Integration with K1

This PoC mirrors the production K1 architecture:

- **ADRs**: References to K1 Architecture Decision Records
  - ADR-0005: Agent architecture
  - ADR-0017: SessionState design
  - ADR-0019: Delta batching and serialization
  - ADR-0073: Lifecycle FSM with IDLE pooling

- **References**:
  - K1 whiteboard: `docs/whiteboard/chat_experience.md`
  - K1 module analysis: `docs/k1_module_analysis.md`
  - K1 config pattern: `k1/config/*.yml`

---

## 🧪 Testing

Run tests with pytest:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_config_loader.py -v

# Run with coverage
python -m pytest tests/ --cov=poc/chat_experience_poc --cov-report=html
```

---

## 📖 Documentation

- **Implementation Plan**: `docs/plans/chat_experience_poc_plan.md`
- **Configuration**: This README + `config/poc_config.yml`
- **API References**:
  - Groq API: https://console.groq.com/docs
  - FastAPI: https://fastapi.tiangolo.com
  - Pydantic: https://docs.pydantic.dev

---

## 🤝 Contributing

When adding new components:

1. Follow the 5-step gated process from `.github/copilot-instructions.md`
2. Update configuration models in `models/config_models.py`
3. Update `config/poc_config.yml` with new defaults
4. Add tests in `tests/`
5. Update this README with new features

---

## 📝 Notes

- **No Simulation Code**: No `asyncio.sleep()`, `time.sleep()`, or mock delays
- **Real Components**: Use actual Groq API, not mock responses (except Mock K0/MCP)
- **ADR-Driven**: All major changes require ADR review
- **Performance First**: Monitor latency budgets and token usage

---

## 🎓 Related Reading

- K1 Whiteboard: `docs/whiteboard/chat_experience.md`
- K1 Architecture: `docs/k1_module_analysis.md`
- Copilot Rules: `.github/copilot-instructions.md`
- Service Design: `.github/instructions/service-design.instructions.md`

---

**Last Updated**: 2025-11-05
**Project Status**: 🟡 In Progress (Milestone 1 - Foundation)
