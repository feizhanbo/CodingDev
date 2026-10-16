"""Hidden tests for DEV-004: Fix percentage coupon calculation error.

These tests are copied to the workspace AFTER the agent run completes
and are used to verify the implementation against hidden acceptance criteria.

Verified behaviour:
  - Normal percentage discount (e.g. 10 % off)
  - 0 % discount → no discount
  - 100 % discount → discount equals total, final is 0
  - discount_value > 100 → discount capped at total, final is 0
  - Decimal discount values (e.g. 10.50)
  - Different order amounts produce correct results
  - Fixed coupon type is NOT regressed
  - End-to-end test via the API
"""

from __future__ import annotations

import pytest
from app.models.coupon import Coupon
from app.services.pricing_service import apply_coupon

# ---------------------------------------------------------------------------
# Normal percentage discounts
# ---------------------------------------------------------------------------


def test_normal_percentage_discount():
    """10 % off a 200.0 total gives a 20.0 discount and 180.0 final."""
    coupon = Coupon(code="PCT10", discount_type="percentage", discount_value=10)
    discount, final = apply_coupon(200.0, coupon)
    assert discount == pytest.approx(20.0)
    assert final == pytest.approx(180.0)


def test_zero_percentage_discount():
    """0 % means no discount at all."""
    coupon = Coupon(code="PCT0", discount_type="percentage", discount_value=0)
    discount, final = apply_coupon(150.0, coupon)
    assert discount == pytest.approx(0.0)
    assert final == pytest.approx(150.0)


def test_full_percentage_discount():
    """100 % means the discount equals the total and the final amount is 0."""
    coupon = Coupon(code="PCT100", discount_type="percentage", discount_value=100)
    discount, final = apply_coupon(250.0, coupon)
    assert discount == pytest.approx(250.0)
    assert final == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Capping — discount must not exceed the total
# ---------------------------------------------------------------------------


def test_percentage_over_100_capped_at_total():
    """discount_value > 100 must be capped so discount ≤ total_amount."""
    coupon = Coupon(code="PCT150", discount_type="percentage", discount_value=150)
    discount, final = apply_coupon(300.0, coupon)
    assert discount == pytest.approx(300.0)
    assert final == pytest.approx(0.0)


def test_percentage_never_exceeds_total():
    """Even with a huge discount_value the discount must not exceed the total."""
    coupon = Coupon(code="PCT500", discount_type="percentage", discount_value=500)
    discount, final = apply_coupon(100.0, coupon)
    assert discount <= 100.0
    assert final >= 0.0
    assert discount == pytest.approx(100.0)
    assert final == pytest.approx(0.0)


def test_percentage_final_amount_never_negative():
    """The final amount must never be negative after a percentage discount."""
    coupon = Coupon(code="PCT200", discount_type="percentage", discount_value=200)
    for total in (50.0, 99.99, 1234.56):
        _, final = apply_coupon(total, coupon)
        assert final >= 0.0


# ---------------------------------------------------------------------------
# Decimal discount values
# ---------------------------------------------------------------------------


def test_decimal_discount_value():
    """A decimal discount_value (10.50 %) is calculated correctly."""
    coupon = Coupon(code="PCT1050", discount_type="percentage", discount_value=10.50)
    discount, final = apply_coupon(200.0, coupon)
    assert discount == pytest.approx(21.0)
    assert final == pytest.approx(179.0)


def test_small_decimal_discount_value():
    """A small decimal percentage (5.25 %) is calculated correctly."""
    coupon = Coupon(code="PCT525", discount_type="percentage", discount_value=5.25)
    discount, final = apply_coupon(400.0, coupon)
    assert discount == pytest.approx(21.0)
    assert final == pytest.approx(379.0)


# ---------------------------------------------------------------------------
# Different order amounts
# ---------------------------------------------------------------------------


def test_percentage_various_amounts():
    """25 % off produces correct results for various totals."""
    coupon = Coupon(code="PCT25", discount_type="percentage", discount_value=25)
    for total in (40.0, 80.0, 400.0):
        discount, final = apply_coupon(total, coupon)
        assert discount == pytest.approx(total * 0.25)
        assert final == pytest.approx(total * 0.75)


# ---------------------------------------------------------------------------
# Fixed coupon type must NOT be regressed
# ---------------------------------------------------------------------------


def test_fixed_coupon_not_regressed():
    """A fixed discount below the total works as before."""
    coupon = Coupon(code="FLAT60", discount_type="fixed", discount_value=60)
    discount, final = apply_coupon(200.0, coupon)
    assert discount == pytest.approx(60.0)
    assert final == pytest.approx(140.0)


def test_fixed_coupon_capped_at_total():
    """A fixed discount above the total is capped (existing behaviour)."""
    coupon = Coupon(code="FLAT60", discount_type="fixed", discount_value=60)
    discount, final = apply_coupon(30.0, coupon)
    assert discount == pytest.approx(30.0)
    assert final == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# End-to-end via the API
# ---------------------------------------------------------------------------


def test_percentage_coupon_via_api(seeded_client):
    """Creating an order with a 10 % coupon applies the correct discount."""
    client, ids = seeded_client
    # Laptop costs 999.0; SAVE10 gives 10 % off → 899.10
    response = client.post(
        "/orders",
        json={
            "customer_id": ids["customers"]["alice"],
            "items": [{"product_id": ids["products"]["laptop"], "quantity": 1}],
            "coupon_code": "SAVE10",
        },
    )
    assert response.status_code == 201
    assert response.json()["total_amount"] == pytest.approx(899.1)


def test_percentage_capped_via_api(seeded_client, session_factory):
    """An over-100 % coupon is capped at the order total via the API."""
    client, ids = seeded_client

    # Insert a 150 % coupon directly
    session = session_factory()
    session.add(Coupon(code="MEGA150", discount_type="percentage", discount_value=150))
    session.commit()
    session.close()

    response = client.post(
        "/orders",
        json={
            "customer_id": ids["customers"]["bob"],
            "items": [{"product_id": ids["products"]["headphones"], "quantity": 1}],
            "coupon_code": "MEGA150",
        },
    )
    assert response.status_code == 201
    # 150 % of 199.0 = 298.5, capped at 199.0 → final 0.0
    assert response.json()["total_amount"] == pytest.approx(0.0)
