"""Test configuration and fixtures for ShopFlow Order Service."""

import asyncio

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 - register all models
from app.db.database import Base, get_db
from app.main import app

# Create test engine (in-memory SQLite with StaticPool for shared connection)
TEST_DATABASE_URL = "sqlite://"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override the get_db dependency to use the test database."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


class TestClient:
    """Synchronous test client wrapping httpx.AsyncClient with ASGITransport."""

    def __init__(self, app):
        self._transport = ASGITransport(app=app)
        self._loop = asyncio.new_event_loop()

    def _request(self, method, url, **kwargs):
        async def _do():
            async with httpx.AsyncClient(
                transport=self._transport, base_url="http://test"
            ) as client:
                return await client.request(method, url, **kwargs)

        return self._loop.run_until_complete(_do())

    def get(self, url, **kwargs):
        return self._request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._request("POST", url, **kwargs)

    def close(self):
        self._loop.close()


def _seed_data(session: Session) -> dict:
    """Seed the database with test data. Returns a dict of IDs."""
    from app.models.coupon import Coupon
    from app.models.customer import Customer
    from app.models.product import Product

    alice = Customer(name="Alice", email="alice@example.com")
    bob = Customer(name="Bob", email="bob@example.com")
    carol = Customer(name="Carol", email="carol@example.com")
    session.add_all([alice, bob, carol])

    laptop = Product(name="Laptop", price=999.0, stock=10)
    phone = Product(name="Phone", price=599.0, stock=20)
    headphones = Product(name="Headphones", price=199.0, stock=50)
    keyboard = Product(name="Keyboard", price=79.0, stock=30)
    mouse = Product(name="Mouse", price=29.0, stock=100)
    session.add_all([laptop, phone, headphones, keyboard, mouse])

    save10 = Coupon(code="SAVE10", discount_type="percentage", discount_value=10)
    flat50 = Coupon(code="FLAT50", discount_type="fixed", discount_value=50)
    session.add_all([save10, flat50])

    session.commit()

    for obj in [
        alice,
        bob,
        carol,
        laptop,
        phone,
        headphones,
        keyboard,
        mouse,
        save10,
        flat50,
    ]:
        session.refresh(obj)

    return {
        "customers": {"alice": alice.id, "bob": bob.id, "carol": carol.id},
        "products": {
            "laptop": laptop.id,
            "phone": phone.id,
            "headphones": headphones.id,
            "keyboard": keyboard.id,
            "mouse": mouse.id,
        },
        "coupons": {"save10": save10.id, "flat50": flat50.id},
    }


@pytest.fixture
def db_session() -> Session:
    """Provide a clean database session (no seed data)."""
    Base.metadata.create_all(test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(test_engine)


@pytest.fixture
def seeded_session() -> tuple[Session, dict]:
    """Provide a database session with seed data."""
    Base.metadata.create_all(test_engine)
    session = TestSessionLocal()
    ids = _seed_data(session)
    try:
        yield session, ids
    finally:
        session.close()
        Base.metadata.drop_all(test_engine)


@pytest.fixture
def client() -> TestClient:
    """Provide a test client with an empty database."""
    Base.metadata.create_all(test_engine)
    tc = TestClient(app)
    try:
        yield tc
    finally:
        tc.close()
        Base.metadata.drop_all(test_engine)


@pytest.fixture
def seeded_client() -> tuple[TestClient, dict]:
    """Provide a test client with seeded data."""
    Base.metadata.create_all(test_engine)
    session = TestSessionLocal()
    ids = _seed_data(session)
    session.close()

    tc = TestClient(app)
    try:
        yield tc, ids
    finally:
        tc.close()
        Base.metadata.drop_all(test_engine)


@pytest.fixture
def session_factory():
    """Factory for creating test database sessions for direct DB access in tests."""
    return TestSessionLocal
