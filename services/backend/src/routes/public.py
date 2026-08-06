"""Unauthenticated public API: job listings and application submission.

Consumed by the landing page. No auth required -- do not expose anything
here that isn't meant to be public (e.g. no candidate PII from other
applicants, no internal pipeline state).
"""

import asyncio
import json
import os
import secrets
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from src import mcp_client
from src.db import get_db
from src.logging_config import get_logger
from src.models import Business, Candidate, JobPosting, PipelineStage, PipelineStageName
from src.notifications import notify_new_application

log = get_logger()

# Length chosen to keep the code short enough to type into a Discord DM by
# hand while keeping collisions rare; retried on the rare unique-constraint
# clash rather than sized to make collisions impossible.
DISCORD_LINK_CODE_LENGTH = 6


def _generate_discord_link_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I -- easy to read/type
    return "".join(secrets.choice(alphabet) for _ in range(DISCORD_LINK_CODE_LENGTH))

router = APIRouter(tags=["public"])

RESUME_STORAGE_DIR = os.environ.get("RESUME_STORAGE_DIR", "./resumes")
# Backend-side equivalents of the landing page's VITE_AGENT_EMAIL_ADDRESS /
# VITE_DISCORD_INVITE_URL (see apps/landing/.env.example) -- needed here so
# the confirmation email can carry the same info as the one-time confirmation
# screen. AGENT_EMAIL_ADDRESS should match VITE_AGENT_EMAIL_ADDRESS.
AGENT_EMAIL_ADDRESS = os.environ.get("AGENT_EMAIL_ADDRESS", "")
DISCORD_INVITE_URL = os.environ.get("DISCORD_INVITE_URL", "")


def _tool_result_to_dict(result) -> dict:
    if isinstance(result.structured_content, dict):
        return result.structured_content
    return json.loads(result.content[0].text)


def _application_confirmation_text(candidate: Candidate, job_posting: JobPosting) -> str:
    """Mirrors what's shown on the landing page's one-time confirmation
    screen (JobDetailPage.tsx) -- this email is the candidate's permanent,
    searchable copy of that screen, since there's no candidate login/"my
    applications" page by design."""
    lines = [
        f"Hi {candidate.name},",
        "",
        f'Thanks for applying to "{job_posting.title}". Your application has been received.',
        "",
        "You can also reach out directly by email:",
        AGENT_EMAIL_ADDRESS or "(application email not configured)",
    ]
    lines += [
        "",
        "Get updates over Discord (optional): DM our Discord bot the code "
        f"below to connect your application: {candidate.discord_link_code}",
    ]
    if DISCORD_INVITE_URL:
        lines.append(f"Join our Discord server: {DISCORD_INVITE_URL}")
    return "\n".join(lines)


async def _send_application_confirmation_email(
    candidate: Candidate, job_posting: JobPosting
) -> None:
    """Goes through mcp-server's own tools (connect_channel/initiate, both
    backed by caspian_client there) -- the same path the interview
    confirmation email (routes/dashboard.py) uses, not a separate ad hoc
    email integration."""
    connection = _tool_result_to_dict(
        await mcp_client.call_tool("connect_channel", {"channel": "email"})
    )
    await mcp_client.call_tool(
        "initiate",
        {
            "connection_id": connection["id"],
            "recipient": candidate.email,
            "text": _application_confirmation_text(candidate, job_posting),
        },
    )


def _notify_candidate_application_received(candidate: Candidate, job_posting: JobPosting) -> None:
    """Best-effort, mirrors dashboard.py's `_notify_candidate_interview_scheduled`:
    the application has already been committed by the time this runs, so a
    failure here (mcp-server down, email channel not connected, ...) must
    never fail the apply request."""
    try:
        asyncio.run(_send_application_confirmation_email(candidate, job_posting))
    except Exception:
        log.warning(
            "application_confirmation_email_failed", candidate_id=candidate.id, exc_info=True
        )


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
        discord_link_code=_generate_discord_link_code(),
    )
    db.add(candidate)
    db.flush()  # assigns candidate.id without committing yet

    db.add(PipelineStage(candidate_id=candidate.id, stage=PipelineStageName.applied))
    db.commit()
    db.refresh(candidate)

    log.info("candidate_applied", candidate_id=candidate.id, job_posting_id=job_posting.id)

    business = db.query(Business).filter(Business.id == job_posting.business_id).first()
    notify_new_application(candidate, job_posting, business)
    _notify_candidate_application_received(candidate, job_posting)

    return {"id": candidate.id, "discord_link_code": candidate.discord_link_code}
