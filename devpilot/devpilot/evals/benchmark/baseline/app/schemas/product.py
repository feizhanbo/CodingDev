"""ShopFlow Order Service - product schemas."""

from pydantic import BaseModel, ConfigDict


class ProductResponse(BaseModel):
    """Response schema for a product."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: float
    stock: int
