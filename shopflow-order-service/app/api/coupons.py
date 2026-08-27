"""ShopFlow Order Service - coupons API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.coupon import Coupon
from app.schemas.coupon import CouponValidateRequest, CouponValidateResponse
from app.services.pricing_service import apply_coupon

router = APIRouter(prefix="/coupons", tags=["coupons"])


@router.post("/validate", response_model=CouponValidateResponse)
def validate_coupon(request: CouponValidateRequest, db: Session = Depends(get_db)):
    """Validate a coupon against an order amount."""
    coupon = db.query(Coupon).filter(Coupon.code == request.code).first()
    if not coupon:
        return CouponValidateResponse(
            valid=False, discount_amount=0.0, message="Coupon not found"
        )

    discount, _final = apply_coupon(request.order_amount, coupon)
    return CouponValidateResponse(
        valid=True, discount_amount=discount, message="Coupon applied successfully"
    )
