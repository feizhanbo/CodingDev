"""ShopFlow Order Service - order repository."""

from sqlalchemy.orm import Session, selectinload

from app.models.order import Order
from app.models.order_item import OrderItem


class OrderRepository:
    """Repository for Order CRUD operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, order_data: dict) -> Order:
        """Create a new order with items.

        Args:
            order_data: dict with keys customer_id, status, total_amount,
                        and items (list of dicts with product_id, quantity, unit_price).
        """
        items_data = order_data.pop("items", [])
        order = Order(**order_data)
        self.db.add(order)
        self.db.flush()

        for item_data in items_data:
            item = OrderItem(order_id=order.id, **item_data)
            self.db.add(item)

        self.db.commit()
        self.db.refresh(order)
        return order

    def get_by_id(self, order_id: int) -> Order | None:
        """Get an order by ID with items eager-loaded."""
        return (
            self.db.query(Order)
            .options(selectinload(Order.items))
            .filter(Order.id == order_id)
            .first()
        )

    def get_all(self, skip: int = 0, limit: int = 20) -> list[Order]:
        """Get all orders with pagination."""
        return self.db.query(Order).offset(skip).limit(limit).all()

    def update_status(self, order_id: int, new_status: str) -> Order | None:
        """Update the status of an order."""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if order:
            order.status = new_status
            self.db.commit()
            self.db.refresh(order)
        return order
