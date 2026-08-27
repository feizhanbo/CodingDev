"""Tests for pricing service."""

from app.models.coupon import Coupon
from app.services.pricing_service import apply_coupon


def test_percentage_discount():
    """Test percentage discount calculation."""
    coupon = Coupon(code="SAVE10", discount_type="percentage", discount_value=10)
    discount, final = apply_coupon(100.0, coupon)
    assert discount == 10.0
    assert final == 90.0


def test_fixed_discount():
    """Test fixed discount calculation."""
    coupon = Coupon(code="FLAT50", discount_type="fixed", discount_value=50)
    discount, final = apply_coupon(100.0, coupon)
    assert discount == 50.0
    assert final == 50.0


def test_fixed_discount_capped():
    """Test fixed discount is capped at total amount."""
    coupon = Coupon(code="FLAT50", discount_type="fixed", discount_value=50)
    discount, final = apply_coupon(30.0, coupon)
    assert discount == 30.0
    assert final == 0.0
