"""Tests for authenticated dashboard routes.

TODO: once GET /candidates, GET /candidates/{id}, assign-screening, and
shortlist are implemented, test those too (see routes/dashboard.py's TODOs).
review-with-ai is covered here since it's implemented.
"""

import json

import pytest
from fastapi.testclient import TestClient

import src.routes.dashboard as dashboard_routes
from src.auth import get_current_actor_and_business, get_current_business
from src.crypto import _fernet
from src.main import app
from src.models import (
    Business,
    Candidate,
    ChannelType,
    Conversation,
    JobPosting,
    Message,
    MessageDirection,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _seed_candidate_with_transcript(db_session, suffix: str = "a") -> tuple[int, int]:
    """Returns (business_id, candidate_id)."""
    business = Business(auth0_sub=f"auth0|dashboard-test-{suffix}", name="Acme Co")
    db_session.add(business)
    db_session.flush()

    job = JobPosting(
        business_id=business.id,
        title="Barista",
        description="Make coffee.",
        faq_json="{}",
        is_active=True,
    )
    db_session.add(job)
    db_session.flush()

    candidate = Candidate(
        business_id=business.id,
        job_posting_id=job.id,
        name="Jamie Doe",
        email="jamie@example.com",
        phone="555-0100",
        address="123 Main St",
        resume_file_path="/resumes/jamie.pdf",
    )
    db_session.add(candidate)
    db_session.flush()

    conversation = Conversation(candidate_id=candidate.id, channel=ChannelType.discord)
    db_session.add(conversation)
    db_session.flush()

    for direction, text in [
        (MessageDirection.outbound, "Tell me about your experience."),
        (MessageDirection.inbound, "I've worked as a barista for 2 years."),
    ]:
        db_session.add(
            Message(
                conversation_id=conversation.id,
                direction=direction,
                content_encrypted=_fernet().encrypt(text.encode("utf-8")),
            )
        )
    db_session.commit()

    return business.id, candidate.id


def test_review_with_ai_returns_score_and_summary(db_session, monkeypatch):
    business_id, candidate_id = _seed_candidate_with_transcript(db_session, suffix="1")
    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business_id,
        "auth0|review-actor-1",
    )
    monkeypatch.setattr(
        dashboard_routes, "review_transcript", lambda transcript: (8, "Strong candidate.")
    )

    response = client.post(f"/candidates/{candidate_id}/review-with-ai")

    assert response.status_code == 200
    assert response.json() == {"score": 8, "summary": "Strong candidate."}


def test_review_with_ai_passes_full_transcript_to_llm(db_session, monkeypatch):
    business_id, candidate_id = _seed_candidate_with_transcript(db_session, suffix="2")
    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business_id,
        "auth0|review-actor-2",
    )
    captured = {}

    def fake_review(transcript: str):
        captured["transcript"] = transcript
        return 5, "ok"

    monkeypatch.setattr(dashboard_routes, "review_transcript", fake_review)

    client.post(f"/candidates/{candidate_id}/review-with-ai")

    assert "Tell me about your experience." in captured["transcript"]
    assert "I've worked as a barista for 2 years." in captured["transcript"]


def test_review_with_ai_404s_for_candidate_without_transcript(db_session):
    business = Business(auth0_sub="auth0|no-transcript", name="Acme Co")
    db_session.add(business)
    db_session.flush()
    job = JobPosting(
        business_id=business.id, title="Role", description="d", faq_json="{}", is_active=True
    )
    db_session.add(job)
    db_session.flush()
    candidate = Candidate(
        business_id=business.id,
        job_posting_id=job.id,
        name="No Convo",
        email="n@example.com",
        phone="1",
        address="x",
        resume_file_path="/r.pdf",
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)

    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business.id,
        "auth0|review-actor-3",
    )

    response = client.post(f"/candidates/{candidate.id}/review-with-ai")
    assert response.status_code == 404


def test_review_with_ai_requires_auth() -> None:
    response = client.post("/candidates/1/review-with-ai")
    assert response.status_code in (401, 403)


def _job_posting_payload(**overrides) -> dict:
    payload = {
        "title": "Barista",
        "description": "Make coffee, delight customers.",
        "location": "Hyderabad, Telangana",
        "employment_type": "Permanent, Full-time",
        "pay_min": 1500000,
        "pay_max": 5000000,
        "pay_currency": "INR",
        "benefits": ["Paid time off", "Provident Fund"],
    }
    payload.update(overrides)
    return payload


def test_create_job_posting_creates_active_posting_for_business(db_session):
    business = Business(auth0_sub="auth0|create-job-1", name="Acme Co")
    db_session.add(business)
    db_session.commit()
    app.dependency_overrides[get_current_business] = lambda: business.id

    response = client.post("/jobs", json=_job_posting_payload())
    assert response.status_code == 201
    job_id = response.json()["id"]

    job = db_session.get(JobPosting, job_id)
    assert job.business_id == business.id
    assert job.title == "Barista"
    assert job.location == "Hyderabad, Telangana"
    assert job.is_active is True


def test_create_job_posting_is_scoped_to_authenticated_business(db_session):
    business_a = Business(auth0_sub="auth0|create-job-a", name="A Co")
    business_b = Business(auth0_sub="auth0|create-job-b", name="B Co")
    db_session.add_all([business_a, business_b])
    db_session.commit()
    app.dependency_overrides[get_current_business] = lambda: business_a.id

    response = client.post("/jobs", json=_job_posting_payload())
    job_id = response.json()["id"]

    job = db_session.get(JobPosting, job_id)
    assert job.business_id == business_a.id
    assert job.business_id != business_b.id


