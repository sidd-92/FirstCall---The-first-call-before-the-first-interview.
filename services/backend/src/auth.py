"""Auth0 JWT verification via JWKS.

Reads `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` from the environment. Dashboard
routes depend on `get_current_business`, which verifies the bearer token's
signature/claims against Auth0's JWKS endpoint and resolves the token's
`sub` claim to a `Business.id`.

Every dashboard route MUST use `get_current_business` to obtain the
business_id for a request -- never accept a business_id from the client
(query param, body, or header) and trust it directly.
"""

import json
import os
import urllib.request
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JOSEError
from sqlalchemy.orm import Session

from src.db import get_db
from src.logging_config import get_logger
from src.models import Business

log = get_logger()

AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "")
ALGORITHMS = ["RS256"]

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


def get_current_auth0_sub(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """FastAPI dependency: verify the request's bearer token and return its
    `sub` claim.

    Unlike `get_current_business`, this does NOT require the account to have
    a Business row yet -- it exists so the onboarding route can register a
    business for an account that isn't registered (which is exactly the case
    `get_current_business` rejects).
    """
    claims = verify_token(credentials.credentials)
    return claims.get("sub")


def get_current_business(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> int:
    """FastAPI dependency: verify the request's bearer token and resolve it
    to a `Business.id`.

    Returns the verified business_id -- routes must use this value for
    every query and must never accept a business_id supplied by the client.
    """
    claims = verify_token(credentials.credentials)
    auth0_sub = claims.get("sub")

    business = db.query(Business).filter(Business.auth0_sub == auth0_sub).first()
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No business is registered for this account",
        )
    return business.id
