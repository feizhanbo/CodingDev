"""Acceptance checks for filtering before pagination, with independent fixtures."""
import pytest
from app.models.order import Order


@pytest.fixture
def orders(seeded_client, session_factory):
    client, ids = seeded_client
    with session_factory() as session:
        rows = [Order(customer_id=ids["customers"]["alice"], status=status, total_amount=17)
                for status in ["pending", "paid", "shipped", "paid", "cancelled", "completed"]]
        session.add_all(rows)
        session.commit()
        return client, [(row.id, row.status) for row in rows]


@pytest.mark.parametrize("status", ["pending", "paid", "shipped", "cancelled", "completed"])
def test_filter_status(orders, status):
    client, rows = orders
    response = client.get(f"/orders?status={status}")
    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {i for i, s in rows if s == status}
    assert all(row["status"] == status for row in response.json())


def test_filter_before_pagination(orders):
    client, rows = orders
    paid = [i for i, status in rows if status == "paid"]
    response = client.get("/orders?status=paid&skip=1&limit=1")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == paid[1:2]
    assert client.get("/orders?status=paid&skip=10").json() == []


@pytest.mark.parametrize("status", ["invalid", "PAID", "unknown-state", ""])
def test_invalid_status_is_400(seeded_client, status):
    client, _ = seeded_client
    assert client.get(f"/orders?status={status}").status_code == 400


def test_no_filter_preserves_response(orders):
    client, rows = orders
    response = client.get("/orders")
    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {i for i, _ in rows}
    assert set(response.json()[0]) == {"id", "customer_id", "status", "total_amount", "created_at"}
