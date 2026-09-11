from src.agent import run_aca
from src.database import get_connection
from src.evaluation import cleanup_decision
from src.schemas import ActionType


ACCOUNT_ID = 9074001
INVOICE_ID = 9074002


def setup_step20_fixture():
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
        "DELETE FROM risk_scores WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM payments WHERE account_id = ?",
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
        "account_status, sms_consent, email_allowed) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            ACCOUNT_ID,
            "Step 20 Test Account",
            "Waste Hauling",
            "COMMERCIAL",
            "ACTIVE",
            0,
            1,
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
            "step20-test",
            '["step20 fixture"]',
            "2026-09-01 12:00:00",
        ),
    )

    conn.commit()
    conn.close()


def cleanup_step20_fixture(results):
    for result in results:
        if result is not None and result.get("decision_id") is not None:
            cleanup_decision(result["decision_id"])

    conn = get_connection()
    conn.execute(
        "DELETE FROM risk_scores WHERE account_id = ?",
        (ACCOUNT_ID,),
    )
    conn.execute(
        "DELETE FROM payments WHERE account_id = ?",
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


def test_third_unsupported_already_paid_claim_mandates_escalation():
    setup_step20_fixture()
    results = []

    try:
        for _ in range(3):
            results.append(
                run_aca(
                    account_id=ACCOUNT_ID,
                    invoice_id=INVOICE_ID,
                    reply_text="We already paid this invoice.",
                )
            )

        first, second, third = results

        assert (
            first[
                "prior_unsupported_already_paid_claims_evidence"
            ]["data"]["count"]
            == 0
        )
        assert (
            first["proposed_action"].action_type
            == ActionType.SEND_MESSAGE
        )
        assert first["final_status"] == "APPROVED"

        assert (
            second[
                "prior_unsupported_already_paid_claims_evidence"
            ]["data"]["count"]
            == 1
        )
        assert (
            second["proposed_action"].action_type
            == ActionType.SEND_MESSAGE
        )
        assert second["final_status"] == "APPROVED"

        assert (
            third[
                "prior_unsupported_already_paid_claims_evidence"
            ]["data"]["count"]
            == 2
        )
        assert third["final_status"] == "ESCALATE"
        assert "proposed_action" not in third
        assert "FR-7.4" in third["forced_escalation_reason"]
        assert any(
            item.get("tool_name") == "get_prior_unsupported_already_paid_claims"
            and item.get("data", {}).get("count") == 2
            for item in third["escalation_packet"].tool_results
        )
        assert third["tool_call_count"] == 2

    finally:
        cleanup_step20_fixture(results)


def test_unsupported_claim_memory_error_fails_closed(monkeypatch):
    import src.agent as agent

    setup_step20_fixture()
    result = None

    def broken_claim_memory(account_id, decision_id=None):
        raise RuntimeError("simulated unsupported-claim memory failure")

    monkeypatch.setattr(
        agent,
        "get_prior_unsupported_already_paid_claims",
        broken_claim_memory,
    )

    try:
        result = agent.run_aca(
            account_id=ACCOUNT_ID,
            invoice_id=INVOICE_ID,
            reply_text="We already paid this invoice.",
        )

        assert (
            result[
                "prior_unsupported_already_paid_claims_evidence"
            ]["status"]
            == "ERROR"
        )
        assert "FR-2.7" in result["forced_escalation_reason"]
        assert (
            "get_prior_unsupported_already_paid_claims"
            in result["forced_escalation_reason"]
        )
        assert result["final_status"] == "ESCALATE"

    finally:
        cleanup_step20_fixture(
            [result] if result is not None else []
        )
