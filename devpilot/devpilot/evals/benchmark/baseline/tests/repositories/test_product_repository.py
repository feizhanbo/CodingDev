"""Tests for ProductRepository."""

from app.repositories.product_repository import ProductRepository


def test_get_by_id(seeded_session):
    """Test getting a product by ID."""
    session, ids = seeded_session
    repo = ProductRepository(session)
    product = repo.get_by_id(ids["products"]["laptop"])
    assert product is not None
    assert product.name == "Laptop"
    assert product.price == 999.0


def test_get_by_id_not_found(seeded_session):
    """Test getting a non-existent product returns None."""
    session, _ids = seeded_session
    repo = ProductRepository(session)
    product = repo.get_by_id(9999)
    assert product is None


def test_get_all(seeded_session):
    """Test getting all products."""
    session, _ids = seeded_session
    repo = ProductRepository(session)
    products = repo.get_all()
    assert len(products) == 5


def test_update_stock(seeded_session):
    """Test updating product stock."""
    session, ids = seeded_session
    repo = ProductRepository(session)
    original = repo.get_by_id(ids["products"]["mouse"])
    assert original.stock == 100

    updated = repo.update_stock(ids["products"]["mouse"], -5)
    assert updated.stock == 95

    updated = repo.update_stock(ids["products"]["mouse"], 10)
    assert updated.stock == 105
