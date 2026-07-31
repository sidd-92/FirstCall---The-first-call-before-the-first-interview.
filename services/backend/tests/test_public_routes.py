"""Tests for unauthenticated public routes."""

from fastapi.testclient import TestClient

import src.routes.public as public_routes
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
