"""
poc.k1_poc.demo.web -- Web UI runner entry point.

Usage::

    python -m poc.k1_poc.demo.web                     # default port 8765
    python -m poc.k1_poc.demo.web --port 3000          # custom port
    python -m poc.k1_poc.demo.web --test-mode          # use test adapter
"""

from poc.k1_poc.demo.web.app import main

main()
