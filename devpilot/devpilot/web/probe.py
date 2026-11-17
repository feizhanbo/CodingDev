"""Trusted external probe, executed outside the Agent workspace."""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from app.db.database import Base, SessionLocal, engine
from app.main import app
from app.models.customer import Customer
from app.models.order import Order
from fastapi.testclient import TestClient

Base.metadata.create_all(engine)
with SessionLocal() as db:
    db.add(Customer(id=1, name="Demo customer", email="demo@example.invalid"))
    for i, status in enumerate(["pending", "paid", "shipped", "paid"], 1):
        db.add(
            Order(
                id=i,
                customer_id=1,
                status=status,
                total_amount=i * 100,
                created_at=datetime(2026, 1, 1, 12, 0, 0),
            )
        )
    db.commit()
results = []
with TestClient(app) as client:
    for query in ["?status=paid", "?status=invalid", ""]:
        response = client.get("/orders" + query)
        try:
            body = response.json()
        except ValueError:
            body = response.text[:2000]
        ok = (
            (
                response.status_code == 200
                and isinstance(body, list)
                and [item.get("id") for item in body] == [2, 4]
                and all(x.get("status") == "paid" for x in body)
            )
            if query == "?status=paid"
            else (
                response.status_code == 400
                if query
                else response.status_code == 200 and isinstance(body, list) and len(body) == 4
            )
        )
        results.append(
            {
                "request": "GET /orders" + query,
                "status": response.status_code,
                "body": body,
                "passed": ok,
            }
        )
Path(sys.argv[2]).write_text(json.dumps(results), encoding="utf-8")
