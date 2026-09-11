import src.agent as agent

from src.database import get_connection
from src.evaluation import cleanup_decision
from src.schemas import Channel, ValidatorOutcome
from src.tools import record_channel_opt_out


ACCOUNT_ID = 9077001
INVOICE_ID = 9077002


def setup_step25_fixture():
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
            "Step 25 Test Account",
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
            "step25-test",
            '["step25 fixture"]',
            "2026-09-01 12:00:00",
        ),
    )

    conn.commit()
    conn.close()

    record_channel_opt_out(
        account_id=ACCOUNT_ID,
        channel="EMAIL",
        source="step25-test",
    )


def cleanup_step25_fixture(result):
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


def test_persistent_email_opt_out_escalates_in_graph():
    setup_step25_fixture()
    result = None

    try:
        repeated_opt_out = record_channel_opt_out(
            account_id=ACCOUNT_ID,
            channel="EMAIL",
            source="later-repeat",
        )

        assert repeated_opt_out["source"] == "step25-test"

        result = agent.run_aca(
            account_id=ACCOUNT_ID,
            invoice_id=INVOICE_ID,
            reply_text="We will pay on Friday.",
        )

        opt_outs = result["account_evidence"]["data"]["channel_opt_outs"]

        assert any(
            item["channel"] == "EMAIL"
            and item["source"] == "step25-test"
            for item in opt_outs
        )
        assert result["proposed_action"].target_channel == Channel.EMAIL
        assert result["validation"].outcome == ValidatorOutcome.ESCALATE
        assert "PR-4.3" in result["validation"].violated_constraints
        assert result["validation"].violated_fields == ["channel_opted_out"]
        assert result["final_status"] == "ESCALATE"

    finally:
        cleanup_step25_fixture(result)


def test_human_call_flag_cannot_be_persisted_as_channel_opt_out():
    import pytest

    with pytest.raises(ValueError):
        record_channel_opt_out(
            account_id=ACCOUNT_ID,
            channel="HUMAN_CALL_FLAG",
            source="step25-test",
        )
