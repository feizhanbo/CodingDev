"""Business invariants, fault rollback and independent SQLite connections."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.order_service import OrderService


def request(quantity=1, product_id=1):
    return OrderCreate(customer_id=1, items=[OrderItemCreate(product_id=product_id,
                                                           quantity=quantity)])


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True])
def test_api_rejects_invalid_quantities(seeded_client, quantity):
    client, ids = seeded_client
    response = client.post("/orders", json={"customer_id": ids["customers"]["alice"],
        "items": [{"product_id": ids["products"]["mouse"], "quantity": quantity}]})
    assert response.status_code == 422


def test_empty_order_rejected(seeded_client):
    client, ids = seeded_client
    assert client.post("/orders", json={"customer_id": ids["customers"]["alice"],
                                       "items": []}).status_code == 422


@pytest.mark.parametrize("query", ["skip=-1", "limit=0", "limit=101"])
def test_pagination_bounds(seeded_client, query):
    client, _ = seeded_client
    assert client.get(f"/orders?{query}").status_code == 422


def test_database_lock_has_retryable_response(seeded_client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    client, ids = seeded_client

    def locked(*args):
        raise OperationalError("UPDATE", {}, RuntimeError("database is locked"))

    monkeypatch.setattr(OrderService, "create_order", locked)
    response = client.post("/orders", json={"customer_id": ids["customers"]["alice"],
        "items": [{"product_id": ids["products"]["mouse"], "quantity": 1}]})
    assert response.status_code == 503


def test_seed_repeatable_only_in_temporary_database(file_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.db import seed as seeding

    monkeypatch.setattr(seeding, "engine", file_engine)
    monkeypatch.setattr(seeding, "SessionLocal", sessionmaker(bind=file_engine))
    seeding.seed()
    seeding.seed()
    with Session(file_engine) as db:
        assert db.query(Order).count() == 2
        assert db.query(OrderItem).count() == 2


def test_duplicate_products_aggregate_before_stock_check(seeded_session):
    session, ids = seeded_session
    product_id = ids["products"]["laptop"]
    data = OrderCreate(customer_id=ids["customers"]["alice"], items=[
        OrderItemCreate(product_id=product_id, quantity=6),
        OrderItemCreate(product_id=product_id, quantity=6)])
    with pytest.raises(ValueError, match="Insufficient stock"):
        OrderService.create_order(session, data)
    assert session.get(Product, product_id).stock == 10
    assert session.query(Order).count() == 0
    data.items[0].quantity = 2
    data.items[1].quantity = 3
    order = OrderService.create_order(session, data)
    assert len(order.items) == 1 and order.items[0].quantity == 5
    assert session.get(Product, product_id).stock == 5


@pytest.mark.parametrize("failure", ["second_stock", "items", "commit"])
def test_failure_rolls_back_everything(seeded_session, monkeypatch, failure):
    session, ids = seeded_session
    keys = [ids["products"]["laptop"], ids["products"]["phone"]]
    if failure == "second_stock":
        original = ProductRepository.update_stock

        def fail(self, product_id, delta):
            if product_id == keys[1]:
                raise RuntimeError("injected stock failure")
            return original(self, product_id, delta)

        monkeypatch.setattr(ProductRepository, "update_stock", fail)
    elif failure == "items":
        original = OrderRepository.create

        def fail(self, data):
            original(self, data)
            raise RuntimeError("injected after item flush")

        monkeypatch.setattr(OrderRepository, "create", fail)
    else:
        def fail():
            raise RuntimeError("injected commit failure")

        monkeypatch.setattr(session, "commit", fail)
    data = OrderCreate(customer_id=ids["customers"]["alice"], items=[
        OrderItemCreate(product_id=p, quantity=2) for p in keys])
    with pytest.raises(RuntimeError, match="injected"):
        OrderService.create_order(session, data)
    assert [session.get(Product, p).stock for p in keys] == [10, 20]
    assert session.query(Order).count() == session.query(OrderItem).count() == 0


def test_cancellation_restores_stock_once(seeded_session):
    session, ids = seeded_session
    product = ids["products"]["laptop"]
    order = OrderService.create_order(session, OrderCreate(customer_id=ids["customers"]["alice"],
        items=[OrderItemCreate(product_id=product, quantity=2)]))
    OrderService.cancel_order(session, order.id)
    OrderService.cancel_order(session, order.id)
    assert session.get(Product, product).stock == 10


@pytest.fixture
def file_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrency.db'}",
                           connect_args={"timeout": 5})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Customer(name="C", email="c@example.invalid"),
                    Product(name="P", price=10, stock=10)])
        db.commit()
    yield engine
    engine.dispose()


def simultaneous(engine, action):
    barrier = Barrier(2)

    def worker(_):
        with Session(engine) as session:
            barrier.wait(timeout=5)
            try:
                action(session)
                return "ok"
            except ValueError:
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        return sorted(pool.map(worker, range(2)))


def test_concurrent_orders_do_not_oversell(file_engine):
    result = simultaneous(file_engine, lambda s: OrderService.create_order(s, request(7)))
    assert result == ["ok", "rejected"]
    with Session(file_engine) as db:
        assert db.get(Product, 1).stock == 3
        assert len(db.scalars(select(Order)).all()) == 1


def test_concurrent_payment_and_cancellation(file_engine):
    with Session(file_engine) as db:
        identifier = OrderService.create_order(db, request(2)).id
    assert simultaneous(file_engine, lambda s: OrderService.pay_order(s, identifier)) == [
        "ok", "rejected"]
    assert simultaneous(file_engine, lambda s: OrderService.cancel_order(s, identifier)) == [
        "ok", "ok"]
    with Session(file_engine) as db:
        assert db.get(Product, 1).stock == 10
        assert db.get(Order, identifier).status == "cancelled"
