"""Tests for coupons API."""


def test_validate_coupon_percentage(seeded_client):
    """Test POST /coupons/validate with a percentage coupon."""
    client, _ids = seeded_client
    response = client.post(
        "/coupons/validate",
        json={"code": "SAVE10", "order_amount": 100.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["discount_amount"] == 10.0


def test_validate_coupon_fixed(seeded_client):
    """Test POST /coupons/validate with a fixed discount coupon."""
    client, _ids = seeded_client
    response = client.post(
        "/coupons/validate",
        json={"code": "FLAT50", "order_amount": 200.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["discount_amount"] == 50.0


def test_validate_coupon_not_found(seeded_client):
    """Test POST /coupons/validate with an invalid coupon code."""
    client, _ids = seeded_client
    response = client.post(
        "/coupons/validate",
        json={"code": "INVALID", "order_amount": 100.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["discount_amount"] == 0.0
