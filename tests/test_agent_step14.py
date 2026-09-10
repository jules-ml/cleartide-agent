from src.agent import (
    gather_amount_dispute_evidence_node,
    initialize_decision_node,
    mock_classify_reply,
    mock_recommend_amount_dispute_action,
    run_aca,
)
from src.schemas import (
    ActionType,
    Channel,
    Intent,
    RiskResult,
)
from src.tools import get_prior_disputes


def test_amount_dispute_classification():
    result = mock_classify_reply(
        "The invoice amount is wrong. We agreed on $8,500, not $8,750."
    )

    assert result.primary_intent == Intent.AMOUNT_DISPUTE
    assert result.confidence >= 0.75


def test_prior_dispute_memory_fixture():
    result = get_prior_disputes(1001)

    assert result["status"] == "SUCCESS"
    assert result["data"]["count"] >= 1

    disputes = result["data"]["disputes"]

    assert any(
        dispute["dispute_type"] == "AMOUNT_DISPUTE"
        and dispute["status"].lower() == "resolved"
        and float(dispute["disputed_amount"]) == 250.0
        for dispute in disputes
    )


def test_amount_dispute_recommender_logs_and_holds_when_prior_disputes_are_resolved():
    state = {
        "prior_disputes_evidence": {
            "status": "SUCCESS",
            "data": {
                "count": 1,
                "disputes": [
                    {
                        "dispute_type": "AMOUNT_DISPUTE",
                        "disputed_amount": 250.0,
                        "status": "resolved",
                        "resolution": "Supporting documentation accepted.",
                    }
                ],
            },
        },
        "risk": RiskResult(
            score=0.42,
            band="MEDIUM",
            model_version="fixture-v0",
            contributing_factors=[
                "invoice more than 20 days past due",
                "prior broken promise to pay",
                "partial payment received",
            ],
        ),
    }

    result = mock_recommend_amount_dispute_action(state)

    assert result.action_type == ActionType.LOG_DISPUTE_AND_HOLD
    assert result.target_channel is None
    assert result.message_body is None
    assert "1 prior resolved amount dispute" in result.rationale
    assert "MEDIUM" in result.rationale


def test_amount_dispute_recommender_flags_existing_unresolved_dispute_for_human_review():
    state = {
        "prior_disputes_evidence": {
            "status": "SUCCESS",
            "data": {
                "count": 1,
                "disputes": [
                    {
                        "dispute_type": "AMOUNT_DISPUTE",
                        "disputed_amount": 400.0,
                        "status": "open",
                        "resolution": None,
                    }
                ],
            },
        },
        "risk": RiskResult(
            score=0.42,
            band="MEDIUM",
            model_version="fixture-v0",
            contributing_factors=[],
        ),
    }

    result = mock_recommend_amount_dispute_action(state)

    assert result.action_type == ActionType.FLAG_FOR_HUMAN_CALL
    assert result.target_channel == Channel.HUMAN_CALL_FLAG
    assert result.message_body is None
    assert "existing unresolved amount dispute" in result.rationale



def test_amount_dispute_evidence_node_retrieves_memory_account_and_risk():
    base_state = {
        "account_id": 1001,
        "invoice_id": 5001,
        "reply_text": (
            "The invoice amount is wrong. "
            "We agreed on $8,500, not $8,750."
        ),
    }

    initialized = initialize_decision_node(base_state)

    state = {
        **base_state,
        **initialized,
    }

    result = gather_amount_dispute_evidence_node(state)

    assert "forced_escalation_reason" not in result

    assert result["prior_disputes_evidence"]["status"] == "SUCCESS"
    assert result["prior_disputes_evidence"]["tool_name"] == "get_prior_disputes"

    assert result["account_evidence"]["status"] == "SUCCESS"
    assert result["account_evidence"]["tool_name"] == "get_account_history"

    assert result["risk_evidence"]["status"] == "SUCCESS"
    assert result["risk_evidence"]["tool_name"] == "get_risk_score"

    assert result["risk"].score == 0.42
    assert result["risk"].band.value == "MEDIUM"

    assert result["tool_call_count"] == 3


def test_amount_dispute_runs_end_to_end_through_graph():
    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text=(
            "The invoice amount is wrong. "
            "We agreed on $8,500, not $8,750."
        ),
    )

    assert result["intent"].primary_intent == Intent.AMOUNT_DISPUTE

    assert result["prior_disputes_evidence"]["status"] == "SUCCESS"
    assert result["prior_disputes_evidence"]["tool_name"] == "get_prior_disputes"

    assert result["account_evidence"]["status"] == "SUCCESS"
    assert result["risk_evidence"]["status"] == "SUCCESS"
    assert result["risk"].score == 0.42
    assert result["risk"].band.value == "MEDIUM"

    assert result["proposed_action"].action_type == ActionType.LOG_DISPUTE_AND_HOLD
    assert result["proposed_action"].target_channel is None

    assert result["final_status"] == "APPROVED"
    assert result["final_action_type"] == ActionType.LOG_DISPUTE_AND_HOLD
    assert result["tool_call_count"] == 3


def test_amount_dispute_over_threshold_escalates_under_pr_5_4():
    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text=(
            "The invoice amount is wrong. "
            "We agreed on $3,000, not $8,750."
        ),
    )

    assert result["intent"].primary_intent == Intent.AMOUNT_DISPUTE

    assert result["validation"].outcome.value == "ESCALATE"
    assert result["validation"].violated_constraints == ["PR-5.4"]

    assert "$5,750.00" in result["validation"].explanation
    assert "$5,000.00" in result["validation"].explanation

    assert result["final_status"] == "ESCALATE"
    assert result["final_action_type"] == ActionType.ESCALATE


def test_amount_dispute_ambiguous_amount_escalates_under_pr_5_4():
    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text=(
            "The invoice amount is wrong. "
            "We discussed $7,000 and $7,500, not $8,750."
        ),
    )

    assert result["intent"].primary_intent == Intent.AMOUNT_DISPUTE

    assert result["validation"].outcome.value == "ESCALATE"
    assert result["validation"].violated_constraints == ["PR-5.4"]

    assert (
        "could not be determined unambiguously"
        in result["validation"].explanation
    )

    assert result["final_status"] == "ESCALATE"
    assert result["final_action_type"] == ActionType.ESCALATE


def test_amount_dispute_missing_ledger_amount_escalates_under_pr_5_4():
    from src.policy import validate_action

    reply_text = (
        "The invoice amount is wrong. "
        "We agreed on $8,500, not $8,750."
    )

    normal_result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text=reply_text,
    )

    validation = validate_action(
        normal_result["proposed_action"],
        primary_intent=Intent.AMOUNT_DISPUTE,
        intent_confidence=normal_result["intent"].confidence,
        reply_text=reply_text,
        ledger_amount=None,
    )

    assert validation.outcome.value == "ESCALATE"
    assert validation.violated_constraints == ["PR-5.4"]

    assert (
        "Trusted ledger amount is unavailable"
        in validation.explanation
    )

