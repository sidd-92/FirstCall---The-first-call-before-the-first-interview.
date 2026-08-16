"""Thin wrapper around the Gemini API for the FAQ fallback answer.

Kept as a single narrow function so tests can monkeypatch it instead of
hitting the real API.
"""

import os
from functools import lru_cache

from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"
MAX_OUTPUT_TOKENS = 300


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


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
    response = _client().models.generate_content(
        model=MODEL,
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return response.text
