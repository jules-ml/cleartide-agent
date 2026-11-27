"""Read and update the demo book for the live console.

This module does not decide what is allowed. It displays the demo
database and, after the agent has already approved an action, records
that outcome on the account.
"""

import json
from datetime import datetime, timedelta, timezone

from src.database import get_connection


LIVE_ACCOUNT_IDS = (8801001, 8801002, 8801003, 8801004, 8801005)

BLOCK_RULES = {"PR-3"}

RULE_READOUT = (
    ("PR-6.3", "Policy version matches the file"),
    ("GV-5", "Autonomy switch is on"),
    ("FR-1.3", "Intent confidence meets the threshold"),
    ("FR-1.5", "Reply is clear enough to act"),
    ("PR-5.3", "No legal or sensitive language in the reply"),
    ("PR-3", "Draft has no unauthorized threat or false debt claim"),
    ("PR-5.4", "Disputed amount is within the limit"),
    ("PR-4.3", "Customer has not opted out of the channel"),
    ("PR-4.1", "Text message has recorded consent"),
    ("PR-2.4", "Consumer text has a send time"),
    ("PR-2.1", "Consumer text is outside quiet hours"),
    ("PR-2.3", "Weekly contact count is under the cap"),
    ("PR-5.5", "Firm tone is allowed for this customer"),
    ("PR-5.2", "Payment plan is allowed for this risk level"),
)


def decision_label(view: dict) -> str:
    """Map an already-finished decision onto the console badge."""

    constraints = set(view.get("violated_constraints") or [])
    if constraints & BLOCK_RULES:
        return "BLOCKED"
    if view.get("final_status") == "APPROVED":
        return "AUTO-APPROVED"
    return "ESCALATED"


def _parse_constraint_list(raw) -> set[str]:
    if not raw or raw in {"[]", "null"}:
        return set()
    if isinstance(raw, list):
        return {str(item) for item in raw}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return set()
    if isinstance(parsed, list):
        return {str(item) for item in parsed}
    return set()


def label_from_row(final_action: str, validator_outcome: str, violated_raw) -> str:
    constraints = _parse_constraint_list(violated_raw)
    if constraints & BLOCK_RULES:
        return "BLOCKED"
    if validator_outcome == "APPROVED" and final_action not in {
        "ESCALATE",
        "FLAG_FOR_HUMAN_CALL",
    }:
        return "AUTO-APPROVED"
    return "ESCALATED"


