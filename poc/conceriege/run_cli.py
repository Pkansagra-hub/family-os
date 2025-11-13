#!/usr/bin/env python
"""
CLI entry point for Concierge PoC

Usage: python run_cli.py
"""
import asyncio
import sys
from pathlib import Path

from backend.cli.__main__ import main

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    asyncio.run(main())
