"""Unauthenticated public API: job listings and application submission.

Consumed by the landing page. No auth required -- do not expose anything
here that isn't meant to be public (e.g. no candidate PII from other
applicants, no internal pipeline state).
"""

import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from src.db import get_db
from src.logging_config import get_logger
from src.models import Business, Candidate, JobPosting, PipelineStage, PipelineStageName
from src.notifications import notify_new_application

log = get_logger()

router = APIRouter(tags=["public"])

RESUME_STORAGE_DIR = os.environ.get("RESUME_STORAGE_DIR", "./resumes")


def _serialize_job_posting(job_posting: JobPosting) -> dict:
    try:
        benefits = json.loads(job_posting.benefits_json or "[]")
    except json.JSONDecodeError:
        benefits = []
    return {
        "id": job_posting.id,
        "title": job_posting.title,
        "description": job_posting.description,
        "location": job_posting.location,
        "employment_type": job_posting.employment_type,
        "pay_min": job_posting.pay_min,
        "pay_max": job_posting.pay_max,
        "pay_currency": job_posting.pay_currency,
        "benefits": benefits,
        "faq_json": job_posting.faq_json,
    }


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)):
    """List active job postings across all businesses."""
    job_postings = db.query(JobPosting).filter(JobPosting.is_active.is_(True)).all()
    return [_serialize_job_posting(job_posting) for job_posting in job_postings]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    """Fetch a single job posting's public detail (title, description, FAQ)."""
    job_posting = (
        db.query(JobPosting)
        .filter(JobPosting.id == job_id, JobPosting.is_active.is_(True))
        .first()
    )
    if job_posting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job posting not found")
    return _serialize_job_posting(job_posting)


@router.post("/jobs/{job_id}/apply")
def apply_to_job(
    job_id: int,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    resume: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Submit an application to a job posting."""
    job_posting = (
        db.query(JobPosting)
        .filter(JobPosting.id == job_id, JobPosting.is_active.is_(True))
        .first()
    )
    if job_posting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job posting not found")

    Path(RESUME_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    resume_filename = f"{uuid.uuid4()}_{resume.filename}"
    resume_file_path = str(Path(RESUME_STORAGE_DIR) / resume_filename)
    with open(resume_file_path, "wb") as f:
        f.write(resume.file.read())

    candidate = Candidate(
        business_id=job_posting.business_id,
        job_posting_id=job_posting.id,
        name=name,
        email=email,
        phone=phone,
        address=address,
        resume_file_path=resume_file_path,
    )
    db.add(candidate)
    db.flush()  # assigns candidate.id without committing yet

    db.add(PipelineStage(candidate_id=candidate.id, stage=PipelineStageName.applied))
    db.commit()
    db.refresh(candidate)

    log.info("candidate_applied", candidate_id=candidate.id, job_posting_id=job_posting.id)

    business = db.query(Business).filter(Business.id == job_posting.business_id).first()
    notify_new_application(candidate, job_posting, business)

    return {"id": candidate.id}
