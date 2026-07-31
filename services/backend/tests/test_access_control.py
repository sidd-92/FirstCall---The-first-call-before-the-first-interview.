"""Placeholder for business_id isolation tests.

TODO: once dashboard routes are implemented, verify that a business
authenticated via Auth0 can never read or modify another business's
candidates, job postings, conversations, or audit log entries -- e.g. seed
two businesses with candidates each, authenticate as business A, and assert
GET /candidates/{business_B_candidate_id} returns 404, not the record.
"""


def test_placeholder() -> None:
    assert True
