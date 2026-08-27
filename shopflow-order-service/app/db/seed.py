"""ShopFlow Order Service - database seeding."""

import app.models  # noqa: F401 - register all models
from app.db.database import Base, SessionLocal, engine
from app.models.coupon import Coupon
from app.models.customer import Customer
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.order_service import OrderService


def seed():
    """Seed the database with sample data."""
    Base.metadata.create_all(engine)
    db = SessionLocal()

    # Clear existing data
    db.query(Coupon).delete()
    db.query(Product).delete()
    db.query(Customer).delete()
    db.commit()

    # Customers
    alice = Customer(name="Alice", email="alice@example.com")
    bob = Customer(name="Bob", email="bob@example.com")
    carol = Customer(name="Carol", email="carol@example.com")
    db.add_all([alice, bob, carol])
    db.commit()

    # Products
    laptop = Product(name="Laptop", price=999.0, stock=10)
    phone = Product(name="Phone", price=599.0, stock=20)
    headphones = Product(name="Headphones", price=199.0, stock=50)
    keyboard = Product(name="Keyboard", price=79.0, stock=30)
    mouse = Product(name="Mouse", price=29.0, stock=100)
    db.add_all([laptop, phone, headphones, keyboard, mouse])
    db.commit()

    # Coupons
    save10 = Coupon(code="SAVE10", discount_type="percentage", discount_value=10)
    flat50 = Coupon(code="FLAT50", discount_type="fixed", discount_value=50)
    db.add_all([save10, flat50])
    db.commit()

    # Orders
    order1 = OrderService.create_order(
        db,
        OrderCreate(
            customer_id=alice.id,
            items=[OrderItemCreate(product_id=laptop.id, quantity=1)],
        ),
    )
    print(f"Created pending order #{order1.id} for Alice")

    order2 = OrderService.create_order(
        db,
        OrderCreate(
            customer_id=bob.id,
            items=[OrderItemCreate(product_id=headphones.id, quantity=2)],
        ),
    )
    OrderService.pay_order(db, order2.id)
    print(f"Created paid order #{order2.id} for Bob")

    db.close()
    print("Seed data created successfully.")


if __name__ == "__main__":
    seed()
