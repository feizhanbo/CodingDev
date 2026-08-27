"""Tests for OrderService."""

import pytest

from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.order_service import OrderService


def test_create_order(seeded_session):
    """Test creating an order via the service."""
    session, ids = seeded_session
    order = OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["alice"],
            items=[OrderItemCreate(product_id=ids["products"]["laptop"], quantity=1)],
        ),
    )
    assert order.id is not None
    assert order.status == "pending"
    assert order.total_amount == 999.0


def test_create_order_with_coupon(seeded_session):
    """Test creating an order with a coupon applied."""
    session, ids = seeded_session
    order = OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["alice"],
            items=[OrderItemCreate(product_id=ids["products"]["laptop"], quantity=1)],
            coupon_code="FLAT50",
        ),
    )
    assert order.total_amount == 949.0  # 999 - 50


def test_create_order_invalid_customer(seeded_session):
    """Test creating an order with a non-existent customer raises ValueError."""
    session, ids = seeded_session
    with pytest.raises(ValueError, match="Customer.*not found"):
        OrderService.create_order(
            session,
            OrderCreate(
                customer_id=9999,
                items=[OrderItemCreate(product_id=ids["products"]["mouse"], quantity=1)],
            ),
        )


def test_create_order_invalid_product(seeded_session):
    """Test creating an order with a non-existent product raises ValueError."""
    session, ids = seeded_session
    with pytest.raises(ValueError, match="Product.*not found"):
        OrderService.create_order(
            session,
            OrderCreate(
                customer_id=ids["customers"]["alice"],
                items=[OrderItemCreate(product_id=9999, quantity=1)],
            ),
        )


def test_create_order_insufficient_stock(seeded_session):
    """Test creating an order with insufficient stock raises ValueError."""
    session, ids = seeded_session
    with pytest.raises(ValueError, match="Insufficient stock"):
        OrderService.create_order(
            session,
            OrderCreate(
                customer_id=ids["customers"]["alice"],
                items=[OrderItemCreate(product_id=ids["products"]["laptop"], quantity=999)],
            ),
        )


def test_get_order(seeded_session):
    """Test getting order details."""
    session, ids = seeded_session
    order = OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["alice"],
            items=[OrderItemCreate(product_id=ids["products"]["laptop"], quantity=1)],
        ),
    )
    detail = OrderService.get_order(session, order.id)
    assert detail.id == order.id
    assert len(detail.items) == 1
    assert detail.items[0].quantity == 1


def test_get_order_not_found(seeded_session):
    """Test getting a non-existent order raises ValueError."""
    session, _ids = seeded_session
    with pytest.raises(ValueError, match="Order.*not found"):
        OrderService.get_order(session, 9999)


def test_get_orders(seeded_session):
    """Test getting all orders."""
    session, ids = seeded_session
    OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["alice"],
            items=[OrderItemCreate(product_id=ids["products"]["mouse"], quantity=1)],
        ),
    )
    OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["bob"],
            items=[OrderItemCreate(product_id=ids["products"]["mouse"], quantity=1)],
        ),
    )
    orders = OrderService.get_orders(session)
    assert len(orders) == 2


def test_get_orders_pagination(seeded_session):
    """Test getting orders with pagination."""
    session, ids = seeded_session
    for _ in range(5):
        OrderService.create_order(
            session,
            OrderCreate(
                customer_id=ids["customers"]["alice"],
                items=[OrderItemCreate(product_id=ids["products"]["mouse"], quantity=1)],
            ),
        )
    orders = OrderService.get_orders(session, skip=2, limit=2)
    assert len(orders) == 2


def test_pay_order(seeded_session):
    """Test paying for an order (pending -> paid)."""
    session, ids = seeded_session
    order = OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["alice"],
            items=[OrderItemCreate(product_id=ids["products"]["mouse"], quantity=1)],
        ),
    )
    paid = OrderService.pay_order(session, order.id)
    assert paid.status == "paid"


def test_pay_order_invalid_transition(seeded_session):
    """Test paying for a non-pending order raises ValueError."""
    session, ids = seeded_session
    order = OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["alice"],
            items=[OrderItemCreate(product_id=ids["products"]["mouse"], quantity=1)],
        ),
    )
    OrderService.pay_order(session, order.id)
    with pytest.raises(ValueError, match="Cannot pay"):
        OrderService.pay_order(session, order.id)


def test_cancel_order(seeded_session):
    """Test cancelling a pending order."""
    session, ids = seeded_session
    order = OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["alice"],
            items=[OrderItemCreate(product_id=ids["products"]["mouse"], quantity=1)],
        ),
    )
    cancelled = OrderService.cancel_order(session, order.id)
    assert cancelled.status == "cancelled"


def test_cancel_order_paid(seeded_session):
    """Test cancelling a paid order."""
    session, ids = seeded_session
    order = OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["alice"],
            items=[OrderItemCreate(product_id=ids["products"]["mouse"], quantity=1)],
        ),
    )
    OrderService.pay_order(session, order.id)
    cancelled = OrderService.cancel_order(session, order.id)
    assert cancelled.status == "cancelled"


def test_cancel_order_shipped(seeded_session):
    """Test cancelling a shipped order raises ValueError."""
    session, ids = seeded_session
    order = OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["alice"],
            items=[OrderItemCreate(product_id=ids["products"]["mouse"], quantity=1)],
        ),
    )
    repo = OrderRepository(session)
    repo.update_status(order.id, "shipped")
    with pytest.raises(ValueError, match="Cannot cancel"):
        OrderService.cancel_order(session, order.id)


def test_cancel_order_completed(seeded_session):
    """Test cancelling a completed order raises ValueError."""
    session, ids = seeded_session
    order = OrderService.create_order(
        session,
        OrderCreate(
            customer_id=ids["customers"]["alice"],
            items=[OrderItemCreate(product_id=ids["products"]["mouse"], quantity=1)],
        ),
    )
    repo = OrderRepository(session)
    repo.update_status(order.id, "completed")
    with pytest.raises(ValueError, match="Cannot cancel"):
        OrderService.cancel_order(session, order.id)
