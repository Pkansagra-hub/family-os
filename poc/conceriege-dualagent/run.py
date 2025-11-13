"""
Run script for the POC - handles module imports correctly
"""

import sys
from pathlib import Path

# Add parent directory to path so imports work
poc_dir = Path(__file__).parent
sys.path.insert(0, str(poc_dir.parent))

if __name__ == "__main__":
    import uvicorn
    from config.settings import settings

    uvicorn.run(
        "main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
        log_level="info",
    )
