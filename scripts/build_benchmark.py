"""Regenerate versioned evaluator-only patches from the pinned upstream baseline.

Never modifies ShopFlow. Run after editing reference definitions, then run
`devpilot benchmark-check` to prove every starting point fails and fix passes.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "devpilot/devpilot/evals/benchmark"
COMMIT = "1ee0adf0549a807e1b99705c027742c48d634292"
PREFIX = "shopflow-order-service/"


def read_baseline() -> dict[str, str]:
    paths = (
        subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", COMMIT, PREFIX], cwd=ROOT
        )
        .decode()
        .splitlines()
    )
    return {
        path.removeprefix(PREFIX): subprocess.check_output(
            ["git", "show", f"{COMMIT}:{path}"], cwd=ROOT
        )
        .decode("utf-8")
        .replace("\r\n", "\n")
        for path in paths
    }


def patch(before: dict[str, str], after: dict[str, str]) -> str:
    chunks = []
    for path in sorted(before.keys() | after.keys()):
        if before.get(path) == after.get(path):
            continue
        chunks.extend(
            difflib.unified_diff(
                before.get(path, "").splitlines(keepends=True),
                after.get(path, "").splitlines(keepends=True),
                fromfile=f"a/{path}" if path in before else "/dev/null",
                tofile=f"b/{path}" if path in after else "/dev/null",
            )
        )
    return "".join(chunks)


def replace(files: dict[str, str], path: str, old: str, new: str) -> None:
    assert files[path].count(old) == 1, (path, old)
    files[path] = files[path].replace(old, new)


def variants(base: dict[str, str], issue: str) -> tuple[dict, dict]:
    start = dict(base)
    service = "app/services/order_service.py"
    api = "app/api/orders.py"
    repository = "app/repositories/order_repository.py"
    if issue == "DEV-002":
        replace(
            start,
            service,
            '        if order.status in ("shipped", "completed"):\n'
            '            raise ValueError(f"Cannot cancel order with status {order.status}")\n',
            "",
        )
    elif issue == "DEV-007":
        replace(
            start,
            service,
            '        if order.status != "pending":\n'
            '            raise ValueError(f"Cannot pay order with status {order.status}")\n',
            "",
        )
    elif issue == "DEV-005":
        replace(
            start,
            service,
            "        return OrderDetailResponse.model_validate(order)",
            "        # Legacy per-item product lookup; this grows with order size.\n"
            "        from app.models.product import Product\n"
            "        for item in order.items:\n"
            "            db.query(Product).filter(Product.id == item.product_id).one()\n"
            "        return OrderDetailResponse.model_validate(order)",
        )
    fixed = dict(start)
    if issue in {"DEV-002", "DEV-005", "DEV-007"}:
        fixed[service] = base[service]
    elif issue == "DEV-001":
        replace(
            fixed,
            repository,
            "def get_all(self, skip: int = 0, limit: int = 20)",
            "def get_all(self, skip: int = 0, limit: int = 20, status: str | None = None)",
        )
        replace(
            fixed,
            repository,
            "        return self.db.query(Order).offset(skip).limit(limit).all()",
            "        query = self.db.query(Order)\n"
            "        if status is not None:\n"
            "            query = query.filter(Order.status == status)\n"
            "        return query.order_by(Order.id).offset(skip).limit(limit).all()",
        )
        replace(
            fixed,
            service,
            "        db: Session, skip: int = 0, limit: int = 20",
            "        db: Session, skip: int = 0, limit: int = 20, status: str | None = None",
        )
        replace(
            fixed,
            service,
            "orders = order_repo.get_all(skip=skip, limit=limit)",
            "orders = order_repo.get_all(skip=skip, limit=limit, status=status)",
        )
        replace(
            fixed,
            api,
            "def get_orders(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):",
            "def get_orders(skip: int = 0, limit: int = 20, status: str | None = None,\n"
            "               db: Session = Depends(get_db)):",
        )
        replace(
            fixed,
            api,
            "    return OrderService.get_orders(db, skip=skip, limit=limit)",
            '    if status is not None and status not in {"pending", "paid", "shipped",\n'
            '                                              "completed", "cancelled"}:\n'
            '        raise HTTPException(status_code=400, detail="Invalid status")\n'
            "    return OrderService.get_orders(db, skip=skip, limit=limit, status=status)",
        )
    elif issue == "DEV-003":
        replace(
            fixed,
            api,
            "    return OrderService.get_orders(db, skip=skip, limit=limit)",
            "    if skip < 0 or limit < 0:\n"
            '        raise HTTPException(status_code=400, detail="Negative pagination")\n'
            "    return OrderService.get_orders(db, skip=skip, limit=limit)",
        )
    elif issue == "DEV-004":
        replace(
            fixed,
            "app/services/pricing_service.py",
            "discount = total_amount * (coupon.discount_value / 100)",
            "discount = min(total_amount, total_amount * (coupon.discount_value / 100))",
        )
    elif issue == "DEV-006":
        customer = "app/models/customer.py"
        replace(
            fixed,
            customer,
            "from sqlalchemy.orm import Mapped, mapped_column, relationship",
            "from sqlalchemy.orm import Mapped, mapped_column, relationship, validates",
        )
        fixed[customer] += (
            '\n    @validates("email")\n'
            "    def normalize_email(self, key, value):\n"
            "        return value.strip().lower()\n"
        )
    elif issue == "DEV-008":
        model = "app/models/order.py"
        replace(
            fixed,
            model,
            "from datetime import datetime",
            "from datetime import UTC, datetime",
        )
        replace(
            fixed,
            model,
            "from sqlalchemy.orm import Mapped, mapped_column, relationship",
            "from sqlalchemy.orm import Mapped, mapped_column, relationship, validates",
        )
        replace(
            fixed,
            model,
            "\n\nclass Order(Base):",
            "\n\ndef utcnow():\n    return datetime.now(UTC).replace(tzinfo=None)\n\n\nclass Order(Base):",
        )
        replace(
            fixed,
            model,
            '    items: Mapped[list["OrderItem"]] = relationship(',
            "    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)\n"
            "    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)\n"
            "    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)\n\n"
            '    items: Mapped[list["OrderItem"]] = relationship(',
        )
        fixed[model] += (
            '\n    @validates("status")\n'
            "    def audit_status(self, key, value):\n"
            "        if value != self.status:\n"
            '            if value == "paid":\n'
            "                self.paid_at = utcnow()\n"
            '            elif value == "cancelled":\n'
            "                self.cancelled_at = utcnow()\n"
            "        return value\n"
        )
        replace(
            fixed,
            "app/schemas/order.py",
            "    created_at: datetime\n",
            "    created_at: datetime\n    updated_at: datetime | None = None\n"
            "    paid_at: datetime | None = None\n    cancelled_at: datetime | None = None\n",
        )
        fixed["app/db/migrate.py"] = MIGRATION
    fixed["tests/test_issue_regression.py"] = VISIBLE_TESTS[issue]
    return start, fixed


MIGRATION = '''"""Idempotent migration of an existing SQLite ShopFlow database."""
import sqlite3
from pathlib import Path


def migrate(path="shopflow.db"):
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(orders)")}
        if not columns:
            raise ValueError("orders table missing")
        for name in ("updated_at", "paid_at", "cancelled_at"):
            if name not in columns:
                db.execute(f"ALTER TABLE orders ADD COLUMN {name} DATETIME")


if __name__ == "__main__":
    migrate()
'''
VISIBLE_TESTS = {
    "DEV-001": 'def test_invalid_status(client):\n    assert client.get("/orders?status=unknown").status_code == 400\n',
    "DEV-002": 'import pytest\nfrom app.models.order import Order\nfrom app.services.order_service import OrderService\n\ndef test_cannot_cancel_shipped(db_session):\n    order = Order(customer_id=1, status="shipped")\n    db_session.add(order)\n    db_session.commit()\n    with pytest.raises(ValueError):\n        OrderService.cancel_order(db_session, order.id)\n',
    "DEV-003": 'def test_negative_limit(client):\n    assert client.get("/orders?limit=-7").status_code == 400\n',
    "DEV-004": 'from app.models.coupon import Coupon\nfrom app.services.pricing_service import apply_coupon\n\ndef test_cap_percentage():\n    assert apply_coupon(30, Coupon(discount_type="percentage", discount_value=120)) == (30, 0)\n',
    "DEV-005": 'def test_missing_order_still_404(client):\n    assert client.get("/orders/999999").status_code == 404\n',
    "DEV-006": 'from app.models.customer import Customer\n\ndef test_normalized_customer():\n    assert Customer(name="test", email=" A@B.COM ").email == "a@b.com"\n',
    "DEV-007": 'import pytest\nfrom app.models.order import Order\nfrom app.services.order_service import OrderService\n\ndef test_cannot_repay(db_session):\n    order = Order(customer_id=1, status="paid")\n    db_session.add(order)\n    db_session.commit()\n    with pytest.raises(ValueError):\n        OrderService.pay_order(db_session, order.id)\n',
    "DEV-008": 'from app.models.order import Order\n\ndef test_audit_columns():\n    assert {"paid_at", "cancelled_at", "updated_at"} <= set(Order.__table__.columns.keys())\n',
}


def main() -> None:
    base = read_baseline()
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "dataset_version": "v1.1",
        "baseline_commit": COMMIT,
        "baseline_files": {
            p: hashlib.sha256(s.encode()).hexdigest() for p, s in base.items()
        },
        "issues": {},
    }
    for number in range(1, 9):
        issue = f"DEV-{number:03}"
        start, fixed = variants(base, issue)
        directory = DEST / issue
        directory.mkdir(exist_ok=True)
        for name, value in (
            ("start.patch", patch(base, start)),
            ("reference.patch", patch(start, fixed)),
        ):
            (directory / name).write_text(value, encoding="utf-8", newline="")
        resources = {
            str(path.relative_to(DEST.parent)).replace("\\", "/"): hashlib.sha256(
                path.read_text(encoding="utf-8").encode()
            ).hexdigest()
            for path in sorted((DEST.parent / "hidden_tests" / issue).rglob("*.py"))
        }
        resources[f"issues/{issue}.yaml"] = hashlib.sha256(
            (DEST.parent / "issues" / f"{issue}.yaml")
            .read_text(encoding="utf-8")
            .encode()
        ).hexdigest()
        resources["shared/conftest.py"] = hashlib.sha256(
            (DEST.parent / "shared/conftest.py").read_text(encoding="utf-8").encode()
        ).hexdigest()
        manifest["issues"][issue] = {
            "resources": resources,
            "start_patch_sha256": hashlib.sha256(
                patch(base, start).encode()
            ).hexdigest(),
            "reference_patch_sha256": hashlib.sha256(
                patch(start, fixed).encode()
            ).hexdigest(),
        }
    (DEST / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
