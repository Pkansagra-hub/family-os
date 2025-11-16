"""Space Module - ACL and Ownership Resolution | Version: 0.1.0 | ADR: K005"""

from .space_resolver import SpaceResolver
from .space_types import SpaceConfig, SpaceResolution, VisibilityScope

__version__ = "0.1.0"
__all__ = ["SpaceResolver", "SpaceResolution", "SpaceConfig", "VisibilityScope"]
