"""Tests for OrderRepository."""

from app.repositories.order_repository import OrderRepository


def test_create(seeded_session):
    """Test creating an order."""
    session, ids = seeded_session
    repo = OrderRepository(session)
    order = repo.create(
        {
            "customer_id": ids["customers"]["alice"],
            "status": "pending",
            "total_amount": 999.0,
            "items": [
                {
                    "product_id": ids["products"]["laptop"],
                    "quantity": 1,
                    "unit_price": 999.0,
                }
            ],
        }
    )
    assert order.id is not None
    assert order.status == "pending"
    assert order.total_amount == 999.0
    assert order.customer_id == ids["customers"]["alice"]


def test_get_by_id(seeded_session):
    """Test getting an order by ID with items eager-loaded."""
    session, ids = seeded_session
    repo = OrderRepository(session)
    created = repo.create(
        {
            "customer_id": ids["customers"]["bob"],
            "status": "pending",
            "total_amount": 199.0,
            "items": [
                {
                    "product_id": ids["products"]["headphones"],
                    "quantity": 1,
                    "unit_price": 199.0,
                }
            ],
        }
    )
    order = repo.get_by_id(created.id)
    assert order is not None
    assert order.id == created.id
    assert len(order.items) == 1
    assert order.items[0].quantity == 1


def test_get_by_id_not_found(seeded_session):
    """Test getting a non-existent order returns None."""
    session, _ids = seeded_session
    repo = OrderRepository(session)
    order = repo.get_by_id(9999)
    assert order is None


def test_get_all(seeded_session):
    """Test getting all orders."""
    session, ids = seeded_session
    repo = OrderRepository(session)
    repo.create(
        {
            "customer_id": ids["customers"]["alice"],
            "status": "pending",
            "total_amount": 999.0,
            "items": [],
        }
    )
    repo.create(
        {
            "customer_id": ids["customers"]["bob"],
            "status": "paid",
            "total_amount": 199.0,
            "items": [],
        }
    )
    orders = repo.get_all()
    assert len(orders) == 2


def test_get_all_pagination(seeded_session):
    """Test get_all with skip and limit."""
    session, ids = seeded_session
    repo = OrderRepository(session)
    for _ in range(5):
        repo.create(
            {
                "customer_id": ids["customers"]["alice"],
                "status": "pending",
                "total_amount": 29.0,
                "items": [],
            }
        )
    orders = repo.get_all(skip=2, limit=2)
    assert len(orders) == 2


def test_update_status(seeded_session):
    """Test updating order status."""
    session, ids = seeded_session
    repo = OrderRepository(session)
    order = repo.create(
        {
            "customer_id": ids["customers"]["alice"],
            "status": "pending",
            "total_amount": 999.0,
            "items": [],
        }
    )
    updated = repo.update_status(order.id, "paid")
    assert updated is not None
    assert updated.status == "paid"