def work_queue() -> list[dict]:
    """Open book for the five operating accounts in the demo database."""

    placeholders = ",".join("?" for _ in LIVE_ACCOUNT_IDS)
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT
                a.account_id,
                a.customer_name,
                a.debt_type,
                i.invoice_id,
                i.amount,
                i.due_date,
                i.status AS invoice_status,
                COALESCE((
                    SELECT SUM(p.amount)
                    FROM payments p
                    WHERE p.invoice_id = i.invoice_id
                      AND lower(p.status) = 'posted'
                ), 0) AS posted,
                r.risk_band,
                r.score,
                (
                    SELECT COUNT(*)
                    FROM promises_to_pay pr
                    WHERE pr.account_id = a.account_id
                      AND lower(pr.status) IN ('open', 'noted')
                ) AS open_promises,
                (
                    SELECT aa.final_action
                    FROM agent_actions aa
                    WHERE aa.account_id = a.account_id
                      AND aa.audit_status = 'COMPLETED'
                    ORDER BY aa.decision_id DESC
                    LIMIT 1
                ) AS last_action,
                (
                    SELECT aa.validator_outcome
                    FROM agent_actions aa
                    WHERE aa.account_id = a.account_id
                      AND aa.audit_status = 'COMPLETED'
                    ORDER BY aa.decision_id DESC
                    LIMIT 1
                ) AS last_outcome,
                (
                    SELECT aa.violated_constraint
                    FROM agent_actions aa
                    WHERE aa.account_id = a.account_id
                      AND aa.audit_status = 'COMPLETED'
                    ORDER BY aa.decision_id DESC
                    LIMIT 1
                ) AS last_violation
            FROM accounts a
            JOIN invoices i ON i.account_id = a.account_id
            LEFT JOIN risk_scores r ON r.risk_score_id = (
                SELECT risk_score_id
                FROM risk_scores
                WHERE account_id = a.account_id
                ORDER BY scored_at DESC, risk_score_id DESC
                LIMIT 1
            )
            WHERE a.account_id IN ({placeholders})
            ORDER BY a.account_id
            """,
            LIVE_ACCOUNT_IDS,
        ).fetchall()
    finally:
        conn.close()

    today = datetime.now(timezone.utc).date()
    book = []
    for row in rows:
        item = dict(row)
        due = datetime.strptime(item["due_date"], "%Y-%m-%d").date()
        item["days_past_due"] = (today - due).days
        item["balance"] = round(float(item["amount"]) - float(item["posted"]), 2)
        if item["last_action"]:
            item["board_status"] = label_from_row(
                item["last_action"],
                item["last_outcome"] or "",
                item["last_violation"],
            )
        elif str(item["invoice_status"]).lower() == "paid":
            item["board_status"] = "PAID"
        else:
            item["board_status"] = "OPEN"
        book.append(item)
    return book


def session_ops() -> dict:
    """Counts taken from the demo database since the last reset."""

    conn = get_connection()
    try:
        decisions = conn.execute(
            """
            SELECT final_action, validator_outcome, violated_constraint
            FROM agent_actions
            WHERE audit_status = 'COMPLETED'
            """
        ).fetchall()
        open_reviews = conn.execute(
            """
            SELECT COUNT(*)
            FROM escalations
            WHERE UPPER(status) = 'OPEN'
            """
        ).fetchone()[0]
    finally:
        conn.close()

    autonomous = escalated = blocked = violations = 0
    for row in decisions:
        label = label_from_row(
            row["final_action"] or "",
            row["validator_outcome"] or "",
            row["violated_constraint"],
        )
        if label == "AUTO-APPROVED":
            autonomous += 1
            if _parse_constraint_list(row["violated_constraint"]):
                violations += 1
        elif label == "BLOCKED":
            blocked += 1
        else:
            escalated += 1
    return {
        "autonomous": autonomous,
        "escalated": escalated,
        "blocked": blocked,
        "open_reviews": int(open_reviews),
        "policy_violations": violations,
    }


def portfolio_frames(book: list[dict]) -> dict:
    """Balance totals by aging bucket and risk tier. Empty groups stay out."""

    aging = {"Current": 0.0, "1–30 days": 0.0, "31–60 days": 0.0, "61–90 days": 0.0, "90+ days": 0.0}
    risk = {}
    for item in book:
        balance = max(item["balance"], 0.0)
        days = item["days_past_due"]
        if days <= 0:
            bucket = "Current"
        elif days <= 30:
            bucket = "1–30 days"
        elif days <= 60:
            bucket = "31–60 days"
        elif days <= 90:
            bucket = "61–90 days"
        else:
            bucket = "90+ days"
        aging[bucket] += balance
        band = item.get("risk_band") or "UNKNOWN"
        risk[band] = risk.get(band, 0.0) + balance
    return {
        "aging": {key: value for key, value in aging.items() if value > 0},
        "risk": risk,
    }


def _rule_applies(rule: str, view: dict, fired: set[str]) -> bool:
    if rule in fired:
        return True
    intent = view.get("intent")
    action = view.get("recommended_action")
    channel = view.get("channel")
    if rule in {"PR-6.3", "GV-5", "FR-1.3"}:
        return bool(action) or view.get("final_status") == "APPROVED"
    if rule == "FR-1.5":
        return intent == "UNCLEAR"
    if rule == "PR-5.3":
        return intent == "HOSTILE_OR_ADVERSARIAL"
    if rule == "PR-3":
        return bool(view.get("message_draft"))
    if rule == "PR-5.4":
        return intent == "AMOUNT_DISPUTE"
    if rule == "PR-4.1":
        return channel == "SMS"
    if rule in {"PR-2.1", "PR-2.4"}:
        return channel == "SMS"
    if rule == "PR-2.3":
        return action in {"SEND_MESSAGE", "RESEND_INVOICE", "PROPOSE_PAYMENT_PLAN"}
    if rule == "PR-5.2":
        return action == "PROPOSE_PAYMENT_PLAN"
    return False


def policy_readout(view: dict) -> list[dict]:
    """
    Show where the validator stopped.

    This does not run the rules again. Passed means the validator
    returned a result after that check. Not reached means it had
    already stopped.
    """

    fired = set(view.get("violated_constraints") or [])
    approved = view.get("final_status") == "APPROVED"
    rows = []
    stopped = False
    for rule, plain in RULE_READOUT:
        applies = _rule_applies(rule, view, fired)
        if not applies:
            state = "Not applicable"
        elif rule in fired:
            state = "Fail"
            stopped = True
        elif stopped and not approved:
            state = "Not reached"
        else:
            state = "Pass"
        if applies or rule in fired:
            rows.append({"rule": rule, "plain": plain, "state": state})
    return rows


def evidence_blocks(result: dict) -> list[dict]:
    """Compact tool payloads for the console. No raw packet dump."""

    blocks = []
    payment = (result.get("payment_evidence") or {}).get("data") or {}
    if result.get("payment_evidence"):
        blocks.append(
            {
                "title": "Ledger lookup",
                "rows": {
                    "payment_claim_verified": payment.get("payment_claim_verified"),
                    "invoice_amount": payment.get("invoice_amount"),
                    "posted_payment_total": payment.get("posted_payment_total"),
                },
            }
        )
    history = (result.get("payment_history_evidence") or {}).get("data") or {}
    if result.get("payment_history_evidence"):
        blocks.append(
            {
                "title": "Payment history",
                "rows": {"count": history.get("count")},
            }
        )
    promises = (result.get("prior_promises_evidence") or {}).get("data") or {}
    if result.get("prior_promises_evidence"):
        blocks.append(
            {
                "title": "Promise history",
                "rows": {"count": promises.get("count")},
            }
        )
    delivery = (result.get("delivery_evidence") or {}).get("data") or {}
    if result.get("delivery_evidence"):
        blocks.append(
            {
                "title": "Invoice delivery",
                "rows": {
                    "was_delivered": delivery.get("was_delivered"),
                    "delivery_verified": delivery.get("delivery_verified"),
                },
            }
        )
    risk = result.get("risk")
    if risk is not None:
        blocks.append(
            {
                "title": "Risk score",
                "rows": {
                    "score": risk.score,
                    "band": risk.band.value,
                    "factors": list(risk.contributing_factors or []),
                },
            }
        )
    contacts = (result.get("recent_outbound_contacts_evidence") or {}).get("data") or {}
    if result.get("recent_outbound_contacts_evidence"):
        blocks.append(
            {
                "title": "Recent outbound contacts",
                "rows": {"count": contacts.get("count")},
            }
        )
    return blocks


def _already_applied(conn, decision_id: int) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM audit_notes
        WHERE decision_id = ?
          AND event_type = 'APPLIED_OUTCOME'
        """,
        (decision_id,),
    ).fetchone()
    return row is not None


