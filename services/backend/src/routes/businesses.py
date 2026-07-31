"""Business management routes: onboarding and listing.

`POST /businesses/onboard` is the missing signup half of the dashboard.
`get_current_business` (auth.py) refuses tokens whose `sub` has no Business
row -- and until a user onboards there is no row. Onboarding therefore
verifies the token via `get_current_auth0_sub` instead, then creates the
row keyed on the token's `sub` (idempotent: a second call returns the
existing business unchanged).
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.auth import get_current_auth0_sub
from src.db import get_db
from src.logging_config import get_logger
from src.models import Business

log = get_logger()

router = APIRouter(tags=["businesses"])


class BusinessOnboard(BaseModel):
    name: str
    owner_email: str | None = None


def _serialize_business(business: Business) -> dict:
    return {
        "id": business.id,
        "auth0_sub": business.auth0_sub,
        "name": business.name,
        "owner_email": business.owner_email,
        "created_at": business.created_at.isoformat() if business.created_at else None,
    }


@router.post("/businesses/onboard", status_code=status.HTTP_201_CREATED)
def onboard_business(
    payload: BusinessOnboard,
    auth0_sub: str = Depends(get_current_auth0_sub),
    db: Session = Depends(get_db),
):
    """Register the calling Auth0 account as a Business (idempotent)."""
    existing = db.query(Business).filter(Business.auth0_sub == auth0_sub).first()
    if existing is not None:
        log.info("business_onboard_skipped", business_id=existing.id, auth0_sub=auth0_sub)
        return _serialize_business(existing)

    business = Business(
        auth0_sub=auth0_sub,
        name=payload.name,
        owner_email=payload.owner_email,
    )
    db.add(business)
    db.commit()
    db.refresh(business)

    log.info("business_onboarded", business_id=business.id, auth0_sub=auth0_sub)
    return _serialize_business(business)


@router.get("/businesses")
def list_businesses(
    _auth0_sub: str = Depends(get_current_auth0_sub),
    db: Session = Depends(get_db),
):
    """List all registered businesses. Any authenticated account may call."""
    businesses = db.query(Business).order_by(Business.id).all()
    return [_serialize_business(business) for business in businesses]
