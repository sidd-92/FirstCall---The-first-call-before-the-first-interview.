"""Tests for Prompt 16's access-control gating.

Self-service signup (Prompt 15's auto-provisioning) always starts a
business at "unrequested" -- creating an account must never by itself grant
access to shared, business-facing infrastructure. Only an explicit
POST /business/request-access moves it to "pending_review" (and notifies
the admin); only POST /admin/businesses/{id}/approve moves it to "active".
Gated capabilities (posting jobs, MCP Server tools) require "active" status
and -- when the JWT actually carries the claim -- a verified email.
"""

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import src.auth as auth_module
from src.auth import get_current_business_row, get_current_claims
from src.db import get_db
from src.main import app
from src.models import Business, BusinessStatus

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _claims(sub: str, email: str = "owner@example.com", email_verified: bool | None = True) -> dict:
    claims = {"sub": sub, "email": email}
    if email_verified is not None:
        claims["email_verified"] = email_verified
    return claims


def _authorize_as_business(
    business: Business, email: str = "owner@example.com", email_verified: bool | None = True
) -> None:
    """Route dependencies that mutate the business (POST /business/request-
    access) commit through their own `Depends(get_db)` session, distinct
    from the test's `db_session` fixture -- re-fetching by id through that
    same request-scoped session (rather than returning the `db_session`-bound
    object directly) means writes actually land instead of silently mutating
    an object no session ever flushes."""

    def _get_business_row(db: Session = Depends(get_db)) -> Business:
        return db.get(Business, business.id)

    app.dependency_overrides[get_current_business_row] = _get_business_row
    app.dependency_overrides[get_current_claims] = lambda: _claims(
        business.auth0_sub, email, email_verified
    )


def _seed_business(
    db_session, suffix: str, status: BusinessStatus = BusinessStatus.unrequested
) -> Business:
    business = Business(
        auth0_sub=f"auth0|gating-{suffix}",
        name="Acme Co",
        status=status,
        needs_onboarding=False,
    )
    db_session.add(business)
    db_session.commit()
    db_session.refresh(business)
    return business


def _job_payload() -> dict:
    return {
        "title": "Barista",
        "description": "Make coffee.",
        "location": "Remote",
        "employment_type": "Full-time",
    }


# -- POST /business/request-access ------------------------------------------


def test_request_access_transitions_unrequested_to_pending_and_notifies(db_session, monkeypatch):
    business = _seed_business(db_session, "1")
    _authorize_as_business(business, email="owner@acme.com")

    notified = {}

    def fake_notify(notified_business, requester_email):
        notified["business_id"] = notified_business.id
        notified["requester_email"] = requester_email

    monkeypatch.setattr("src.routes.dashboard.notify_access_requested", fake_notify)

    response = client.post("/business/request-access")

    assert response.status_code == 200
    assert response.json()["status"] == "pending_review"

    db_session.refresh(business)
    assert business.status == BusinessStatus.pending_review
    assert business.requested_by_email == "owner@acme.com"
    assert notified == {"business_id": business.id, "requester_email": "owner@acme.com"}


def test_request_access_again_while_pending_does_not_resend_or_error(db_session, monkeypatch):
    business = _seed_business(db_session, "2", status=BusinessStatus.pending_review)
    _authorize_as_business(business)

    calls = []
    monkeypatch.setattr(
        "src.routes.dashboard.notify_access_requested", lambda *a, **k: calls.append(1)
    )

    response = client.post("/business/request-access")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_review"
    assert "already" in body["message"].lower()
    assert calls == []

    db_session.refresh(business)
    assert business.status == BusinessStatus.pending_review


def test_request_access_when_already_active_reports_state_without_error(db_session):
    business = _seed_business(db_session, "3", status=BusinessStatus.active)
    _authorize_as_business(business)

    response = client.post("/business/request-access")

    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_request_access_requires_verified_email(db_session):
    business = _seed_business(db_session, "4")
    _authorize_as_business(business, email_verified=False)

    response = client.post("/business/request-access")

    assert response.status_code == 403

    db_session.refresh(business)
    assert business.status == BusinessStatus.unrequested


def test_request_access_requires_auth() -> None:
    assert client.post("/business/request-access").status_code in (401, 403)


# -- gated capabilities: POST /jobs and MCP Server routes -------------------

