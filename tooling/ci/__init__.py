"""CI gate orchestration for the bridge substrate.

Every wall, drift, and cross-kernel reach is detected at PR time by the
gates under :mod:`tooling.ci.gates`. The orchestrator
:mod:`tooling.ci.run_all_gates` runs them in subprocesses so a single
gate's crash cannot poison the rest of the run.
"""
