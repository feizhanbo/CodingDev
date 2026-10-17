"""Tests for orders API."""


def _create_order(client, ids, product_key="mouse", quantity=1, coupon_code=None):
    """Helper to create an order and return the response."""
    body = {
        "customer_id": ids["customers"]["alice"],
        "items": [{"product_id": ids["products"][product_key], "quantity": quantity}],
    }
    if coupon_code:
        body["coupon_code"] = coupon_code
    return client.post("/orders", json=body)


def test_create_order(seeded_client):
    """Test POST /orders creates an order and returns 201."""
    client, ids = seeded_client
    response = _create_order(client, ids, product_key="mouse", quantity=2)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["total_amount"] == 58.0  # 29 * 2
    assert data["customer_id"] == ids["customers"]["alice"]


def test_create_order_with_coupon(seeded_client):
    """Test POST /orders with a coupon applies the discount."""
    client, ids = seeded_client
    response = _create_order(client, ids, product_key="laptop", quantity=1, coupon_code="FLAT50")
    assert response.status_code == 201
    assert response.json()["total_amount"] == 949.0  # 999 - 50


def test_create_order_invalid_customer(seeded_client):
    """Test POST /orders with invalid customer returns 400."""
    client, _ids = seeded_client
    response = client.post(
        "/orders",
        json={"customer_id": 9999, "items": [{"product_id": 1, "quantity": 1}]},
    )
    assert response.status_code == 400


def test_get_orders(seeded_client):
    """Test GET /orders returns all orders."""
    client, ids = seeded_client
    _create_order(client, ids, product_key="mouse", quantity=1)
    _create_order(client, ids, product_key="mouse", quantity=1)
    response = client.get("/orders")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_orders_empty(seeded_client):
    """Test GET /orders returns empty list when no orders exist."""
    client, _ids = seeded_client
    response = client.get("/orders")
    assert response.status_code == 200
    assert response.json() == []


def test_get_orders_pagination(seeded_client):
    """Test GET /orders with skip and limit."""
    client, ids = seeded_client
    for _ in range(3):
        _create_order(client, ids, product_key="mouse", quantity=1)
    response = client.get("/orders?skip=1&limit=1")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_order_found(seeded_client):
    """Test GET /orders/{id} returns order details."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="mouse", quantity=2)
    order_id = create_resp.json()["id"]
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 2


def test_get_order_not_found(seeded_client):
    """Test GET /orders/{id} returns 404 for non-existent order."""
    client, _ids = seeded_client
    response = client.get("/orders/9999")
    assert response.status_code == 404


def test_pay_order(seeded_client):
    """Test POST /orders/{id}/pay transitions to paid."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="mouse", quantity=1)
    order_id = create_resp.json()["id"]
    response = client.post(f"/orders/{order_id}/pay")
    assert response.status_code == 200
    assert response.json()["status"] == "paid"


def test_pay_order_invalid(seeded_client):
    """Test POST /orders/{id}/pay on non-pending returns 409."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="mouse", quantity=1)
    order_id = create_resp.json()["id"]
    client.post(f"/orders/{order_id}/pay")
    response = client.post(f"/orders/{order_id}/pay")
    assert response.status_code == 409


def test_cancel_order(seeded_client):
    """Test POST /orders/{id}/cancel cancels a pending order."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="mouse", quantity=1)
    order_id = create_resp.json()["id"]
    response = client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_order_paid(seeded_client):
    """Test POST /orders/{id}/cancel cancels a paid order."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="mouse", quantity=1)
    order_id = create_resp.json()["id"]
    client.post(f"/orders/{order_id}/pay")
    response = client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_order_shipped(seeded_client, session_factory):
    """Test POST /orders/{id}/cancel on shipped order returns 409."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="mouse", quantity=1)
    order_id = create_resp.json()["id"]

    session = session_factory()
    from app.models.order import Order

    order = session.query(Order).filter(Order.id == order_id).first()
    order.status = "shipped"
    session.commit()
    session.close()

    response = client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 409


def test_cancel_order_completed(seeded_client, session_factory):
    """Test POST /orders/{id}/cancel on completed order returns 409."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="mouse", quantity=1)
    order_id = create_resp.json()["id"]

    session = session_factory()
    from app.models.order import Order

    order = session.query(Order).filter(Order.id == order_id).first()
    order.status = "completed"
    session.commit()
    session.close()

    response = client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 409
