"""ShopFlow Order Service - product repository."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.product import Product


class ProductRepository:
    """Repository for Product CRUD operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, product_id: int) -> Product | None:
        """Get a product by ID."""
        return self.db.query(Product).filter(Product.id == product_id).first()

    def get_all(self) -> list[Product]:
        """Get all products."""
        return self.db.query(Product).all()

    def update_stock(self, product_id: int, delta: int) -> Product | None:
        """Update product stock by delta (can be negative)."""
        changed = self.db.execute(
            update(Product).where(Product.id == product_id, Product.stock + delta >= 0)
            .values(stock=Product.stock + delta)
        )
        self.db.flush()
        if changed.rowcount != 1:
            return None
        product = self.get_by_id(product_id)
        self.db.refresh(product)
        return product
