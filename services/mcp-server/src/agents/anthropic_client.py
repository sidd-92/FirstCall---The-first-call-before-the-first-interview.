"""Thin wrapper around the Anthropic API for the FAQ fallback answer.

Kept as a single narrow function so tests can monkeypatch it instead of
hitting the real API.
"""

import os
from functools import lru_cache

from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 300


@lru_cache(maxsize=1)
def _client() -> Anthropic:
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def ask_faq_fallback(job_description: str, faq_text: str, question: str) -> str:
    """Answer a candidate's question that isn't covered by the fixed FAQ,
    grounded only in this job's description + FAQ doc -- not general knowledge."""
    system_prompt = (
        "You are answering a job applicant's question about a single open role. "
        "Only use the role information below; if the answer truly isn't in it, "
        "say you don't have that information and suggest they ask the hiring team "
        "directly. Keep the answer short (a few sentences).\n\n"
        f"Role description:\n{job_description}\n\n"
        f"FAQ:\n{faq_text}"
    )
    response = _client().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": question}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
