"""ShopFlow Order Service - order schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrderItemCreate(BaseModel):
    """Schema for creating an order item."""

    product_id: int
    quantity: int


class OrderCreate(BaseModel):
    """Schema for creating an order."""

    customer_id: int
    items: list[OrderItemCreate]
    coupon_code: str | None = None


class OrderItemResponse(BaseModel):
    """Response schema for an order item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    unit_price: float


class OrderResponse(BaseModel):
    """Response schema for an order."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    status: str
    total_amount: float
    created_at: datetime


class OrderDetailResponse(OrderResponse):
    """Detailed response schema for an order, including line items."""

    items: list[OrderItemResponse]
