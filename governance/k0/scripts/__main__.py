"""
CLI Entry Point for Governance Sync.

This makes the sync tool accessible via:
    python -m governance.k0.scripts.sync

The main() function is in sync.py.
"""

from governance.k0.scripts.sync import main

if __name__ == "__main__":
    import sys

    sys.exit(main())
