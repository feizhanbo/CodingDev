"""ShopFlow Order Service - customer schemas."""

from pydantic import BaseModel, ConfigDict


class CustomerResponse(BaseModel):
    """Response schema for a customer."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
