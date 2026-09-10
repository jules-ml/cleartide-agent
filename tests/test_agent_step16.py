from src.agent import (
    mock_classify_reply,
    run_aca,
)
from src.policy import check_unclear_intent
from src.schemas import (
    ActionType,
    Intent,
)


def test_short_unclear_reply_classifies_as_unclear():
    result = mock_classify_reply(
        "What?"
    )

    assert result.primary_intent == Intent.UNCLEAR
    assert result.confidence == 0.50


def test_ambiguous_reply_classifies_as_unclear():
    result = mock_classify_reply(
        "I do not understand what this is about."
    )

    assert result.primary_intent == Intent.UNCLEAR
    assert result.confidence == 0.50


def test_unclear_policy_returns_fr_1_5_escalation():
    validation = check_unclear_intent(
        Intent.UNCLEAR
    )

    assert validation is not None
    assert validation.outcome.value == "ESCALATE"
    assert validation.violated_constraints == ["FR-1.5"]
    assert "UNCLEAR intent cannot be acted on autonomously" in validation.explanation


def test_short_unclear_case_escalates_end_to_end_with_zero_tools():
    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text="What?",
    )

    assert result["intent"].primary_intent == Intent.UNCLEAR
    assert result["validation"].outcome.value == "ESCALATE"
    assert result["validation"].violated_constraints == ["FR-1.5"]
    assert result.get("tool_call_count", 0) == 0
    assert result.get("proposed_action") is None
    assert result.get("risk") is None
    assert result["final_status"] == "ESCALATE"
    assert result["final_action_type"] == ActionType.ESCALATE


def test_ambiguous_unclear_case_escalates_end_to_end_with_zero_tools():
    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text="I do not understand what this is about.",
    )

    assert result["intent"].primary_intent == Intent.UNCLEAR
    assert result["validation"].outcome.value == "ESCALATE"
    assert result["validation"].violated_constraints == ["FR-1.5"]
    assert result.get("tool_call_count", 0) == 0
    assert result.get("proposed_action") is None
    assert result.get("risk") is None
    assert result["final_status"] == "ESCALATE"
    assert result["final_action_type"] == ActionType.ESCALATE
