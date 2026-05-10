"""Live-system integration test harness for MS-7.

This package provides primitives for spawning real processes (no mocks)
to exercise the K0↔K1 system end-to-end.

Adapted for the deployment shape where K0 runs in Docker (already up at
``localhost:8080`` plus its own postgres on ``5432``) and K1 is spawned
locally as a subprocess.

Public surface (Epic 7.1):

* :class:`port_allocator.allocate_free_port`
* :class:`leak_detector.LeakDetector`
* :class:`process_supervisor.ProcessSupervisor`
* :class:`k0_handle.K0Handle`
* :class:`k1_handle.K1Handle`
* :class:`family_layout.FamilyLayout`, :class:`PersonSpec`, :class:`DeviceSpec`
* :class:`live_system.LiveSystem`
"""

from __future__ import annotations

from .family_layout import (
    DeviceSpec,
    FamilyLayout,
    PersonSpec,
    default_father_mother_kid_layout,
    single_father_layout,
)
from .k0_handle import K0Handle, K0NotReachableError
from .k1_handle import K1Handle
from .leak_detector import LeakDetector, LeakReport
from .live_system import LiveSystem
from .port_allocator import allocate_free_port
from .process_supervisor import ProcessHandle, ProcessSupervisor

__all__ = [
    "DeviceSpec",
    "FamilyLayout",
    "K0Handle",
    "K0NotReachableError",
    "K1Handle",
    "LeakDetector",
    "LeakReport",
    "LiveSystem",
    "PersonSpec",
    "ProcessHandle",
    "ProcessSupervisor",
    "allocate_free_port",
    "default_father_mother_kid_layout",
    "single_father_layout",
]
