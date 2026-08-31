"""Hidden tests for DEV-003: Fix order pagination edge case.

These tests are copied to the workspace AFTER the agent run completes
and are used to verify the implementation against hidden acceptance criteria.

Verified behaviour:
  - Normal pagination works (first page, single item, last page)
  - skip beyond total records returns an empty list (HTTP 200)
  - limit=0 returns an empty list (HTTP 200)
  - Negative skip returns HTTP 400
  - Negative limit returns HTTP 400
  - Empty dataset returns an empty list (HTTP 200)
  - Numbers differ from visible tests to prevent hard-coding
"""

from __future__ import annotations


def _create_orders(client, ids, count, product_key="mouse"):
    """Create *count* orders and return their IDs."""
    created_ids = []
    for _ in range(count):
        resp = client.post(
            "/orders",
            json={
                "customer_id": ids["customers"]["alice"],
                "items": [
                    {"product_id": ids["products"][product_key], "quantity": 1}
                ],
            },
        )
        created_ids.append(resp.json()["id"])
    return created_ids


# ---------------------------------------------------------------------------
# Normal pagination (no regression)
# ---------------------------------------------------------------------------


def test_first_page_returns_orders(seeded_client):
    """skip=0 with limit smaller than total returns the first page."""
    client, ids = seeded_client
    _create_orders(client, ids, 5)

    response = client.get("/orders?skip=0&limit=3")

    assert response.status_code == 200
    assert len(response.json()) == 3


def test_limit_one_returns_single_item(seeded_client):
    """limit=1 returns exactly one order per page."""
    client, ids = seeded_client
    _create_orders(client, ids, 5)

    response = client.get("/orders?skip=0&limit=1")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_last_page_returns_remaining(seeded_client):
    """The last page returns only the remaining items, not a full page."""
    client, ids = seeded_client
    _create_orders(client, ids, 7)

    # 7 items with limit=3 → pages of 3, 3, 1. Last page (skip=6) → 1 item.
    response = client.get("/orders?skip=6&limit=3")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_default_pagination_unchanged(seeded_client):
    """Default pagination (no query params) returns all orders."""
    client, ids = seeded_client
    _create_orders(client, ids, 4)

    response = client.get("/orders")

    assert response.status_code == 200
    assert len(response.json()) == 4


# ---------------------------------------------------------------------------
# Edge cases — out-of-range skip
# ---------------------------------------------------------------------------


def test_skip_beyond_total_returns_empty(seeded_client):
    """skip exceeding the total record count returns an empty list (200)."""
    client, ids = seeded_client
    _create_orders(client, ids, 3)

    response = client.get("/orders?skip=100&limit=10")

    assert response.status_code == 200
    assert response.json() == []


def test_skip_equals_total_returns_empty(seeded_client):
    """skip exactly equal to the total record count returns an empty list."""
    client, ids = seeded_client
    _create_orders(client, ids, 5)

    response = client.get("/orders?skip=5&limit=10")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Edge cases — limit=0
# ---------------------------------------------------------------------------


def test_limit_zero_returns_empty(seeded_client):
    """limit=0 returns an empty list (200), not an error."""
    client, ids = seeded_client
    _create_orders(client, ids, 3)

    response = client.get("/orders?skip=0&limit=0")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Invalid inputs — negative values
# ---------------------------------------------------------------------------


def test_negative_skip_returns_400(seeded_client):
    """Negative skip must return HTTP 400, not 500."""
    client, _ids = seeded_client

    response = client.get("/orders?skip=-1&limit=10")

    assert response.status_code == 400


def test_negative_limit_returns_400(seeded_client):
    """Negative limit must return HTTP 400, not 500."""
    client, _ids = seeded_client

    response = client.get("/orders?skip=0&limit=-5")

    assert response.status_code == 400


def test_negative_skip_and_limit_returns_400(seeded_client):
    """Both skip and limit negative must return HTTP 400."""
    client, _ids = seeded_client

    response = client.get("/orders?skip=-3&limit=-1")

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Empty dataset
# ---------------------------------------------------------------------------


def test_empty_dataset_returns_empty_list(seeded_client):
    """When no orders exist, the API returns an empty list."""
    client, _ids = seeded_client

    response = client.get("/orders")

    assert response.status_code == 200
    assert response.json() == []


def test_empty_dataset_skip_beyond_returns_empty(seeded_client):
    """On an empty dataset, skip beyond total still returns empty list (200)."""
    client, _ids = seeded_client

    response = client.get("/orders?skip=10&limit=5")

    assert response.status_code == 200
    assert response.json() == []
