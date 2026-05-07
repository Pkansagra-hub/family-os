"""Individual CI gate scripts. Each module is independently runnable.

Common contract:

* ``main(argv: list[str] | None = None) -> int`` — exit 0 (clean), 1 (violation).
* CLI flags: ``--fail-on-violation`` (default) / ``--warn-only``.
* Stderr: ``[<gate-name>] <outcome> in <duration_ms> ms`` summary line.
* Stdout: machine-grepable offending file/line entries (one per line).
* Subprocess invocation supported (``python -m tooling.ci.gates.<name>``).
"""
