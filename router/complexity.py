"""Rule-based complexity evaluation."""

from __future__ import annotations

HIGH_KEYWORDS = frozenset({
    "analyze", "generate", "report", "recommend", "files", "directory",
    "create", "summarize", "all", "each", "code quality",
})

MEDIUM_KEYWORDS = frozenset({
    "help", "explain", "analyze", "summarize", "document", "key points",
    "compare", "review",
})


def evaluate_complexity(user_input: str) -> str:
    """Evaluate request complexity based on word count and keywords.

    Returns 'low', 'medium', or 'high'.
    """
    text = user_input.lower()
    words = text.split()
    word_count = len(words)

    high_hits = sum(1 for kw in HIGH_KEYWORDS if kw in text)
    medium_hits = sum(1 for kw in MEDIUM_KEYWORDS if kw in text)

    if word_count > 25 or high_hits >= 3:
        return "high"
    if word_count > 10 or medium_hits >= 2 or high_hits >= 1:
        return "medium"
    return "low"
