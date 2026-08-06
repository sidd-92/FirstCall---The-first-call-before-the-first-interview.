"""SQLAlchemy models for FirstCall.

All business-owned rows (job postings, candidates, audit entries, and —
transitively, via candidate/job posting — conversations, messages, pipeline
stages) are scoped by `business_id`. Every query in routes/dashboard.py must
filter by the `business_id` resolved from the verified Auth0 JWT
(`get_current_business` in auth.py) -- never trust a client-supplied
business_id.

`Message.content_encrypted` stores Fernet-encrypted message content; message
bodies must never be written to this column in plaintext.
"""

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ChannelType(str, enum.Enum):
    email = "email"
    discord = "discord"


class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class PipelineStageName(str, enum.Enum):
    applied = "applied"
    screening_assigned = "screening_assigned"
    screening_completed = "screening_completed"
    shortlisted = "shortlisted"
    interview_scheduled = "interview_scheduled"
    confirmed = "confirmed"


class BusinessStatus(str, enum.Enum):
    """A business's access to gated capabilities (posting jobs, MCP Server
    tools) -- distinct from `needs_onboarding`, which is just about having a
    real name. Self-service signup (auto-provisioning in auth.py) always
    starts a business at "unrequested": creating an account must never by
    itself grant access to shared, business-facing infrastructure (Email/
    Discord channels, the public job board). "unrequested" -> "pending_review"
    only happens via the business's own explicit POST /business/request-access
    call; "pending_review" -> "active" only via an admin's POST
    /admin/businesses/{id}/approve."""

    unrequested = "unrequested"
    pending_review = "pending_review"
    active = "active"
    suspended = "suspended"


# Placeholder `name` given to a Business row auto-created on a verified JWT's
# first request (see get_current_actor_and_business in auth.py). Distinct
# from any name a real onboarding submission would plausibly use.
PLACEHOLDER_BUSINESS_NAME = "New Business (unnamed)"


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    auth0_sub: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    # True until the business sets a real name via PATCH /business/me.
    # Auto-created rows (get_current_actor_and_business) start True; rows
    # created with a real name (the legacy POST /businesses/onboard route)
    # start False. Dashboard gates on this to show the onboarding step.
    needs_onboarding: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Gates access to shared infrastructure (see BusinessStatus). Every new
    # signup -- including auto-provisioned ones -- starts "unrequested".
    status: Mapped[BusinessStatus] = mapped_column(
        Enum(BusinessStatus), default=BusinessStatus.unrequested, server_default="unrequested"
    )
    # Captured from the Auth0 JWT's "email" claim at the moment the business
    # calls POST /business/request-access -- the admin review list
    # (GET /admin/businesses) shows this so the admin knows who's asking,
    # without needing a separate Auth0 Management API lookup by sub. Null
    # until a request is made.
    requested_by_email: Mapped[str | None] = mapped_column(String, nullable=True)
    # Where Agent 2's ops notifications (new application, screening
    # completed) get sent. Null until the business fills this in somewhere
    # (onboarding isn't built yet) -- notifications are skipped, not errored,
    # when it's unset.
    owner_email: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    job_postings: Mapped[list["JobPosting"]] = relationship(back_populates="business")
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="business")
    audit_log_entries: Mapped[list["AuditLogEntry"]] = relationship(back_populates="business")


class JobPosting(Base):
    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String, default="")
    # Free-text, e.g. "Permanent, Full-time" -- mirrors how job boards like
    # Indeed show multiple tags rather than a single enum value.
    employment_type: Mapped[str] = mapped_column(String, default="")
    pay_min: Mapped[int | None] = mapped_column(nullable=True)
    pay_max: Mapped[int | None] = mapped_column(nullable=True)
    pay_currency: Mapped[str] = mapped_column(String, default="INR")
    # JSON-encoded list[str], e.g. '["Paid time off", "Provident Fund"]'.
    benefits_json: Mapped[str] = mapped_column(Text, default="[]")
    faq_json: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    business: Mapped["Business"] = relationship(back_populates="job_postings")
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="job_posting")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String)
    address: Mapped[str] = mapped_column(String)
    resume_file_path: Mapped[str] = mapped_column(String)
    # Set once a candidate's Discord identity is linked (e.g. they DM the
    # agent, or the apply flow collects it) -- lets mcp-server's Agent 1
    # resolve an inbound Discord message to a candidate. Null until linked.
    discord_user_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    # Short one-time code shown on the apply confirmation screen; the
    # candidate DMs it to the Discord bot to link discord_user_id above (see
    # services/mcp-server/src/agents/agent1.py's linking flow). Left in place
    # once used -- agent1 only consults it while discord_user_id is unset.
    discord_link_code: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    business: Mapped["Business"] = relationship(back_populates="candidates")
    job_posting: Mapped["JobPosting"] = relationship(back_populates="candidates")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="candidate")
    pipeline_stages: Mapped[list["PipelineStage"]] = relationship(back_populates="candidate")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    channel: Mapped[ChannelType] = mapped_column(Enum(ChannelType))
    # caspian-sdk's own conversation_id for this thread -- lets mcp-server's
    # Agent 1 find the existing conversation (and thus candidate_id) for an
    # inbound message without re-deriving it from sender identity every time.
    external_conversation_id: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True, index=True
    )
    # True only for a conversation we know is a private DM between the bot
    # and the candidate (never a shared/public channel). Agent 1 refuses to
    # send or continue screening content on any conversation where this is
    # False -- see services/mcp-server/src/agents/agent1.py's is_dm routing.
    is_dm: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    candidate: Mapped["Candidate"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    direction: Mapped[MessageDirection] = mapped_column(Enum(MessageDirection))
    # Fernet-encrypted message content. Never store plaintext here.
    content_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    # Optional tag for outbound messages ("faq_answer" | "screening_question" |
    # "holding"); lets Agent 1 derive "which screening question is next" by
    # counting prior screening_question messages, without an LLM call or a
    # separate progress table. Null for inbound / untagged messages.
    kind: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"

    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"), primary_key=True
    )
    stage: Mapped[PipelineStageName] = mapped_column(Enum(PipelineStageName))
    # Set together when HR schedules an interview (POST
    # /candidates/{id}/schedule-interview moves `stage` to
    # interview_scheduled at the same time). No separate Interview table --
    # PipelineStage is already 1:1 with a candidate, so these just live here.
    scheduled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Free-text, e.g. a meeting link or interviewer name. Null until scheduled.
    interview_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    candidate: Mapped["Candidate"] = relationship(back_populates="pipeline_stages")


class AuditLogEntry(Base):
    """Append-only audit trail of who did what to which candidate.

    Distinct from structlog operational logs (logging_config.py) -- this
    table is the source of truth for business-facing audit history and
    must never be edited or deleted, only inserted into.
    """

    __tablename__ = "audit_log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    actor: Mapped[str] = mapped_column(String)  # Auth0 sub of who acted
    action: Mapped[str] = mapped_column(String)
    target_candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    timestamp: Mapped[datetime] = mapped_column(default=_utcnow)

    business: Mapped["Business"] = relationship(back_populates="audit_log_entries")
