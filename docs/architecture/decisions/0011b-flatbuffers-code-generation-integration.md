# ADR-0011b: FlatBuffers Code Generation & Integration

**Status:** Accepted
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0011: FlatBuffers Serialization](./0011-flatbuffers-serialization.md)

---

## Context

K1 requires automated code generation from FlatBuffers schemas to ensure:
1. **Type safety** through generated language bindings
2. **Cross-language consistency** (Python, C++, Rust)
3. **Build system integration** (CMake, Bazel, setup.py)
4. **CI/CD validation** (schema changes, breaking detection)

**Current State:**
- 76 FlatBuffers schemas across 5 architectural layers
- Multi-language codebase (Python K1 runtime, C++ K0 kernel, Rust MCP servers)
- Need for strict type checking (mypy, C++ concepts, Rust traits)

This ADR defines the code generation toolchain, build integration, and type safety guarantees.

---

## Decision

### 1. FlatBuffers Compiler (flatc)

#### 1.1 Version & Installation

**Version:** flatc v23.5.26 (stable release)

**Installation Methods:**

**Option 1: System Package Manager (Development)**
```bash
# Ubuntu/Debian
sudo apt-get install flatbuffers-compiler

# macOS
brew install flatbuffers

# Windows (Chocolatey)
choco install flatbuffers
```

**Option 2: Pre-built Binary (CI/CD)**
```bash
# Download from GitHub releases
FLATC_VERSION="23.5.26"
wget https://github.com/google/flatbuffers/releases/download/v${FLATC_VERSION}/flatc_linux_x64.zip
unzip flatc_linux_x64.zip
chmod +x flatc
sudo mv flatc /usr/local/bin/
```

**Option 3: Build from Source (Custom Builds)**
```bash
git clone https://github.com/google/flatbuffers.git
cd flatbuffers
cmake -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
sudo make install
```

#### 1.2 Compiler Flags

**Standard Flags:**
```bash
flatc \
  --python \                    # Generate Python bindings
  --cpp \                       # Generate C++ bindings
  --rust \                      # Generate Rust bindings
  --gen-object-api \            # Generate object-based API (Python/C++)
  --gen-mutable \               # Generate mutable API (C++)
  --gen-compare \               # Generate comparison operators
  --scoped-enums \              # Use scoped enums (C++)
  --reflect-names \             # Include field names for reflection
  --reflect-types \             # Include type info for reflection
  -o output_dir \               # Output directory
  schema.fbs                    # Input schema
```

**Performance Flags:**
```bash
flatc \
  --no-includes \               # Don't generate include directives (faster compilation)
  --no-fb-import \              # Don't import flatbuffers module (smaller code)
  --force-empty-vectors \       # Allow empty vectors (optimize memory)
  schema.fbs
```

---

### 2. Language Bindings

#### 2.1 Python Bindings (K1 Runtime)

**Generated Code Structure:**
```
k1/schemas/generated/python/
├── k1/
│   ├── __init__.py
│   ├── agent_fabric/
│   │   ├── __init__.py
│   │   ├── AgentState.py
│   │   ├── AgentCapability.py
│   │   └── AgentLifecycleState.py
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── TaskAnnouncement.py
│   │   ├── Proposal.py
│   │   └── Selection.py
│   └── session_state/
│       ├── __init__.py
│       ├── SessionState.py
│       ├── Beliefs.py
│       └── Scoreboard.py
└── flatbuffers/          # FlatBuffers runtime library
```

