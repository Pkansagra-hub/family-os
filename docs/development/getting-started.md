# Getting Started with K1 Development

## Prerequisites

Before you begin developing for K1, ensure you have the following installed:

- **Python 3.11+**: K1 requires Python 3.11 or higher
- **Git**: For version control and collaboration
- **FlatBuffers compiler**: For schema compilation (`flatc`)
- **WARD test framework**: For running K1's test suite

### System Requirements

- **OS**: Linux (Ubuntu 22.04+), macOS (12+), or Windows 10/11 with WSL2
- **RAM**: Minimum 8GB, recommended 16GB+
- **Disk**: 10GB free space for K1 + dependencies
- **CPU**: Multi-core processor recommended for parallel testing

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/intelligence_module.git
cd intelligence_module
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip
```

### 3. Install Dependencies

```bash
# Install K1 dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
```

### 4. Install FlatBuffers Compiler

```bash
# On Ubuntu/Debian:
sudo apt-get install flatbuffers-compiler

# On macOS (with Homebrew):
brew install flatbuffers

# On Windows:
# Download from https://github.com/google/flatbuffers/releases
# Add to PATH
```

### 5. Compile FlatBuffers Schemas

```bash
# Compile all 76 FlatBuffers schemas
python scripts/compile_schemas.py

# Verify compilation
python scripts/verify_schemas.py
```

### 6. Install WARD Test Framework

```bash
# WARD is included in requirements-dev.txt
# Verify installation:
python -m ward --version
```

## Verify Installation

Run the verification script to ensure everything is set up correctly:

```bash
# Run verification checks
python scripts/verify_installation.py
```

Expected output:
```
✓ Python version: 3.11.x
✓ FlatBuffers compiler: flatc version x.x.x
✓ WARD test framework: ward x.x.x
✓ All 76 FlatBuffers schemas compiled
✓ K1 modules importable
✓ Test suite discovered: 250+ tests

Installation complete! Ready to develop K1.
```

## Run Tests

Verify your setup by running the K1 test suite:

```bash
# Run all tests
python -m ward test --path tests/

# Run specific module tests
python -m ward test --path tests/agent_fabric/
python -m ward test --path tests/orchestrator/

# Run with verbose output
python -m ward test --path tests/ --verbose
```

Expected results:
- **Total tests**: 250+ tests
- **Pass rate**: 100% (all tests should pass)
- **Coverage**: ≥85% overall, ≥90% core modules

## Development Workflow

### 1. Create Feature Branch

```bash
# Create feature branch from develop
git checkout develop
git pull origin develop
git checkout -b feature/123-your-feature-name
```

### 2. Make Changes

- **Edit code**: Follow K1 patterns (Actor Model, MPST, Capabilities, etc.)
- **Update tests**: Write WARD tests for new functionality (≥85% coverage)
- **Update docs**: Document changes in relevant docs/ files
- **Update diagrams**: Modify architecture diagrams if structure changed

### 3. Run Tests Locally

```bash
# Run tests for affected modules
python -m ward test --path tests/your_module/

# Run all tests
python -m ward test --path tests/

# Check coverage
python -m ward test --path tests/ --coverage
```

### 4. Commit Changes

```bash
# Stage changes
git add .

# Commit with Conventional Commits format
git commit -m "feat: add new agent capability for tool calls

- Implement TOOL_CALL capability in agent fabric
- Add WARD tests with 90% coverage
- Update agent_lifecycle_fsm.mmd diagram
- Document in ADR-0042-agent-capabilities.md

Closes #123"
```

### 5. Push and Create PR

```bash
# Push to remote
git push origin feature/123-your-feature-name

