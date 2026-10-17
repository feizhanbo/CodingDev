"""ShopFlow Order Service - pricing service."""

from app.models.coupon import Coupon


def apply_coupon(total_amount: float, coupon: Coupon) -> tuple[float, float]:
    """Apply a coupon to a total amount.

    Args:
        total_amount: The original total amount.
        coupon: The coupon to apply.

    Returns:
        A tuple of (discount_amount, final_amount).
    """
    if coupon.discount_type == "percentage":
        discount = total_amount * (coupon.discount_value / 100)
    elif coupon.discount_type == "fixed":
        discount = min(coupon.discount_value, total_amount)
    else:
        discount = 0.0

    final_amount = total_amount - discount
    return discount, final_amount