**Usage Example:**
```python
import flatbuffers
from k1.schemas.generated.python.k1.agent_fabric import (
    AgentState,
    AgentLifecycleState
)

# Serialization
def create_agent_state(agent_id: str, state: AgentLifecycleState.AgentLifecycleState) -> bytes:
    """Create AgentState FlatBuffer"""
    builder = flatbuffers.Builder(256)

    # Create string
    agent_id_offset = builder.CreateString(agent_id)

    # Create AgentState table
    AgentState.Start(builder)
    AgentState.AddAgentId(builder, agent_id_offset)
    AgentState.AddState(builder, state)
    AgentState.AddMemoryMb(builder, 512)
    state_offset = AgentState.End(builder)

    # Finish buffer
    builder.Finish(state_offset, file_identifier=b"AGST")
    return bytes(builder.Output())

# Deserialization (zero-copy)
def read_agent_state(buf: bytes) -> AgentState.AgentState:
    """Read AgentState from FlatBuffer (zero-copy)"""
    return AgentState.AgentState.GetRootAs(buf, 0)

# Usage
buf = create_agent_state("agent_xyz", AgentLifecycleState.AgentLifecycleState.ACTIVE)
state = read_agent_state(buf)

print(f"Agent ID: {state.AgentId().decode()}")
print(f"State: {state.State()}")
print(f"Memory: {state.MemoryMb()} MB")
```

**Type Hints (Python 3.11+):**
```python
# k1/schemas/types.py (type stub generation)

from typing import Optional
from k1.schemas.generated.python.k1.agent_fabric import AgentState

def serialize_agent_state(
    agent_id: str,
    state: int,  # AgentLifecycleState enum value
    memory_mb: int = 0
) -> bytes:
    """Type-safe AgentState serialization"""
    ...

def deserialize_agent_state(buf: bytes) -> AgentState.AgentState:
    """Type-safe AgentState deserialization"""
    ...
```

#### 2.2 C++ Bindings (K0 Kernel)

**Generated Code Structure:**
```
k1/schemas/generated/cpp/
├── k1/
│   ├── agent_fabric/
│   │   ├── agent_state_generated.h
│   │   ├── agent_capability_generated.h
│   │   └── agent_lifecycle_state_generated.h
│   ├── orchestrator/
│   │   ├── task_announcement_generated.h
│   │   ├── proposal_generated.h
│   │   └── selection_generated.h
│   └── session_state/
│       ├── session_state_generated.h
│       ├── beliefs_generated.h
│       └── scoreboard_generated.h
└── flatbuffers/          # FlatBuffers runtime library
```

**Usage Example (C++17):**
```cpp
#include <flatbuffers/flatbuffers.h>
#include "k1/agent_fabric/agent_state_generated.h"

// Serialization
std::vector<uint8_t> create_agent_state(
    const std::string& agent_id,
    k1::agent_fabric::AgentLifecycleState state
) {
    flatbuffers::FlatBufferBuilder builder(256);

    // Create string
    auto agent_id_offset = builder.CreateString(agent_id);

    // Create AgentState table
    auto state_offset = k1::agent_fabric::CreateAgentState(
        builder,
        agent_id_offset,
        state,
        512  // memory_mb
    );

    // Finish buffer
    builder.Finish(state_offset, "AGST");

    // Return buffer
    return std::vector<uint8_t>(
        builder.GetBufferPointer(),
        builder.GetBufferPointer() + builder.GetSize()
    );
}

// Deserialization (zero-copy)
const k1::agent_fabric::AgentState* read_agent_state(const uint8_t* buf) {
    return k1::agent_fabric::GetAgentState(buf);
}

// Usage
auto buf = create_agent_state("agent_xyz", k1::agent_fabric::AgentLifecycleState_ACTIVE);
auto state = read_agent_state(buf.data());

std::cout << "Agent ID: " << state->agent_id()->str() << std::endl;
std::cout << "State: " << state->state() << std::endl;
std::cout << "Memory: " << state->memory_mb() << " MB" << std::endl;
```

