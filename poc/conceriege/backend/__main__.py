"""
Entry point: python -m backend.cli.chat from project root
"""

import asyncio

from backend.cli.__main__ import main

if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(main())
