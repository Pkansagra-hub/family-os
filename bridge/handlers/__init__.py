"""Hand-written bridge handler implementations.

Files under ``bridge/handlers/<role>/`` contain *non-generated* business
logic that wires generated registration entry-points to concrete
behaviour. They sit alongside the generated tree but are never
overwritten by ``python -m tooling.contracts.codegen``.

Per gate ``manifest_implementation_bound``, every ``status: active``
manifest must have both:

* a generated module under ``bridge/_generated/<role>/...``, and
* a corresponding hand-written impl under ``bridge/handlers/<role>/...``.
"""
