"""One-shot Claude Haiku call for the HR-triggered "Review with AI" action
(routes/dashboard.py). Never called automatically -- only from that route.
"""

import json
import os
from functools import lru_cache

from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 200

_SYSTEM_PROMPT = (
    "You are helping a hiring manager review a completed screening conversation "
    "with a job candidate. Read the transcript and respond with ONLY a JSON "
    'object of the exact form {"score": <integer 1-10>, "summary": "<2-3 '
    'sentence summary>"} -- score is how promising the candidate seems for '
    "this role based solely on their answers. No text outside the JSON."
)


@lru_cache(maxsize=1)
def _client() -> Anthropic:
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def review_transcript(transcript: str) -> tuple[int | None, str]:
    """Return (score, summary). If the model's response isn't parseable JSON,
    score is None and summary falls back to the raw response text."""
    response = _client().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": transcript}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")

    try:
        parsed = json.loads(text)
        return int(parsed["score"]), str(parsed["summary"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None, text
