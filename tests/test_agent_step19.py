from src.agent import run_aca

from src.database import get_connection


def test_payment_plan_retrieves_prior_escalation_disposition():
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO escalations (account_id, invoice_id, reply_text, status, human_disposition, resolved_at) VALUES (?, ?, ?, ?, ?, ?)",
        (1001, 5001, "Prior payment-plan escalation", "RESOLVED", "Approved prior payment arrangement after review", "2026-09-01 12:00:00"),
    )
    fixture_escalation_id = cursor.lastrowid
    conn.commit()
    conn.close()

    decision_id = None

    try:
        result = run_aca(
            account_id=1001,
            invoice_id=5001,
            reply_text="Can we split the balance into four monthly payments?",
        )

        decision_id = result["decision_id"]

        assert (
            result["prior_escalations_evidence"]["tool_name"]
            == "get_prior_escalations"
        )
        assert any(
            item.get("human_disposition")
            == "Approved prior payment arrangement after review"
            for item in result["prior_escalations_evidence"]["data"]["escalations"]
        )
        assert (
            "Approved prior payment arrangement after review"
            in result["proposed_action"].rationale
        )

        assert all(
            "packet_json" not in item
            for item in result["prior_escalations_evidence"]["data"]["escalations"]
        )

        packet = result["escalation_packet"]
        assert any(
            item.get("tool_name") == "get_prior_escalations"
            and any(
                escalation.get("human_disposition")
                == "Approved prior payment arrangement after review"
                for escalation in item.get("data", {}).get("escalations", [])
            )
            for item in packet.tool_results
        )

    finally:
        conn = get_connection()
        if decision_id is not None:
            conn.execute("DELETE FROM tool_calls WHERE decision_id = ?", (decision_id,))
            conn.execute("DELETE FROM escalations WHERE decision_id = ?", (decision_id,))
            conn.execute("DELETE FROM agent_actions WHERE decision_id = ?", (decision_id,))
        conn.execute("DELETE FROM escalations WHERE escalation_id = ?", (fixture_escalation_id,))
        conn.commit()
        conn.close()



def test_prior_escalation_tool_error_fails_closed(monkeypatch):
    import src.agent as agent

    def broken_prior_escalations(account_id, decision_id=None):
        raise RuntimeError("simulated prior escalation tool failure")

    monkeypatch.setattr(
        agent,
        "get_prior_escalations",
        broken_prior_escalations,
    )

    result = agent.run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text="Can we split the balance into four monthly payments?",
    )

    assert result["prior_escalations_evidence"]["status"] == "ERROR"
    assert result.get("forced_escalation_reason") is not None
    assert "FR-2.7" in result["forced_escalation_reason"]
    assert "get_prior_escalations" in result["forced_escalation_reason"]
    assert result["final_status"] == "ESCALATE"


    conn = get_connection()
    conn.execute("DELETE FROM tool_calls WHERE decision_id = ?", (result["decision_id"],))
    conn.execute("DELETE FROM escalations WHERE decision_id = ?", (result["decision_id"],))
    conn.execute("DELETE FROM agent_actions WHERE decision_id = ?", (result["decision_id"],))
    conn.commit()
    conn.close()