def apply_approved_outcome(view: dict, result: dict) -> str:
    """
    Record an already-approved action on the demo book.

    Returns a short description of what changed, or an empty string.
    """

    if decision_label(view) != "AUTO-APPROVED":
        return ""

    decision_id = view.get("decision_id")
    account_id = view.get("account_id")
    invoice_id = view.get("invoice_id")
    if not decision_id or not account_id:
        return ""

    conn = get_connection()
    try:
        if _already_applied(conn, int(decision_id)):
            return ""

        notes = []
        action = view.get("final_action")
        intent = view.get("intent")
        channel = view.get("channel") if view.get("channel") in {"EMAIL", "SMS"} else "EMAIL"
        draft = (view.get("message_draft") or "").strip()

        if draft and action in {"SEND_MESSAGE", "RESEND_INVOICE", "PROPOSE_PAYMENT_PLAN"}:
            conn.execute(
                """
                INSERT INTO communications (
                    account_id, invoice_id, direction, channel, message
                )
                VALUES (?, ?, 'OUTBOUND', ?, ?)
                """,
                (account_id, invoice_id, channel, draft),
            )
            notes.append(f"outbound {channel} logged")

        if intent == "PROMISE_TO_PAY" and action == "SEND_MESSAGE":
            balance_row = conn.execute(
                """
                SELECT amount FROM invoices WHERE invoice_id = ?
                """,
                (invoice_id,),
            ).fetchone()
            amount = float(balance_row["amount"]) if balance_row else None
            promised_date = (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()
            if "friday" in (view.get("reply_text") or "").lower():
                promised_date = _next_weekday(4).isoformat()
            conn.execute(
                """
                INSERT INTO promises_to_pay (
                    account_id, invoice_id, promised_amount, promised_date, status
                )
                VALUES (?, ?, ?, ?, 'noted')
                """,
                (account_id, invoice_id, amount, promised_date),
            )
            notes.append("promise noted")

        payment = (result.get("payment_evidence") or {}).get("data") or {}
        if action == "NO_ACTION_MONITOR" and payment.get("payment_claim_verified"):
            conn.execute(
                """
                UPDATE invoices SET status = 'paid' WHERE invoice_id = ?
                """,
                (invoice_id,),
            )
            notes.append("invoice marked paid")

        if action == "LOG_DISPUTE_AND_HOLD":
            conn.execute(
                """
                UPDATE invoices SET status = 'on_hold' WHERE invoice_id = ?
                """,
                (invoice_id,),
            )
            notes.append("invoice placed on hold")

        detail = ", ".join(notes) or "approved with no ledger write"
        conn.execute(
            """
            INSERT INTO audit_notes (
                decision_id, escalation_id, event_type, detail, created_at
            )
            VALUES (?, NULL, 'APPLIED_OUTCOME', ?, ?)
            """,
            (
                int(decision_id),
                detail,
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        return detail
    finally:
        conn.close()


def _next_weekday(weekday: int):
    today = datetime.now(timezone.utc).date()
    ahead = (weekday - today.weekday()) % 7
    if ahead == 0:
        ahead = 7
    return today + timedelta(days=ahead)


def inbox_items() -> list[dict]:
    from src.review import list_review_queue

    cases = list_review_queue("OPEN")
    if not cases:
        return []
    conn = get_connection()
    try:
        names = {
            row["account_id"]: row["customer_name"]
            for row in conn.execute("SELECT account_id, customer_name FROM accounts")
        }
        decision_ids = [case["decision_id"] for case in cases if case.get("decision_id")]
        decisions = {}
        if decision_ids:
            marks = ",".join("?" for _ in decision_ids)
            for row in conn.execute(
                f"""
                SELECT decision_id, final_action, validator_outcome, violated_constraint
                FROM agent_actions
                WHERE decision_id IN ({marks})
                """,
                decision_ids,
            ):
                decisions[row["decision_id"]] = row
    finally:
        conn.close()
    now = datetime.now(timezone.utc)
    items = []
    for case in cases:
        created = _parse_timestamp(case.get("created_at"))
        age_hours = None if created is None else (now - created).total_seconds() / 3600
        constraints = _parse_constraint_list(case.get("rejection_reason"))
        packet = case.get("packet") or {}
        brief = packet.get("reviewer_brief") or {}
        decision = decisions.get(case.get("decision_id"))
        if decision is not None:
            label = label_from_row(
                decision["final_action"] or "",
                decision["validator_outcome"] or "",
                decision["violated_constraint"],
            )
            if label == "AUTO-APPROVED":
                label = "ESCALATED"
        else:
            label = "ESCALATED"
        items.append(
            {
                **case,
                "customer_name": names.get(case.get("account_id"), "Account"),
                "age_hours": age_hours,
                "age_label": _age_label(age_hours),
                "queue_label": label,
                "brief": brief,
                "constraints": sorted(constraints),
            }
        )
    return items


def recent_audits(limit: int = 25) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                aa.decision_id,
                aa.account_id,
                a.customer_name,
                aa.primary_intent,
                aa.final_action,
                aa.validator_outcome,
                aa.violated_constraint,
                aa.final_reason,
                aa.created_at,
                aa.audit_status
            FROM agent_actions aa
            LEFT JOIN accounts a ON a.account_id = aa.account_id
            WHERE aa.audit_status = 'COMPLETED'
            ORDER BY aa.decision_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    items = []
    for row in rows:
        item = dict(row)
        item["label"] = label_from_row(
            item.get("final_action") or "",
            item.get("validator_outcome") or "",
            item.get("violated_constraint"),
        )
        items.append(item)
    return items


def _parse_timestamp(value: str):
    if not value:
        return None
    text = str(value).replace("T", " ").split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if " " in fmt else text[:10], fmt).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
    return None


def _age_label(hours) -> str:
    if hours is None:
        return "—"
    if hours < 1:
        return f"{max(int(hours * 60), 0)} min"
    if hours < 48:
        return f"{hours:.1f} h"
    return f"{hours / 24:.1f} d"
