"""Tests for business onboarding and listing routes."""

import pytest
from fastapi.testclient import TestClient

from src.auth import get_current_auth0_sub
from src.main import app
from src.models import Business

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _auth_as(sub: str) -> None:
    app.dependency_overrides[get_current_auth0_sub] = lambda: sub


def test_onboard_creates_business_for_auth0_sub(db_session):
    _auth_as("google-oauth2|test-user")

    response = client.post(
        "/businesses/onboard",
        json={"name": "Acme Co", "owner_email": "owner@acme.com"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["auth0_sub"] == "google-oauth2|test-user"
    assert body["name"] == "Acme Co"
    assert body["owner_email"] == "owner@acme.com"

    business = (
        db_session.query(Business)
        .filter(Business.auth0_sub == "google-oauth2|test-user")
        .first()
    )
    assert business is not None
    assert business.name == "Acme Co"


def test_onboard_is_idempotent_and_keeps_existing_row(db_session):
    business = Business(auth0_sub="google-oauth2|existing-user", name="Original Co")
    db_session.add(business)
    db_session.commit()

    _auth_as("google-oauth2|existing-user")

    response = client.post("/businesses/onboard", json={"name": "Renamed Co"})

    assert response.status_code == 201
    assert response.json()["id"] == business.id
    assert response.json()["name"] == "Original Co"

    count = (
        db_session.query(Business)
        .filter(Business.auth0_sub == "google-oauth2|existing-user")
        .count()
    )
    assert count == 1


def test_onboard_requires_auth() -> None:
    response = client.post("/businesses/onboard", json={"name": "Acme Co"})
    assert response.status_code in (401, 403)


def test_list_businesses_returns_all(db_session):
    db_session.add_all(
        [
            Business(auth0_sub="google-oauth2|list-a", name="A Co"),
            Business(auth0_sub="google-oauth2|list-b", name="B Co"),
        ]
    )
    db_session.commit()

    _auth_as("google-oauth2|any-user")

    response = client.get("/businesses")

    assert response.status_code == 200
    businesses = {b["name"]: b["auth0_sub"] for b in response.json()}
    assert businesses["A Co"] == "google-oauth2|list-a"
    assert businesses["B Co"] == "google-oauth2|list-b"


def test_list_businesses_requires_auth() -> None:
    response = client.get("/businesses")
    assert response.status_code in (401, 403)
