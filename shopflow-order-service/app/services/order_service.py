"""ShopFlow Order Service - order service."""

from sqlalchemy.orm import Session

from app.models.coupon import Coupon
from app.repositories.customer_repository import CustomerRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.order import OrderCreate, OrderDetailResponse, OrderResponse
from app.services.pricing_service import apply_coupon


class OrderService:
    """Service for order business logic."""

    @staticmethod
    def create_order(db: Session, order_data: OrderCreate) -> object:
        """Create a new order.

        Validates customer exists, products exist with sufficient stock,
        calculates total, applies coupon if provided, creates order with items,
        and updates product stock.
        """
        try:
            if not order_data.items:
                raise ValueError("Order must contain items")
            quantities: dict[int, int] = {}
            for item in order_data.items:
                if type(item.quantity) is not int or item.quantity <= 0:
                    raise ValueError("Quantity must be a positive integer")
                quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
            if not CustomerRepository(db).get_by_id(order_data.customer_id):
                raise ValueError(f"Customer {order_data.customer_id} not found")
            product_repo = ProductRepository(db)
            items = []
            total = 0.0
            for product_id, quantity in sorted(quantities.items()):
                product = product_repo.get_by_id(product_id)
                if not product:
                    raise ValueError(f"Product {product_id} not found")
                total += product.price * quantity
                items.append({"product_id": product_id, "quantity": quantity,
                              "unit_price": product.price})
                if product_repo.update_stock(product_id, -quantity) is None:
                    raise ValueError(f"Insufficient stock for product {product_id}")
            if order_data.coupon_code:
                coupon = db.query(Coupon).filter(Coupon.code == order_data.coupon_code).first()
                if not coupon:
                    raise ValueError(f"Coupon {order_data.coupon_code} not found")
                _, total = apply_coupon(total, coupon)
            order = OrderRepository(db).create({"customer_id": order_data.customer_id,
                                               "status": "pending", "total_amount": total,
                                               "items": items})
            db.commit()
            db.refresh(order)
            return order
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_order(db: Session, order_id: int) -> OrderDetailResponse:
        """Get order details by ID."""
        order_repo = OrderRepository(db)
        order = order_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return OrderDetailResponse.model_validate(order)

    @staticmethod
    def get_orders(
        db: Session, skip: int = 0, limit: int = 20
    ) -> list[OrderResponse]:
        """Get all orders with pagination."""
        if skip < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid pagination")
        order_repo = OrderRepository(db)
        orders = order_repo.get_all(skip=skip, limit=limit)
        return [OrderResponse.model_validate(order) for order in orders]

    @staticmethod
    def pay_order(db: Session, order_id: int) -> object:
        """Transition an order from pending to paid."""
        try:
            repo = OrderRepository(db)
            if not repo.transition_status(order_id, ("pending",), "paid"):
                order = repo.get_by_id(order_id)
                if order is None:
                    raise ValueError(f"Order {order_id} not found")
                raise ValueError(f"Cannot pay order with status {order.status}")
            db.commit()
            return repo.get_by_id(order_id)
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def cancel_order(db: Session, order_id: int) -> object:
        """Cancel once, restoring stock in the same transaction; payment is simulated."""
        try:
            repo = OrderRepository(db)
            changed = repo.transition_status(order_id, ("pending", "paid"), "cancelled")
            order = repo.get_by_id(order_id)
            if order is None:
                raise ValueError(f"Order {order_id} not found")
            if not changed:
                if order.status != "cancelled":
                    raise ValueError(f"Cannot cancel order with status {order.status}")
            else:
                for item in sorted(order.items, key=lambda x: x.product_id):
                    if ProductRepository(db).update_stock(item.product_id, item.quantity) is None:
                        raise ValueError(f"Product {item.product_id} not found")
            db.commit()
            return repo.get_by_id(order_id)
        except Exception:
            db.rollback()
            raise