def test_create_job_posting_requires_auth() -> None:
    response = client.post("/jobs", json=_job_posting_payload())
    assert response.status_code in (401, 403)


def _create_job_posting(db_session, business_id: int, title: str = "Barista") -> int:
    job = JobPosting(
        business_id=business_id,
        title=title,
        description="Make coffee.",
        location="Remote",
        employment_type="Full-time",
        faq_json="{}",
        is_active=True,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job.id


def test_list_job_postings_scoped_to_business(db_session):
    business_a = Business(auth0_sub="auth0|jp-list-a", name="A Co")
    business_b = Business(auth0_sub="auth0|jp-list-b", name="B Co")
    db_session.add_all([business_a, business_b])
    db_session.commit()
    _create_job_posting(db_session, business_a.id, title="A's role")
    _create_job_posting(db_session, business_b.id, title="B's role")

    app.dependency_overrides[get_current_business] = lambda: business_a.id
    response = client.get("/job-postings")

    assert response.status_code == 200
    titles = [posting["title"] for posting in response.json()]
    assert titles == ["A's role"]


def test_list_job_postings_reports_faq_and_screening_counts(db_session):
    business = Business(auth0_sub="auth0|jp-list-counts", name="Acme Co")
    db_session.add(business)
    db_session.commit()
    job_id = _create_job_posting(db_session, business.id)
    job = db_session.get(JobPosting, job_id)
    job.faq_json = json.dumps(
        {
            "faq": [{"question": "Q1", "answer": "A1"}],
            "screening_questions": ["Q1?", "Q2?", "Q3?"],
        }
    )
    db_session.commit()

    app.dependency_overrides[get_current_business] = lambda: business.id
    response = client.get("/job-postings")

    body = response.json()[0]
    assert body["faq_count"] == 1
    assert body["screening_question_count"] == 3


def test_get_job_posting_returns_parsed_config(db_session):
    business = Business(auth0_sub="auth0|jp-get", name="Acme Co")
    db_session.add(business)
    db_session.commit()
    job_id = _create_job_posting(db_session, business.id)
    job = db_session.get(JobPosting, job_id)
    job.faq_json = json.dumps(
        {
            "faq": [{"question": "Salary?", "answer": "$20-24/hr"}],
            "screening_questions": ["Tell me about yourself."],
        }
    )
    db_session.commit()

    app.dependency_overrides[get_current_business] = lambda: business.id
    response = client.get(f"/job-postings/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["faq"] == [{"question": "Salary?", "answer": "$20-24/hr"}]
    assert body["screening_questions"] == ["Tell me about yourself."]


def test_get_job_posting_404s_for_another_business(db_session):
    business_a = Business(auth0_sub="auth0|jp-get-404-a", name="A Co")
    business_b = Business(auth0_sub="auth0|jp-get-404-b", name="B Co")
    db_session.add_all([business_a, business_b])
    db_session.commit()
    job_id = _create_job_posting(db_session, business_a.id)

    app.dependency_overrides[get_current_business] = lambda: business_b.id
    response = client.get(f"/job-postings/{job_id}")

    assert response.status_code == 404


def test_update_job_posting_config_saves_faq_and_screening_questions(db_session):
    business = Business(auth0_sub="auth0|jp-update", name="Acme Co")
    db_session.add(business)
    db_session.commit()
    job_id = _create_job_posting(db_session, business.id)

    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business.id,
        "auth0|jp-update-actor",
    )
    response = client.patch(
        f"/job-postings/{job_id}",
        json={
            "faq": [{"question": "What's the salary range?", "answer": "$20-24/hr."}],
            "screening_questions": [
                "Can you tell me about your relevant experience?",
                "What are your salary expectations?",
            ],
        },
    )

    assert response.status_code == 200
    job = db_session.get(JobPosting, job_id)
    stored = json.loads(job.faq_json)
    assert stored["faq"] == [{"question": "What's the salary range?", "answer": "$20-24/hr."}]
    assert stored["screening_questions"] == [
        "Can you tell me about your relevant experience?",
        "What are your salary expectations?",
    ]


def test_update_job_posting_config_is_scoped_to_business(db_session):
    business_a = Business(auth0_sub="auth0|jp-update-scope-a", name="A Co")
    business_b = Business(auth0_sub="auth0|jp-update-scope-b", name="B Co")
    db_session.add_all([business_a, business_b])
    db_session.commit()
    job_id = _create_job_posting(db_session, business_a.id)

    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business_b.id,
        "auth0|jp-update-scope-actor",
    )
    response = client.patch(
        f"/job-postings/{job_id}",
        json={"faq": [], "screening_questions": ["Should not save"]},
    )

    assert response.status_code == 404
    job = db_session.get(JobPosting, job_id)
    assert json.loads(job.faq_json) == {}


def test_update_job_posting_config_requires_auth(db_session) -> None:
    business = Business(auth0_sub="auth0|jp-update-auth", name="Acme Co")
    db_session.add(business)
    db_session.commit()
    job_id = _create_job_posting(db_session, business.id)

    response = client.patch(
        f"/job-postings/{job_id}",
        json={"faq": [], "screening_questions": []},
    )
    assert response.status_code in (401, 403)
