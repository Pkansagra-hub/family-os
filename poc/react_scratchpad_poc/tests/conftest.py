"""
conftest.py -- shared fixtures for the scratchpad PoC tests.
"""

import sys
from pathlib import Path

# Ensure PoC root is on path
_POC_ROOT = Path(__file__).parent.parent
if str(_POC_ROOT) not in sys.path:
    sys.path.insert(0, str(_POC_ROOT))

# Ensure project root is on path (for k1.sessionstate imports)
_PROJECT_ROOT = _POC_ROOT.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
