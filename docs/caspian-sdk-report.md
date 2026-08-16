# Caspian SDK Integration Report — FirstCall

**Submission:** FirstCall — The first call, before the first interview
**Event:** Caspian AI Agent Hackathon
**SDK version:** `caspian-sdk` 0.6.1 (locked in `services/mcp-server/uv.lock`)

This report documents, with direct file/line citations, how FirstCall integrates the Caspian SDK: what we call, how we wrapped it, and the specific gaps in the 0.6.1 SDK we had to work around.

---

## 1. Where the SDK sits in the architecture

FirstCall never calls `caspian-sdk` from application code directly. Every call is routed through one of two layers, both living in `services/mcp-server`:

```
Agent code (agent1.py, agent2.py)
        │
        ▼
CommClient (caspian_sdk) ──── wrapped by ────▶ CaspianClient (caspian_client.py)
        │                                              │
        ▼                                              ▼
  api.trycaspianai.com                    exposed as MCP tools (server.py)
  (hosted gateway)                        for any MCP-capable agent to call
```

This wasn't incidental — centralizing all SDK access meant encrypted storage, access control, and channel logic stayed in one place instead of being scattered across every route that needed to send a message.

---

## 2. The `CaspianClient` wrapper (`services/mcp-server/src/caspian_client.py`)

A thin wrapper around `CommClient`, built to solve one specific mismatch: **`CommClient.listen()` blocks forever** and fires `on_message` synchronously per inbound message — but MCP tools are request/response, not long-running.

`start_listener()` solves this by:
1. Registering `self._client.on_message(self._inbox.put)` — every inbound `Message` gets pushed onto an in-memory `queue.Queue`
2. Running `self._client.listen()` on a background daemon thread (`caspian-listener`)

The `get_new_messages` MCP tool later drains that queue non-blockingly via `queue.get_nowait()`. This is a separate, generic `on_message` registration from the one Agent 1 actually uses for real handling — Agent 1 installs its own handler directly on the same underlying `CommClient` via the wrapper's `raw_client` property, bypassing the queue path entirely for the live email/Discord flow.

Other methods wrapped 1:1 onto `CommClient`:
- `list_channels()` → `client.channels()`
- `connect_channel(channel, **kwargs)` → `client.connect_email(**kwargs)` / `client.connect_discord(**kwargs)`
- `send_message`, `reply`, `initiate` → direct pass-throughs

**Gateway choice is encoded in code, not just documentation.** `caspian_client.py` never sets `CASPIAN_BASE_URL`, with an explicit comment that self-hosting the gateway was out of scope — so every request in this project goes to Caspian's hosted gateway, `api.trycaspianai.com`.

---

## 3. The MCP server layer (`services/mcp-server/src/server.py`)

Rather than exposing SDK calls as internal functions only, we wrapped them as MCP tools — usable by any MCP-capable agent, not just the two built for this hackathon. This is itself listed on Caspian's own roadmap as planned-but-unshipped, so building it here was a genuine addition on top of the SDK rather than a wrapper for its own sake.

| Tool | Purpose |
|---|---|
| `list_channels()` | Lists channels/connections currently configured |
| `connect_channel(channel, bot_token=None, username=None, domain=None)` | Connects "email" or "discord" |
| `send_message(conversation_id, text)` | New outbound message on an existing conversation |
| `reply(message_id, text)` | Reply to a specific inbound message |
| `initiate(connection_id, recipient, text)` | Cold-starts a conversation (needs `Capability.INITIATE`) |
| `start_discord_screening(candidate_id)` | Proactively DMs a candidate's first screening question |
| `get_new_messages(max_messages=50)` | Drains the background listener's buffered inbox |
| `get_conversation(conversation_id)` | Reads conversation history — from FirstCall's **own** encrypted storage, not the Caspian gateway |

That last distinction matters: `get_conversation` deliberately never calls a gateway read method. "Conversation" history for the hiring workflow is our own encrypted-at-rest record, keyed by our local conversation id — the gateway's own message list is not treated as the source of truth.

---

## 4. Agent 1 — the two-channel handler (`services/mcp-server/src/agents/agent1.py`)

This is the piece that satisfies the hackathon's core requirement: **at least two channels, through one handler.**

