"""Order models and fake backend for the approval workflow demo."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    """One line item in a submitted order."""

    sku: str = Field(description="Product SKU")
    quantity: int = Field(description="Quantity to order", ge=1)
    description: str | None = Field(
        default=None,
        description="Optional human-readable item description",
    )


class SubmittedOrder(BaseModel):
    """Structured payload for an order submission."""

    items: list[OrderItem] = Field(description="Line items in the order")
    shipping_method: str | None = Field(
        default=None,
        description="Optional shipping method such as overnight or ground",
    )
    notes: str | None = Field(
        default=None,
        description="Optional notes for the order",
    )


@dataclass
class FakeOrderBackend:
    """In-memory store for approved orders."""

    orders: list[SubmittedOrder] = field(default_factory=list)

    def submit(self, order: SubmittedOrder) -> str:
        self.orders.append(order)
        return f"Order submitted with {len(order.items)} line item(s)."
