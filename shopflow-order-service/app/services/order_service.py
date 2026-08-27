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
        customer_repo = CustomerRepository(db)
        customer = customer_repo.get_by_id(order_data.customer_id)
        if not customer:
            raise ValueError(f"Customer {order_data.customer_id} not found")

        product_repo = ProductRepository(db)
        order_items = []
        total_amount = 0.0

        for item in order_data.items:
            product = product_repo.get_by_id(item.product_id)
            if not product:
                raise ValueError(f"Product {item.product_id} not found")
            if product.stock < item.quantity:
                raise ValueError(f"Insufficient stock for product {item.product_id}")

            unit_price = product.price
            total_amount += unit_price * item.quantity
            order_items.append(
                {
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "unit_price": unit_price,
                }
            )

        if order_data.coupon_code:
            coupon = db.query(Coupon).filter(Coupon.code == order_data.coupon_code).first()
            if not coupon:
                raise ValueError(f"Coupon {order_data.coupon_code} not found")
            _discount, total_amount = apply_coupon(total_amount, coupon)

        order_repo = OrderRepository(db)
        order = order_repo.create(
            {
                "customer_id": order_data.customer_id,
                "status": "pending",
                "total_amount": total_amount,
                "items": order_items,
            }
        )

        for item in order_data.items:
            product_repo.update_stock(item.product_id, -item.quantity)

        return order

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
        order_repo = OrderRepository(db)
        orders = order_repo.get_all(skip=skip, limit=limit)
        return [OrderResponse.model_validate(order) for order in orders]

    @staticmethod
    def pay_order(db: Session, order_id: int) -> object:
        """Transition an order from pending to paid."""
        order_repo = OrderRepository(db)
        order = order_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.status != "pending":
            raise ValueError(f"Cannot pay order with status {order.status}")
        return order_repo.update_status(order_id, "paid")

    @staticmethod
    def cancel_order(db: Session, order_id: int) -> object:
        """Cancel an order.

        Allowed transitions: pending -> cancelled, paid -> cancelled.
        Rejected for shipped or completed orders.
        """
        order_repo = OrderRepository(db)
        order = order_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.status in ("shipped", "completed"):
            raise ValueError(f"Cannot cancel order with status {order.status}")
        return order_repo.update_status(order_id, "cancelled")
