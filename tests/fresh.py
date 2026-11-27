"""Timestamps that stay inside the configured risk-score window."""

from datetime import datetime, timezone


def fresh_scored_at() -> str:
    """
    FR-3.4 treats a risk score older than policy risk.score_staleness_days
    as missing and substitutes the highest band. Fixtures must be scored
    at runtime or those tests silently change meaning as the calendar moves.
    """

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
