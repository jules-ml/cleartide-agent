import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.database import get_connection


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _row_to_dict(row) -> Optional[dict]:
    """
    Convert a sqlite3.Row into a standard dictionary.
    """

    return dict(row) if row is not None else None


def _rows_to_dicts(rows) -> list[dict]:
    """
    Convert multiple sqlite3.Row objects into dictionaries.
    """

    return [dict(row) for row in rows]


def _safe_json_load(value: Optional[str]) -> Any:
    """
    Decode stored JSON when possible.

    If an older fixture contains plain text instead of JSON,
    return the original value rather than failing the tool.
    """

    if value is None:
        return None

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _record_tool_call(
    tool_name: str,
    arguments: dict,
    result: dict,
    status: str,
    decision_id: Optional[int] = None,
) -> str:
    """
    FR-2.8

    Record every tool invocation and its result.

    Returns a stable human-readable tool-call identifier such as:
        TC-000001
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO tool_calls (
            decision_id,
            tool_name,
            arguments_json,
            result_json,
            status
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            tool_name,
            json.dumps(arguments, default=str),
            json.dumps(result, default=str),
            status,
        ),
    )

    tool_call_number = cursor.lastrowid

    conn.commit()
    conn.close()

    return f"TC-{tool_call_number:06d}"


def _tool_response(
    tool_name: str,
    arguments: dict,
    data: dict,
    status: str = "SUCCESS",
    decision_id: Optional[int] = None,
) -> dict:
    """
    Standardize every Cleartide tool response.

    Every tool returns:
        tool_call_id
        tool_name
        status
        data
    """

    tool_call_id = _record_tool_call(
        tool_name=tool_name,
        arguments=arguments,
        result=data,
        status=status,
        decision_id=decision_id,
    )

    return {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "status": status,
        "data": data,
    }


def record_blocked_tool_call(
    tool_name: str,
    arguments: dict,
    reason: str,
    decision_id: int,
) -> dict:
    """
    Record a tool invocation attempt that was blocked by
    deterministic loop / usage guards.

    The tool itself is NOT executed.
    """

    return _tool_response(
        tool_name=tool_name,
        arguments=arguments,
        data={
            "blocked": True,
            "reason": reason,
        },
        status="BLOCKED_BY_GUARD",
        decision_id=decision_id,
    )


def record_tool_error(
    tool_name: str,
    arguments: dict,
    error_message: str,
    decision_id: int,
) -> dict:
    """
    Record an unexpected exception produced while attempting
    a tool call.
    """

    return _tool_response(
        tool_name=tool_name,
        arguments=arguments,
        data={
            "error": True,
            "error_message": error_message,
        },
        status="ERROR",
        decision_id=decision_id,
    )


# ============================================================
# TOOL 1
# VERIFY INVOICE DELIVERY
# ============================================================

def verify_invoice_delivery(
    invoice_id: int,
    decision_id: Optional[int] = None,
) -> dict:
    """
    FR-2.2

    Verify the most recent delivery event for an invoice.

    DELIVERY_DISPUTE must use this tool before action.
    """

    conn = get_connection()

    invoice = conn.execute(
        """
        SELECT
            invoice_id,
            account_id,
            amount,
            issue_date,
            due_date,
            status
        FROM invoices
        WHERE invoice_id = ?
        """,
        (invoice_id,),
    ).fetchone()

    if invoice is None:
        conn.close()

        return _tool_response(
            tool_name="verify_invoice_delivery",
            arguments={"invoice_id": invoice_id},
            data={
                "invoice_found": False,
                "delivery_verified": False,
                "reason": "Invoice does not exist.",
            },
            status="NOT_FOUND",
            decision_id=decision_id,
        )

    delivery = conn.execute(
        """
        SELECT
            delivery_id,
            channel,
            delivery_status,
            delivered_at,
            failure_reason,
            created_at
        FROM delivery_log
        WHERE invoice_id = ?
        ORDER BY created_at DESC, delivery_id DESC
        LIMIT 1
        """,
        (invoice_id,),
    ).fetchone()

    conn.close()

    if delivery is None:
        return _tool_response(
            tool_name="verify_invoice_delivery",
            arguments={"invoice_id": invoice_id},
            data={
                "invoice_found": True,
                "delivery_verified": False,
                "invoice": dict(invoice),
                "reason": "No delivery-log record exists.",
            },
            status="NO_RESULT",
            decision_id=decision_id,
        )

    delivery_data = dict(delivery)

    successful_statuses = {
        "DELIVERED",
        "SENT",
        "RESENT_SIMULATED",
    }

    was_delivered = (
        str(delivery_data["delivery_status"]).upper()
        in successful_statuses
    )

    return _tool_response(
        tool_name="verify_invoice_delivery",
        arguments={"invoice_id": invoice_id},
        data={
            "invoice_found": True,
            "delivery_verified": True,
            "was_delivered": was_delivered,
            "invoice": dict(invoice),
            "latest_delivery_event": delivery_data,
        },
        decision_id=decision_id,
    )


# ============================================================
# TOOL 2
# RECONCILE PAYMENT CLAIM
# ============================================================

def reconcile_payment_claim(
    invoice_id: int,
    decision_id: Optional[int] = None,
) -> dict:
    """
    FR-2.3

    Reconcile an ALREADY_PAID_CLAIM against the simulated ledger.
    """

    conn = get_connection()

    invoice = conn.execute(
        """
        SELECT
            invoice_id,
            account_id,
            amount,
            status
        FROM invoices
        WHERE invoice_id = ?
        """,
        (invoice_id,),
    ).fetchone()

    if invoice is None:
        conn.close()

        return _tool_response(
            tool_name="reconcile_payment_claim",
            arguments={"invoice_id": invoice_id},
            data={
                "invoice_found": False,
                "payment_claim_verified": False,
                "reason": "Invoice does not exist.",
            },
            status="NOT_FOUND",
            decision_id=decision_id,
        )

    payment_rows = conn.execute(
        """
        SELECT
            payment_id,
            amount,
            payment_date,
            status,
            payment_method
        FROM payments
        WHERE invoice_id = ?
        ORDER BY payment_date DESC, payment_id DESC
        """,
        (invoice_id,),
    ).fetchall()

    conn.close()

    payments = _rows_to_dicts(payment_rows)

    posted_payments = [
        payment
        for payment in payments
        if str(payment["status"]).lower() == "posted"
    ]

    posted_total = sum(
        float(payment["amount"])
        for payment in posted_payments
    )

    invoice_amount = float(invoice["amount"])

    fully_paid = posted_total >= invoice_amount

    return _tool_response(
        tool_name="reconcile_payment_claim",
        arguments={"invoice_id": invoice_id},
        data={
            "invoice_found": True,
            "invoice_amount": invoice_amount,
            "posted_payment_total": posted_total,
            "fully_paid": fully_paid,
            "payment_claim_verified": fully_paid,
            "payments": payments,
        },
        decision_id=decision_id,
    )


# ============================================================
# TOOL 3
# GET PAYMENT HISTORY
# ============================================================

def get_payment_history(
    account_id: int,
    decision_id: Optional[int] = None,
) -> dict:
    """
    FR-2.4

    Retrieve exact relational payment history for an account.
    """

    conn = get_connection()

    account = conn.execute(
        """
        SELECT account_id, customer_name
        FROM accounts
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()

    if account is None:
        conn.close()

        return _tool_response(
            tool_name="get_payment_history",
            arguments={"account_id": account_id},
            data={
                "account_found": False,
                "payments": [],
            },
            status="NOT_FOUND",
            decision_id=decision_id,
        )

    rows = conn.execute(
        """
        SELECT
            payment_id,
            invoice_id,
            amount,
            payment_date,
            status,
            payment_method
        FROM payments
        WHERE account_id = ?
        ORDER BY payment_date DESC, payment_id DESC
        """,
        (account_id,),
    ).fetchall()

    conn.close()

    payments = _rows_to_dicts(rows)

    posted_total = sum(
        float(payment["amount"])
        for payment in payments
        if str(payment["status"]).lower() == "posted"
    )

    return _tool_response(
        tool_name="get_payment_history",
        arguments={"account_id": account_id},
        data={
            "account_found": True,
            "customer_name": account["customer_name"],
            "payment_count": len(payments),
            "posted_total": posted_total,
            "payments": payments,
        },
        decision_id=decision_id,
    )


