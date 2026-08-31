"""Hidden tests for DEV-005: Optimize order detail N+1 query.

These tests are copied to the workspace AFTER the agent run completes
and are used to verify the implementation against hidden acceptance criteria.

Verified behaviour:
  - API response schema is unchanged (all expected fields present)
  - OrderItem data is correct (quantity, unit_price, product_id)
  - Large orders return all items with correct data
  - DB query count is bounded (O(1)) regardless of item count — no N+1
  - Query-count tests use SQLAlchemy event listeners (deterministic, not
    timing-based)
"""

from __future__ import annotations

from sqlalchemy import event

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.services.order_service import OrderService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_select_queries(engine, func):
    """Execute *func* and return the number of SELECT statements issued."""
    count = 0

    def _on_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        nonlocal count
        if statement and statement.strip().lower().startswith("select"):
            count += 1

    event.listen(engine, "after_cursor_execute", _on_cursor_execute)
    try:
        func()
    finally:
        event.remove(engine, "after_cursor_execute", _on_cursor_execute)

    return count


def _build_order_with_items(session, num_items):
    """Create a customer, *num_items* products, and an order containing them.

    Returns the order ID.
    """
    customer = Customer(name="QueryTest", email="qt@example.com")
    session.add(customer)
    session.flush()

    products = [
        Product(name=f"Item{i}", price=10.0 + i, stock=100)
        for i in range(num_items)
    ]
    session.add_all(products)
    session.flush()

    order = Order(customer_id=customer.id, status="pending", total_amount=0.0)
    session.add(order)
    session.flush()

    for product in products:
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=1,
                unit_price=product.price,
            )
        )
    session.commit()
    return order.id, products


# ---------------------------------------------------------------------------
# Correctness — schema unchanged
# ---------------------------------------------------------------------------


def test_order_detail_schema_unchanged(seeded_client):
    """GET /orders/{id} response must contain all expected fields."""
    client, ids = seeded_client
    create_resp = client.post(
        "/orders",
        json={
            "customer_id": ids["customers"]["alice"],
            "items": [{"product_id": ids["products"]["laptop"], "quantity": 2}],
        },
    )
    order_id = create_resp.json()["id"]

    response = client.get(f"/orders/{order_id}")
    data = response.json()

    # Order-level fields
    assert "id" in data
    assert "customer_id" in data
    assert "status" in data
    assert "total_amount" in data
    assert "created_at" in data
    assert "items" in data

    # Item-level fields
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert "id" in item
    assert "product_id" in item
    assert "quantity" in item
    assert "unit_price" in item


# ---------------------------------------------------------------------------
# Correctness — item data
# ---------------------------------------------------------------------------


def test_order_item_data_correct(seeded_client):
    """OrderItem quantity, unit_price and product_id must be correct."""
    client, ids = seeded_client
    create_resp = client.post(
        "/orders",
        json={
            "customer_id": ids["customers"]["bob"],
            "items": [{"product_id": ids["products"]["phone"], "quantity": 3}],
        },
    )
    order_id = create_resp.json()["id"]

    response = client.get(f"/orders/{order_id}")
    item = response.json()["items"][0]

    assert item["product_id"] == ids["products"]["phone"]
    assert item["quantity"] == 3
    assert item["unit_price"] == 599.0  # phone price


def test_large_order_returns_all_items(seeded_client):
    """An order with multiple items returns every item with correct data."""
    client, ids = seeded_client
    product_keys = ["laptop", "phone", "headphones", "keyboard", "mouse"]
    items = [
        {"product_id": ids["products"][key], "quantity": 1}
        for key in product_keys
    ]
    create_resp = client.post(
        "/orders",
        json={
            "customer_id": ids["customers"]["carol"],
            "items": items,
        },
    )
    order_id = create_resp.json()["id"]

    response = client.get(f"/orders/{order_id}")
    data = response.json()

    assert response.status_code == 200
    assert len(data["items"]) == 5

    # Every item must have valid fields
    for item in data["items"]:
        assert item["quantity"] == 1
        assert "unit_price" in item
        assert "product_id" in item


# ---------------------------------------------------------------------------
# Performance — no N+1 queries (deterministic query count)
# ---------------------------------------------------------------------------


def test_query_count_bounded_for_large_order(db_session):
    """Fetching an order with 20 items must not cause N+1 queries."""
    session = db_session
    order_id, products = _build_order_with_items(session, 20)

    engine = session.get_bind()
    select_count = _count_select_queries(
        engine, lambda: OrderService.get_order(session, order_id)
    )

    # With batch loading the query count is constant (≈ 2–3 SELECTs).
    # An N+1 implementation would issue 1 (order) + 1 (items) + 20 (products)
    # = 22+ SELECTs.
    assert select_count <= 5, (
        f"Expected at most 5 SELECT queries for 20 items, got {select_count}. "
        "Possible N+1 query issue."
    )


def test_query_count_does_not_grow_with_item_count(db_session):
    """Query count must stay roughly constant as the item count increases."""
    session = db_session

    # Create two orders: one with 3 items, one with 15 items.
    customer = Customer(name="Compare", email="cmp@example.com")
    session.add(customer)
    session.flush()

    products = [
        Product(name=f"Prod{i}", price=10.0 + i, stock=100) for i in range(15)
    ]
    session.add_all(products)
    session.flush()

    order_small = Order(customer_id=customer.id, status="pending", total_amount=0.0)
    session.add(order_small)
    session.flush()
    for product in products[:3]:
        session.add(
            OrderItem(
                order_id=order_small.id,
                product_id=product.id,
                quantity=1,
                unit_price=product.price,
            )
        )

    order_large = Order(customer_id=customer.id, status="pending", total_amount=0.0)
    session.add(order_large)
    session.flush()
    for product in products:
        session.add(
            OrderItem(
                order_id=order_large.id,
                product_id=product.id,
                quantity=1,
                unit_price=product.price,
            )
        )

    session.commit()

    engine = session.get_bind()

    count_small = _count_select_queries(
        engine, lambda: OrderService.get_order(session, order_small.id)
    )
    count_large = _count_select_queries(
        engine, lambda: OrderService.get_order(session, order_large.id)
    )

    # O(1) → counts are similar.  O(N) → count_large >> count_small.
    assert count_large <= count_small + 2, (
        f"Query count grew from {count_small} (3 items) to {count_large} "
        f"(15 items). Possible N+1 query issue."
    )


def test_large_order_data_correct_via_service(db_session):
    """A 20-item order fetched via the service returns all items correctly."""
    session = db_session
    order_id, products = _build_order_with_items(session, 20)

    detail = OrderService.get_order(session, order_id)

    assert len(detail.items) == 20
    # Build a lookup of expected prices
    expected_prices = {p.id: p.price for p in products}
    for item in detail.items:
        assert item.quantity == 1
        assert item.product_id in expected_prices
        assert item.unit_price == expected_prices[item.product_id]
