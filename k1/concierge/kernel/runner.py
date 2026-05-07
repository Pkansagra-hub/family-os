"""Backward-compat shim -- real code moved to k1.kernel.runner (Issue 2.0.6)."""

from k1.kernel.runner import _parse_args, _run  # noqa: F401
from k1.kernel.bootstrap import KernelConfig, start_kernel, stop_kernel  # noqa: F401
