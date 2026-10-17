"""ShopFlow Order Service - coupon schemas."""

from pydantic import BaseModel


class CouponValidateRequest(BaseModel):
    """Request schema for validating a coupon."""

    code: str
    order_amount: float


class CouponValidateResponse(BaseModel):
    """Response schema for coupon validation."""

    valid: bool
    discount_amount: float
    message: str
