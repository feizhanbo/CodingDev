"""ShopFlow Order Service - Coupon model."""

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Coupon(Base):
    """Coupon entity for applying discounts to orders."""

    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    discount_type: Mapped[str] = mapped_column(String(20))
    discount_value: Mapped[float] = mapped_column(Float)