# ============================================================
# TOOL 4
# GET RISK SCORE
# ============================================================

def get_risk_score(
    account_id: int,
    invoice_id: Optional[int] = None,
    decision_id: Optional[int] = None,
) -> dict:
    """
    FR-3.1 / FR-3.2 / FR-3.5

    Retrieve a previously computed risk-model result.

    IMPORTANT:
    This function does not ask an LLM to estimate risk.
    """

    conn = get_connection()

    if invoice_id is not None:
        row = conn.execute(
            """
            SELECT
                risk_score_id,
                account_id,
                invoice_id,
                score,
                risk_band,
                model_version,
                contributing_factors,
                scored_at
            FROM risk_scores
            WHERE account_id = ?
              AND invoice_id = ?
            ORDER BY scored_at DESC, risk_score_id DESC
            LIMIT 1
            """,
            (account_id, invoice_id),
        ).fetchone()

    else:
        row = conn.execute(
            """
            SELECT
                risk_score_id,
                account_id,
                invoice_id,
                score,
                risk_band,
                model_version,
                contributing_factors,
                scored_at
            FROM risk_scores
            WHERE account_id = ?
            ORDER BY scored_at DESC, risk_score_id DESC
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()

    conn.close()

    if row is None:
        return _tool_response(
            tool_name="get_risk_score",
            arguments={
                "account_id": account_id,
                "invoice_id": invoice_id,
            },
            data={
                "risk_score_available": False,
            },
            status="NO_RESULT",
            decision_id=decision_id,
        )

    result = dict(row)

    result["contributing_factors"] = _safe_json_load(
        result["contributing_factors"]
    )

    result["risk_score_available"] = True

    return _tool_response(
        tool_name="get_risk_score",
        arguments={
            "account_id": account_id,
            "invoice_id": invoice_id,
        },
        data=result,
        decision_id=decision_id,
    )


# ============================================================
# TOOL 5
# GET ACCOUNT HISTORY
# ============================================================

def get_account_history(
    account_id: int,
    decision_id: Optional[int] = None,
) -> dict:
    """
    Retrieve the exact structured history for an account.

    FR-7.5:
    use relational records instead of approximate retrieval
    when an exact query is available.
    """

    conn = get_connection()

    account = conn.execute(
        """
        SELECT *
        FROM accounts
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()

    if account is None:
        conn.close()

        return _tool_response(
            tool_name="get_account_history",
            arguments={"account_id": account_id},
            data={"account_found": False},
            status="NOT_FOUND",
            decision_id=decision_id,
        )

    invoices = conn.execute(
        """
        SELECT *
        FROM invoices
        WHERE account_id = ?
        ORDER BY due_date DESC
        """,
        (account_id,),
    ).fetchall()

    communications = conn.execute(
        """
        SELECT *
        FROM communications
        WHERE account_id = ?
        ORDER BY created_at DESC
        LIMIT 25
        """,
        (account_id,),
    ).fetchall()

    conn.close()

    return _tool_response(
        tool_name="get_account_history",
        arguments={"account_id": account_id},
        data={
            "account_found": True,
            "account": dict(account),
            "invoices": _rows_to_dicts(invoices),
            "recent_communications": _rows_to_dicts(
                communications
            ),
        },
        decision_id=decision_id,
    )


# ============================================================
# TOOL 6
# GET PRIOR DISPUTES
# ============================================================

def get_prior_disputes(
    account_id: int,
    decision_id: Optional[int] = None,
) -> dict:
    """
    FR-7.2

    Retrieve prior disputes and their resolutions.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM disputes
        WHERE account_id = ?
        ORDER BY created_at DESC, dispute_id DESC
        """,
        (account_id,),
    ).fetchall()

    conn.close()

    disputes = _rows_to_dicts(rows)

    return _tool_response(
        tool_name="get_prior_disputes",
        arguments={"account_id": account_id},
        data={
            "count": len(disputes),
            "disputes": disputes,
        },
        decision_id=decision_id,
    )


