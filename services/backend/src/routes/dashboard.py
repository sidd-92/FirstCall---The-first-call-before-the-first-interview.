"""Authenticated HR dashboard API: candidate pipeline and screening review.

Every route here depends on `get_current_business` to resolve the caller's
business_id from their verified Auth0 JWT. Every query MUST filter by that
business_id -- never accept or trust a business_id supplied by the client.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.anthropic_client import review_transcript
from src.auth import get_current_business
from src.crypto import decrypt_content
from src.db import get_db
from src.logging_config import get_logger
from src.models import Candidate, ChannelType, Conversation, JobPosting, Message

log = get_logger()

router = APIRouter(tags=["dashboard"])


class JobPostingCreate(BaseModel):
    title: str
    description: str
    location: str
    employment_type: str
    pay_min: int | None = None
    pay_max: int | None = None
    pay_currency: str = "INR"
    benefits: list[str] = []


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job_posting(
    payload: JobPostingCreate,
    business_id: int = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Create a new job posting for the authenticated business.

    FAQ/screening-question config (src/agents/config.py's faq_json contract)
    isn't authored through this form -- new postings start with none and can
    have it added later.
    """
    job_posting = JobPosting(
        business_id=business_id,
        title=payload.title,
        description=payload.description,
        location=payload.location,
        employment_type=payload.employment_type,
        pay_min=payload.pay_min,
        pay_max=payload.pay_max,
        pay_currency=payload.pay_currency,
        benefits_json=json.dumps(payload.benefits),
        faq_json="{}",
    )
    db.add(job_posting)
    db.commit()
    db.refresh(job_posting)

    log.info("job_posting_created", job_posting_id=job_posting.id, business_id=business_id)

    return {"id": job_posting.id}


@router.get("/candidates")
def list_candidates(
    business_id: int = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """List candidates belonging to the authenticated business.

    TODO: query Candidate filtered by business_id, optionally joined with
    PipelineStage for pipeline view.
    """
    raise NotImplementedError


@router.get("/candidates/{candidate_id}")
def get_candidate(
    candidate_id: int,
    business_id: int = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Fetch a single candidate's detail, scoped to the authenticated business.

    TODO: query Candidate by (id=candidate_id, business_id=business_id),
    404 if not found -- do not leak existence of candidates in other
    businesses.
    """
    raise NotImplementedError


@router.post("/candidates/{candidate_id}/assign-screening")
def assign_screening(
    candidate_id: int,
    business_id: int = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Move a candidate into the screening_assigned pipeline stage.

    TODO: verify candidate belongs to business_id, update PipelineStage,
    write an AuditLogEntry (actor = caller's Auth0 sub).
    """
    raise NotImplementedError


@router.post("/candidates/{candidate_id}/shortlist")
def shortlist_candidate(
    candidate_id: int,
    business_id: int = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Move a candidate into the shortlisted pipeline stage.

    TODO: verify candidate belongs to business_id, update PipelineStage,
    write an AuditLogEntry (actor = caller's Auth0 sub).
    """
    raise NotImplementedError


@router.post("/candidates/{candidate_id}/review-with-ai")
def review_with_ai(
    candidate_id: int,
    business_id: int = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """On-demand only -- fetches the candidate's screening (Discord) transcript
    and sends it in ONE Claude Haiku call for a score + short summary. Never
    triggered automatically; only ever runs when HR explicitly calls this."""
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.business_id == business_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.candidate_id == candidate_id,
            Conversation.channel == ChannelType.discord,
        )
        .first()
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No screening transcript available for this candidate",
        )

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.id)
        .all()
    )
    speaker = {"inbound": "Candidate", "outbound": "Agent"}
    transcript = "\n".join(
        f"{speaker[m.direction.value]}: {decrypt_content(m.content_encrypted)}" for m in messages
    )

    log.info("ai_review_requested", candidate_id=candidate_id, business_id=business_id)
    score, summary = review_transcript(transcript)
    log.info(
        "ai_review_completed",
        candidate_id=candidate_id,
        business_id=business_id,
        has_score=score is not None,
    )

    return {"score": score, "summary": summary}
