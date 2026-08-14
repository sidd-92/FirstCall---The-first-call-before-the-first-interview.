"""Admin-only surface: reviewing and approving self-service business
signups (see routes/dashboard.py's POST /business/request-access).

Every route here depends on `require_admin` (auth.py), which only lets the
single configured `PLATFORM_ADMIN_EMAIL` through -- exact match against the
verified JWT's `email` claim. No separate admin role/table: one admin email
is all this hackathon showcase needs.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from src.auth import require_admin
from src.db import get_db
from src.logging_config import get_logger
from src.models import Business, BusinessStatus

log = get_logger()

router = APIRouter(prefix="/admin", tags=["admin"])


def _serialize_business_for_admin(business: Business) -> dict:
    return {
        "id": business.id,
        "name": business.name,
        "auth0_sub": business.auth0_sub,
        "requested_by_email": business.requested_by_email,
        "owner_email": business.owner_email,
        "status": business.status.value,
        "created_at": business.created_at.isoformat() if business.created_at else None,
        "job_posting_count": len(business.job_postings),
    }


@router.get("/businesses")
def list_businesses_for_admin(
    status_filter: str | None = Query(default=None, alias="status"),
    _admin_email: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List businesses for admin review, e.g. `?status=pending_review`.
    Omit `status` to list every business regardless of state."""
    query = db.query(Business).options(joinedload(Business.job_postings))
    if status_filter is not None:
        try:
            parsed_status = BusinessStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter!r}",
            ) from exc
        query = query.filter(Business.status == parsed_status)

    businesses = query.order_by(Business.id).all()
    return [_serialize_business_for_admin(business) for business in businesses]


@router.post("/businesses/{business_id}/approve")
def approve_business(
    business_id: int,
    _admin_email: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Grant a business active access to gated capabilities (posting jobs,
    MCP Server tools)."""
    business = db.get(Business, business_id)
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    business.status = BusinessStatus.active
    db.commit()

    log.info("business_approved", business_id=business.id, admin_email=_admin_email)

    return _serialize_business_for_admin(business)
