"""Backward-compat shim — real code moved to k1.kernel (Issue 2.0.6)."""

from k1.kernel.bootstrap import KernelConfig, KernelRuntime, start_kernel, stop_kernel

__all__ = ["KernelConfig", "KernelRuntime", "start_kernel", "stop_kernel"]
