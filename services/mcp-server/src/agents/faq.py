"""FAQ answering for inbound email: match against the job's fixed FAQ first,
falling back to Claude Haiku only when nothing matches closely enough.

The match is a simple keyword-overlap heuristic, not embeddings/NLP -- good
enough to catch "what's the pay range?" hitting a "Salary range?" FAQ entry
without a model call. TODO: revisit if FAQ entries grow numerous enough that
this starts missing real matches.
"""

import re

from src.agents.anthropic_client import ask_faq_fallback
from src.agents.config import JobAgentConfig

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "what", "when", "where",
    "how", "do", "does", "did", "i", "you", "your", "my", "of", "for", "to",
    "in", "on", "and", "or", "it", "this", "that", "will", "can", "please",
    "about",
}
_MATCH_THRESHOLD = 0.3


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def render_faq_section(config: JobAgentConfig) -> str:
    """Render the full fixed FAQ as plain text (e.g. for a first-contact reply)."""
    if not config.faq:
        return "We don't have any FAQ entries for this role yet -- feel free to ask us anything."
    lines = [f"Q: {entry.question}\nA: {entry.answer}" for entry in config.faq]
    return "\n\n".join(lines)


def _best_match(config: JobAgentConfig, question: str) -> str | None:
    question_tokens = _tokens(question)
    if not question_tokens:
        return None

    best_score = 0.0
    best_answer: str | None = None
    for entry in config.faq:
        entry_tokens = _tokens(entry.question)
        if not entry_tokens:
            continue
        overlap = len(question_tokens & entry_tokens)
        score = overlap / len(entry_tokens)
        if score > best_score:
            best_score = score
            best_answer = entry.answer

    return best_answer if best_score >= _MATCH_THRESHOLD else None


def answer_question(config: JobAgentConfig, question: str | None) -> tuple[str, bool]:
    """Answer a candidate's email. Returns (answer_text, used_llm_fallback).

    With no question text (e.g. a bare first-contact email), sends the full
    FAQ. Otherwise tries the fixed FAQ match first and only calls Claude
    Haiku if nothing matches closely enough.
    """
    if not question or not question.strip():
        return render_faq_section(config), False

    matched = _best_match(config, question)
    if matched is not None:
        return matched, False

    faq_text = render_faq_section(config)
    answer = ask_faq_fallback(config.description, faq_text, question)
    return answer, True