# ============================================================
# TOOL 7
# GET PRIOR PROMISES
# ============================================================

def get_prior_promises(
    account_id: int,
    decision_id: Optional[int] = None,
) -> dict:
    """
    FR-7.1

    Retrieve prior promises to pay and their statuses.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM promises_to_pay
        WHERE account_id = ?
        ORDER BY created_at DESC, promise_id DESC
        """,
        (account_id,),
    ).fetchall()

    conn.close()

    promises = _rows_to_dicts(rows)

    return _tool_response(
        tool_name="get_prior_promises",
        arguments={"account_id": account_id},
        data={
            "count": len(promises),
            "promises": promises,
        },
        decision_id=decision_id,
    )


# ============================================================
# TOOL 8
# GET PRIOR ESCALATIONS
# ============================================================

def get_prior_escalations(
    account_id: int,
    decision_id: Optional[int] = None,
) -> dict:
    """
    FR-7.3

    Retrieve prior escalations and their human dispositions.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
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
            status,
            created_at,
            resolved_at
        FROM escalations
        WHERE account_id = ?
        ORDER BY created_at DESC, escalation_id DESC
        """,
        (account_id,),
    ).fetchall()

    conn.close()

    escalations = _rows_to_dicts(rows)

    return _tool_response(
        tool_name="get_prior_escalations",
        arguments={"account_id": account_id},
        data={
            "count": len(escalations),
            "escalations": escalations,
        },
        decision_id=decision_id,
    )

