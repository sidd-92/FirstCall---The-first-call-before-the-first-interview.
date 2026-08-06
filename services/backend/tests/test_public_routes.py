"""Tests for unauthenticated public routes."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import src.routes.public as public_routes
from src import mcp_client
from src.db import SessionLocal
from src.main import app
from src.models import Business, Candidate, JobPosting, PipelineStage, PipelineStageName

client = TestClient(app)


def _seed_active_job(db_session, title="Barista") -> JobPosting:
    business = Business(auth0_sub=f"auth0|seed-{title}", name="Acme Co")
    db_session.add(business)
    db_session.flush()
    job = JobPosting(
        business_id=business.id,
        title=title,
        description="Make coffee.",
        faq_json="{}",
        is_active=True,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


@pytest.fixture(autouse=True)
def _stub_mcp_call_tool(monkeypatch):
    """apply_to_job's confirmation email is best-effort and goes through
    mcp_client.call_tool (connect_channel, then initiate) -- stub it so
    these tests don't need a live mcp-server, and record calls so tests can
    assert on them."""
    calls = []

    async def fake_call_tool(name: str, arguments: dict):
        calls.append((name, arguments))
        if name == "connect_channel":
            return SimpleNamespace(
                structured_content={"id": "conn-email-1", "status": "active"}, content=[]
            )
        return SimpleNamespace(
            structured_content={"id": "conv-application-1", "status": "active"}, content=[]
        )

    monkeypatch.setattr(mcp_client, "call_tool", fake_call_tool)
    return calls


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_apply_to_job_creates_candidate_and_pipeline_stage(db_session, monkeypatch):
    job = _seed_active_job(db_session, title="Barista A")
    monkeypatch.setattr(public_routes, "notify_new_application", lambda *a, **k: None)

    response = client.post(
        f"/jobs/{job.id}/apply",
        data={
            "name": "Jamie Doe",
            "email": "jamie@example.com",
            "phone": "555-0100",
            "address": "123 Main St",
        },
        files={"resume": ("resume.pdf", b"%PDF-1.4 fake resume", "application/pdf")},
    )

    assert response.status_code == 200
    candidate_id = response.json()["id"]

    db = SessionLocal()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        assert candidate is not None
        assert candidate.email == "jamie@example.com"
        assert candidate.job_posting_id == job.id

        stage = db.query(PipelineStage).filter(PipelineStage.candidate_id == candidate_id).first()
        assert stage is not None
        assert stage.stage == PipelineStageName.applied
    finally:
        db.close()


def test_apply_to_job_calls_notification(db_session, monkeypatch):
    job = _seed_active_job(db_session, title="Barista B")
    calls = []
    monkeypatch.setattr(
        public_routes,
        "notify_new_application",
        lambda candidate, job_posting, business: calls.append(candidate.id),
    )

    response = client.post(
        f"/jobs/{job.id}/apply",
        data={
            "name": "Alex Smith",
            "email": "alex@example.com",
            "phone": "555-0101",
            "address": "456 Oak Ave",
        },
        files={"resume": ("resume.pdf", b"fake", "application/pdf")},
    )

    assert response.status_code == 200
    assert calls == [response.json()["id"]]


def test_apply_to_job_returns_a_discord_link_code(db_session, monkeypatch):
    job = _seed_active_job(db_session, title="Barista C")
    monkeypatch.setattr(public_routes, "notify_new_application", lambda *a, **k: None)

    response = client.post(
        f"/jobs/{job.id}/apply",
        data={
            "name": "Sam Lee",
            "email": "sam@example.com",
            "phone": "555-0102",
            "address": "789 Pine Rd",
        },
        files={"resume": ("resume.pdf", b"fake", "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["discord_link_code"], str)
    assert len(body["discord_link_code"]) == 6

    db = SessionLocal()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == body["id"]).first()
        assert candidate.discord_link_code == body["discord_link_code"]
        assert candidate.discord_user_id is None
    finally:
        db.close()


def test_apply_to_job_sends_confirmation_email_via_mcp_tools(
    db_session, monkeypatch, _stub_mcp_call_tool
):
    monkeypatch.setattr(public_routes, "notify_new_application", lambda *a, **k: None)
    monkeypatch.setattr(public_routes, "AGENT_EMAIL_ADDRESS", "agent@example.com")
    monkeypatch.setattr(public_routes, "DISCORD_INVITE_URL", "https://discord.gg/abc123")
    job = _seed_active_job(db_session, title="Barista D")

    response = client.post(
        f"/jobs/{job.id}/apply",
        data={
            "name": "Robin Doe",
            "email": "robin@example.com",
            "phone": "555-0103",
            "address": "1 Elm St",
        },
        files={"resume": ("resume.pdf", b"fake", "application/pdf")},
    )

    assert response.status_code == 200
    discord_link_code = response.json()["discord_link_code"]

    tool_names = [name for name, _ in _stub_mcp_call_tool]
    assert tool_names == ["connect_channel", "initiate"]
    connect_args = _stub_mcp_call_tool[0][1]
    initiate_args = _stub_mcp_call_tool[1][1]
    assert connect_args == {"channel": "email"}
    assert initiate_args["connection_id"] == "conn-email-1"
    assert initiate_args["recipient"] == "robin@example.com"

    text = initiate_args["text"]
    assert "Barista D" in text
    assert "agent@example.com" in text
    assert "https://discord.gg/abc123" in text
    assert discord_link_code in text


def test_apply_to_job_email_failure_does_not_fail_request(db_session, monkeypatch):
    monkeypatch.setattr(public_routes, "notify_new_application", lambda *a, **k: None)
    job = _seed_active_job(db_session, title="Barista E")

    async def failing_call_tool(name: str, arguments: dict):
        raise RuntimeError("mcp-server unreachable")

    monkeypatch.setattr(mcp_client, "call_tool", failing_call_tool)

    response = client.post(
        f"/jobs/{job.id}/apply",
        data={
            "name": "Jesse Doe",
            "email": "jesse@example.com",
            "phone": "555-0104",
            "address": "2 Elm St",
        },
        files={"resume": ("resume.pdf", b"fake", "application/pdf")},
    )

    assert response.status_code == 200
    candidate_id = response.json()["id"]

    db = SessionLocal()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        assert candidate is not None
        stage = db.query(PipelineStage).filter(PipelineStage.candidate_id == candidate_id).first()
        assert stage is not None
        assert stage.stage == PipelineStageName.applied
    finally:
        db.close()


def test_apply_to_inactive_job_404s(db_session):
    business = Business(auth0_sub="auth0|seed-inactive", name="Acme Co")
    db_session.add(business)
    db_session.flush()
    job = JobPosting(
        business_id=business.id,
        title="Closed role",
        description="n/a",
        faq_json="{}",
        is_active=False,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    response = client.post(
        f"/jobs/{job.id}/apply",
        data={"name": "A", "email": "a@example.com", "phone": "1", "address": "x"},
        files={"resume": ("r.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 404


def test_apply_to_nonexistent_job_404s() -> None:
    response = client.post(
        "/jobs/999999/apply",
        data={"name": "A", "email": "a@example.com", "phone": "1", "address": "x"},
        files={"resume": ("r.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 404
