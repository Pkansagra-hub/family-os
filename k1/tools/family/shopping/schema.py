"""k1.tools.family.shopping.schema -- Shopping list entity types."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, model_validator

from k1.tools.family.base import BaseEntity

ShoppingCategory = Literal[
    "groceries",
    "clothes",
    "household",
    "school",
    "pharmacy",
    "gifts",
    "pets",
    "other",
]
ShoppingItemStatus = Literal["needed", "checked"]
ApprovalStatus = Literal["approved", "pending_parent_approval", "rejected"]


class ShoppingList(BaseEntity):
    """A named shopping list, such as Groceries or Clothes."""

    name: str = Field(..., min_length=1, description="Human-readable list name.")
    category: ShoppingCategory = Field(
        default="groceries",
        description="Default category for items in this list.",
    )


class ShoppingItem(BaseEntity):
    """A shopping request or approved list item."""

    list_id: str = Field(..., min_length=1, description="ShoppingList.id this item belongs to.")
    name: str = Field(..., min_length=1, description="Item name.")
    quantity: Optional[str] = Field(
        default=None,
        description="Flexible quantity text, e.g. '2', 'one pack', or '3T'.",
    )
    unit: Optional[str] = Field(default=None, description="Optional unit, e.g. box, lb, pair.")
    category: ShoppingCategory = Field(default="groceries", description="Item category.")
    requested_by: str = Field(..., min_length=1, description="member_id requesting the item.")
    notes: Optional[str] = Field(default=None, description="Optional shopping note.")
    priority: Literal["low", "medium", "high"] = Field(default="medium")
    status: ShoppingItemStatus = Field(default="needed")
    approval_status: ApprovalStatus = Field(default="approved")
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_by: Optional[str] = None
    rejected_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    checked_by: Optional[str] = None
    checked_at: Optional[str] = None

    @model_validator(mode="after")
    def _approval_status_coherence(self) -> "ShoppingItem":
        if self.status == "checked" and self.approval_status != "approved":
            raise ValueError("ShoppingItem must be approved before it can be checked off")
        if self.approval_status != "rejected" and (self.rejected_by or self.rejected_at):
            raise ValueError("rejection fields require approval_status='rejected'")
        return self
