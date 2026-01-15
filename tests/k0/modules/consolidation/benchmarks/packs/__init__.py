"""Scenario pack registry for R5 benchmarks.

Each pack module exposes a `build_world(seed: int, use_ultrabert: bool | None)` function
returning a World instance compatible with `r5_data_factory.World`.
"""

from __future__ import annotations

# Import pack modules for registration
# Note: Only import implemented packs; stubs will be loaded dynamically by factory

try:
    from . import toy
except ImportError:
    toy = None

# Future packs (stubs for now - will raise NotImplementedError)
try:
    from . import causal_deep
except ImportError:
    causal_deep = None

try:
    from . import causal_fork_join
except ImportError:
    causal_fork_join = None

try:
    from . import mcts_delayed
except ImportError:
    mcts_delayed = None

try:
    from . import mcts_constrained
except ImportError:
    mcts_constrained = None

try:
    from . import bgt_clustered
except ImportError:
    bgt_clustered = None

try:
    from . import bgt_adversarial
except ImportError:
    bgt_adversarial = None

try:
    from . import spc_multi_prov
except ImportError:
    spc_multi_prov = None

try:
    from . import spc_conflict
except ImportError:
    spc_conflict = None

try:
    from . import mixed_stress
except ImportError:
    mixed_stress = None

try:
    from . import real_world
except ImportError:
    real_world = None

__all__ = [
    "toy",
    "causal_deep",
    "causal_fork_join",
    "mcts_delayed",
    "mcts_constrained",
    "bgt_clustered",
    "bgt_adversarial",
    "spc_multi_prov",
    "spc_conflict",
    "mixed_stress",
    "real_world",
]
