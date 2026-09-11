import json

import src.agent as agent

from src.database import get_connection
from src.evaluation import cleanup_decision
from src.schemas import MessageTone, ValidatorOutcome


ACCOUNT_ID = 9076001
INVOICE_ID = 9076002


def setup_step23_fixture():
    conn = get_connection()

    conn.execute(
        "DELETE FROM tool_calls WHERE decision_id IN "
        "(SELECT decision_id FROM agent_actions WHERE account_id = ?)",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM escalations WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM agent_actions WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM promises_to_pay WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM communications WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM risk_scores WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM invoices WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM accounts WHERE account_id = ?",
        (ACCOUNT_ID,),
    )

    conn.execute(
        "INSERT INTO accounts "
        "(account_id, customer_name, industry, debt_type, "
        "account_status, sms_consent, email_allowed, "
        "lifetime_value, customer_since) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ACCOUNT_ID,
            "Step 23 Test Account",
            "Waste Hauling",
            "COMMERCIAL",
            "ACTIVE",
            0,
            1,
            60000.00,
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
            "step23-test",
            '["step23 fixture"]',
            "2026-09-01 12:00:00",
        ),
    )

    conn.commit()
    conn.close()


def cleanup_step23_fixture(result):
    if result is not None and result.get("decision_id") is not None:
        cleanup_decision(result["decision_id"])

    conn = get_connection()
    conn.execute(
        "DELETE FROM promises_to_pay WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM communications WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM risk_scores WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM invoices WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM accounts WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.commit()
    conn.close()


def test_firm_tone_high_value_account_escalates_in_graph(monkeypatch):
    setup_step23_fixture()
    result = None
    original_recommender = agent.mock_recommend_promise_to_pay_action

    def firm_recommender(state):
        recommendation = original_recommender(state)
        return recommendation.model_copy(
            update={"message_tone": MessageTone.FIRM}
        )

    monkeypatch.setattr(
        agent,
        "mock_recommend_promise_to_pay_action",
        firm_recommender,
    )

    try:
        result = agent.run_aca(
            account_id=ACCOUNT_ID,
            invoice_id=INVOICE_ID,
            reply_text="We will pay on Friday.",
        )

        assert result["proposed_action"].message_tone == MessageTone.FIRM
        assert result["validation"].outcome == ValidatorOutcome.ESCALATE
        assert "PR-5.5" in result["validation"].violated_constraints
        assert result["final_status"] == "ESCALATE"

        conn = get_connection()
        row = conn.execute(
            "SELECT violated_fields FROM agent_actions WHERE decision_id = ?",
            (result["decision_id"],),
        ).fetchone()
        conn.close()

        assert row is not None
        assert json.loads(row["violated_fields"]) == [
            "account_lifetime_value",
        ]

    finally:
        cleanup_step23_fixture(result)
