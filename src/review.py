"""Minimal human-review queue for escalated ACA decisions."""

from datetime import datetime, timezone

from src.database import get_connection


class HumanReviewError(ValueError):
    """A disposition could not be recorded."""


DISPOSITIONS = (
    "APPROVE",
    "REJECT",
    "MODIFY",
    "RESOLVED",
)

_QUEUE_COLUMNS = """
    escalation_id,
    decision_id,
    account_id,
    invoice_id,
    reply_text,
    intent,
    confidence,
    proposed_action,
    rejection_reason,
    risk_score,
    risk_band,
    human_disposition,
    disposition_code,
    reviewer_note,
    reviewed_by,
    status,
    created_at,
    resolved_at,
    packet_json
"""


def _row_to_case(row) -> dict:
    case = dict(row)
    packet_json = case.pop("packet_json", None)

    if packet_json:
        import json

        try:
            case["packet"] = json.loads(packet_json)
        except json.JSONDecodeError:
            case["packet"] = None
    else:
        case["packet"] = None

    return case


def list_review_queue(status: str = "OPEN") -> list[dict]:
    """Return escalations waiting for, or already given, a disposition."""

    conn = get_connection()

    rows = conn.execute(
        f"""
        SELECT {_QUEUE_COLUMNS}
        FROM escalations
        WHERE UPPER(status) = ?
        ORDER BY created_at ASC, escalation_id ASC
        """,
        (status.strip().upper(),),
    ).fetchall()

    conn.close()

    return [_row_to_case(row) for row in rows]


def get_review_case(escalation_id: int) -> dict:
    conn = get_connection()

    row = conn.execute(
        f"""
        SELECT {_QUEUE_COLUMNS}
        FROM escalations
        WHERE escalation_id = ?
        """,
        (escalation_id,),
    ).fetchone()

    conn.close()

    if row is None:
        raise HumanReviewError(
            f"Escalation {escalation_id} does not exist."
        )

    return _row_to_case(row)


def record_human_disposition(
    escalation_id: int,
    disposition: str,
    reviewer_note: str = "",
    reviewed_by: str = "human_reviewer",
) -> dict:
    """
    Record one disposition on an open escalation.

    A second disposition is refused. The stored text is what
    later agent decisions retrieve through get_prior_escalations.
    """

    code = str(disposition).strip().upper()

    if code not in DISPOSITIONS:
        raise HumanReviewError(
            "Disposition must be one of "
            + ", ".join(DISPOSITIONS)
            + "."
        )

    note = (reviewer_note or "").strip()
    human_text = f"{code}: {note}" if note else code
    resolved_at = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    conn = get_connection()

    try:
        existing = conn.execute(
            """
            SELECT status, decision_id
            FROM escalations
            WHERE escalation_id = ?
            """,
            (escalation_id,),
        ).fetchone()

        if existing is None:
            raise HumanReviewError(
                f"Escalation {escalation_id} does not exist."
            )

        if str(existing["status"]).upper() != "OPEN":
            raise HumanReviewError(
                f"Escalation {escalation_id} already has a disposition."
            )

        cursor = conn.execute(
            """
            UPDATE escalations
            SET
                disposition_code = ?,
                human_disposition = ?,
                reviewer_note = ?,
                reviewed_by = ?,
                status = 'RESOLVED',
                resolved_at = ?
            WHERE escalation_id = ?
              AND UPPER(status) = 'OPEN'
            """,
            (
                code,
                human_text,
                note or None,
                reviewed_by,
                resolved_at,
                escalation_id,
            ),
        )

        if cursor.rowcount != 1:
            conn.rollback()
            raise HumanReviewError(
                f"Escalation {escalation_id} could not be updated."
            )

        conn.execute(
            """
            INSERT INTO audit_notes (
                decision_id,
                escalation_id,
                event_type,
                detail,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                existing["decision_id"],
                escalation_id,
                "HUMAN_DISPOSITION",
                human_text,
                resolved_at,
            ),
        )

        conn.commit()

    finally:
        conn.close()

    return get_review_case(escalation_id)
