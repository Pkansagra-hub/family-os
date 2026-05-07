"""
k1.kernel.adapters -- Adapter implementations for Kernel ports.

This package will contain production and test adapters for the 8 kernel
port protocols defined in ``k1.kernel.ports``.

Adapters are created as part of Epic 2.1 (KernelService Core) and later.
This ``__init__.py`` is scaffolding from Issue 2.0.8.

Convention:
  - One file per adapter (matching the port it implements).
  - File name: ``<component>_adapter.py`` (e.g. ``bus_adapter.py``).
  - Test adapters: ``test_<component>_adapter.py`` or grouped in
    ``test_adapters.py``.
"""
