from src.agent import (
    mock_classify_reply,
    run_aca,
)
from src.policy import check_sensitive_language
from src.schemas import (
    ActionType,
    Intent,
)


def test_attorney_language_classifies_as_hostile_or_adversarial():
    result = mock_classify_reply(
        "My attorney will be contacting you."
    )

    assert result.primary_intent == Intent.HOSTILE_OR_ADVERSARIAL
    assert result.confidence >= 0.75


def test_sue_you_language_classifies_as_hostile_or_adversarial():
    result = mock_classify_reply(
        "I am going to sue you over this."
    )

    assert result.primary_intent == Intent.HOSTILE_OR_ADVERSARIAL
    assert result.confidence >= 0.75


def test_sensitive_language_policy_returns_pr_5_3_escalation():
    validation = check_sensitive_language(
        "My attorney will be contacting you."
    )

    assert validation is not None
    assert validation.outcome.value == "ESCALATE"
    assert validation.violated_constraints == ["PR-5.3"]
    assert "attorney" in validation.explanation


def test_attorney_case_escalates_end_to_end_with_zero_tools():
    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text="My attorney will be contacting you.",
    )

    assert result["intent"].primary_intent == Intent.HOSTILE_OR_ADVERSARIAL
    assert result["validation"].outcome.value == "ESCALATE"
    assert result["validation"].violated_constraints == ["PR-5.3"]
    assert result.get("tool_call_count", 0) == 0
    assert result.get("proposed_action") is None
    assert result.get("risk") is None
    assert result["final_status"] == "ESCALATE"
    assert result["final_action_type"] == ActionType.ESCALATE


def test_sue_you_case_escalates_end_to_end_with_zero_tools():
    result = run_aca(
        account_id=1001,
        invoice_id=5001,
        reply_text="I am going to sue you over this.",
    )

    assert result["intent"].primary_intent == Intent.HOSTILE_OR_ADVERSARIAL
    assert result["validation"].outcome.value == "ESCALATE"
    assert result["validation"].violated_constraints == ["PR-5.3"]
    assert result.get("tool_call_count", 0) == 0
    assert result.get("proposed_action") is None
    assert result.get("risk") is None
    assert result["final_status"] == "ESCALATE"
    assert result["final_action_type"] == ActionType.ESCALATE
