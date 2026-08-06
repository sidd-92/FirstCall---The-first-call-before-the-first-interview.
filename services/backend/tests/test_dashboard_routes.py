"""Tests for authenticated dashboard routes.

TODO: once GET /candidates, GET /candidates/{id}, assign-screening, and
shortlist are implemented, test those too (see routes/dashboard.py's TODOs).
review-with-ai is covered here since it's implemented.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import src.routes.dashboard as dashboard_routes
from src import mcp_client
from src.auth import (
    get_current_actor_and_business,
    get_current_business,
    require_active_business,
)
from src.crypto import _fernet
from src.main import app
from src.models import (
    Business,
    BusinessStatus,
    Candidate,
    ChannelType,
    Conversation,
    JobPosting,
    Message,
    MessageDirection,
    PipelineStage,
    PipelineStageName,
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
    business = Business(auth0_sub="auth0|create-job-1", name="Acme Co", status=BusinessStatus.active)
    db_session.add(business)
    db_session.commit()
    app.dependency_overrides[require_active_business] = lambda: business

    response = client.post("/jobs", json=_job_posting_payload())
    assert response.status_code == 201
    job_id = response.json()["id"]

    job = db_session.get(JobPosting, job_id)
    assert job.business_id == business.id
    assert job.title == "Barista"
    assert job.location == "Hyderabad, Telangana"
    assert job.is_active is True


def test_create_job_posting_is_scoped_to_authenticated_business(db_session):
    business_a = Business(auth0_sub="auth0|create-job-a", name="A Co", status=BusinessStatus.active)
    business_b = Business(auth0_sub="auth0|create-job-b", name="B Co", status=BusinessStatus.active)
    db_session.add_all([business_a, business_b])
    db_session.commit()
    app.dependency_overrides[require_active_business] = lambda: business_a

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


# -- schedule-interview / interviews ----------------------------------------


def _seed_shortlisted_candidate(db_session, suffix: str = "a", business_id: int | None = None) -> tuple[int, int]:
    """Returns (business_id, candidate_id) for a candidate already
    shortlisted. Pass an existing `business_id` to add another candidate to
    the same business instead of creating a new one."""
    if business_id is None:
        business = Business(auth0_sub=f"auth0|interview-test-{suffix}", name="Acme Co")
        db_session.add(business)
        db_session.flush()
        business_id = business.id

    job = JobPosting(
        business_id=business_id,
        title="Barista",
        description="Make coffee.",
        faq_json="{}",
        is_active=True,
    )
    db_session.add(job)
    db_session.flush()

    candidate = Candidate(
        business_id=business_id,
        job_posting_id=job.id,
        name=f"Jamie Doe {suffix}",
        email=f"jamie-{suffix}@example.com",
        phone="555-0100",
        address="123 Main St",
        resume_file_path="/resumes/jamie.pdf",
    )
    db_session.add(candidate)
    db_session.flush()

    db_session.add(
        PipelineStage(candidate_id=candidate.id, stage=PipelineStageName.shortlisted)
    )
    db_session.commit()

    return business_id, candidate.id


@pytest.fixture(autouse=True)
def _stub_mcp_call_tool(monkeypatch):
    """schedule-interview's confirmation email is best-effort and goes
    through mcp_client.call_tool (connect_channel, then initiate) -- stub it
    so these tests don't need a live mcp-server, and record calls so the
    "goes through the mcp path" tests can assert on them."""
    calls = []

    async def fake_call_tool(name: str, arguments: dict):
        calls.append((name, arguments))
        if name == "connect_channel":
            return SimpleNamespace(
                structured_content={"id": "conn-email-1", "status": "active"}, content=[]
            )
        return SimpleNamespace(
            structured_content={"id": "conv-cold-1", "status": "active"}, content=[]
        )

    monkeypatch.setattr(mcp_client, "call_tool", fake_call_tool)
    return calls


def test_schedule_interview_updates_stage_and_fields(db_session, _stub_mcp_call_tool):
    business_id, candidate_id = _seed_shortlisted_candidate(db_session, suffix="1")
    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business_id,
        "auth0|schedule-actor-1",
    )

    response = client.post(
        f"/candidates/{candidate_id}/schedule-interview",
        json={
            "scheduled_at": "2026-09-01T15:00:00+00:00",
            "interview_notes": "Google Meet link: meet.example/abc",
        },
    )

    assert response.status_code == 200
    assert response.json()["stage"] == "interview_scheduled"

    stage = (
        db_session.query(PipelineStage)
        .filter(PipelineStage.candidate_id == candidate_id)
        .first()
    )
    assert stage.stage == PipelineStageName.interview_scheduled
    assert stage.scheduled_at.strftime("%Y-%m-%dT%H:%M:%S") == "2026-09-01T15:00:00"
    assert stage.interview_notes == "Google Meet link: meet.example/abc"


def test_schedule_interview_sends_confirmation_via_mcp_tools(db_session, _stub_mcp_call_tool):
    business_id, candidate_id = _seed_shortlisted_candidate(db_session, suffix="2")
    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business_id,
        "auth0|schedule-actor-2",
    )

    client.post(
        f"/candidates/{candidate_id}/schedule-interview",
        json={"scheduled_at": "2026-09-02T10:00:00+00:00"},
    )

    tool_names = [name for name, _ in _stub_mcp_call_tool]
    assert tool_names == ["connect_channel", "initiate"]
    connect_args = _stub_mcp_call_tool[0][1]
    initiate_args = _stub_mcp_call_tool[1][1]
    assert connect_args == {"channel": "email"}
    assert initiate_args["connection_id"] == "conn-email-1"
    assert initiate_args["recipient"] == "jamie-2@example.com"
    assert "interview" in initiate_args["text"].lower()


def test_schedule_interview_email_failure_does_not_fail_request(db_session, monkeypatch):
    business_id, candidate_id = _seed_shortlisted_candidate(db_session, suffix="3")
    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business_id,
        "auth0|schedule-actor-3",
    )

    async def failing_call_tool(name: str, arguments: dict):
        raise RuntimeError("mcp-server unreachable")

    monkeypatch.setattr(mcp_client, "call_tool", failing_call_tool)

    response = client.post(
        f"/candidates/{candidate_id}/schedule-interview",
        json={"scheduled_at": "2026-09-03T10:00:00+00:00"},
    )

    assert response.status_code == 200
    stage = (
        db_session.query(PipelineStage)
        .filter(PipelineStage.candidate_id == candidate_id)
        .first()
    )
    assert stage.stage == PipelineStageName.interview_scheduled


def test_schedule_interview_rejects_candidate_from_another_business(
    db_session, _stub_mcp_call_tool
):
    business_a_id, _candidate_a_id = _seed_shortlisted_candidate(db_session, suffix="4a")
    _business_b_id, candidate_b_id = _seed_shortlisted_candidate(db_session, suffix="4b")

    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business_a_id,
        "auth0|schedule-actor-4",
    )

    response = client.post(
        f"/candidates/{candidate_b_id}/schedule-interview",
        json={"scheduled_at": "2026-09-04T10:00:00+00:00"},
    )

    assert response.status_code == 404
    stage = (
        db_session.query(PipelineStage)
        .filter(PipelineStage.candidate_id == candidate_b_id)
        .first()
    )
    assert stage.stage == PipelineStageName.shortlisted


def test_schedule_interview_requires_auth() -> None:
    response = client.post(
        "/candidates/1/schedule-interview", json={"scheduled_at": "2026-09-01T10:00:00+00:00"}
    )
    assert response.status_code in (401, 403)


def test_list_interviews_returns_only_own_business_sorted_by_scheduled_at(
    db_session, _stub_mcp_call_tool
):
    business_a_id, candidate_a1 = _seed_shortlisted_candidate(db_session, suffix="5a")
    _, candidate_a2 = _seed_shortlisted_candidate(
        db_session, suffix="5a2", business_id=business_a_id
    )
    business_b_id, candidate_b1 = _seed_shortlisted_candidate(db_session, suffix="5b")

    def _schedule(business_id: int, candidate_id: int, scheduled_at: str) -> None:
        app.dependency_overrides[get_current_actor_and_business] = lambda: (
            business_id,
            "auth0|schedule-list-actor",
        )
        response = client.post(
            f"/candidates/{candidate_id}/schedule-interview",
            json={"scheduled_at": scheduled_at},
        )
        assert response.status_code == 200

    _schedule(business_a_id, candidate_a1, "2026-09-10T10:00:00+00:00")
    _schedule(business_a_id, candidate_a2, "2026-09-05T10:00:00+00:00")
    _schedule(business_b_id, candidate_b1, "2026-09-01T10:00:00+00:00")

    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business_a_id,
        "auth0|schedule-list-actor",
    )
    response = client.get("/interviews")

    assert response.status_code == 200
    body = response.json()
    assert [entry["id"] for entry in body] == [candidate_a2, candidate_a1]
    assert [entry["scheduled_at"][:19] for entry in body] == [
        "2026-09-05T10:00:00",
        "2026-09-10T10:00:00",
    ]
    for entry in body:
        assert entry["job_posting_title"] == "Barista"
    assert candidate_b1 not in [entry["id"] for entry in body]


def test_list_interviews_excludes_candidates_not_yet_scheduled(db_session):
    business_id, _candidate_id = _seed_shortlisted_candidate(db_session, suffix="6")

    app.dependency_overrides[get_current_actor_and_business] = lambda: (
        business_id,
        "auth0|schedule-list-actor-2",
    )
    response = client.get("/interviews")

    assert response.status_code == 200
    assert response.json() == []


def test_list_interviews_requires_auth() -> None:
    response = client.get("/interviews")
    assert response.status_code in (401, 403)
