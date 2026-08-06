"""business_id isolation tests, end-to-end.

Every dashboard route must scope queries by the business_id resolved from
the verified Auth0 JWT (get_current_actor_and_business) and must never
trust a client-supplied business_id. These tests set up two businesses and
verify, as Business A, that Business B's data is unreachable through every
candidate route, that spoofed business_ids are ignored, and that candidate
access is recorded in the append-only AuditLogEntry table.

The `business_set` fixture is reusable: add new dashboard routes later and
extend it with whatever data those routes need, then write more isolation
tests against the same fixture.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import src.routes.dashboard as dashboard_routes
from src.auth import (
    get_current_actor_and_business,
    get_current_business,
    require_active_business,
)
from src.crypto import _fernet
from src.main import app
from src.models import (
    AuditLogEntry,
    Business,
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

ACTOR_A = "auth0|isolation-actor-a"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _auth_as(business_id: int, actor: str = ACTOR_A) -> None:
    """Mock JWT verification: resolve the caller to (business_id, auth0_sub).
    The token itself is never checked here -- the routes must only trust
    whatever these dependencies return. All three are overridden since they
    stand in for the same verified JWT; require_active_business (Prompt 16's
    access-request gating) is stubbed with an already-active business here
    since these tests are about business_id isolation, not that gate --
    see test_access_gating.py for the gate itself."""
    app.dependency_overrides[get_current_actor_and_business] = lambda: (business_id, actor)
    app.dependency_overrides[get_current_business] = lambda: business_id
    app.dependency_overrides[require_active_business] = lambda: SimpleNamespace(id=business_id)


@pytest.fixture
def business_set(db_session):
    """Two businesses, each with a job posting and a candidate that has a
    Discord screening transcript. Returns ids/subs for both."""
    suffix = uuid.uuid4().hex[:8]
    business_a = Business(auth0_sub=f"auth0|iso-a-{suffix}", name="A Co")
    business_b = Business(auth0_sub=f"auth0|iso-b-{suffix}", name="B Co")
    db_session.add_all([business_a, business_b])
    db_session.flush()

    job_a = JobPosting(
        business_id=business_a.id,
        title="Role A",
        description="Build things.",
        faq_json="{}",
        is_active=True,
    )
    job_b = JobPosting(
        business_id=business_b.id,
        title="Role B",
        description="Build other things.",
        faq_json="{}",
        is_active=True,
    )
    db_session.add_all([job_a, job_b])
    db_session.flush()

    candidate_a = Candidate(
        business_id=business_a.id,
        job_posting_id=job_a.id,
        name="Alice In A",
        email="alice@a.com",
        phone="555-0100",
        address="1 A Street",
        resume_file_path="/resumes/alice.pdf",
    )
    candidate_b = Candidate(
        business_id=business_b.id,
        job_posting_id=job_b.id,
        name="Bob In B",
        email="bob@b.com",
        phone="555-0200",
        address="2 B Street",
        resume_file_path="/resumes/bob.pdf",
    )
    db_session.add_all([candidate_a, candidate_b])
    db_session.flush()

    db_session.add_all(
        [
            PipelineStage(candidate_id=candidate_a.id, stage=PipelineStageName.applied),
            PipelineStage(candidate_id=candidate_b.id, stage=PipelineStageName.applied),
        ]
    )

    for candidate in (candidate_a, candidate_b):
        conversation = Conversation(candidate_id=candidate.id, channel=ChannelType.discord)
        db_session.add(conversation)
        db_session.flush()
        for direction, text in [
            (MessageDirection.outbound, f"Tell me about your experience, {candidate.name}."),
            (MessageDirection.inbound, f"I've been doing this for years -- {candidate.name}."),
        ]:
            db_session.add(
                Message(
                    conversation_id=conversation.id,
                    direction=direction,
                    content_encrypted=_fernet().encrypt(text.encode("utf-8")),
                )
            )

    db_session.commit()

    return SimpleNamespace(
        a_id=business_a.id,
        b_id=business_b.id,
        a_sub=business_a.auth0_sub,
        b_sub=business_b.auth0_sub,
        a_job_id=job_a.id,
        b_job_id=job_b.id,
        a_candidate_id=candidate_a.id,
        b_candidate_id=candidate_b.id,
    )


def _audit_rows(db_session, business_id: int | None = None, action: str | None = None):
    query = db_session.query(AuditLogEntry)
    if business_id is not None:
        query = query.filter(AuditLogEntry.business_id == business_id)
    if action is not None:
        query = query.filter(AuditLogEntry.action == action)
    return query.all()


def test_list_candidates_only_returns_own_business(db_session, business_set):
    _auth_as(business_set.a_id)

    response = client.get("/candidates")

    assert response.status_code == 200
    names = [candidate["name"] for candidate in response.json()]
    assert "Alice In A" in names
    assert "Bob In B" not in names


def test_list_candidates_ignores_spoofed_business_id_query_param(db_session, business_set):
    _auth_as(business_set.a_id)

    response = client.get(f"/candidates?business_id={business_set.b_id}")

    assert response.status_code == 200
    candidate_ids = [candidate["id"] for candidate in response.json()]
    assert business_set.a_candidate_id in candidate_ids
    assert business_set.b_candidate_id not in candidate_ids


def test_candidate_detail_is_scoped_to_own_business(db_session, business_set):
    _auth_as(business_set.a_id)

    # Own candidate: reachable, with PII.
    own = client.get(f"/candidates/{business_set.a_candidate_id}")
    assert own.status_code == 200
    assert own.json()["name"] == "Alice In A"
    assert own.json()["email"] == "alice@a.com"

    # Business B's candidate: 404 -- never the data, and indistinguishable
    # from "doesn't exist".
    other = client.get(f"/candidates/{business_set.b_candidate_id}")
    assert other.status_code == 404
    assert other.json() == {"detail": "Candidate not found"}


def test_candidate_detail_ignores_spoofed_business_id_query_param(db_session, business_set):
    _auth_as(business_set.a_id)

    response = client.get(
        f"/candidates/{business_set.b_candidate_id}?business_id={business_set.a_id}"
    )

    assert response.status_code == 404


def test_assign_screening_is_scoped_to_own_business(db_session, business_set):
    _auth_as(business_set.a_id)

    assert (
        client.post(f"/candidates/{business_set.b_candidate_id}/assign-screening").status_code
        == 404
    )

    response = client.post(f"/candidates/{business_set.a_candidate_id}/assign-screening")
    assert response.status_code == 200

    stage = (
        db_session.query(PipelineStage)
        .filter(PipelineStage.candidate_id == business_set.a_candidate_id)
        .first()
    )
    assert stage.stage == PipelineStageName.screening_assigned


def test_shortlist_is_scoped_to_own_business(db_session, business_set):
    _auth_as(business_set.a_id)

    assert (
        client.post(f"/candidates/{business_set.b_candidate_id}/shortlist").status_code == 404
    )

    response = client.post(f"/candidates/{business_set.a_candidate_id}/shortlist")
    assert response.status_code == 200

    stage = (
        db_session.query(PipelineStage)
        .filter(PipelineStage.candidate_id == business_set.a_candidate_id)
        .first()
    )
    assert stage.stage == PipelineStageName.shortlisted


def test_review_with_ai_never_reveals_other_business_transcript(
    db_session, business_set, monkeypatch
):
    called = []

    def fake_review(transcript: str):
        called.append(transcript)
        return 7, "Looks good."

    monkeypatch.setattr(dashboard_routes, "review_transcript", fake_review)
    _auth_as(business_set.a_id)

    # Business B's candidate has a transcript, but A must not reach it.
    other = client.post(f"/candidates/{business_set.b_candidate_id}/review-with-ai")
    assert other.status_code == 404
    assert called == []

    # Own candidate works and the transcript is the decrypted one.
    own = client.post(f"/candidates/{business_set.a_candidate_id}/review-with-ai")
    assert own.status_code == 200
    assert own.json() == {"score": 7, "summary": "Looks good."}
    assert len(called) == 1
    assert "Alice In A" in called[0]


def test_spoofed_business_id_in_job_body_is_ignored(db_session, business_set):
    _auth_as(business_set.a_id)

    response = client.post(
        "/jobs",
        json={
            "title": "Spoofed",
            "description": "d",
            "location": "x",
            "employment_type": "Full-time",
            "business_id": business_set.b_id,
        },
    )

    assert response.status_code == 201
    job = db_session.get(JobPosting, response.json()["id"])
    assert job.business_id == business_set.a_id
    assert job.business_id != business_set.b_id


def test_candidate_viewed_writes_audit_log_entry(db_session, business_set):
    _auth_as(business_set.a_id)

    response = client.get(f"/candidates/{business_set.a_candidate_id}")
    assert response.status_code == 200

    entries = _audit_rows(db_session, business_id=business_set.a_id, action="candidate_viewed")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.actor == ACTOR_A
    assert entry.target_candidate_id == business_set.a_candidate_id


def test_assign_screening_writes_audit_log_entry(db_session, business_set):
    _auth_as(business_set.a_id)

    client.post(f"/candidates/{business_set.a_candidate_id}/assign-screening")

    entries = _audit_rows(db_session, business_id=business_set.a_id, action="assign_screening")
    assert len(entries) == 1
    assert entries[0].actor == ACTOR_A
    assert entries[0].target_candidate_id == business_set.a_candidate_id


def test_shortlist_writes_audit_log_entry(db_session, business_set):
    _auth_as(business_set.a_id)

    client.post(f"/candidates/{business_set.a_candidate_id}/shortlist")

    entries = _audit_rows(db_session, business_id=business_set.a_id, action="shortlist")
    assert len(entries) == 1
    assert entries[0].actor == ACTOR_A
    assert entries[0].target_candidate_id == business_set.a_candidate_id


def test_review_with_ai_writes_audit_log_entry(db_session, business_set, monkeypatch):
    monkeypatch.setattr(
        dashboard_routes, "review_transcript", lambda transcript: (6, "Decent.")
    )
    _auth_as(business_set.a_id)

    client.post(f"/candidates/{business_set.a_candidate_id}/review-with-ai")

    entries = _audit_rows(db_session, business_id=business_set.a_id, action="ai_review")
    assert len(entries) == 1
    assert entries[0].actor == ACTOR_A
    assert entries[0].target_candidate_id == business_set.a_candidate_id


def test_denied_access_to_other_business_writes_no_audit_entry(db_session, business_set):
    _auth_as(business_set.a_id)

    client.get(f"/candidates/{business_set.b_candidate_id}")
    client.post(f"/candidates/{business_set.b_candidate_id}/assign-screening")
    client.post(f"/candidates/{business_set.b_candidate_id}/review-with-ai")

    entries = _audit_rows(db_session, business_id=business_set.a_id)
    assert entries == []


def test_schedule_interview_is_scoped_to_own_business(db_session, business_set):
    _auth_as(business_set.a_id)

    assert (
        client.post(
            f"/candidates/{business_set.b_candidate_id}/schedule-interview",
            json={"scheduled_at": "2026-09-01T10:00:00+00:00"},
        ).status_code
        == 404
    )

    response = client.post(
        f"/candidates/{business_set.a_candidate_id}/schedule-interview",
        json={"scheduled_at": "2026-09-01T10:00:00+00:00", "interview_notes": "Zoom link"},
    )
    assert response.status_code == 200

    own_stage = (
        db_session.query(PipelineStage)
        .filter(PipelineStage.candidate_id == business_set.a_candidate_id)
        .first()
    )
    assert own_stage.stage == PipelineStageName.interview_scheduled
    assert own_stage.interview_notes == "Zoom link"

    # Business B's candidate must be untouched by A's request.
    other_stage = (
        db_session.query(PipelineStage)
        .filter(PipelineStage.candidate_id == business_set.b_candidate_id)
        .first()
    )
    assert other_stage.stage == PipelineStageName.applied


def test_schedule_interview_writes_audit_log_entry(db_session, business_set):
    _auth_as(business_set.a_id)

    client.post(
        f"/candidates/{business_set.a_candidate_id}/schedule-interview",
        json={"scheduled_at": "2026-09-01T10:00:00+00:00"},
    )

    entries = _audit_rows(db_session, business_id=business_set.a_id, action="schedule_interview")
    assert len(entries) == 1
    assert entries[0].actor == ACTOR_A
    assert entries[0].target_candidate_id == business_set.a_candidate_id


def test_list_interviews_is_scoped_to_own_business(db_session, business_set):
    _auth_as(business_set.a_id)
    client.post(
        f"/candidates/{business_set.a_candidate_id}/schedule-interview",
        json={"scheduled_at": "2026-09-01T10:00:00+00:00"},
    )

    _auth_as(business_set.b_id, actor="auth0|isolation-actor-b")
    client.post(
        f"/candidates/{business_set.b_candidate_id}/schedule-interview",
        json={"scheduled_at": "2026-09-02T10:00:00+00:00"},
    )

    _auth_as(business_set.a_id)
    response = client.get("/interviews")

    assert response.status_code == 200
    candidate_ids = [entry["id"] for entry in response.json()]
    assert business_set.a_candidate_id in candidate_ids
    assert business_set.b_candidate_id not in candidate_ids


def test_dashboard_routes_require_authentication() -> None:
    assert client.get("/candidates").status_code in (401, 403)
    assert client.get("/candidates/1").status_code in (401, 403)
    assert client.post("/candidates/1/assign-screening").status_code in (401, 403)
    assert client.post("/candidates/1/shortlist").status_code in (401, 403)
    assert client.post("/candidates/1/review-with-ai").status_code in (401, 403)
    assert client.post(
        "/candidates/1/schedule-interview", json={"scheduled_at": "2026-09-01T10:00:00+00:00"}
    ).status_code in (401, 403)
    assert client.get("/interviews").status_code in (401, 403)
    assert client.post("/jobs", json={"title": "x", "description": "y"}).status_code in (401, 403)
