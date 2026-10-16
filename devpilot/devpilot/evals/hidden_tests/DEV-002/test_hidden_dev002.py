"""Hidden tests for DEV-002: Prevent invalid order cancellation.

These tests are copied to the workspace AFTER the agent run completes
and are used to verify the implementation against hidden acceptance criteria.

Verified behaviour:
  - pending  -> cancelled : allowed (HTTP 200)
  - paid     -> cancelled : allowed (HTTP 200)
  - shipped  -> cancelled : rejected (HTTP 409)
  - completed -> cancelled : rejected (HTTP 409)
  - Order status is NOT modified after a failed cancel attempt
  - Invalid transition is NOT persisted to the database
  - Legal transitions (pending -> paid) have no regression
"""

from __future__ import annotations

from app.models.order import Order


def _create_order(client, ids, product_key="headphones", quantity=2):
    """Helper to create an order via the API and return the response."""
    body = {
        "customer_id": ids["customers"]["bob"],
        "items": [{"product_id": ids["products"][product_key], "quantity": quantity}],
    }
    return client.post("/orders", json=body)


def _set_order_status(session_factory, order_id, status):
    """Directly set an order's status in the database (bypassing the API)."""
    session = session_factory()
    order = session.query(Order).filter(Order.id == order_id).first()
    assert order is not None, f"Order {order_id} not found for status setup"
    order.status = status
    session.commit()
    session.close()


def _get_order_status(session_factory, order_id):
    """Read an order's status directly from the database."""
    session = session_factory()
    order = session.query(Order).filter(Order.id == order_id).first()
    status = order.status if order else None
    session.close()
    return status


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------


def test_cancel_pending_order_allowed(seeded_client):
    """pending -> cancelled must succeed and return HTTP 200."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="headphones", quantity=3)
    order_id = create_resp.json()["id"]

    response = client.post(f"/orders/{order_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_paid_order_allowed(seeded_client):
    """paid -> cancelled must succeed and return HTTP 200."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="keyboard", quantity=2)
    order_id = create_resp.json()["id"]

    client.post(f"/orders/{order_id}/pay")
    response = client.post(f"/orders/{order_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Invalid transitions — HTTP 409
# ---------------------------------------------------------------------------


def test_cancel_shipped_returns_409(seeded_client, session_factory):
    """shipped -> cancelled must be rejected with HTTP 409."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="phone", quantity=1)
    order_id = create_resp.json()["id"]
    _set_order_status(session_factory, order_id, "shipped")

    response = client.post(f"/orders/{order_id}/cancel")

    assert response.status_code == 409


def test_cancel_completed_returns_409(seeded_client, session_factory):
    """completed -> cancelled must be rejected with HTTP 409."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="laptop", quantity=1)
    order_id = create_resp.json()["id"]
    _set_order_status(session_factory, order_id, "completed")

    response = client.post(f"/orders/{order_id}/cancel")

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Status must NOT be modified after a failed cancel attempt
# ---------------------------------------------------------------------------


def test_shipped_status_not_modified_after_failed_cancel(seeded_client, session_factory):
    """After a failed cancel on a shipped order, the status must remain 'shipped'."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="headphones", quantity=1)
    order_id = create_resp.json()["id"]
    _set_order_status(session_factory, order_id, "shipped")

    client.post(f"/orders/{order_id}/cancel")

    assert _get_order_status(session_factory, order_id) == "shipped"


def test_completed_status_not_modified_after_failed_cancel(seeded_client, session_factory):
    """After a failed cancel on a completed order, the status must remain 'completed'."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="phone", quantity=1)
    order_id = create_resp.json()["id"]
    _set_order_status(session_factory, order_id, "completed")

    client.post(f"/orders/{order_id}/cancel")

    assert _get_order_status(session_factory, order_id) == "completed"


def test_invalid_transition_not_persisted(seeded_client, session_factory):
    """An invalid transition must not be persisted to the database."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="laptop", quantity=1)
    order_id = create_resp.json()["id"]
    _set_order_status(session_factory, order_id, "shipped")

    response = client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 409

    # Database must still show 'shipped', not 'cancelled'
    assert _get_order_status(session_factory, order_id) == "shipped"


# ---------------------------------------------------------------------------
# Regression — legal paths still work
# ---------------------------------------------------------------------------


def test_pay_order_regression(seeded_client):
    """Regression: pending -> paid must still work after the cancel fix."""
    client, ids = seeded_client
    create_resp = _create_order(client, ids, product_key="mouse", quantity=1)
    order_id = create_resp.json()["id"]

    response = client.post(f"/orders/{order_id}/pay")

    assert response.status_code == 200
    assert response.json()["status"] == "paid"


def test_cancel_does_not_affect_other_orders(seeded_client):
    """Cancelling one order must not change another order's status."""
    client, ids = seeded_client
    create_resp_1 = _create_order(client, ids, product_key="mouse", quantity=1)
    create_resp_2 = _create_order(client, ids, product_key="keyboard", quantity=1)
    order_id_1 = create_resp_1.json()["id"]
    order_id_2 = create_resp_2.json()["id"]

    client.post(f"/orders/{order_id_1}/cancel")

    other = client.get(f"/orders/{order_id_2}").json()
    assert other["status"] == "pending"
