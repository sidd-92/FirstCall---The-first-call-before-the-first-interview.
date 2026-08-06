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

Discord privacy invariant: screening answers (salary expectations, work
history, etc.) are candidate-specific and must never be visible to another
candidate. caspian-sdk's Discord integration is guild/server-oriented by
default (see caspian_sdk.CommClient.install_discord's docstring) and
`Message.reply()` always replies "on the channel the message arrived from"
-- so a naive reply-based flow leaks straight into a shared server channel.
Every conversation this module treats as safe for screening content is
tracked with `is_dm=True` (src/db.py's `conversations.is_dm` column, which
*we* set -- never inferred from timing). Anything else -- including a
candidate's very first message, wherever it lands -- gets at most a
generic, non-revealing reply.

This is fail-CLOSED by design: `caspian_sdk.Message` (checked directly
against the installed 0.6.1 package) carries no field of any kind that
distinguishes a DM from a guild/public-channel message -- no `is_dm`,
`guild_id`, `channel_type`, or similar; `sender` is an untyped `dict | None`
populated straight from the gateway payload, and the only key any code here
relies on is `"address"`. So `is_dm` is determined per-message by calling
`client.list_messages(conversation_id)` (a real, documented SDK method that
hits the gateway directly -- verified live: it returns each message's raw
`chat_type` field, which the `Message` wrapper itself drops) and checking
*that specific message's* `chat_type` (see `_is_dm_message`). `is_dm=True`
only when the lookup positively returns `chat_type == "dm"` for this exact
message id -- never cached, never reused from an earlier message on the
same conversation, and never inferred from `client.initiate()` (see below).
Any failure mode -- the lookup call raising, the message not showing up in
the response, or a `chat_type` that's anything other than exactly `"dm"`
(including `None`/missing) -- is treated as NOT a DM. A candidate with
Discord's "block DMs from server members" privacy setting enabled, for
example, could make a lookup come back ambiguous; treating that as
"probably a DM" would silently reopen the exact leak this module exists to
close, so it doesn't.

`client.initiate()` (see `_open_discord_dm`) is still called on linking as
a best-effort proactive nicety -- it's what actually opens/delivers a DM
channel to the candidate -- but its response is no longer used to decide
`is_dm` for anything. Whether `initiate()` reports "confirmed",
"unconfirmed", or "failed" has no bearing on how any message is classified;
only a positive `chat_type == "dm"` from `list_messages()` does.

Known gap: the installed caspian-sdk (0.6.1) dispatches exactly three event
types (message.received, interaction.received, reaction.received; see
`CommClient._dispatch_event`) and has no "member joined the server" hook of
any kind. So a candidate's *first-ever* contact -- typing their Discord link
code somewhere -- cannot be pre-empted by a join-time DM; the earliest this
code can act is the moment that first message arrives, at which point it
immediately pivots to DMs for everything else. Closing that first-message
gap for real would need either a Discord-native integration (discord.py
`on_member_join`) alongside caspian-sdk, or gateway-side support caspian-sdk
doesn't currently expose.
"""

import os
import re

from caspian_sdk import CommClient, CommError, Message

from src import db, status, storage
from src.agents import agent2, faq, screening
from src.agents.config import load_job_agent_config
from src.logging_config import get_logger

log = get_logger()

JOB_TAG_RE = re.compile(r"\[JOB-(\d+)\]")

# Set once at startup by `register()`. Needed to `initiate()` a DM, which
# (unlike `reply()`/`send_message()`) requires the connection id rather than
# an existing conversation id.
_discord_connection: dict[str, str | None] = {"id": None}


def _get_or_create_conversation(
    candidate_id: int, channel: str, external_conversation_id: str
) -> int:
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
    candidate = (
        db.find_candidate_by_email(sender_email, job_posting_id)
        if sender_email
        else None
    )
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

    conversation_id = _get_or_create_conversation(
        candidate_id, "email", message.conversation_id
    )
    storage.save_message(conversation_id, "inbound", message.text or "")

    answer, used_llm_fallback = faq.answer_question(config, message.text)
    message.reply(text=answer)
    storage.save_message(conversation_id, "outbound", answer, kind="faq_answer")

    conv_log.info("faq_answered", used_llm_fallback=used_llm_fallback)


def _open_discord_dm(
    client: CommClient, discord_user_id: str, text: str
) -> tuple[str, str | None]:
    """Best-effort: proactively DM a candidate on Discord via `initiate()`
    (needs Capability.INITIATE), the only SDK primitive that addresses a
    recipient directly rather than replying wherever a message came from.

    Never raises: a failed DM must not break whatever caller triggered it
    (an inbound message handler, or the dashboard's assign-screening call).

    This is purely a delivery nicety now -- it does NOT determine `is_dm`
    for anything (see module docstring and `_is_dm_message`). Whether this
    returns "confirmed", "unconfirmed", or "failed" has no bearing on how
    any inbound message gets classified; only a positive `chat_type == "dm"`
    from `client.list_messages()` does.

    Returns (status, external_conversation_id):
    - ("confirmed", id): `initiate()` succeeded and its response included a
      conversation id we recognize.
    - ("unconfirmed", None): `initiate()` succeeded, but its response didn't
      include a recognizable id -- the message plausibly reached the
      candidate, but we can't identify the resulting conversation from this
      response alone.
    - ("failed", None): no Discord connection configured, or `initiate()`
      itself raised.
    """
    connection_id = _discord_connection["id"]
    if not connection_id:
        log.warning("discord_dm_skipped", reason="no_discord_connection")
        return "failed", None

    # Diagnostic logging: capture the exact outbound request and the FULL
    # raw response/error -- not just whether we internally called it
    # confirmed/unconfirmed -- so a DM that never actually lands on Discord's
    # side (permissions, recipient privacy settings, etc.) is distinguishable
    # from a parsing/detection bug in this module.
    log.info(
        "discord_dm_initiate_request",
        connection_id=connection_id,
        recipient=discord_user_id,
        text=text,
    )
    try:
        result = client.initiate(connection_id, recipient=discord_user_id, text=text)
    except CommError as exc:
        log.warning(
            "discord_dm_initiate_error",
            connection_id=connection_id,
            recipient=discord_user_id,
            status_code=exc.status_code,
            detail=exc.detail,
        )
        return "failed", None
    except Exception:
        log.warning(
            "discord_dm_initiate_error",
            connection_id=connection_id,
            recipient=discord_user_id,
            status_code=None,
            detail=None,
            exc_info=True,
        )
        return "failed", None

    log.info(
        "discord_dm_initiate_response",
        connection_id=connection_id,
        recipient=discord_user_id,
        raw_response=result,
    )

    external_conversation_id = None
    if isinstance(result, dict):
        # Mirrors agent2.py's `_email_connection_id`, which relies on this
        # same "connection_id" key on `connect_email()`'s response for the
        # same reason: both channels go through the SDK's shared `_connect`/
        # `initiate` machinery, so the response shape should match. `id` is
        # kept as a fallback since `_connect()`'s own internal code (see the
        # installed SDK) addresses connections by an `id` key.
        external_conversation_id = result.get("conversation_id") or result.get("id")

    if not external_conversation_id:
        log.warning(
            "discord_dm_status_unconfirmed",
            detail="initiate() response had no recognizable conversation id",
            raw_response=result,
        )
        return "unconfirmed", None
    return "confirmed", external_conversation_id


def _lookup_chat_type(client: CommClient, conversation_id: str, message_id: str) -> str | None:
    """Fetch `message_id`'s `chat_type` straight from the gateway via
    `client.list_messages(conversation_id)` -- a real, documented SDK method
    (verified live against the actual gateway) that returns each message's
    raw `chat_type` field, which the `Message` wrapper handed to on_message
    handlers drops entirely (see module docstring).

    Returns None -- never raises -- on any failure: a lookup error, a
    response that isn't the expected list, or `message_id` simply not being
    in it. Callers treat None exactly like a non-"dm" chat_type (fail
    closed)."""
    try:
        raw_messages = client.list_messages(conversation_id)
    except CommError as exc:
        log.warning(
            "discord_chat_type_lookup_failed",
            conversation_id=conversation_id,
            message_id=message_id,
            status_code=exc.status_code,
            detail=exc.detail,
        )
        return None
    except Exception:
        log.warning(
            "discord_chat_type_lookup_failed",
            conversation_id=conversation_id,
            message_id=message_id,
            exc_info=True,
        )
        return None

    if not isinstance(raw_messages, list):
        log.warning(
            "discord_chat_type_lookup_unexpected_response",
            conversation_id=conversation_id,
            message_id=message_id,
            raw_response=raw_messages,
        )
        return None

    for raw_message in raw_messages:
        if isinstance(raw_message, dict) and raw_message.get("id") == message_id:
            return raw_message.get("chat_type")

    log.warning(
        "discord_chat_type_lookup_message_not_found",
        conversation_id=conversation_id,
        message_id=message_id,
    )
    return None


def _is_dm_message(client: CommClient, message: Message) -> bool:
    """Positively confirm THIS specific inbound message arrived on a private
    DM, straight from the gateway's own `chat_type` field (see
    `_lookup_chat_type`) -- never inferred from `client.initiate()` (that's
    now only a best-effort delivery nicety; see `_open_discord_dm`) and never
    cached or reused from an earlier message on the same conversation: every
    message gets its own fresh lookup. Fail CLOSED (see module docstring):
    any lookup failure or any chat_type other than exactly "dm" (including
    missing/None) is NOT a DM."""
    return _lookup_chat_type(client, message.conversation_id, message.id) == "dm"


def _get_or_create_discord_conversation(candidate_id: int, message: Message, is_dm: bool) -> int:
    """Find-or-create the conversation row for `message.conversation_id`,
    recording this message's freshly-looked-up `is_dm`. `is_dm` is a
    monotonic upgrade only: if a row already exists and was previously
    False, a later message confirmed as a DM flips it to True (a channel's
    DM-ness doesn't change, but earlier lookups can fail closed); an
    already-True row is never downgraded by one ambiguous message."""
    existing = db.find_conversation_by_external_id(message.conversation_id)
    if existing is not None:
        if is_dm and not existing["is_dm"]:
            db.set_conversation_is_dm(existing["id"], True)
        return existing["id"]
    return db.create_conversation(candidate_id, "discord", message.conversation_id, is_dm=is_dm)


def _resolve_discord_candidate(message: Message) -> tuple[int, int, bool] | None:
    """Returns (candidate_id, conversation_id, is_dm) if this Discord sender
    is already linked to a candidate, else None.

    `is_dm` tells the caller whether THIS inbound message is safe to use for
    screening content: True only if `_is_dm_message` positively confirms
    `chat_type == "dm"` for this exact message, straight from the gateway.
    Anything else -- a lookup failure, a message in a shared server channel,
    or any non-"dm" chat_type -- is never treated as safe, even though the
    candidate is fully resolved (fail-closed; see module docstring).
    """
    # caspian_sdk's Discord `sender` carries Caspian's own stable per-user
    # identifier under "address" (e.g. "powerful_flamingo_41530") -- there is
    # no "id" key on this payload.
    discord_user_id = (message.sender or {}).get("address")
    if not discord_user_id:
        return None
    candidate = db.find_candidate_by_discord_user_id(discord_user_id)
    if candidate is None:
        return None
    candidate_id = candidate["id"]

    is_dm = _is_dm_message(message._client, message)
    conversation_id = _get_or_create_discord_conversation(candidate_id, message, is_dm)
    return candidate_id, conversation_id, is_dm


def _try_link_discord_candidate(message: Message) -> int | None:
    """If this message's text is an unused Discord link code (shown on a
    candidate's apply confirmation screen), link the sending Discord identity
    to that candidate. Returns the candidate_id on a successful link, else
    None -- callers fall back to the generic unrecognized-sender reply."""
    # caspian_sdk's Discord `sender` carries Caspian's own stable per-user
    # identifier under "address" (e.g. "powerful_flamingo_41530") -- there is
    # no "id" key on this payload.
    discord_user_id = (message.sender or {}).get("address")
    if not discord_user_id or not message.text:
        return None
    code = message.text.strip().upper()
    candidate = db.find_candidate_by_discord_link_code(code)
    if candidate is None:
        return None
    db.link_candidate_discord(candidate["id"], discord_user_id)
    return candidate["id"]


def _handle_discord(message: Message) -> None:
    conv_log = log.bind(channel="discord")
    conv_log.info("message_received")

    resolved = _resolve_discord_candidate(message)
    if resolved is None:
        linked_candidate_id = _try_link_discord_candidate(message)
        if linked_candidate_id is not None:
            conv_log.info("discord_candidate_linked", candidate_id=linked_candidate_id)
            discord_user_id = (message.sender or {}).get("address")
            # Pivot to DMs the moment we learn who this is -- this is the
            # earliest point this code can act (see module docstring: there
            # is no join-time hook to act any earlier). Best-effort only --
            # does NOT determine is_dm (see _is_dm_message below).
            if discord_user_id:
                _open_discord_dm(message._client, discord_user_id, screening.LINKED_MESSAGE)

            is_dm = _is_dm_message(message._client, message)
            conversation_id = _get_or_create_discord_conversation(
                linked_candidate_id, message, is_dm
            )
            storage.save_message(conversation_id, "inbound", message.text or "")
            message.reply(text=screening.LINKED_MESSAGE)
            storage.save_message(
                conversation_id, "outbound", screening.LINKED_MESSAGE, kind="linked"
            )
            return
        # No candidate/conversation to attach this message to -- can't persist
        # it (conversations.candidate_id is a required FK), so we only log +
        # reply.
        conv_log.warning("discord_candidate_unresolved")
        message.reply(text=screening.UNRECOGNIZED_MESSAGE)
        return
    candidate_id, conversation_id, is_dm = resolved
    conv_log = conv_log.bind(candidate_id=candidate_id)

    storage.save_message(conversation_id, "inbound", message.text or "")

    stage = db.get_pipeline_stage(candidate_id)
    if stage != "screening_assigned":
        # Generic, non-candidate-specific content -- safe to send wherever
        # this message came from, DM or not.
        conv_log.info("discord_holding_reply", stage=stage)
        message.reply(text=screening.HOLDING_MESSAGE)
        storage.save_message(
            conversation_id, "outbound", screening.HOLDING_MESSAGE, kind="holding"
        )
        return

    if not is_dm:
        # Screening has been assigned, but this message didn't arrive on the
        # candidate's DM -- never leak the actual question/answer exchange
        # into whatever channel this is. This reply is generic/non-revealing
        # by construction, so it's fine to send wherever this came from.
        conv_log.info("discord_public_message_redirected")
        message.reply(text=screening.DM_REDIRECT_MESSAGE)
        storage.save_message(
            conversation_id, "outbound", screening.DM_REDIRECT_MESSAGE, kind="dm_redirect"
        )
        return

    candidate = db.get_candidate(candidate_id)
    config = load_job_agent_config(candidate["job_posting_id"]) if candidate else None
    questions = config.screening_questions if config else []

    question_index = db.count_messages_by_kind(
        conversation_id, screening.SCREENING_QUESTION_KIND
    )
    if question_index > 0:
        conv_log.info("screening_answer_received", question_index=question_index - 1)

    turn = screening.next_screening_turn(questions, question_index)
    message.reply(text=turn.reply_text)
    storage.save_message(conversation_id, "outbound", turn.reply_text, kind=turn.kind)

    if turn.kind == screening.SCREENING_QUESTION_KIND:
        conv_log.info("screening_question_asked", question_index=question_index)
    else:
        db.set_pipeline_stage(candidate_id, "screening_completed")
        conv_log.info("screening_sequence_complete")
        agent2.notify_screening_completed(message._client, candidate_id)


def start_discord_screening(client: CommClient, candidate_id: int) -> dict:
    """Proactively DM a candidate the first screening question over Discord,
    the moment HR assigns screening -- called from the dashboard's
    assign-screening action (services/backend/src/routes/dashboard.py) via
    this module's `start_discord_screening` MCP tool (src/server.py).

    Best-effort by design: returns a status dict rather than raising, since
    HR has already committed the pipeline stage change by the time this
    runs, and a missing Discord link or a channel hiccup must never surface
    as a dashboard error. If the candidate hasn't linked Discord yet, the
    invite simply goes out later, the moment they do (see
    `_try_link_discord_candidate`).
    """
    invite_log = log.bind(candidate_id=candidate_id)

    candidate = db.get_candidate(candidate_id)
    if candidate is None:
        return {"status": "candidate_not_found"}

    discord_user_id = db.get_candidate_discord_user_id(candidate_id)
    if not discord_user_id:
        invite_log.info("discord_screening_invite_skipped", reason="not_linked")
        return {"status": "not_linked"}

    config = load_job_agent_config(candidate["job_posting_id"])
    questions = config.screening_questions if config else []
    turn = screening.next_screening_turn(questions, 0)

    dm_conversation = db.find_discord_dm_conversation(candidate_id)
    if dm_conversation is not None:
        # Already have a confirmed DM on file (e.g. from linking earlier) --
        # send into it directly rather than opening a second one.
        try:
            client.send_message(dm_conversation["external_conversation_id"], text=turn.reply_text)
        except Exception:  # noqa: BLE001 -- best-effort by design, see docstring
            invite_log.warning("discord_screening_invite_failed", exc_info=True)
            return {"status": "dm_send_failed"}
        conversation_id = dm_conversation["id"]
    else:
        dm_status, external_conversation_id = _open_discord_dm(
            client, discord_user_id, turn.reply_text
        )
        if dm_status != "confirmed":
            # Fail closed (see module docstring): if we can't positively
            # confirm the DM, we don't record a conversation for it, and no
            # further automated screening content will go out until one
            # arrives on a conversation we've explicitly confirmed.
            invite_log.info("discord_screening_invite_not_confirmed", status=dm_status)
            return {
                "status": "dm_send_failed" if dm_status == "failed" else "dm_status_unconfirmed"
            }
        conversation_id = db.create_conversation(
            candidate_id, "discord", external_conversation_id, is_dm=True
        )

    storage.save_message(conversation_id, "outbound", turn.reply_text, kind=turn.kind)
    invite_log.info("discord_screening_invite_sent")
    return {"status": "sent"}


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
    status.set_channel("email", "connecting")
    try:
        client.connect_email()
    except Exception:
        log.warning("email_connect_failed", exc_info=True)
        status.set_channel("email", "disconnected")
    else:
        status.set_channel("email", "connected")

    discord_bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if discord_bot_token:
        status.set_channel("discord", "connecting")
        try:
            connection = client.connect_discord(bot_token=discord_bot_token)
        except Exception:
            log.warning("discord_connect_failed", exc_info=True)
            status.set_channel("discord", "disconnected")
        else:
            status.set_channel("discord", "connected")
            # The connection resource returned by `_connect()` (verified
            # directly against the live gateway) keys the connection's own
            # id as `"id"`, not `"connection_id"` -- e.g.
            # {"id": "conn_...", "channel": "discord", "status": "active", ...}.
            # There is no `"connection_id"` key on this response at all.
            _discord_connection["id"] = connection.get("id")
    else:
        log.warning("discord_not_configured", detail="DISCORD_BOT_TOKEN is not set")
        status.set_channel("discord", "disconnected")

    client.on_message(handle_message)
