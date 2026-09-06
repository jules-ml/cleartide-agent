from types import SimpleNamespace

from src.agent import (
    get_development_payment_plan_terms,
    mock_recommend_payment_plan_action,
    run_aca,
)

from src.evaluation import cleanup_decision

from src.schemas import (
    ActionType,
    Channel,
    Intent,
)


def test_payment_plan_request_uses_required_evidence():

    result = None

    try:
        result = run_aca(
            account_id=1001,
            invoice_id=5001,
            reply_text=(
                "Can we split the balance into "
                "four monthly payments?"
            ),
        )

        assert (
            result["intent"].primary_intent
            == Intent.PAYMENT_PLAN_REQUEST
        )

        assert (
            result["payment_history_evidence"]["tool_name"]
            == "get_payment_history"
        )

        assert (
            result["prior_promises_evidence"]["tool_name"]
            == "get_prior_promises"
        )

        assert (
            result["risk_evidence"]["tool_name"]
            == "get_risk_score"
        )

        assert (
            result["proposed_action"].action_type
            == ActionType.PROPOSE_PAYMENT_PLAN
        )

        assert (
            result["proposed_action"].payment_plan_duration_days
            == 45
        )

        assert (
            result["proposed_action"].payment_plan_down_payment_pct
            == 0.25
        )

        assert result["final_status"] == "ESCALATE"

        assert (
            result["final_action_type"]
            == ActionType.ESCALATE
        )

    finally:
        if result is not None and result.get("decision_id"):
            cleanup_decision(
                result["decision_id"]
            )


def test_development_payment_plan_terms():

    assert get_development_payment_plan_terms("LOW") == (
        60,
        0.20,
    )

    assert get_development_payment_plan_terms("MEDIUM") == (
        45,
        0.25,
    )

    assert get_development_payment_plan_terms("HIGH") == (
        30,
        0.40,
    )

    assert get_development_payment_plan_terms("CRITICAL") == (
        None,
        None,
    )


def test_critical_risk_payment_plan_escalates():

    state = {
        "risk": SimpleNamespace(
            band=SimpleNamespace(
                value="CRITICAL"
            )
        ),

        "account_evidence": {
            "data": {
                "account": {
                    "email_allowed": 1
                }
            }
        },
    }

    recommendation = mock_recommend_payment_plan_action(
        state
    )

    assert (
        recommendation.action_type
        == ActionType.ESCALATE
    )

    assert (
        recommendation.target_channel
        == Channel.HUMAN_CALL_FLAG
    )