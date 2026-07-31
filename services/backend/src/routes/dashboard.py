"""Authenticated HR dashboard API: candidate pipeline and screening review.

Every route here depends on `get_current_business` to resolve the caller's
business_id from their verified Auth0 JWT. Every query MUST filter by that
business_id -- never accept or trust a business_id supplied by the client.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth import get_current_business
from src.db import get_db

router = APIRouter(tags=["dashboard"])


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
