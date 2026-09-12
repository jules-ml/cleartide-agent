import src.agent as agent

from src.database import get_connection
from src.evaluation import cleanup_decision
from src.schemas import ValidatorOutcome


ACCOUNT_ID = 9078001
INVOICE_ID = 9078002


def setup_step26_fixture():
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
    conn.execute("DELETE FROM channel_opt_outs WHERE account_id = ?", (ACCOUNT_ID,))
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
            "Step 26 Test Account",
            "Waste Hauling",
            "COMMERCIAL",
            "ACTIVE",
            0,
            1,
            1000.00,
            "2025-01-01",
        ),
    )

    conn.execute(
        "INSERT INTO invoices "
        "(invoice_id, account_id, amount, issue_date, due_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            INVOICE_ID,
            ACCOUNT_ID,
            1000.00,
            "2026-08-01",
            "2026-08-31",
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
            0.25,
            "LOW",
            "step26-test",
            '["step26 fixture"]',
            "2026-09-01 12:00:00",
        ),
    )

    conn.commit()
    conn.close()


def cleanup_step26_fixture(result):
    if result is not None and result.get("decision_id") is not None:
        cleanup_decision(result["decision_id"])

    conn = get_connection()
    conn.execute("DELETE FROM promises_to_pay WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM communications WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM channel_opt_outs WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM risk_scores WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM invoices WHERE account_id = ?", (ACCOUNT_ID,))
    conn.execute("DELETE FROM accounts WHERE account_id = ?", (ACCOUNT_ID,))
    conn.commit()
    conn.close()


def test_pr3_unsafe_message_is_blocked_in_graph(monkeypatch):
    setup_step26_fixture()
    result = None
    original_recommender = agent.mock_recommend_promise_to_pay_action

    def unsafe_recommender(state):
        recommendation = original_recommender(state)
        return recommendation.model_copy(
            update={
                "message_body": "Failure to pay may result in legal action."
            }
        )

    monkeypatch.setattr(
        agent,
        "mock_recommend_promise_to_pay_action",
        unsafe_recommender,
    )

    try:
        result = agent.run_aca(
            account_id=ACCOUNT_ID,
            invoice_id=INVOICE_ID,
            reply_text="We will pay on Friday.",
        )

        assert result["validation"].outcome == ValidatorOutcome.REJECTED
        assert result["validation"].violated_constraints == ["PR-3"]
        assert result["validation"].violated_fields == ["message_body"]
        assert result["final_status"] == "ESCALATE"
        assert result["revision_count"] == 1
        assert "PR-3" in result["forced_escalation_reason"]

    finally:
        cleanup_step26_fixture(result)
