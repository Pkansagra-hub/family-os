"""Re-export shim — shares singleton with poc.k1_poc.config.loader."""

import sys as _sys

import poc.k1_poc.config.loader as _canonical

# Re-export everything including private names used by tests
from poc.k1_poc.config.loader import *  # noqa: F401,F403

# Make this module a full alias so `from k1.concierge.config.loader import _build_arbiter` works
_self = _sys.modules[__name__]
for _name in dir(_canonical):
    if not hasattr(_self, _name):
        setattr(_self, _name, getattr(_canonical, _name))
for _name in dir(_canonical):
    if not hasattr(_self, _name):
        setattr(_self, _name, getattr(_canonical, _name))
for _name in dir(_canonical):
    if not hasattr(_self, _name):
        setattr(_self, _name, getattr(_canonical, _name))
