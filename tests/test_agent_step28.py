from src.agent import run_aca
from src.database import get_connection
from src.evaluation import cleanup_decision
from src.review import (
    HumanReviewError,
    list_review_queue,
    record_human_disposition,
)
from src.schemas import Intent
from tests.fresh import fresh_scored_at


ACCOUNT_ID = 9088101
INVOICE_ID = 9088102


def setup_step28_fixture():
    conn = get_connection()
    conn.execute(
        "DELETE FROM tool_calls WHERE decision_id IN "
        "(SELECT decision_id FROM agent_actions WHERE account_id = ?)",
        (ACCOUNT_ID,),
    )
    conn.execute("DELETE FROM escalations WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM agent_actions WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM promises_to_pay WHERE account_id = ?", (ACCOUNT_ID,))
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
            "Step 28 Review Account",
            "Roll-off waste hauling",
            "COMMERCIAL",
            "ACTIVE",
            1,
            1,
            8000.00,
            "2024-06-01",
        ),
    )
    conn.execute(
        "INSERT INTO invoices "
        "(invoice_id, account_id, amount, issue_date, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            INVOICE_ID,
            ACCOUNT_ID,
            1500.00,
            "2026-10-01",
            "2026-11-01",
            "OPEN",
        ),
    )
    conn.execute(
        "INSERT INTO risk_scores "
        "(account_id, invoice_id, score, risk_band, model_version, "
        "contributing_factors, scored_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            ACCOUNT_ID,
            INVOICE_ID,
            0.18,
            "LOW",
            "step28-test",
            '["step28 fixture"]',
            fresh_scored_at(),
        ),
    )
    conn.commit()
    conn.close()


def cleanup_step28_fixture(decision_ids):
    for decision_id in decision_ids:
        if decision_id is not None:
            cleanup_decision(decision_id)

    conn = get_connection()
    conn.execute("DELETE FROM escalations WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM risk_scores WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM invoices WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM accounts WHERE account_id = ?", (ACCOUNT_ID,))
    conn.commit()
    conn.close()


def test_human_disposition_is_queued_and_retrieved_on_the_next_decision():
    setup_step28_fixture()
    decision_ids = []

    try:
        escalated = run_aca(
            account_id=ACCOUNT_ID,
            invoice_id=INVOICE_ID,
            reply_text="My attorney will be contacting you.",
        )
        decision_ids.append(escalated["decision_id"])

        assert escalated["intent"].primary_intent == Intent.HOSTILE_OR_ADVERSARIAL
        assert escalated["final_status"] == "ESCALATE"
        escalation_id = escalated["escalation_id"]

        open_cases = list_review_queue("OPEN")
        assert any(item["escalation_id"] == escalation_id for item in open_cases)

        recorded = record_human_disposition(
            escalation_id,
            "RESOLVED",
            reviewer_note="Standard acknowledgement is acceptable after legal review.",
            reviewed_by="capstone-reviewer",
        )
        assert recorded["disposition_code"] == "RESOLVED"
        assert recorded["status"] == "RESOLVED"
        assert "Standard acknowledgement is acceptable" in recorded["human_disposition"]

        from src.audit import get_complete_audit_record, get_decision_record

        before_reason = get_decision_record(escalated["decision_id"])["final_reason"]
        audit = get_complete_audit_record(escalated["decision_id"])
        assert any(
            note["event_type"] == "HUMAN_DISPOSITION"
            for note in audit["audit_notes"]
        )
        assert get_decision_record(escalated["decision_id"])["final_reason"] == before_reason
        assert any(
            step["step"] == "Audit note appended" for step in audit["timeline"]
        )

        try:
            record_human_disposition(escalation_id, "APPROVE")
            raise AssertionError("A second disposition was accepted.")
        except HumanReviewError:
            pass

        assert all(
            item["escalation_id"] != escalation_id
            for item in list_review_queue("OPEN")
        )

        follow_up = run_aca(
            account_id=ACCOUNT_ID,
            invoice_id=INVOICE_ID,
            reply_text="Can we set up a payment plan?",
        )
        decision_ids.append(follow_up["decision_id"])

        dispositions = [
            item.get("human_disposition")
            for item in follow_up["prior_escalations_evidence"]["data"]["escalations"]
        ]
        assert any(
            disposition
            and "Standard acknowledgement is acceptable" in disposition
            for disposition in dispositions
        )
        assert "Standard acknowledgement is acceptable" in follow_up["proposed_action"].rationale
        assert any(
            item.get("disposition_code") == "RESOLVED"
            for item in follow_up["prior_escalations_evidence"]["data"]["escalations"]
        )

    finally:
        cleanup_step28_fixture(decision_ids)


def test_unknown_disposition_is_rejected():
    with __import__("pytest").raises(HumanReviewError):
        record_human_disposition(999999991, "SEND_IT")
