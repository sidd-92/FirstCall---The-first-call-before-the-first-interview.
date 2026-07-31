"""Agent 1: the hackathon's "at least 2 channels, 1 handler" agent.

Both Email and Discord connect through the single `handle_message` function
registered below -- do not split this into one handler per channel; branch
on `message.channel` instead.

- Email: answer FAQ questions about a job posting (parsed from the subject's
  "[JOB-{id}]" tag), falling back to Claude Haiku only for questions the
  fixed FAQ doesn't cover (src/agents/faq.py).
- Discord: run the fixed screening question sequence (src/agents/screening.py)
  once HR has assigned screening for that candidate; otherwise send a
  holding reply. No LLM call is used to sequence questions -- only (later,
  in a separate agent) to score/summarize the finished conversation.
"""

import os
import re

from caspian_sdk import CommClient, Message

from src import db, storage
from src.agents import faq, screening
from src.agents.config import load_job_agent_config
from src.logging_config import get_logger

log = get_logger()

JOB_TAG_RE = re.compile(r"\[JOB-(\d+)\]")


def _get_or_create_conversation(candidate_id: int, channel: str, external_conversation_id: str) -> int:
    existing = db.find_conversation_by_external_id(external_conversation_id)
    if existing is not None:
        return existing["id"]
    return db.create_conversation(candidate_id, channel, external_conversation_id)


def _handle_email(message: Message) -> None:
    conv_log = log.bind(channel="email")
    conv_log.info("message_received")

    match = JOB_TAG_RE.search(message.subject or "")
    if not match:
        conv_log.warning("email_missing_job_tag")
        message.reply(
            text="Sorry, we couldn't tell which role this is about -- please reply using "
            "the original application email thread so we can find your application."
        )
        return
    job_posting_id = int(match.group(1))

    sender_email = (message.sender or {}).get("email")
    candidate = db.find_candidate_by_email(sender_email, job_posting_id) if sender_email else None
    if candidate is None:
        conv_log.warning("email_candidate_not_found", job_posting_id=job_posting_id)
        message.reply(
            text="Sorry, we couldn't match this email to an application on file for this role."
        )
        return
    candidate_id = candidate["id"]
    conv_log = conv_log.bind(candidate_id=candidate_id, job_posting_id=job_posting_id)

    config = load_job_agent_config(job_posting_id)
    if config is None:
        conv_log.error("job_posting_not_found")
        message.reply(text="Sorry, we couldn't find that role anymore.")
        return

    conversation_id = _get_or_create_conversation(candidate_id, "email", message.conversation_id)
    storage.save_message(conversation_id, "inbound", message.text or "")

    answer, used_llm_fallback = faq.answer_question(config, message.text)
    message.reply(text=answer)
    storage.save_message(conversation_id, "outbound", answer, kind="faq_answer")

    conv_log.info("faq_answered", used_llm_fallback=used_llm_fallback)


def _resolve_discord_candidate(message: Message) -> tuple[int, int] | None:
    """Returns (candidate_id, conversation_id) if this Discord thread is
    already linked to a candidate, else None."""
    existing = db.find_conversation_by_external_id(message.conversation_id)
    if existing is not None:
        return existing["candidate_id"], existing["id"]

    discord_user_id = (message.sender or {}).get("id")
    if not discord_user_id:
        return None
    candidate = db.find_candidate_by_discord_user_id(discord_user_id)
    if candidate is None:
        return None

    conversation_id = db.create_conversation(candidate["id"], "discord", message.conversation_id)
    return candidate["id"], conversation_id


def _handle_discord(message: Message) -> None:
    conv_log = log.bind(channel="discord")
    conv_log.info("message_received")

    resolved = _resolve_discord_candidate(message)
    if resolved is None:
        # No candidate/conversation to attach this message to -- can't persist
        # it (conversations.candidate_id is a required FK), so we only log +
        # reply. See module docstring: linking a Discord identity to a
        # candidate (Candidate.discord_user_id) happens elsewhere.
        conv_log.warning("discord_candidate_unresolved")
        message.reply(text=screening.UNRECOGNIZED_MESSAGE)
        return
    candidate_id, conversation_id = resolved
    conv_log = conv_log.bind(candidate_id=candidate_id)

    storage.save_message(conversation_id, "inbound", message.text or "")

    stage = db.get_pipeline_stage(candidate_id)
    if stage != "screening_assigned":
        conv_log.info("discord_holding_reply", stage=stage)
        message.reply(text=screening.HOLDING_MESSAGE)
        storage.save_message(conversation_id, "outbound", screening.HOLDING_MESSAGE, kind="holding")
        return

    candidate = db.get_candidate(candidate_id)
    config = load_job_agent_config(candidate["job_posting_id"]) if candidate else None
    questions = config.screening_questions if config else []

    question_index = db.count_messages_by_kind(conversation_id, screening.SCREENING_QUESTION_KIND)
    if question_index > 0:
        conv_log.info("screening_answer_received", question_index=question_index - 1)

    turn = screening.next_screening_turn(questions, question_index)
    message.reply(text=turn.reply_text)
    storage.save_message(conversation_id, "outbound", turn.reply_text, kind=turn.kind)

    if turn.kind == screening.SCREENING_QUESTION_KIND:
        conv_log.info("screening_question_asked", question_index=question_index)
    else:
        conv_log.info("screening_sequence_complete")


def handle_message(message: Message) -> None:
    """The single on_message handler for both Email and Discord."""
    if message.channel == "email":
        _handle_email(message)
    elif message.channel == "discord":
        _handle_discord(message)
    else:
        log.warning("unhandled_channel", channel=message.channel)


def register(client: CommClient) -> None:
    """Connect Email + Discord and register Agent 1's single handler for both.

    Connecting is best-effort: a channel that's already connected, or whose
    credentials aren't configured yet, shouldn't stop the mcp-server process
    from starting -- just that channel won't receive traffic until fixed.
    """
    try:
        client.connect_email()
    except Exception:
        log.warning("email_connect_failed", exc_info=True)

    discord_bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if discord_bot_token:
        try:
            client.connect_discord(bot_token=discord_bot_token)
        except Exception:
            log.warning("discord_connect_failed", exc_info=True)
    else:
        log.warning("discord_not_configured", detail="DISCORD_BOT_TOKEN is not set")

    client.on_message(handle_message)
