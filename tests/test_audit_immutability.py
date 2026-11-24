from src.agent import run_aca
from src.audit import (
    AuditImmutableError,
    attempt_audit_rewrite,
    finalize_decision,
    get_complete_audit_record,
    get_decision_record,
)
from src.database import get_connection
from src.evaluation import cleanup_decision
from tests.fresh import fresh_scored_at


ACCOUNT_ID = 9088201
INVOICE_ID = 9088202


def setup_audit_fixture():
    conn = get_connection()
    conn.execute(
        "DELETE FROM tool_calls WHERE decision_id IN "
        "(SELECT decision_id FROM agent_actions WHERE account_id = ?)",
        (ACCOUNT_ID,),
    )
    conn.execute("DELETE FROM escalations WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM agent_actions WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM communications WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM risk_scores WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM invoices WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM accounts WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute(
        "INSERT INTO accounts "
        "(account_id, customer_name, industry, debt_type, "
        "account_status, sms_consent, email_allowed, "
        "lifetime_value, customer_since) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ACCOUNT_ID,
            "Audit Immutability Account",
            "Roll-off waste hauling",
            "COMMERCIAL",
            "ACTIVE",
            1,
            1,
            5000.00,
            "2024-01-15",
        ),
    )
    conn.execute(
        "INSERT INTO invoices "
        "(invoice_id, account_id, amount, issue_date, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (INVOICE_ID, ACCOUNT_ID, 900.00, "2026-10-01", "2026-11-01", "OPEN"),
    )
    conn.execute(
        "INSERT INTO risk_scores "
        "(account_id, invoice_id, score, risk_band, model_version, "
        "contributing_factors, scored_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            ACCOUNT_ID,
            INVOICE_ID,
            0.16,
            "LOW",
            "audit-test",
            '["audit fixture"]',
            fresh_scored_at(),
        ),
    )
    conn.execute(
        "INSERT INTO communications "
        "(account_id, invoice_id, direction, channel, message) "
        "VALUES (?, ?, ?, ?, ?)",
        (ACCOUNT_ID, INVOICE_ID, "INBOUND", "EMAIL", "Earlier customer reply."),
    )
    conn.commit()
    conn.close()


def test_completed_audit_record_is_complete_and_immutable():
    setup_audit_fixture()
    result = None

    try:
        result = run_aca(
            account_id=ACCOUNT_ID,
            invoice_id=INVOICE_ID,
            reply_text="I'll pay the invoice on Friday.",
        )

        record = get_complete_audit_record(result["decision_id"])
        assert record is not None
        assert record["complete"] is True
        decision = record["decision"]
        assert decision["audit_status"] == "COMPLETED"
        assert decision["primary_intent"] == "PROMISE_TO_PAY"
        assert decision["debt_classification"] == "COMMERCIAL"
        assert decision["policy_version"]
        assert decision["final_action"] == "SEND_MESSAGE"
        assert decision["validator_outcome"] == "APPROVED"
        assert any(step["step"] == "Intent classified" for step in record["timeline"])
        assert any(step["step"] == "Policy validated" for step in record["timeline"])
        assert record["tool_calls"]

        original_reason = decision["final_reason"]

        try:
            attempt_audit_rewrite(
                result["decision_id"],
                {"final_reason": "tampered after the fact"},
            )
            raise AssertionError("Rewrite of a finalized audit was accepted.")
        except AuditImmutableError:
            pass

        try:
            finalize_decision(result)
            raise AssertionError("A second finalize was accepted.")
        except AuditImmutableError:
            pass

        unchanged = get_decision_record(result["decision_id"])
        assert unchanged["final_reason"] == original_reason
        assert unchanged["audit_status"] == "COMPLETED"

    finally:
        if result is not None and result.get("decision_id"):
            cleanup_decision(result["decision_id"])
        conn = get_connection()
        conn.execute("DELETE FROM communications WHERE account_id = ?", (ACCOUNT_ID,))
        conn.execute("DELETE FROM risk_scores WHERE account_id = ?", (ACCOUNT_ID,))
        conn.execute("DELETE FROM invoices WHERE account_id = ?", (ACCOUNT_ID,))
        conn.execute("DELETE FROM accounts WHERE account_id = ?", (ACCOUNT_ID,))
        conn.commit()
        conn.close()
