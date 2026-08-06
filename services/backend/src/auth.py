"""Auth0 JWT verification via JWKS.

Reads `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` from the environment. Dashboard
routes depend on `get_current_business` / `get_current_actor_and_business`,
which verify the bearer token's signature/claims against Auth0's JWKS
endpoint and resolve the token's `sub` claim to a `Business.id`.

Every dashboard route MUST obtain the business_id from one of these
dependencies -- never accept a business_id from the client (query param,
body, or header) and trust it directly.
"""

import json
import os
import urllib.request
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JOSEError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db import get_db
from src.logging_config import get_logger
from src.models import PLACEHOLDER_BUSINESS_NAME, Business, BusinessStatus

log = get_logger()

AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "")
ALGORITHMS = ["RS256"]

# Single admin address for this hackathon showcase -- see routes/admin.py.
# Supporting multiple admins is a future enhancement, not needed now.
PLATFORM_ADMIN_EMAIL = os.environ.get("PLATFORM_ADMIN_EMAIL", "")

_bearer_scheme = HTTPBearer()


@lru_cache(maxsize=1)
def _get_jwks() -> dict:
    """Fetch (and cache) Auth0's JSON Web Key Set for this tenant.

    TODO: add TTL-based refresh / handle key rotation instead of a permanent
    process-lifetime cache.
    """
    url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
    with urllib.request.urlopen(url) as response:
        return json.load(response)


def _get_signing_key(token: str) -> dict:
    unverified_header = jwt.get_unverified_header(token)
    jwks = _get_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            return key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unable to find matching JWKS signing key",
    )


def verify_token(token: str) -> dict:
    """Verify an Auth0-issued JWT and return its decoded claims."""
    try:
        signing_key = _get_signing_key(token)
        return jwt.decode(
            token,
            signing_key,
            algorithms=ALGORITHMS,
            audience=AUTH0_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/",
        )
    except JOSEError as exc:
        log.info("jwt_verification_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def get_current_claims(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency: verify the request's bearer token and return its
    full decoded claims.

    FastAPI caches a dependency's result per request, so composing this into
    several other dependencies (get_current_auth0_sub, get_current_business_row,
    require_admin, ...) on the same route still only verifies the token once.
    """
    return verify_token(credentials.credentials)


def get_current_auth0_sub(claims: dict = Depends(get_current_claims)) -> str:
    """FastAPI dependency: the verified token's `sub` claim.

    Unlike `get_current_business`, this does NOT require the account to have
    a Business row yet -- it exists so the onboarding route can register a
    business for an account that isn't registered (which is exactly the case
    `get_current_business` rejects).
    """
    return claims.get("sub")


def _get_or_provision_business(db: Session, auth0_sub: str) -> Business:
    """Look up the Business row for a verified `sub`, auto-provisioning a
    minimal one (placeholder name, needs_onboarding True, status
    "unrequested") on first sight -- this must be fully self-service, with
    no admin manually inserting a row before a new account can be used.
    Shared by every dependency below so there's exactly one provisioning
    path."""
    business = db.query(Business).filter(Business.auth0_sub == auth0_sub).first()
    if business is None:
        business = Business(auth0_sub=auth0_sub, name=PLACEHOLDER_BUSINESS_NAME)
        db.add(business)
        try:
            db.commit()
        except IntegrityError:
            # Lost a race with a concurrent request for the same sub -- fall
            # back to the row the other request just inserted.
            db.rollback()
            business = db.query(Business).filter(Business.auth0_sub == auth0_sub).first()
        else:
            db.refresh(business)
            log.info("business_auto_provisioned", business_id=business.id, auth0_sub=auth0_sub)
    return business


def get_current_actor_and_business(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> tuple[int, str]:
    """FastAPI dependency: resolve the verified token to
    `(business_id, auth0_sub)`, auto-provisioning the Business row if this
    is the account's first request (see `_get_or_provision_business`).

    Also returns the verified `sub`, which routes that write to
    `AuditLogEntry` need for the `actor` column. Never trust a business_id
    supplied by the client -- use only this value.
    """
    auth0_sub = claims.get("sub")
    business = _get_or_provision_business(db, auth0_sub)
    return business.id, auth0_sub


def get_current_business(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> int:
    """FastAPI dependency: resolve the verified token to a `Business.id`.

    Returns the verified business_id -- routes must use this value for
    every query and must never accept a business_id supplied by the client.
    """
    business_id, _ = get_current_actor_and_business(claims, db)
    return business_id


def get_current_business_row(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> Business:
    """FastAPI dependency: like `get_current_actor_and_business` but returns
    the full Business ORM row -- for dependencies (`require_active_business`)
    and routes (POST /business/request-access) that need to read/write
    `status`/`needs_onboarding` directly instead of just the id."""
    auth0_sub = claims.get("sub")
    return _get_or_provision_business(db, auth0_sub)


# Auth0 Access Tokens (unlike ID Tokens) only carry profile claims like
# "email"/"email_verified" if a tenant Action/Rule explicitly adds them
# (commonly namespaced, e.g. "https://firstcall.app/email"). No such
# Action/config-as-code is checked into this repo, so it has NOT been
# confirmed that tokens issued by this Auth0 tenant/application actually
# carry these claims -- verify against the real tenant before relying on
# this. Known limitation: if the claim is simply absent (None), the checks
# below treat that as "cannot determine" and allow the request through,
# rather than silently blocking every caller because the claim was never
# wired up.


def _require_verified_email(claims: dict) -> None:
    """Block gated actions when Auth0 explicitly reports the account's email
    as unverified. Only fires on an explicit `False` -- see the module note
    above on why a missing claim doesn't block."""
    if claims.get("email_verified") is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before continuing.",
        )


_GATED_STATUS_MESSAGES = {
    BusinessStatus.unrequested: "Request access to get started.",
    BusinessStatus.pending_review: "Your access request is pending review.",
    BusinessStatus.suspended: "Your business access has been suspended.",
}


def require_active_business(
    business: Business = Depends(get_current_business_row),
    claims: dict = Depends(get_current_claims),
) -> Business:
    """FastAPI dependency for capabilities gated on admin approval (posting
    jobs, MCP Server tools): requires the account's email isn't explicitly
    unverified and the business's `status` is "active", else 403 with a
    message matching the caller's actual state. Compose this instead of
    `get_current_business` on routes that must stay blocked until an admin
    approves the business."""
    _require_verified_email(claims)
    if business.status != BusinessStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_GATED_STATUS_MESSAGES.get(
                business.status, "Your business does not have active access."
            ),
        )
    return business


def require_admin(claims: dict = Depends(get_current_claims)) -> str:
    """FastAPI dependency for the admin-only surface (routes/admin.py):
    only the single configured `PLATFORM_ADMIN_EMAIL` gets through, checked
    by exact match against the token's `email` claim -- not a list/allowlist,
    since only one admin is needed for this showcase. See the module note
    above: if this Auth0 tenant's Access Tokens don't carry an `email`
    claim, this always denies (fails closed, never open)."""
    admin_email = claims.get("email")
    if not PLATFORM_ADMIN_EMAIL or not admin_email or admin_email != PLATFORM_ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return admin_email
