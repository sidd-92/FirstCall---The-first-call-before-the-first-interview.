"""Authenticated HR dashboard API: candidate pipeline, screening review, and
candidate lifecycle actions.

Every route here depends on `get_current_actor_and_business` (or
`get_current_business` for routes that don't audit) to resolve the caller's
business_id and Auth0 sub from their verified Auth0 JWT. Every query MUST
filter by that business_id -- never accept or trust a business_id supplied
by the client.

Candidate reads and lifecycle transitions are recorded in the append-only
AuditLogEntry table (actor = the verified Auth0 `sub`).
"""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.anthropic_client import review_transcript
from src.auth import get_current_actor_and_business, get_current_business
from src.crypto import decrypt_content
from src.db import get_db
from src.logging_config import get_logger
from src.models import (
    AuditLogEntry,
    Candidate,
    ChannelType,
    Conversation,
    JobPosting,
    Message,
    PipelineStage,
    PipelineStageName,
)

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


def _write_audit(db: Session, business_id: int, actor: str, action: str, candidate_id: int) -> None:
    db.add(
        AuditLogEntry(
            business_id=business_id,
            actor=actor,
            action=action,
            target_candidate_id=candidate_id,
        )
    )


def _get_candidate_or_404(db: Session, candidate_id: int, business_id: int) -> Candidate:
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.business_id == business_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate


def _set_pipeline_stage(
    db: Session, candidate_id: int, stage: PipelineStageName
) -> None:
    pipeline_stage = (
        db.query(PipelineStage).filter(PipelineStage.candidate_id == candidate_id).first()
    )
    if pipeline_stage is None:
        db.add(PipelineStage(candidate_id=candidate_id, stage=stage))
    else:
        pipeline_stage.stage = stage


def _stage_for(candidate: Candidate) -> str | None:
    return candidate.pipeline_stages[0].stage.value if candidate.pipeline_stages else None


def _serialize_candidate_summary(candidate: Candidate) -> dict:
    last_activity = None
    for conversation in candidate.conversations:
        for message in conversation.messages:
            if last_activity is None or message.created_at > last_activity:
                last_activity = message.created_at
    if last_activity is None and candidate.pipeline_stages:
        last_activity = candidate.pipeline_stages[0].updated_at
    if last_activity is None:
        last_activity = candidate.created_at

    return {
        "id": candidate.id,
        "name": candidate.name,
        "job_posting_title": candidate.job_posting.title,
        "stage": _stage_for(candidate),
        "last_activity_at": last_activity.isoformat(),
    }


def _serialize_message(message: Message) -> dict:
    return {
        "id": message.id,
        "direction": message.direction.value,
        "content": decrypt_content(message.content_encrypted),
        "created_at": message.created_at.isoformat(),
    }


def _candidate_messages(db: Session, candidate_id: int) -> list[Message]:
    return (
        db.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Conversation.candidate_id == candidate_id)
        .order_by(Message.id)
        .all()
    )


def _screening_transcript(db: Session, candidate_id: int) -> str | None:
    """Build the Discord screening transcript, or None if there's no Discord
    conversation (or it has no messages yet) for this candidate."""
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.candidate_id == candidate_id,
            Conversation.channel == ChannelType.discord,
        )
        .first()
    )
    if conversation is None:
        return None
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.id)
        .all()
    )
    if not messages:
        return None

    speaker = {"inbound": "Candidate", "outbound": "Agent"}
    return "\n".join(
        f"{speaker[message.direction.value]}: {decrypt_content(message.content_encrypted)}"
        for message in messages
    )


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
    context: tuple[int, str] = Depends(get_current_actor_and_business),
    db: Session = Depends(get_db),
):
    """List candidates belonging to the authenticated business.

    Scope comes solely from the verified JWT -- a `business_id` passed as a
    query param or body field is ignored.
    """
    business_id, _actor = context
    candidates = (
        db.query(Candidate)
        .filter(Candidate.business_id == business_id)
        .order_by(Candidate.id)
        .all()
    )
    return [_serialize_candidate_summary(candidate) for candidate in candidates]


@router.get("/candidates/{candidate_id}")
def get_candidate(
    candidate_id: int,
    context: tuple[int, str] = Depends(get_current_actor_and_business),
    db: Session = Depends(get_db),
):
    """Fetch a single candidate's detail, scoped to the authenticated business.

    Returns 404 -- not 403 -- when the candidate belongs to another
    business, so callers can't tell whether the candidate exists.
    """
    business_id, actor = context
    candidate = _get_candidate_or_404(db, candidate_id, business_id)

    _write_audit(db, business_id, actor, "candidate_viewed", candidate.id)
    db.commit()

    return {
        "id": candidate.id,
        "name": candidate.name,
        "email": candidate.email,
        "phone": candidate.phone,
        "address": candidate.address,
        "resume_file_path": candidate.resume_file_path,
        "job_posting_title": candidate.job_posting.title,
        "stage": _stage_for(candidate),
        "messages": [_serialize_message(message) for message in _candidate_messages(db, candidate.id)],
        "screening_transcript": _screening_transcript(db, candidate.id),
    }


@router.post("/candidates/{candidate_id}/assign-screening")
def assign_screening(
    candidate_id: int,
    context: tuple[int, str] = Depends(get_current_actor_and_business),
    db: Session = Depends(get_db),
):
    """Move a candidate into the screening_assigned pipeline stage."""
    business_id, actor = context
    candidate = _get_candidate_or_404(db, candidate_id, business_id)

    _set_pipeline_stage(db, candidate_id, PipelineStageName.screening_assigned)
    _write_audit(db, business_id, actor, "assign_screening", candidate.id)
    db.commit()

    log.info("screening_assigned", candidate_id=candidate_id, business_id=business_id)
    return {"stage": "screening_assigned"}


@router.post("/candidates/{candidate_id}/shortlist")
def shortlist_candidate(
    candidate_id: int,
    context: tuple[int, str] = Depends(get_current_actor_and_business),
    db: Session = Depends(get_db),
):
    """Move a candidate into the shortlisted pipeline stage."""
    business_id, actor = context
    candidate = _get_candidate_or_404(db, candidate_id, business_id)

    _set_pipeline_stage(db, candidate_id, PipelineStageName.shortlisted)
    _write_audit(db, business_id, actor, "shortlist", candidate.id)
    db.commit()

    log.info("candidate_shortlisted", candidate_id=candidate_id, business_id=business_id)
    return {"stage": "shortlisted"}


@router.post("/candidates/{candidate_id}/review-with-ai")
def review_with_ai(
    candidate_id: int,
    context: tuple[int, str] = Depends(get_current_actor_and_business),
    db: Session = Depends(get_db),
):
    """On-demand only -- fetches the candidate's screening (Discord) transcript
    and sends it in ONE Claude Haiku call for a score + short summary. Never
    triggered automatically; only ever runs when HR explicitly calls this."""
    business_id, actor = context
    candidate = _get_candidate_or_404(db, candidate_id, business_id)

    transcript = _screening_transcript(db, candidate_id)
    if transcript is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No screening transcript available for this candidate",
        )

    log.info("ai_review_requested", candidate_id=candidate_id, business_id=business_id)
    score, summary = review_transcript(transcript)

    _write_audit(db, business_id, actor, "ai_review", candidate.id)
    db.commit()

    log.info(
        "ai_review_completed",
        candidate_id=candidate_id,
        business_id=business_id,
        has_score=score is not None,
    )
    return {"score": score, "summary": summary}
