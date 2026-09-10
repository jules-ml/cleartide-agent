import src.agent as agent

from src.schemas import RiskBand


def test_missing_risk_uses_fr_3_4_critical_fallback(monkeypatch):
    def missing_risk_score(account_id, invoice_id, decision_id=None):
        return {
            "tool_call_id": "step17-missing-risk",
            "tool_name": "get_risk_score",
            "status": "NO_RESULT",
            "data": {
                "risk_score_available": False,
            },
        }

    monkeypatch.setattr(
        agent,
        "get_risk_score",
        missing_risk_score,
    )

    result = agent.run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text="I never received the invoice.",
    )

    assert result["risk"] is not None
    assert result["risk"].band == RiskBand.CRITICAL
    assert result["risk"].score == 0.80
    assert (
        result["risk"].model_version
        == "POLICY_FALLBACK_FR_3_4"
    )
    assert any(
        "risk score unavailable" in factor
        for factor in result["risk"].contributing_factors
    )
    assert result.get("forced_escalation_reason") is None



def test_stale_risk_uses_fr_3_4_critical_fallback(monkeypatch):
    def stale_risk_score(account_id, invoice_id, decision_id=None):
        return {
            "tool_call_id": "step17-stale-risk",
            "tool_name": "get_risk_score",
            "status": "SUCCESS",
            "data": {
                "account_id": account_id,
                "invoice_id": invoice_id,
                "score": 0.42,
                "risk_band": "MEDIUM",
                "model_version": "fixture-v0",
                "contributing_factors": [
                    "invoice more than 20 days past due",
                ],
                "risk_score_available": True,
                "scored_at": "2020-01-01 00:00:00",
            },
        }

    monkeypatch.setattr(
        agent,
        "get_risk_score",
        stale_risk_score,
    )

    result = agent.run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text="I never received the invoice.",
    )

    assert result["risk"] is not None
    assert result["risk"].band == RiskBand.CRITICAL
    assert result["risk"].score == 0.80
    assert (
        result["risk"].model_version
        == "POLICY_FALLBACK_FR_3_4"
    )
    assert any(
        "risk score stale" in factor
        for factor in result["risk"].contributing_factors
    )
    assert result.get("forced_escalation_reason") is None



def test_risk_tool_error_remains_operational_escalation(monkeypatch):
    def error_risk_score(account_id, invoice_id, decision_id=None):
        return {
            "tool_call_id": "step17-risk-error",
            "tool_name": "get_risk_score",
            "status": "ERROR",
            "data": {
                "error": True,
                "error_message": "simulated risk tool failure",
            },
        }

    monkeypatch.setattr(
        agent,
        "get_risk_score",
        error_risk_score,
    )

    result = agent.run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text="I never received the invoice.",
    )

    assert result.get("risk") is None
    assert result.get("forced_escalation_reason") is not None
    assert "FR-2.7" in result["forced_escalation_reason"]
    assert "get_risk_score" in result["forced_escalation_reason"]
    assert result["final_status"] == "ESCALATE"