**Type Safety (C++20 Concepts):**
```cpp
// k1/schemas/concepts.hpp

#include <concepts>
#include <flatbuffers/flatbuffers.h>

namespace k1::schemas {

// Concept: FlatBuffers table type
template<typename T>
concept FlatBuffersTable = requires(const uint8_t* buf) {
    { T::GetRoot(buf) } -> std::convertible_to<const T*>;
};

// Concept: FlatBuffers builder
template<typename T>
concept FlatBuffersBuilder = requires(flatbuffers::FlatBufferBuilder& builder) {
    { T::Pack(builder, nullptr) } -> std::convertible_to<flatbuffers::Offset<T>>;
};

// Type-safe serialization
template<FlatBuffersTable T>
std::vector<uint8_t> serialize(const T* obj) {
    flatbuffers::FlatBufferBuilder builder(256);
    auto offset = T::Pack(builder, obj);
    builder.Finish(offset);
    return std::vector<uint8_t>(
        builder.GetBufferPointer(),
        builder.GetBufferPointer() + builder.GetSize()
    );
}

// Type-safe deserialization
template<FlatBuffersTable T>
const T* deserialize(const uint8_t* buf) {
    return T::GetRoot(buf);
}

}  // namespace k1::schemas
```

#### 2.3 Rust Bindings (Future MCP Servers)

**Generated Code Structure:**
```
k1/schemas/generated/rust/
├── src/
│   ├── lib.rs
│   ├── agent_fabric/
│   │   ├── mod.rs
│   │   ├── agent_state_generated.rs
│   │   ├── agent_capability_generated.rs
│   │   └── agent_lifecycle_state_generated.rs
│   ├── orchestrator/
│   │   ├── mod.rs
│   │   ├── task_announcement_generated.rs
│   │   ├── proposal_generated.rs
│   │   └── selection_generated.rs
│   └── session_state/
│       ├── mod.rs
│       ├── session_state_generated.rs
│       ├── beliefs_generated.rs
│       └── scoreboard_generated.rs
└── Cargo.toml
```

**Usage Example (Rust 1.70):**
```rust
use flatbuffers::{FlatBufferBuilder, WIPOffset};
use k1_schemas::agent_fabric::{AgentState, AgentStateArgs, AgentLifecycleState};

// Serialization
fn create_agent_state(agent_id: &str, state: AgentLifecycleState) -> Vec<u8> {
    let mut builder = FlatBufferBuilder::with_capacity(256);

    // Create string
    let agent_id_offset = builder.create_string(agent_id);

    // Create AgentState table
    let state_offset = AgentState::create(&mut builder, &AgentStateArgs {
        agent_id: Some(agent_id_offset),
        state,
        memory_mb: 512,
        ..Default::default()
    });

    // Finish buffer
    builder.finish(state_offset, Some("AGST"));

    // Return buffer
    builder.finished_data().to_vec()
}

// Deserialization (zero-copy)
fn read_agent_state(buf: &[u8]) -> AgentState {
    flatbuffers::root::<AgentState>(buf).unwrap()
}

// Usage
let buf = create_agent_state("agent_xyz", AgentLifecycleState::ACTIVE);
let state = read_agent_state(&buf);

println!("Agent ID: {}", state.agent_id());
println!("State: {:?}", state.state());
println!("Memory: {} MB", state.memory_mb());
```

---

### 3. Build System Integration

#### 3.1 CMake Integration (K0 Kernel)

**CMakeLists.txt:**
```cmake
cmake_minimum_required(VERSION 3.20)
project(k1_schemas)

# Find FlatBuffers
find_package(Flatbuffers REQUIRED)

# Schema sources
set(SCHEMA_DIR "${CMAKE_SOURCE_DIR}/k1/schemas")
file(GLOB_RECURSE SCHEMA_FILES "${SCHEMA_DIR}/**/*.fbs")

# Generated output directory
set(GENERATED_DIR "${CMAKE_BINARY_DIR}/generated/cpp")

# Code generation target
add_custom_target(
    generate_schemas
    COMMAND ${FLATBUFFERS_FLATC_EXECUTABLE}
        --cpp
        --gen-object-api
        --gen-mutable
        --scoped-enums
        --reflect-names
        -o ${GENERATED_DIR}
        ${SCHEMA_FILES}
    DEPENDS ${SCHEMA_FILES}
    COMMENT "Generating C++ bindings from FlatBuffers schemas"
)

# Schema library
add_library(k1_schemas INTERFACE)
target_include_directories(k1_schemas INTERFACE ${GENERATED_DIR})
target_link_libraries(k1_schemas INTERFACE flatbuffers::flatbuffers)
add_dependencies(k1_schemas generate_schemas)

# K0 kernel depends on schemas
add_executable(k0_kernel src/main.cpp)
target_link_libraries(k0_kernel PRIVATE k1_schemas)
```

