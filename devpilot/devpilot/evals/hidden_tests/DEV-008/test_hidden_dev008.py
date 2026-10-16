"""Audit fields, state changes and idempotent migration of existing SQLite rows."""

import importlib.util
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.models.order import Order

AUDIT = {"updated_at", "paid_at", "cancelled_at"}


def assert_audit_columns():
    assert set(Order.__table__.columns.keys()) >= AUDIT


def test_audit_updates_and_reads(seeded_client, session_factory):
    assert_audit_columns()
    client, ids = seeded_client
    created = client.post(
        "/orders",
        json={
            "customer_id": ids["customers"]["alice"],
            "items": [{"product_id": ids["products"]["mouse"], "quantity": 1}],
        },
    )
    assert created.status_code == 201
    identifier = created.json()["id"]
    before = client.get(f"/orders/{identifier}").json()
    assert before.keys() >= AUDIT
    assert before["paid_at"] is None and before["cancelled_at"] is None
    assert before["updated_at"] is not None
    assert client.get(f"/orders/{identifier}").json() == before
    paid = client.post(f"/orders/{identifier}/pay")
    assert paid.status_code == 200
    after = client.get(f"/orders/{identifier}").json()
    assert after["paid_at"] is not None and after["cancelled_at"] is None
    assert datetime.fromisoformat(after["updated_at"]) >= datetime.fromisoformat(
        before["updated_at"]
    )
    assert client.post(f"/orders/{identifier}/pay").status_code == 409
    assert client.get(f"/orders/{identifier}").json() == after
    assert client.post(f"/orders/{identifier}/cancel").status_code == 200
    cancelled = client.get(f"/orders/{identifier}").json()
    assert cancelled["paid_at"] == after["paid_at"]
    assert cancelled["cancelled_at"] is not None
    assert cancelled["status"] == "cancelled"
    with session_factory() as session:
        row = session.get(Order, identifier)
        row.updated_at = datetime(2001, 1, 1)
        session.commit()
        row.total_amount += 1
        session.commit()
        session.refresh(row)
        assert row.updated_at.year == datetime.now(UTC).year


def test_pending_cancel_leaves_paid_null(seeded_client):
    assert_audit_columns()
    client, ids = seeded_client
    response = client.post(
        "/orders",
        json={
            "customer_id": ids["customers"]["alice"],
            "items": [{"product_id": ids["products"]["mouse"], "quantity": 1}],
        },
    )
    identifier = response.json()["id"]
    assert client.post(f"/orders/{identifier}/cancel").status_code == 200
    value = client.get(f"/orders/{identifier}").json()
    assert value["cancelled_at"] is not None
    assert value["paid_at"] is None


def test_existing_database_migration_twice(tmp_path):
    assert importlib.util.find_spec("app.db.migrate") is not None, "Provide app.db.migrate"
    path = tmp_path / "shopflow.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, "
            "status TEXT, total_amount FLOAT, created_at DATETIME)"
        )
        db.execute("INSERT INTO orders VALUES (17, 4, 'paid', 19.5, '2020-01-02')")
    # Explicit source path allows the documented module command from another cwd.
    import app

    env = dict(os.environ, PYTHONPATH=str(Path(app.__file__).resolve().parent.parent))
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-m", "app.db.migrate"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    with sqlite3.connect(path) as db:
        names = [row[1] for row in db.execute("PRAGMA table_info(orders)")]
        assert set(names) >= AUDIT
        assert len(names) == len(set(names))
        row = db.execute(
            "SELECT id, customer_id, status, total_amount, created_at, "
            "updated_at, paid_at, cancelled_at FROM orders"
        ).fetchone()
        assert row == (17, 4, "paid", 19.5, "2020-01-02", None, None, None)
