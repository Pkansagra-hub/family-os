# Contribution Guide

## Welcome Contributors!

Thank you for your interest in contributing to K1 Intelligence Module. This guide will help you understand our contribution workflow, coding standards, and how to get your changes merged.

## Getting Started

Before contributing:

1. **Read [Getting Started](./getting-started.md)**: Set up your development environment
2. **Review [Architecture](../architecture/)**: Understand K1's design patterns
3. **Check [Open Issues](https://github.com/your-org/intelligence_module/issues)**: Find something to work on
4. **Read [Testing Guide](./testing-guide.md)**: Learn how to write WARD tests

## Contribution Workflow

### 1. Find or Create an Issue

All contributions should be linked to an issue:

- **Bug fixes**: Create issue with `bug` label
- **New features**: Create issue with `enhancement` label
- **Documentation**: Create issue with `documentation` label
- **Refactoring**: Create issue with `refactoring` label

**Issue template example:**
```markdown
**Issue Type**: Bug / Enhancement / Documentation / Refactoring

**Description**: [Clear description of the problem or feature]

**Affected Modules**: [List modules from k1_module_analysis.md]

**Related Diagrams**: [Link to architecture diagrams if applicable]

**Acceptance Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Tests added with ≥85% coverage
- [ ] Documentation updated
```

### 2. Fork and Clone

```bash
# Fork the repository on GitHub

# Clone your fork
git clone https://github.com/your-username/intelligence_module.git
cd intelligence_module

# Add upstream remote
git remote add upstream https://github.com/your-org/intelligence_module.git

# Verify remotes
git remote -v
```

### 3. Create Feature Branch

```bash
# Update develop branch
git checkout develop
git pull upstream develop

# Create feature branch
git checkout -b feature/123-short-description
# Or for bugs:
git checkout -b fix/456-short-description
```

**Branch naming conventions:**
- `feature/<issue-number>-<description>`: New features
- `fix/<issue-number>-<description>`: Bug fixes
- `docs/<description>`: Documentation updates
- `refactor/<description>`: Code refactoring
- `test/<description>`: Test additions

### 4. Make Changes

Follow K1 development standards:

#### Code Changes

- **Architecture-first**: Create/update ADRs for architectural changes
- **Diagram updates**: Update Mermaid diagrams if structure changes
- **Follow patterns**: Actor Model, MPST, Capabilities, SEDA, Saga, Contract Net
- **Module boundaries**: Respect 5-layer architecture (see k1_module_analysis.md)
- **FlatBuffers**: Use FlatBuffers for all serialization (76 schemas)
- **Zero tolerance**: NO sleep calls, NO simulations, NO mock theater

#### Test Changes

- **WARD framework**: Write integration tests with real components
- **Coverage**: Achieve ≥85% overall, ≥90% for core modules
- **Performance**: Validate against P95 budgets
- **Error paths**: Test all error conditions

#### Documentation Changes

- **ADRs**: Document architectural decisions in `docs/architecture/decisions/`
- **API docs**: Update `docs/api/` for interface changes
- **Inline docs**: Add docstrings for all public functions/classes
- **README updates**: Update relevant README files

### 5. Commit Changes

Use **Conventional Commits** format:

```bash
git add .

git commit -m "feat: add agent capability for tool execution

- Implement TOOL_CALL capability in agent fabric
- Add capability checking in protocol monitor
- Write WARD tests with 92% coverage for agent_fabric
- Update k1_agent_lifecycle_fsm.mmd diagram
- Document in ADR-0042-agent-capabilities.md

Performance:
- Tool call latency: 2800ms (P95 budget: 3000ms)
- Memory per agent: +5MB (within 50MB budget)

Closes #123"
```

**Commit message format:**
```
<type>: <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring
- `test`: Test additions
- `perf`: Performance improvements
- `chore`: Build/tooling changes

### 6. Run Tests Locally

```bash
# Run tests for affected modules
python -m ward test --path tests/agent_fabric/

# Run all tests
python -m ward test --path tests/

# Check coverage
python -m ward test --path tests/ --coverage

# Verify no lint errors
pylint k1/ tests/
```

**All tests must pass before pushing.**

### 7. Push to Your Fork

```bash
# Push feature branch to your fork
git push origin feature/123-short-description
```

### 8. Create Pull Request

Create PR on GitHub with this structure:

---

**Title**: `feat: Add agent capability for tool execution (#123)`

**Description**:

## Summary

Implements TOOL_CALL capability for agents in agent fabric, enabling fine-grained access control for tool execution.

## Changes

### Code Changes
- **Module**: `k1/agent_fabric/capabilities.py`
  - Added `TOOL_CALL` capability enum
  - Implemented capability checking in `Agent.has_capability()`
- **Module**: `k1/protocol_monitor/tool_call_protocol.py`
  - Added capability check in REQUESTED → AUTHORIZED transition
  - Return `UNAUTHORIZED` if agent lacks capability

### Test Changes
- **Tests**: `tests/agent_fabric/test_capabilities.py`
  - Added 12 tests for capability checking
  - Coverage: 92% for agent_fabric module
- **Tests**: `tests/protocol_monitor/test_tool_call_protocol.py`
  - Added 8 tests for authorization flow
  - Coverage: 90% for protocol_monitor module

### Documentation Changes
- **ADR**: [ADR-0042-agent-capabilities.md](docs/architecture/decisions/0042-agent-capabilities.md)
- **Diagram**: Updated `k1_agent_lifecycle_fsm.mmd` with capability annotations
- **API Docs**: Updated agent API in `docs/api/flatbuffers/agent_state.md`

## Architecture Impact

**Affected Modules** (from k1_module_analysis.md):
- Layer 1 - Core Kernel: `agent_fabric/` (12 modules)
- Layer 1 - Core Kernel: `protocol_monitor/` (12 modules)

**Diagrams Updated**:
- `architecture_diagrams/k1_agent_lifecycle_fsm.mmd`

**Performance**:
- Tool call latency: 2800ms P95 (budget: 3000ms) ✅
- Capability check overhead: <1ms ✅
- Memory per agent: +5MB (total: 48MB, budget: 50MB) ✅

## Testing Evidence

```
WARD Test Results:
- Total tests: 20 new tests
- All tests passed: ✅
- Coverage: 92% agent_fabric, 90% protocol_monitor
- Performance validated against P95 budgets
```

## Checklist

- [x] Architecture diagrams updated (k1_agent_lifecycle_fsm.mmd)
- [x] ADR created (0042-agent-capabilities.md)
- [x] WARD tests written and passing (≥85% coverage achieved)
- [x] Documentation updated (API docs, inline docs)
- [x] Performance budgets respected (all within limits)
- [x] No simulation code (zero tolerance policy)
- [x] Code follows K1 patterns (Capabilities pattern from Dennis 1966)
- [x] Observability added (metrics: `capability_checks_total`, `unauthorized_tool_calls_total`)

## Related Issues

Closes #123

---

### 9. Code Review

Your PR will be reviewed by maintainers:

**Review criteria:**
- ✅ Architecture diagrams updated (if applicable)
- ✅ ADR created/updated (if architectural change)
- ✅ WARD tests passing with ≥85% coverage
- ✅ Documentation updated
- ✅ Performance budgets respected
- ✅ No simulation code
- ✅ Code follows K1 patterns
- ✅ Observability added (metrics, tracing, logging)

**Respond to feedback:**
```bash
# Make requested changes
git add .
git commit -m "refactor: address code review feedback"
git push origin feature/123-short-description
```

### 10. Merge

Once approved, maintainers will merge your PR:
- **Squash and merge**: Multiple commits squashed into one
- **Merge to develop**: PRs merge to `develop` branch
- **Release to main**: Periodic releases from `develop` to `main`

## Coding Standards

### Python Style

- **PEP 8**: Follow Python style guide
- **Type hints**: Use type annotations for all functions
- **Docstrings**: Google-style docstrings for all public APIs
- **Naming**: Clear, descriptive names (no abbreviations)
- **Imports**: Organized (stdlib → third-party → local)

**Example:**
```python
"""
Module: k1.agent_fabric.capabilities
Purpose: Capability-based access control for agents

Research: Capabilities (Dennis & Van Horn 1966)
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import asyncio

class Capability(Enum):
    """Agent capabilities for fine-grained access control"""
    TOOL_CALL = "TOOL_CALL"
    K0_WRITE = "K0_WRITE"
    K0_READ = "K0_READ"
    MODEL_ACCESS = "MODEL_ACCESS"
    SESSION_MUTATE = "SESSION_MUTATE"

@dataclass
class Agent:
    """Agent with capability-based access control"""
    agent_id: str
    capabilities: List[Capability]

    def has_capability(self, capability: Capability) -> bool:
        """
        Check if agent has specific capability.

        Args:
            capability: Capability to check

        Returns:
            True if agent has capability, False otherwise

        Example:
            >>> agent = Agent(agent_id="agent-1", capabilities=[Capability.TOOL_CALL])
            >>> agent.has_capability(Capability.TOOL_CALL)
            True
        """
        return capability in self.capabilities
```

### Testing Standards

- **Integration focus**: Integration tests > unit tests
- **Real components**: No mocking K1 components
- **WARD framework**: Use WARD test framework
- **Coverage**: ≥85% overall, ≥90% core modules
- **Performance**: Validate against P95 budgets
- **Error paths**: Test all error conditions

See [Testing Guide](./testing-guide.md) for details.

### Documentation Standards

- **ADRs**: Use [ADR template](../architecture/decisions-K1/0000-template.md)
- **API docs**: Document all public APIs
- **Inline docs**: Docstrings for all functions/classes
- **Examples**: Include code examples
- **Diagrams**: Update architecture diagrams

See [documentation-standards.instructions.md](../../.github/instructions/documentation-standards.instructions.md) for details.

## Common Contribution Scenarios

### Scenario 1: Adding New Agent Capability

1. Create ADR: `docs/architecture/decisions/NNNN-new-capability.md`
2. Update FlatBuffers schema: `k1/schemas/agent/agent_state.fbs`
3. Implement capability: `k1/agent_fabric/capabilities.py`
4. Update protocol monitor: `k1/protocol_monitor/tool_call_protocol.py`
5. Write WARD tests: `tests/agent_fabric/test_capabilities.py`
6. Update diagram: `architecture_diagrams/k1_agent_lifecycle_fsm.mmd`
7. Document API: `docs/api/flatbuffers/agent_state.md`

### Scenario 2: Fixing Performance Issue

1. Profile component: Use `py-spy` or `cProfile`
2. Identify bottleneck: Review traces and metrics
3. Implement fix: Optimize hot path
4. Validate performance: Run WARD tests with timing
5. Update benchmarks: Document new P95 latency
6. Create PR: Show before/after performance

### Scenario 3: Updating Architecture Diagram

1. Edit diagram: `architecture_diagrams/k1_<component>_<type>.mmd`
2. Validate diagram: `mmd_validate(<diagram_id>)` via MCP
3. Update supporting docs: `docs/architecture/diagrams/<component>.md`
4. Update ADR: Reference diagram changes in related ADR
5. Regenerate renders: Export to PNG/SVG if needed
6. Create PR: Show diagram diff

## Getting Help

### Before Asking

1. **Search existing issues**: Check if question already asked
2. **Read documentation**: Review docs/whiteboard.md, k1_module_analysis.md
3. **Check ADRs**: See if architectural decision documented
4. **Review diagrams**: Study architecture diagrams

### How to Ask

Create issue with `question` label:

```markdown
**Question**: [Clear, specific question]

**Context**: [What you've tried, what you're trying to achieve]

**Relevant Modules**: [From k1_module_analysis.md]

**Related Diagrams**: [Link to architecture diagrams if applicable]
```

### Communication Channels

- **GitHub Issues**: Technical questions, bug reports, feature requests
- **GitHub Discussions**: General discussions, ideas, show-and-tell
- **Pull Requests**: Code review discussions

## Maintainer Guidelines

### For Maintainers Reviewing PRs

**Review checklist:**
- [ ] Architecture diagrams updated (if applicable)
- [ ] ADR created/updated (if architectural change)
- [ ] WARD tests passing with coverage ≥85%
- [ ] Documentation updated (API docs, inline docs, README)
- [ ] Performance budgets respected
- [ ] No simulation code (zero tolerance policy)
- [ ] Code follows K1 patterns and conventions
- [ ] Observability added (metrics, tracing, logging)
- [ ] Module boundaries respected (5-layer architecture)
- [ ] FlatBuffers used for serialization
- [ ] Error paths tested

**Feedback guidelines:**
- **Be specific**: Point to specific lines/files
- **Be constructive**: Suggest improvements, not just problems
- **Be respectful**: Assume good intent
- **Be educational**: Explain *why* changes needed

## License

By contributing to K1 Intelligence Module, you agree that your contributions become part of the FamilyOS Proprietary License described in [LICENSE](../../LICENSE).

## Thank You!

Thank you for contributing to K1 Intelligence Module. Your contributions help build a production-ready agentic orchestrator kernel!

---

**Next Steps:**
- **[Getting Started](./getting-started.md)**: Set up development environment
- **[Testing Guide](./testing-guide.md)**: Write WARD tests
- **[Debugging Guide](./debugging-guide.md)**: Debug K1 with traces and metrics
