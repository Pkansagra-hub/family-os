"""SQLite driver compatibility shim.

DEPRECATED: SQLite backend has been replaced by PostgreSQL (asyncpg).
This module provides backward compatibility for code that imports from
k0.drivers.archived.sqlite.

The set_bus_dispatcher function is re-exported from internal_bus_driver.
"""

from __future__ import annotations

from k0.drivers.internal_bus_driver import set_bus_dispatcher

__all__ = ["set_bus_dispatcher"]