#### 3.2 Bazel Integration (Alternative)

**BUILD.bazel:**
```python
load("@rules_flatbuffers//flatbuffers:flatbuffers.bzl", "flatbuffer_library")

# Schema library
flatbuffer_library(
    name = "k1_schemas",
    srcs = glob(["k1/schemas/**/*.fbs"]),
    flatc_args = [
        "--gen-object-api",
        "--gen-mutable",
        "--scoped-enums",
        "--reflect-names",
    ],
    language_outputs = [
        "cpp",
        "python",
        "rust",
    ],
    visibility = ["//visibility:public"],
)

# K0 kernel depends on schemas
cc_binary(
    name = "k0_kernel",
    srcs = ["src/main.cpp"],
    deps = [
        ":k1_schemas",
        "@flatbuffers//:flatbuffers",
    ],
)
```

#### 3.3 Python Setup (K1 Runtime)

**setup.py:**
```python
from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
import subprocess
import os

class BuildSchemas(build_py):
    """Custom build command to generate FlatBuffers schemas"""

    def run(self):
        # Find all schema files
        schema_dir = "k1/schemas"
        schema_files = []
        for root, dirs, files in os.walk(schema_dir):
            for file in files:
                if file.endswith(".fbs"):
                    schema_files.append(os.path.join(root, file))

        # Generate Python bindings
        output_dir = "k1/schemas/generated/python"
        os.makedirs(output_dir, exist_ok=True)

        subprocess.run([
            "flatc",
            "--python",
            "--gen-object-api",
            "-o", output_dir,
            *schema_files
        ], check=True)

        # Run standard build
        super().run()

setup(
    name="k1-intelligence",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "flatbuffers>=23.5.26",
    ],
    cmdclass={
        "build_py": BuildSchemas,
    },
)
```

**pyproject.toml (Modern Python Packaging):**
```toml
[build-system]
requires = ["setuptools>=65.0", "flatbuffers>=23.5.26"]
build-backend = "setuptools.build_meta"

[project]
name = "k1-intelligence"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "flatbuffers>=23.5.26",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["k1*"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

---

### 4. CI/CD Pipeline

#### 4.1 GitHub Actions Workflow

**.github/workflows/schemas.yml:**
```yaml
name: FlatBuffers Schema Validation

on:
  push:
    paths:
      - 'k1/schemas/**/*.fbs'
  pull_request:
    paths:
      - 'k1/schemas/**/*.fbs'

jobs:
  validate-schemas:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Install FlatBuffers compiler
        run: |
          FLATC_VERSION="23.5.26"
          wget https://github.com/google/flatbuffers/releases/download/v${FLATC_VERSION}/flatc_linux_x64.zip
          unzip flatc_linux_x64.zip
          chmod +x flatc
          sudo mv flatc /usr/local/bin/

      - name: Validate schema syntax
        run: |
          flatc --schema -o /tmp k1/schemas/**/*.fbs

      - name: Check for breaking changes
        run: |
          python scripts/check_schema_breaking_changes.py

      - name: Generate Python bindings
        run: |
          flatc --python --gen-object-api -o k1/schemas/generated/python k1/schemas/**/*.fbs

      - name: Generate C++ bindings
        run: |
          flatc --cpp --gen-object-api --gen-mutable -o k1/schemas/generated/cpp k1/schemas/**/*.fbs

      - name: Type check Python bindings
        run: |
          pip install mypy
          mypy k1/schemas/generated/python --strict

      - name: Upload generated bindings
        uses: actions/upload-artifact@v3
        with:
          name: generated-schemas
          path: k1/schemas/generated/
