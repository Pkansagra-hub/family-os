"""Bootstrap and per-session handle for k1.selfmodel.

Wired into ``KernelService`` at S2.6 / P3.5 in M5.
"""

from __future__ import annotations

from k1.selfmodel.kernel.bootstrap import (
    SelfModelServiceBundle,
    build_self_model_bundle,
)
from k1.selfmodel.kernel.handle import (
    DEFAULT_SITUATION_KIND,
    SelfModelHandle,
    build_self_model_handle,
)

__all__ = [
    "SelfModelServiceBundle",
    "build_self_model_bundle",
    "SelfModelHandle",
    "build_self_model_handle",
    "DEFAULT_SITUATION_KIND",
]
