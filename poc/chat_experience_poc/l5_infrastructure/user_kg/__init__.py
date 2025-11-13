"""User Knowledge Graph - user self-model and personalization."""

from .kg_query_interface import UserKG, get_user_kg
from .kg_schema import (
    EdgeType,
    NodeType,
    get_schema_documentation,
    validate_node_properties,
)

__all__ = [
    "NodeType",
    "EdgeType",
    "validate_node_properties",
    "get_schema_documentation",
    "UserKG",
    "get_user_kg",
]