```

#### 4.2 Pre-commit Hooks

**.pre-commit-config.yaml:**
```yaml
repos:
  - repo: local
    hooks:
      - id: validate-flatbuffers-schemas
        name: Validate FlatBuffers schemas
        entry: flatc --schema -o /tmp
        language: system
        files: '\.fbs$'
        pass_filenames: true

      - id: check-schema-breaking-changes
        name: Check for breaking schema changes
        entry: python scripts/check_schema_breaking_changes.py
        language: python
        files: '\.fbs$'
        pass_filenames: true

      - id: generate-python-bindings
        name: Generate Python bindings
        entry: bash -c 'flatc --python -o k1/schemas/generated/python k1/schemas/**/*.fbs'
        language: system
        files: '\.fbs$'
```

#### 4.3 Breaking Change Detection

**scripts/check_schema_breaking_changes.py:**
```python
#!/usr/bin/env python3
"""Detect breaking changes in FlatBuffers schemas"""

import sys
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any

def parse_schema(schema_path: Path) -> Dict[str, Any]:
    """Parse FlatBuffers schema to JSON AST"""
    result = subprocess.run(
        ["flatc", "--schema", "--json", str(schema_path)],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def get_changed_schemas() -> List[Path]:
    """Get list of changed schema files from git"""
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        capture_output=True,
        text=True
    )
    return [
        Path(line) for line in result.stdout.splitlines()
        if line.endswith(".fbs")
    ]

def check_breaking_changes(old_schema: Dict, new_schema: Dict) -> List[str]:
    """Check for breaking changes between schema versions"""
    errors = []

    # Check table removals
    old_tables = {t["name"] for t in old_schema.get("tables", [])}
    new_tables = {t["name"] for t in new_schema.get("tables", [])}
    removed_tables = old_tables - new_tables
    if removed_tables:
        errors.append(f"BREAKING: Removed tables: {removed_tables}")

    # Check field removals
    for old_table in old_schema.get("tables", []):
        new_table = next(
            (t for t in new_schema.get("tables", []) if t["name"] == old_table["name"]),
            None
        )
        if not new_table:
            continue

        old_fields = {f["name"]: f["type"] for f in old_table.get("fields", [])}
        new_fields = {f["name"]: f["type"] for f in new_table.get("fields", [])}

        # Removed fields
        removed_fields = set(old_fields.keys()) - set(new_fields.keys())
        if removed_fields:
            errors.append(
                f"BREAKING: Table {old_table['name']} removed fields: {removed_fields}"
            )

        # Changed field types
        for field_name in set(old_fields.keys()) & set(new_fields.keys()):
            if old_fields[field_name] != new_fields[field_name]:
                errors.append(
                    f"BREAKING: Table {old_table['name']} field {field_name} "
                    f"type changed: {old_fields[field_name]} -> {new_fields[field_name]}"
                )

    return errors

def main():
    changed_schemas = get_changed_schemas()
    if not changed_schemas:
        print("No schema changes detected")
        return 0

    has_breaking_changes = False

    for schema_path in changed_schemas:
        print(f"Checking {schema_path}...")

        # Get old version from git
        old_content = subprocess.run(
            ["git", "show", f"HEAD~1:{schema_path}"],
            capture_output=True,
            text=True
        ).stdout

        # Parse old and new schemas
        old_schema = parse_schema(Path("/tmp/old_schema.fbs"))
        new_schema = parse_schema(schema_path)

        # Check for breaking changes
        errors = check_breaking_changes(old_schema, new_schema)
        if errors:
            has_breaking_changes = True
            print(f"  ❌ Breaking changes detected:")
            for error in errors:
                print(f"    - {error}")
        else:
            print(f"  ✅ No breaking changes")

    return 1 if has_breaking_changes else 0

if __name__ == "__main__":
    sys.exit(main())
```

---

### 5. Type Safety Guarantees

#### 5.1 Python Type Checking (mypy)

**mypy.ini:**
```ini
[mypy]
python_version = 3.11
strict = True
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
disallow_any_unimported = True
disallow_any_expr = False
disallow_any_decorated = False
disallow_any_explicit = False
disallow_any_generics = True
disallow_subclassing_any = True
warn_redundant_casts = True
warn_unused_ignores = True
warn_no_return = True
warn_unreachable = True
strict_equality = True

