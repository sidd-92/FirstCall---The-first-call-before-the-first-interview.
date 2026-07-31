"""Unauthenticated public API: job listings and application submission.

Consumed by the landing page. No auth required -- do not expose anything
here that isn't meant to be public (e.g. no candidate PII from other
applicants, no internal pipeline state).
"""

from fastapi import APIRouter, File, Form, UploadFile

router = APIRouter(tags=["public"])


@router.get("/jobs")
def list_jobs():
    """List active job postings across all businesses.

    TODO: query JobPosting where is_active=True, return public fields only.
    """
    raise NotImplementedError


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    """Fetch a single job posting's public detail (title, description, FAQ).

    TODO: query JobPosting by id, 404 if missing or inactive.
    """
    raise NotImplementedError


@router.post("/jobs/{job_id}/apply")
def apply_to_job(
    job_id: int,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    resume: UploadFile = File(...),
):
    """Submit an application to a job posting.

    TODO: validate job_id is active, store the resume file, create a
    Candidate row, and kick off the initial PipelineStage ("applied").
    """
    raise NotImplementedError
