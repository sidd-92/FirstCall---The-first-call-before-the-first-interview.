"""Business management routes: onboarding and self-service profile.

`get_current_actor_and_business` (auth.py) auto-creates a placeholder
Business row the first time a verified `sub` is seen, so there is always a
row by the time any of these routes run -- no admin ever inserts one by
hand. `GET/PATCH /business/me` are how the dashboard discovers that a
business is still on its placeholder name (`needs_onboarding`) and clears
that flag by submitting a real one, scoped to the calling `sub` alone.

`POST /businesses/onboard` predates auto-provisioning and is kept for
backwards compatibility: it lets a caller register a real name up front
instead of accepting the placeholder (idempotent: a second call returns the
existing business unchanged).

There used to be a `GET /businesses` here listing every business (name,
owner_email, auth0_sub) to any authenticated caller -- a cross-tenant PII
leak, not scoped to the caller at all. Removed: nothing legitimate depended
on it (see git history / the dashboard's old BusinessesPage, since removed).
A business fetching its own record uses `GET /business/me` above; listing
businesses for review is now `GET /admin/businesses` (routes/admin.py),
gated on `require_admin`.
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.auth import get_current_actor_and_business, get_current_auth0_sub
from src.db import get_db
from src.logging_config import get_logger
from src.models import Business

log = get_logger()

router = APIRouter(tags=["businesses"])


class BusinessOnboard(BaseModel):
    name: str
    owner_email: str | None = None


class BusinessUpdate(BaseModel):
    name: str


def _serialize_business(business: Business) -> dict:
    return {
        "id": business.id,
        "auth0_sub": business.auth0_sub,
        "name": business.name,
        "owner_email": business.owner_email,
        "needs_onboarding": business.needs_onboarding,
        "status": business.status.value,
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
        needs_onboarding=False,
    )
    db.add(business)
    db.commit()
    db.refresh(business)

    log.info("business_onboarded", business_id=business.id, auth0_sub=auth0_sub)
    return _serialize_business(business)


@router.get("/business/me")
def get_my_business(
    business_and_sub: tuple[int, str] = Depends(get_current_actor_and_business),
    db: Session = Depends(get_db),
):
    """Return the calling account's own Business row, auto-provisioning one
    (via `get_current_actor_and_business`) if this is its first request."""
    business_id, _ = business_and_sub
    business = db.get(Business, business_id)
    return _serialize_business(business)


@router.patch("/business/me")
def update_my_business(
    payload: BusinessUpdate,
    business_and_sub: tuple[int, str] = Depends(get_current_actor_and_business),
    db: Session = Depends(get_db),
):
    """Set the calling account's real business name and clear
    `needs_onboarding`. Scoped to the business_id resolved from the verified
    JWT -- never a client-supplied id, so one business can only ever update
    itself."""
    business_id, auth0_sub = business_and_sub
    business = db.get(Business, business_id)

    business.name = payload.name
    business.needs_onboarding = False
    db.commit()
    db.refresh(business)

    log.info("business_updated", business_id=business.id, auth0_sub=auth0_sub)
    return _serialize_business(business)