[mypy-k1.schemas.generated.python.*]
ignore_errors = True  # Generated code, skip checks
```

**Type Stub Generation:**
```python
# scripts/generate_type_stubs.py

def generate_stub(schema_name: str) -> str:
    """Generate .pyi stub for FlatBuffers schema"""
    return f"""
from typing import Optional, List
import flatbuffers

class {schema_name}:
    @staticmethod
    def GetRootAs(buf: bytes, offset: int = 0) -> '{schema_name}': ...

    def AgentId(self) -> bytes: ...
    def State(self) -> int: ...
    def MemoryMb(self) -> int: ...

    @staticmethod
    def Start(builder: flatbuffers.Builder) -> None: ...

    @staticmethod
    def AddAgentId(builder: flatbuffers.Builder, agent_id: int) -> None: ...

    @staticmethod
    def End(builder: flatbuffers.Builder) -> int: ...
"""
```

#### 5.2 C++ Type Checking (Clang-Tidy)

**.clang-tidy:**
```yaml
Checks: >
  clang-analyzer-*,
  bugprone-*,
  cppcoreguidelines-*,
  modernize-*,
  performance-*,
  readability-*,
  -modernize-use-trailing-return-type

CheckOptions:
  - key: readability-identifier-naming.ClassCase
    value: CamelCase
  - key: readability-identifier-naming.FunctionCase
    value: camelBack
  - key: readability-identifier-naming.VariableCase
    value: lower_case
  - key: readability-identifier-naming.ConstantCase
    value: UPPER_CASE
```

#### 5.3 Rust Type Checking (Clippy)

**clippy.toml:**
```toml
# Clippy configuration for generated Rust bindings

# Deny all warnings in production
deny-warnings = true

# Allow generated code patterns
allow = [
    "clippy::too_many_arguments",
    "clippy::type_complexity",
]
```

---

## Consequences

### Positive

1. **Type Safety:** Generated code with type hints (Python), concepts (C++), traits (Rust) prevents serialization bugs
2. **Cross-Language Consistency:** All languages use same schemas, eliminating protocol mismatches
3. **Automated Builds:** CI/CD pipeline automatically validates schemas and generates bindings
4. **Breaking Change Detection:** Pre-commit hooks and CI catch breaking changes before merge
5. **Developer Experience:** IDEs provide autocomplete and type checking for schema fields

### Negative

1. **Build Complexity:** Requires `flatc` compiler in all build environments (dev, CI, prod)
2. **Generated Code Size:** 76 schemas generate ~50MB of bindings (Python + C++ + Rust)
3. **Compilation Time:** Schema generation adds ~10-30s to build time
4. **Tooling Dependency:** Tied to FlatBuffers toolchain (hard to switch serialization formats)

### Risks

1. **FlatBuffers Version Skew:** Different `flatc` versions may generate incompatible code (mitigation: pin version)
2. **Breaking Changes:** Accidental field removal breaks compatibility (mitigation: CI validation)
3. **Type Stub Drift:** Manual type stubs may drift from generated code (mitigation: auto-generate stubs)

---

## References

- **FlatBuffers Code Generation:** https://google.github.io/flatbuffers/flatbuffers_guide_using_schema_compiler.html
- **CMake FlatBuffers Integration:** https://github.com/google/flatbuffers/blob/master/CMakeLists.txt
- **Bazel FlatBuffers Rules:** https://github.com/google/flatbuffers/tree/master/bazel
- **ADR-0011a:** FlatBuffers Schema Design Principles
- **ADR-0011c:** Serialization Performance & Zero-Copy
- **ADR-0011d:** Schema Evolution & Versioning

---

**Status:** ✅ Accepted
**Next ADR:** [ADR-0011c: Serialization Performance & Zero-Copy](./0011c-serialization-performance-zero-copy.md)
