"""Self-service first-time provisioning: a verified Auth0 sub with no
Business row yet must be auto-provisioned on its first authenticated
request -- never blocked pending a manually-inserted row -- and the
dashboard must be able to detect it still needs onboarding (real name not
yet set) via GET/PATCH /business/me.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

import src.auth as auth_module
from src.main import app
from src.models import PLACEHOLDER_BUSINESS_NAME, Business

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fake_jwt_verification(monkeypatch):
    """Bypass real Auth0/JWKS verification: whatever sub the test sets as
    the bearer token's value is returned as the claims' `sub`, so the real
    get_current_actor_and_business / get_current_business dependency bodies
    run unmocked against the test DB."""
    monkeypatch.setattr(
        auth_module, "verify_token", lambda token: {"sub": token}
    )
    yield
    app.dependency_overrides.clear()


def _auth_headers(sub: str) -> dict:
    return {"Authorization": f"Bearer {sub}"}


def test_new_sub_gets_business_auto_created_on_first_request(db_session):
    sub = f"auth0|new-{uuid.uuid4().hex[:8]}"

    assert db_session.query(Business).filter(Business.auth0_sub == sub).first() is None

    response = client.get("/candidates", headers=_auth_headers(sub))
    assert response.status_code == 200

    business = db_session.query(Business).filter(Business.auth0_sub == sub).first()
    assert business is not None
    assert business.name == PLACEHOLDER_BUSINESS_NAME
    assert business.needs_onboarding is True


def test_new_sub_business_me_reports_needs_onboarding(db_session):
    sub = f"auth0|me-{uuid.uuid4().hex[:8]}"

    response = client.get("/business/me", headers=_auth_headers(sub))
    assert response.status_code == 200
    body = response.json()
    assert body["needs_onboarding"] is True
    assert body["name"] == PLACEHOLDER_BUSINESS_NAME


def test_patch_business_me_updates_only_the_authenticated_sub(db_session):
    sub_a = f"auth0|patch-a-{uuid.uuid4().hex[:8]}"
    sub_b = f"auth0|patch-b-{uuid.uuid4().hex[:8]}"

    # Auto-provision both by touching an authenticated route first.
    client.get("/business/me", headers=_auth_headers(sub_a))
    client.get("/business/me", headers=_auth_headers(sub_b))

    response = client.patch(
        "/business/me", json={"name": "Acme Staffing"}, headers=_auth_headers(sub_a)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Acme Staffing"
    assert body["needs_onboarding"] is False

    business_a = db_session.query(Business).filter(Business.auth0_sub == sub_a).first()
    business_b = db_session.query(Business).filter(Business.auth0_sub == sub_b).first()
    assert business_a.name == "Acme Staffing"
    assert business_a.needs_onboarding is False
    # Business B, a different sub, must be untouched.
    assert business_b.name == PLACEHOLDER_BUSINESS_NAME
    assert business_b.needs_onboarding is True


def test_patch_business_me_requires_auth() -> None:
    response = client.patch("/business/me", json={"name": "Acme Staffing"})
    assert response.status_code in (401, 403)


def test_existing_business_with_real_name_skips_onboarding(db_session):
    sub = f"auth0|existing-{uuid.uuid4().hex[:8]}"
    business = Business(auth0_sub=sub, name="Already Named Co", needs_onboarding=False)
    db_session.add(business)
    db_session.commit()

    response = client.get("/business/me", headers=_auth_headers(sub))
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Already Named Co"
    assert body["needs_onboarding"] is False

    # No duplicate row was created for this sub.
    count = (
        db_session.query(Business).filter(Business.auth0_sub == sub).count()
    )
    assert count == 1
