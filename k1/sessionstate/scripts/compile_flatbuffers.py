#!/usr/bin/env python
"""
FlatBuffers Schema Compilation Script for SessionState.

This script compiles the SessionState FlatBuffers schemas (.fbs) into Python
bindings. It's part of the build pipeline for the K1 SessionState module.

Usage:
    python -m k1.sessionstate.scripts.compile_flatbuffers

Requirements:
    - flatc (FlatBuffers compiler) must be installed and in PATH
    - Minimum version: 1.12.0

Output:
    - Python bindings at: k1/sessionstate/generated/flatbuffers/

Related ADRs:
    - ADR-0017: SessionState Design
    - ADR-0019a: FlatBuffers Serialization
"""

import subprocess
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    # This script is at k1/sessionstate/scripts/compile_flatbuffers.py
    return Path(__file__).parent.parent.parent.parent


def check_flatc_installed() -> bool:
    """Check if flatc is installed and get version."""
    try:
        result = subprocess.run(
            ["flatc", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"Found: {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("ERROR: flatc not found. Please install FlatBuffers:")
        print("  - Windows: scoop install flatbuffers")
        print("  - macOS: brew install flatbuffers")
        print("  - Linux: apt install flatbuffers-compiler")
        return False
    except subprocess.CalledProcessError as e:
        print(f"ERROR: flatc check failed: {e}")
        return False


def compile_schemas() -> bool:
    """Compile FlatBuffers schemas to Python."""
    root = get_project_root()

    # Paths
    schema_dir = root / "k1" / "contracts" / "flatbuffers" / "sessionstate"
    output_dir = root / "k1" / "sessionstate" / "generated" / "flatbuffers"
    root_schema = schema_dir / "session_kernel.fbs"

    # Validate paths
    if not schema_dir.exists():
        print(f"ERROR: Schema directory not found: {schema_dir}")
        return False

    if not root_schema.exists():
        print(f"ERROR: Root schema not found: {root_schema}")
        return False

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Schema directory: {schema_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Root schema: {root_schema.name}")

    # List schemas
    schemas = list(schema_dir.glob("*.fbs"))
    print(f"\nSchemas to compile: {len(schemas)}")
    for schema in sorted(schemas):
        print(f"  - {schema.name}")

    # Run flatc
    print("\nCompiling FlatBuffers schemas...")
    try:
        result = subprocess.run(
            [
                "flatc",
                "--python",  # Generate Python code
                "--gen-all",  # Generate all types, not just root
                "-o",
                str(output_dir),
                str(root_schema),
            ],
            capture_output=True,
            text=True,
            cwd=str(schema_dir),
            check=True,
        )

        if result.stdout:
            print(result.stdout)

        print("✓ Compilation successful!")

        # Count generated files
        generated = list(output_dir.rglob("*.py"))
        print(f"✓ Generated {len(generated)} Python files")

        return True

    except subprocess.CalledProcessError as e:
        print("ERROR: Compilation failed:")
        print(e.stderr)
        return False


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("SessionState FlatBuffers Compiler")
    print("=" * 60)
    print()

    if not check_flatc_installed():
        return 1

    print()

    if not compile_schemas():
        return 1

    print()
    print("=" * 60)
    print("Build complete!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
