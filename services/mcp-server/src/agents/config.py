"""Per-job-posting agent config: FAQ entries + the fixed screening question
sequence, both sourced from `JobPosting.faq_json`.

`faq_json` doesn't have a formal schema elsewhere yet, so this module defines
the contract Agent 1 expects:

    {
      "faq": [{"question": "...", "answer": "..."}, ...],
      "screening_questions": ["...", "...", ...]
    }

A job posting missing either key just gets treated as having none of that
content (empty list) rather than erroring -- postings created before this
contract existed shouldn't crash the agent.
"""

import json
from dataclasses import dataclass, field

from src.db import get_job_posting


@dataclass
class FaqEntry:
    question: str
    answer: str


@dataclass
class JobAgentConfig:
    job_posting_id: int
    business_id: int
    title: str
    description: str
    faq: list[FaqEntry] = field(default_factory=list)
    screening_questions: list[str] = field(default_factory=list)


def load_job_agent_config(job_posting_id: int) -> JobAgentConfig | None:
    """Load a job posting's agent config, or None if the posting doesn't exist."""
    posting = get_job_posting(job_posting_id)
    if posting is None:
        return None

    try:
        parsed = json.loads(posting["faq_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        parsed = {}

    faq = [
        FaqEntry(question=entry["question"], answer=entry["answer"])
        for entry in parsed.get("faq", [])
    ]
    screening_questions = list(parsed.get("screening_questions", []))

    return JobAgentConfig(
        job_posting_id=posting["id"],
        business_id=posting["business_id"],
        title=posting["title"],
        description=posting["description"],
        faq=faq,
        screening_questions=screening_questions,
    )
