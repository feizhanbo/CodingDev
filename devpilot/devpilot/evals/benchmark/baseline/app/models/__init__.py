"""ShopFlow Order Service - models package.

Importing this package registers all models with the SQLAlchemy metadata.
"""

from app.models.coupon import Coupon
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product

__all__ = ["Coupon", "Customer", "Order", "OrderItem", "Product"]
