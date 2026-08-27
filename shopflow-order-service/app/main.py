"""ShopFlow Order Service - FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401 - register all models
from app.api.coupons import router as coupons_router
from app.api.customers import router as customers_router
from app.api.orders import router as orders_router
from app.api.products import router as products_router
from app.db.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="ShopFlow Order Service", version="1.0.0", lifespan=lifespan)

app.include_router(customers_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(coupons_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
