"""ShopFlow Order Service - customer repository."""

from sqlalchemy.orm import Session

from app.models.customer import Customer


class CustomerRepository:
    """Repository for Customer CRUD operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, customer_id: int) -> Customer | None:
        """Get a customer by ID."""
        return self.db.query(Customer).filter(Customer.id == customer_id).first()