# ============================================================
# TOOL 9
# GET PRIOR UNSUPPORTED ALREADY-PAID CLAIMS
# ============================================================

def get_prior_unsupported_already_paid_claims(
    account_id: int,
    decision_id: Optional[int] = None,
) -> dict:
    """
    FR-7.4

    Retrieve prior ALREADY_PAID_CLAIM decisions whose persisted
    reconciliation evidence did not verify the payment claim.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            aa.decision_id,
            aa.invoice_id,
            aa.created_at,
            tc.tool_call_id,
            tc.result_json
        FROM agent_actions AS aa
        JOIN tool_calls AS tc
            ON tc.decision_id = aa.decision_id
        WHERE aa.account_id = ?
          AND aa.primary_intent = 'ALREADY_PAID_CLAIM'
          AND tc.tool_name = 'reconcile_payment_claim'
          AND tc.status = 'SUCCESS'
          AND (? IS NULL OR aa.decision_id <> ?)
        ORDER BY aa.created_at DESC, aa.decision_id DESC, tc.tool_call_id DESC
        """,
        (
            account_id,
            decision_id,
            decision_id,
        ),
    ).fetchall()

    conn.close()

    unsupported_claims = []
    seen_decisions = set()

    for row in rows:
        item = dict(row)
        prior_decision_id = item["decision_id"]

        if prior_decision_id in seen_decisions:
            continue

        seen_decisions.add(prior_decision_id)

        reconciliation = json.loads(
            item["result_json"] or "{}"
        )

        if (
            reconciliation.get(
                "payment_claim_verified"
            )
            is False
        ):
            unsupported_claims.append(
                {
                    "decision_id":
                        prior_decision_id,
                    "invoice_id":
                        item["invoice_id"],
                    "created_at":
                        item["created_at"],
                    "tool_call_id":
                        item["tool_call_id"],
                    "reconciliation":
                        reconciliation,
                }
            )

    return _tool_response(
        tool_name=(
            "get_prior_unsupported_already_paid_claims"
        ),
        arguments={"account_id": account_id},
        data={
            "count": len(
                unsupported_claims
            ),
            "unsupported_claims":
                unsupported_claims,
        },
        decision_id=decision_id,
    )

# ============================================================
# TOOL 11
# GET RECENT OUTBOUND CONTACTS
# ============================================================

def get_recent_outbound_contacts(
    account_id: int,
    proposed_send_time: datetime,
    decision_id: Optional[int] = None,
) -> dict:
    """
    PR-2.3.
    Retrieve outbound customer contacts in the rolling
    seven-day window preceding the proposed send time.

    Stored SQLite CURRENT_TIMESTAMP values are treated as UTC.
    """

    if proposed_send_time.tzinfo is None:
        raise ValueError(
            "proposed_send_time must be timezone-aware."
        )

    send_time_utc = proposed_send_time.astimezone(
        timezone.utc
    )

    window_start_utc = (
        send_time_utc
        - timedelta(days=7)
    )

    window_start_text = window_start_utc.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    send_time_text = send_time_utc.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM communications
        WHERE account_id = ?
          AND direction = 'OUTBOUND'
          AND created_at >= ?
          AND created_at < ?
        ORDER BY created_at DESC, communication_id DESC
        """,
        (
            account_id,
            window_start_text,
            send_time_text,
        ),
    ).fetchall()

    conn.close()

    contacts = _rows_to_dicts(rows)

    return _tool_response(
        tool_name="get_recent_outbound_contacts",
        arguments={
            "account_id": account_id,
            "proposed_send_time": proposed_send_time,
        },
        data={
            "count": len(contacts),
            "window_start_utc": window_start_utc.isoformat(),
            "proposed_send_time_utc": send_time_utc.isoformat(),
            "contacts": contacts,
        },
        decision_id=decision_id,
    )
