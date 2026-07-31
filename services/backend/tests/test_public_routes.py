"""Placeholder tests for unauthenticated public routes.

TODO: once implemented, test GET /jobs, GET /jobs/{id}, and
POST /jobs/{id}/apply against a temporary SQLite DB.
"""

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
