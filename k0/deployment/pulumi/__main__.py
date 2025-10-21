"""Pulumi program entry point for k0-deployment."""

from __future__ import annotations

import sys
from pathlib import Path

# Add repository root to sys.path for proper package imports
# __file__ is at: memory_kernel/k0/deployment/pulumi/__main__.py
# repo_root is:   memory_kernel/
repo_root = Path(__file__).parent.parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Import using the k0.deployment.pulumi package path
from k0.deployment.pulumi.stacks.local_single_node import pulumi_program_from_config

# Run the Pulumi program for local-single-node stack
program = pulumi_program_from_config()
program()
