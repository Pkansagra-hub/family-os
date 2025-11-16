"""Space Module Types"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class VisibilityScope(str, Enum):
    OWNER_ONLY = "OWNER_ONLY"
    SPACE_DEFAULT = "SPACE_DEFAULT"
    HOUSEHOLD_ALL = "HOUSEHOLD_ALL"
    CUSTOM_SUBSET = "CUSTOM_SUBSET"
    EXTERNAL_SHARE = "EXTERNAL_SHARE"


@dataclass
class SpaceResolution:
    owner_id: str
    co_owners: List[str]
    author_role: str  # OWNER, CO_OWNER, GUEST
    visible_to: List[str]  # Final ACL after intersection
    visibility_scope: VisibilityScope
    model_version: str = "space_v0.1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpaceConfig:
    acl_mode: str = "intersection"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    target_latency_ms: int = 3
    emit_metrics: bool = True
    custom_config: Dict[str, Any] = field(default_factory=dict)
    custom_config: Dict[str, Any] = field(default_factory=dict)
    custom_config: Dict[str, Any] = field(default_factory=dict)
