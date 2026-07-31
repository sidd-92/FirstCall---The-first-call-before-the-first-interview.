"""business_id isolation tests.

TODO: once GET /candidates, GET /candidates/{id}, assign-screening, and
shortlist are implemented, add the same cross-business isolation checks for
those (see routes/dashboard.py's TODOs). review-with-ai is covered here
since it's implemented.
"""

import pytest
from fastapi.testclient import TestClient

from src.auth import get_current_business
from src.main import app
from src.models import Business, Candidate, JobPosting

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_review_with_ai_404s_for_another_businesss_candidate(db_session):
    business_a = Business(auth0_sub="auth0|business-a", name="A Co")
    business_b = Business(auth0_sub="auth0|business-b", name="B Co")
    db_session.add_all([business_a, business_b])
    db_session.flush()

    job_b = JobPosting(
        business_id=business_b.id, title="Role", description="d", faq_json="{}", is_active=True
    )
    db_session.add(job_b)
    db_session.flush()

    candidate_b = Candidate(
        business_id=business_b.id,
        job_posting_id=job_b.id,
        name="Belongs To B",
        email="b@example.com",
        phone="1",
        address="x",
        resume_file_path="/r.pdf",
    )
    db_session.add(candidate_b)
    db_session.commit()
    db_session.refresh(candidate_b)

    # Authenticated as business A, but requesting business B's candidate.
    app.dependency_overrides[get_current_business] = lambda: business_a.id

    response = client.post(f"/candidates/{candidate_b.id}/review-with-ai")

    assert response.status_code == 404
