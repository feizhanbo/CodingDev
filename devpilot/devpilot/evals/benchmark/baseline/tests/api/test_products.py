"""Tests for products API."""


def test_get_products(seeded_client):
    """Test GET /products returns all products."""
    client, _ids = seeded_client
    response = client.get("/products")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5
    names = [p["name"] for p in data]
    assert "Laptop" in names
    assert "Phone" in names


def test_get_product_found(seeded_client):
    """Test GET /products/{id} returns 200 for existing product."""
    client, ids = seeded_client
    response = client.get(f"/products/{ids['products']['laptop']}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Laptop"
    assert data["price"] == 999.0


def test_get_product_not_found(client):
    """Test GET /products/{id} returns 404 for non-existent product."""
    response = client.get("/products/9999")
    assert response.status_code == 404
