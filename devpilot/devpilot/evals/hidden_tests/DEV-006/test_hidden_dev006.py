"""Email normalization at assignment and after persistence, without a new API."""
import pytest
from app.models.customer import Customer


@pytest.mark.parametrize("raw,normalized", [
    ("  Mixed.Case+tag@EXAMPLE.Org  ", "mixed.case+tag@example.org"),
    ("\tALPHA@EXAMPLE.COM\n", "alpha@example.com"),
    ("already@example.org", "already@example.org"),
])
def test_normalization_persists(db_session, raw, normalized):
    customer = Customer(name="Email check", email=raw)
    assert customer.email == normalized
    db_session.add(customer)
    db_session.commit()
    identifier = customer.id
    db_session.expunge_all()
    persisted = db_session.get(Customer, identifier)
    assert persisted.email == normalized
    assert persisted.name == "Email check"
    persisted.email = "  CHANGED@EXAMPLE.NET "
    assert persisted.email == "changed@example.net"
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(Customer, identifier).email == "changed@example.net"


def test_normalization_idempotent():
    customer = Customer(name="Repeated", email=" Same@EXAMPLE.ORG ")
    first = customer.email
    customer.email = customer.email
    assert customer.email == first == "same@example.org"


def test_existing_customer_api_preserves_schema(seeded_client):
    client, ids = seeded_client
    response = client.get(f"/customers/{ids['customers']['alice']}")
    assert response.status_code == 200
    assert response.json() == {"id": ids["customers"]["alice"],
                               "name": "Alice", "email": "alice@example.com"}
