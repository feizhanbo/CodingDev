"""ShopFlow Order Service - orders API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.order import OrderCreate, OrderDetailResponse, OrderResponse
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResponse, status_code=201)
def create_order(order_data: OrderCreate, db: Session = Depends(get_db)):
    """Create a new order."""
    try:
        return OrderService.create_order(db, order_data)
    except OperationalError as e:
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            raise HTTPException(status_code=503, detail="Database busy; retry later") from e
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("", response_model=list[OrderResponse])
def get_orders(
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get all orders with pagination."""
    return OrderService.get_orders(db, skip=skip, limit=limit)


@router.get("/{order_id}", response_model=OrderDetailResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    """Get order details by ID."""
    try:
        return OrderService.get_order(db, order_id)
    except OperationalError as e:
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            raise HTTPException(status_code=503, detail="Database busy; retry later") from e
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{order_id}/pay", response_model=OrderResponse)
def pay_order(order_id: int, db: Session = Depends(get_db)):
    """Pay for an order (pending -> paid)."""
    try:
        return OrderService.pay_order(db, order_id)
    except OperationalError as e:
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            raise HTTPException(status_code=503, detail="Database busy; retry later") from e
        raise
    except ValueError as e:
        msg = str(e)
        if "Cannot pay" in msg:
            raise HTTPException(status_code=409, detail=msg) from e
        raise HTTPException(status_code=404, detail=msg) from e


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    """Cancel an order (pending or paid -> cancelled)."""
    try:
        return OrderService.cancel_order(db, order_id)
    except OperationalError as e:
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            raise HTTPException(status_code=503, detail="Database busy; retry later") from e
        raise
    except ValueError as e:
        msg = str(e)
        if "Cannot cancel" in msg:
            raise HTTPException(status_code=409, detail=msg) from e
        raise HTTPException(status_code=404, detail=msg) from e