`register(client)` connects both channels at startup:
```python
client.connect_email()
if discord_bot_token:
    client.connect_discord(bot_token=discord_bot_token)
client.on_message(handle_message)
```

`handle_message(message)` branches purely on `message.channel` ("email" vs "discord") and dispatches to `_handle_email` / `_handle_discord` — one registration, two channels, exactly as the hackathon rules require.

SDK `Message` object usage in this handler: `.channel`, `.text`, `.subject`, `.sender` (an untyped `dict | None`), `.conversation_id`, `.id`, and `.reply(text=...)`.

---

## 5. Real gaps found in caspian-sdk 0.6.1 — and how we worked around them

These weren't assumptions — each was verified directly against the installed SDK source and, in one case, the live gateway's own OpenAPI schema, before being worked around.

### 5.1 No way to set an email Subject header

`initiate()`, `reply()`, and `send_message()` all take only `connection_id`/`recipient`/`text` — no `subject` parameter exists anywhere in the SDK for these three calls (only the unrelated `test_email()` test helper accepts one). This is a real constraint on a hiring flow: candidates need to be traceable back to the job they applied for, across an email thread a mail client will reformat, requote, and mangle.

**Workaround:** we embed a `[JOB-{id}]` tag directly in the message **body**, not a header, since it's the only place guaranteed to survive into a reply's quoted history.

### 5.2 `Message` has no field distinguishing a DM from a public channel message

This one had real privacy consequences. Checked directly against the installed 0.6.1 package: `Message` carries no `is_dm`, `guild_id`, `channel_type`, or equivalent field. `sender` is an untyped `dict | None` populated straight from the gateway payload. Discord screening answers (salary expectations, work history) are candidate-specific and must never leak into a shared guild channel — and `Message.reply()` always replies into whatever channel the message arrived on, DM or not.

**Workaround:** for every inbound Discord message, we call the SDK's `client.list_messages(conversation_id)` — a real, separate gateway call — and read that specific message's raw `chat_type` field directly from the response (the `Message` wrapper itself drops this field). Only an exact `chat_type == "dm"` sets `is_dm = True`; any failure mode — the lookup raising, the message not appearing in the response, or any value other than exactly `"dm"` — is treated as **not** a DM. This is fail-closed by design: a lookup that comes back ambiguous must never be treated as "probably fine," since that would reopen the exact leak this logic exists to close. `is_dm` is stored per-conversation and only ever upgraded, never downgraded.

### 5.3 No "member joined" event hook

The installed SDK dispatches exactly three event types — `message.received`, `interaction.received`, `reaction.received` — and has no join-time hook of any kind. This means a candidate's very first-ever contact (typing their Discord link code somewhere) can't be pre-empted with a proactive DM; the earliest the agent can act is the moment that first message arrives, at which point it immediately pivots to DMs for everything else. This is a known, accepted gap — closing it for real would need a Discord-native integration (e.g. `discord.py`'s `on_member_join`) alongside caspian-sdk, which was out of scope for the hackathon window.

### 5.4 Inconsistent key naming on connection resources

The connection object returned by the SDK's connect calls keys its id as `"id"`, not `"connection_id"` — despite `"connection_id"` being the parameter name other calls expect. Using the wrong key here previously caused a `KeyError` on every notification call, silently swallowed by a broad exception handler until it was traced back to this specific mismatch.

---

## 6. What we deliberately didn't use

- **`client.events()`** — not called anywhere in the mcp-server codebase. The `listen()` + background-thread pattern was sufficient; we never needed to poll the raw event stream directly for application logic (only used ad hoc for debugging via a one-off script during development).
- **Self-hosted gateway** — the SDK ships an AGPL-3.0 self-hostable version of its own FastAPI gateway. We used the hosted gateway instead: zero setup time, no infrastructure to run for the demo window, and a free dashboard (bots live, conversations, messages, cost) that doubled as independent proof-of-liveness for the required demo video.

---

## 7. Summary

Two agents, one shared `CommClient` instance, one `on_message` handler spanning Email and Discord, wrapped as MCP tools so the same messaging capability is available to any MCP-capable agent going forward — not just the two built here. Every workaround above came from reading the actual installed SDK source rather than assuming behavior, which is why each is cited to a specific gap rather than a general "the SDK is limited" claim.