# Create PR on GitHub
# Follow PR template in .github/PULL_REQUEST_TEMPLATE.md
```

## Project Structure

```
intelligence_module/
├── .github/                    # GitHub workflows, instructions, chatmodes
├── architecture_diagrams/      # 11 Mermaid .mmd diagrams
├── docs/                       # All documentation
│   ├── architecture/          # ADRs, patterns, diagram docs
│   ├── api/                   # API documentation
│   ├── development/           # Development guides (you are here)
│   └── deployment/            # Deployment guides
├── k1/                        # K1 kernel source code (future)
│   ├── agent_fabric/          # Agent lifecycle management
│   ├── orchestrator/          # 3-phase orchestration
│   ├── planner/               # 4-stage planning pipeline
│   ├── protocol_monitor/      # MPST validation
│   ├── learning_loop/         # Adaptive intelligence
│   ├── session_state/         # State management
│   ├── infrastructure/        # KV cache, thermal, batching
│   └── config/                # Configuration YAML files
├── tests/                     # WARD test suites (future)
│   ├── agent_fabric/
│   ├── orchestrator/
│   └── integration/
├── scripts/                   # Development scripts
├── requirements.txt           # Production dependencies
└── requirements-dev.txt       # Development dependencies
```

## Configuration

K1 uses YAML configuration files in `k1/config/`:

- `agent_fabric.yml`: Agent lifecycle configuration
- `orchestrator.yml`: Orchestration configuration
- `planner.yml`: Planning pipeline configuration
- `protocol_monitor.yml`: MPST protocol configuration
- `learning_loop.yml`: Adaptive learning configuration
- `session_state.yml`: State management configuration
- `infrastructure.yml`: Infrastructure configuration

### Environment Variables

Set these environment variables for development:

```bash
export K1_ENV=development
export K1_LOG_LEVEL=DEBUG
export K1_METRICS_PORT=9090
export K1_TRACE_ENABLED=true
```

## IDE Setup

### VS Code (Recommended)

Install recommended extensions:
- **Python** (ms-python.python)
- **Pylance** (ms-python.vscode-pylance)
- **WARD Test Explorer** (if available)
- **Mermaid Preview** (for viewing .mmd diagrams)

Open workspace settings (`.vscode/settings.json`):
```json
{
  "python.testing.wardEnabled": true,
  "python.testing.wardArgs": ["--path", "tests/"],
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "editor.formatOnSave": true,
  "python.formatting.provider": "black"
}
```

### PyCharm

1. Open project in PyCharm
2. Configure Python interpreter (venv)
3. Enable WARD test runner in settings
4. Configure code style: PEP 8

## Troubleshooting

### FlatBuffers compilation fails

**Issue**: `flatc: command not found`

**Solution**:
```bash
# Install FlatBuffers compiler
# See step 4 in Installation Steps above
```

### WARD tests not discovered

**Issue**: `No tests found`

**Solution**:
```bash
# Ensure you're in project root
cd intelligence_module

# Run with explicit path
python -m ward test --path tests/

# Check if tests directory exists
ls -la tests/
```

### Import errors for K1 modules

**Issue**: `ModuleNotFoundError: No module named 'k1'`

**Solution**:
```bash
# Install K1 in editable mode
pip install -e .

# Or add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Python version mismatch

**Issue**: `K1 requires Python 3.11+`

**Solution**:
```bash
# Check Python version
python --version

# Install Python 3.11+ if needed
# Use pyenv for multiple Python versions
pyenv install 3.11.x
pyenv local 3.11.x
```

## Next Steps

- **[Testing Guide](./testing-guide.md)**: Learn how to write WARD tests for K1
- **[Contribution Guide](./contribution-guide.md)**: Understand the full contribution workflow
- **[Debugging Guide](./debugging-guide.md)**: Debug K1 with traces, metrics, and logs
- **[Architecture Overview](../architecture/)**: Understand K1's architectural patterns

## Getting Help

- **Architecture questions**: Review [docs/whiteboard.md](../whiteboard.md) (21,123 lines)
- **Module structure**: Check [docs/k1_module_analysis.md](../k1_module_analysis.md)
- **Open questions**: Browse [docs/questions.md](../questions.md)
- **GitHub Issues**: Create issue with `question` label
