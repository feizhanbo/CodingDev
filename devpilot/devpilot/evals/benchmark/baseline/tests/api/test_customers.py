"""Tests for customers API."""


def test_get_customer_found(seeded_client):
    """Test GET /customers/{id} returns 200 for existing customer."""
    client, ids = seeded_client
    response = client.get(f"/customers/{ids['customers']['alice']}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Alice"
    assert data["email"] == "alice@example.com"


def test_get_customer_not_found(client):
    """Test GET /customers/{id} returns 404 for non-existent customer."""
    response = client.get("/customers/9999")
    assert response.status_code == 404