GATED_MCP_ROUTES = [
    ("GET", "/mcp-server/status"),
    ("GET", "/mcp-server/tools"),
    ("POST", "/mcp-server/tools/list_channels/call"),
]


def _call(method: str, url: str):
    if method == "GET":
        return client.get(url)
    return client.post(url, json={"arguments": {}})


@pytest.mark.parametrize("business_status", [BusinessStatus.unrequested, BusinessStatus.pending_review])
def test_create_job_posting_rejected_before_active(db_session, business_status):
    business = _seed_business(db_session, f"job-{business_status.value}", status=business_status)
    _authorize_as_business(business)

    response = client.post("/jobs", json=_job_payload())

    assert response.status_code == 403
    assert response.json()["detail"]


def test_create_job_posting_succeeds_once_active(db_session):
    business = _seed_business(db_session, "job-active", status=BusinessStatus.active)
    _authorize_as_business(business)

    response = client.post("/jobs", json=_job_payload())

    assert response.status_code == 201


@pytest.mark.parametrize("method,url", GATED_MCP_ROUTES)
@pytest.mark.parametrize("business_status", [BusinessStatus.unrequested, BusinessStatus.pending_review])
def test_mcp_routes_rejected_before_active(db_session, method, url, business_status):
    business = _seed_business(
        db_session, f"mcp-{business_status.value}-{method}-{hash(url)}", status=business_status
    )
    _authorize_as_business(business)

    response = _call(method, url)

    assert response.status_code == 403
    assert response.json()["detail"]


@pytest.mark.parametrize("method,url", GATED_MCP_ROUTES)
def test_mcp_routes_pass_gate_once_active(db_session, method, url):
    business = _seed_business(db_session, f"mcp-active-{method}-{hash(url)}", status=BusinessStatus.active)
    _authorize_as_business(business)

    response = _call(method, url)

    # mcp-server isn't running in tests -- the point here is only that the
    # access gate itself no longer blocks with 403, not what the (unreachable
    # downstream) response looks like.
    assert response.status_code != 403


def test_gated_routes_blocked_when_email_not_verified_even_if_active(db_session):
    business = _seed_business(db_session, "email-unverified", status=BusinessStatus.active)
    _authorize_as_business(business, email_verified=False)

    assert client.post("/jobs", json=_job_payload()).status_code == 403
    assert client.get("/mcp-server/status").status_code == 403


# -- admin approval ----------------------------------------------------------


def test_admin_list_businesses_rejects_non_admin(monkeypatch):
    monkeypatch.setattr(auth_module, "PLATFORM_ADMIN_EMAIL", "admin@firstcall.dev")
    app.dependency_overrides[get_current_claims] = lambda: {
        "sub": "auth0|someone",
        "email": "someone@else.com",
    }

    response = client.get("/admin/businesses", params={"status": "pending_review"})

    assert response.status_code == 403


def test_admin_approve_rejects_non_admin(db_session, monkeypatch):
    monkeypatch.setattr(auth_module, "PLATFORM_ADMIN_EMAIL", "admin@firstcall.dev")
    business = _seed_business(db_session, "admin-reject", status=BusinessStatus.pending_review)
    app.dependency_overrides[get_current_claims] = lambda: {
        "sub": "auth0|someone",
        "email": "someone@else.com",
    }

    response = client.post(f"/admin/businesses/{business.id}/approve")

    assert response.status_code == 403
    db_session.refresh(business)
    assert business.status == BusinessStatus.pending_review


def test_admin_list_and_approve_business_succeeds_for_admin(db_session, monkeypatch):
    monkeypatch.setattr(auth_module, "PLATFORM_ADMIN_EMAIL", "admin@firstcall.dev")
    business = _seed_business(db_session, "admin-approve", status=BusinessStatus.pending_review)
    app.dependency_overrides[get_current_claims] = lambda: {
        "sub": "auth0|admin",
        "email": "admin@firstcall.dev",
    }

    list_response = client.get("/admin/businesses", params={"status": "pending_review"})
    assert list_response.status_code == 200
    ids = [entry["id"] for entry in list_response.json()]
    assert business.id in ids

    approve_response = client.post(f"/admin/businesses/{business.id}/approve")
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "active"

    db_session.refresh(business)
    assert business.status == BusinessStatus.active


def test_admin_routes_require_auth() -> None:
    assert client.get("/admin/businesses").status_code in (401, 403)
    assert client.post("/admin/businesses/1/approve").status_code in (401, 403)
