"""Payment transition acceptance and persisted state checks."""
import pytest
from app.models.order import Order


@pytest.mark.parametrize("status", ["paid", "shipped", "cancelled", "completed"])
def test_reject_non_pending_payment(seeded_client, session_factory, status):
    client, ids = seeded_client
    with session_factory() as session:
        order = Order(customer_id=ids["customers"]["bob"], status=status, total_amount=87.25)
        session.add(order)
        session.commit()
        identifier = order.id
    response = client.post(f"/orders/{identifier}/pay")
    assert response.status_code == 409
    with session_factory() as session:
        persisted = session.get(Order, identifier)
        assert persisted.status == status
        assert persisted.total_amount == 87.25


def test_pending_payment_and_duplicate(seeded_client, session_factory):
    client, ids = seeded_client
    with session_factory() as session:
        order = Order(customer_id=ids["customers"]["bob"], status="pending", total_amount=12.5)
        session.add(order)
        session.commit()
        identifier = order.id
    first = client.post(f"/orders/{identifier}/pay")
    assert first.status_code == 200
    assert first.json()["status"] == "paid"
    assert client.post(f"/orders/{identifier}/pay").status_code == 409
    assert client.get(f"/orders/{identifier}").json()["status"] == "paid"


def test_missing_order_remains_404(seeded_client):
    client, _ = seeded_client
    assert client.post("/orders/99999999/pay").status_code == 404
