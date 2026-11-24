"""Flesch-Kincaid grade for the human review brief.

The grade is the U.S. school-grade estimate

    0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59

Customer quotes and drafted message text are evidence. They are kept
word for word and are removed before the grade is computed. The limit
applies only to the sentences the agent writes around those quotes.

Grade 8 is the limit. Plain-language guides for public notices commonly
use grade 8 so a reader does not need college prose. A collections
reviewer in the office is that reader. The limit is a maximum: a lower
grade is easier.
"""

import re


# Maximum Flesch-Kincaid grade for agent-written review text.
REVIEWER_GRADE_LIMIT = 8.0

_SENTENCE_BREAK = re.compile(r"[.!?]+")
_WORD = re.compile(r"[A-Za-z0-9']+")
_QUOTED = re.compile(r'"[^"]*"')


def count_syllables(word: str) -> int:
    """Count syllables with a small vowel-group estimate."""

    cleaned = re.sub(r"[^a-z]", "", word.lower())
    if len(cleaned) <= 3:
        return 1

    if cleaned.endswith("e") and not cleaned.endswith("le"):
        cleaned = cleaned[:-1]

    groups = re.findall(r"[aeiouy]+", cleaned)
    return max(1, len(groups))


def agent_authored_text(text: str) -> str:
    """Drop verbatim quotes so the grade scores the agent's own sentences."""

    return _QUOTED.sub(" ", text or "")


def flesch_kincaid_grade(text: str) -> float:
    """Return the grade level. Empty text is treated as too hard to score."""

    prose = agent_authored_text(text).strip()
    sentences = [part for part in _SENTENCE_BREAK.split(prose) if part.strip()]
    words = _WORD.findall(prose)

    if not sentences or not words:
        return 99.0

    syllables = sum(count_syllables(word) for word in words)
    grade = (
        0.39 * (len(words) / len(sentences))
        + 11.8 * (syllables / len(words))
        - 15.59
    )
    return round(grade, 2)
